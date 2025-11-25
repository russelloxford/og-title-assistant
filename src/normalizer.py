"""
Normalizer Module

Standardizes extracted data for graph storage and querying.
Includes legal description normalization (spatial keys) and
party name normalization (for matching across documents).
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)

# State name to abbreviation mapping
STATE_ABBREVIATIONS = {
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "ARIZONA": "AZ",
    "ARKANSAS": "AR",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "CONNECTICUT": "CT",
    "DELAWARE": "DE",
    "FLORIDA": "FL",
    "GEORGIA": "GA",
    "HAWAII": "HI",
    "IDAHO": "ID",
    "ILLINOIS": "IL",
    "INDIANA": "IN",
    "IOWA": "IA",
    "KANSAS": "KS",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM",
    "NEW YORK": "NY",
    "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN",
    "TEXAS": "TX",
    "UTAH": "UT",
    "VERMONT": "VT",
    "VIRGINIA": "VA",
    "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI",
    "WYOMING": "WY",
}

# Entity suffixes to remove for normalization
# NOTE: Order matters - longer/more specific patterns first
ENTITY_SUFFIXES = [
    r",?\s*LIMITED\s+LIABILITY\s+COMPANY$",
    r",?\s*LIMITED\s+PARTNERSHIP$",
    r",?\s*LIMITED\s+LIABILITY\s+PARTNERSHIP$",
    r",?\s*INCORPORATED$",
    r",?\s*CORPORATION$",
    r",?\s*COMPANY$",
    r",?\s*LIMITED$",
    r",?\s*L\.?L\.?C\.?$",
    r",?\s*LLC\.?$",
    r",?\s*L\.?L\.?P\.?$",
    r",?\s*LLP\.?$",
    r",?\s*L\.?P\.?$",
    r",?\s*LP\.?$",
    r",?\s*P\.?L\.?L\.?C\.?$",
    r",?\s*PLLC\.?$",
    r",?\s*INC\.?$",
    r",?\s*CORP\.?$",
    r",?\s*LTD\.?$",
    r",?\s*P\.?C\.?$",
    r",?\s*PC\.?$",
    r",?\s*CO\.?$",
    r",?\s*ET\s+AL\.?$",
    r",?\s*ET\s+UX\.?$",
    r",?\s*ET\s+VIR\.?$",
    r",?\s*A/K/A\s+.*$",
    r",?\s*AKA\s+.*$",
    r",?\s*F/K/A\s+.*$",
    r",?\s*FKA\s+.*$",
    r",?\s*N/K/A\s+.*$",
    r",?\s*D/B/A\s+.*$",
    r",?\s*DBA\s+.*$",
]


@dataclass
class SpatialKey:
    """Parsed components of a spatial key."""

    state: str
    county: str
    section: str
    township: str
    range: str
    aliquot: Optional[str] = None
    key: str = ""

    def __post_init__(self):
        """Generate the full key after initialization."""
        if not self.key:
            self.key = f"{self.state}-{self.county}-{self.section}-{self.township}-{self.range}"
            if self.aliquot:
                self.key += f"-{self.aliquot}"


@dataclass
class NormalizedParty:
    """Normalized party information."""

    original_name: str
    normalized_name: str
    entity_type: Optional[str] = None


def _extract_state(text: str) -> Optional[str]:
    """
    Extract state from legal description text.

    Args:
        text: Legal description text (uppercase)

    Returns:
        Two-letter state abbreviation or None
    """
    # Check for full state names FIRST (more specific)
    for full_name, abbrev in STATE_ABBREVIATIONS.items():
        if full_name in text:
            return abbrev

    # Check for two-letter abbreviations at end of string or followed by punctuation
    # This avoids matching "IN" from "IN OKLAHOMA"
    abbrev_match = re.search(
        r"(?:,\s*|\s+)(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IA|KS|KY|LA|ME|MD|"
        r"MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|"
        r"TN|TX|UT|VT|VA|WA|WV|WI|WY)(?:\s*$|\s*,|\s+\d)",
        text,
    )
    if abbrev_match:
        return abbrev_match.group(1)

    return None


def _extract_county(text: str) -> Optional[str]:
    """
    Extract county from legal description text.

    Args:
        text: Legal description text (uppercase)

    Returns:
        County name or None
    """
    # Pattern: "COUNTY_NAME COUNTY" or "COUNTY_NAME PARISH" (Louisiana)
    county_match = re.search(r"(\w+(?:\s+\w+)?)\s+(?:COUNTY|PARISH)", text)
    if county_match:
        return county_match.group(1).strip()

    return None


def _extract_section_township_range(
    text: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extract section, township, and range from legal description.

    Handles multiple common formats:
    - "Section 15, Township 154 North, Range 97 West"
    - "Sec 14-3N-4W"
    - "S14-T3N-R4W"
    - "T154N-R97W, Section 15"

    Args:
        text: Legal description text (uppercase)

    Returns:
        Tuple of (section, township, range) or (None, None, None)
    """
    section, township, range_val = None, None, None

    # Pattern 1: "Section 15, Township 154 North, Range 97 West"
    p1 = re.search(
        r"SECTION\s+(\d+).*?"
        r"TOWNSHIP\s+(\d+)\s*(N|NORTH|S|SOUTH).*?"
        r"RANGE\s+(\d+)\s*(W|WEST|E|EAST)",
        text,
    )
    if p1:
        section = p1.group(1)
        township = f"{p1.group(2)}{p1.group(3)[0]}"
        range_val = f"{p1.group(4)}{p1.group(5)[0]}"
        return section, township, range_val

    # Pattern 2: "Sec 14-3N-4W" or "S14-T3N-R4W" or variations
    p2 = re.search(
        r"S(?:EC(?:TION)?)?\s*(\d+)[-,\s]+T?(\d+[NS])[-,\s]+R?(\d+[EW])",
        text,
    )
    if p2:
        section = p2.group(1)
        township = p2.group(2)
        range_val = p2.group(3)
        return section, township, range_val

    # Pattern 3: "T154N-R97W, Section 15" (reversed order)
    p3 = re.search(
        r"T(\d+[NS])[-,\s]+R(\d+[EW]).*?S(?:EC(?:TION)?)?\s*(\d+)",
        text,
    )
    if p3:
        township = p3.group(1)
        range_val = p3.group(2)
        section = p3.group(3)
        return section, township, range_val

    # Pattern 4: Just "T3N R4W" without section
    p4 = re.search(r"T(\d+[NS])[-,\s]+R(\d+[EW])", text)
    if p4:
        township = p4.group(1)
        range_val = p4.group(2)

        # Try to find section separately
        sec_match = re.search(r"S(?:EC(?:TION)?)?\s*(\d+)", text)
        if sec_match:
            section = sec_match.group(1)

        if section:
            return section, township, range_val

    # Pattern 5: Compact "15-154N-97W" format
    p5 = re.search(r"(\d+)-(\d+[NS])-(\d+[EW])", text)
    if p5:
        section = p5.group(1)
        township = p5.group(2)
        range_val = p5.group(3)
        return section, township, range_val

    return None, None, None


def _extract_aliquot(text: str) -> Optional[str]:
    """
    Extract aliquot parts from legal description.

    Handles formats like:
    - NW/4, SW/4, NE/4, SE/4
    - N/2, S/2, E/2, W/2
    - NW/4 of NE/4
    - North Half, South Quarter

    Args:
        text: Legal description text (uppercase)

    Returns:
        Normalized aliquot string or None
    """
    aliquot_parts = []

    # Pattern for fractional aliquots: NW/4, S/2, etc.
    fraction_pattern = r"((?:N|S|E|W|NE|NW|SE|SW))\s*[/\\]?\s*([24])"
    for match in re.finditer(fraction_pattern, text):
        direction = match.group(1)
        fraction = match.group(2)
        aliquot_parts.append(f"{direction}{fraction}")

    # Pattern for spelled out: "NORTH HALF", "SOUTHWEST QUARTER"
    spelled_patterns = [
        (r"NORTH\s*(?:HALF|1/2)", "N2"),
        (r"SOUTH\s*(?:HALF|1/2)", "S2"),
        (r"EAST\s*(?:HALF|1/2)", "E2"),
        (r"WEST\s*(?:HALF|1/2)", "W2"),
        (r"NORTH\s*EAST\s*(?:QUARTER|1/4)", "NE4"),
        (r"NORTH\s*WEST\s*(?:QUARTER|1/4)", "NW4"),
        (r"SOUTH\s*EAST\s*(?:QUARTER|1/4)", "SE4"),
        (r"SOUTH\s*WEST\s*(?:QUARTER|1/4)", "SW4"),
    ]

    for pattern, replacement in spelled_patterns:
        if re.search(pattern, text):
            if replacement not in aliquot_parts:
                aliquot_parts.append(replacement)

    if aliquot_parts:
        return "-".join(sorted(set(aliquot_parts)))

    return None


def generate_spatial_key(legal_desc: str) -> Optional[SpatialKey]:
    """
    Convert legal description to normalized spatial key.

    Format: {STATE}-{COUNTY}-{SECTION}-{TOWNSHIP}-{RANGE}[-{ALIQUOT}]

    Examples:
        "NW/4 of Section 15, T154N, R97W, Williams County, ND"
        → SpatialKey(key="ND-WILLIAMS-15-154N-97W-NW4")

        "Sec 14-3N-4W, Garfield County, OK"
        → SpatialKey(key="OK-GARFIELD-14-3N-4W")

    Args:
        legal_desc: Raw legal description text

    Returns:
        SpatialKey object or None if cannot be parsed
    """
    if not legal_desc:
        return None

    text = legal_desc.upper().strip()

    # Extract components
    state = _extract_state(text)
    county = _extract_county(text)
    section, township, range_val = _extract_section_township_range(text)
    aliquot = _extract_aliquot(text)

    # Validate required components
    if not all([state, county, section, township, range_val]):
        logger.debug(
            f"Could not parse legal description: state={state}, county={county}, "
            f"section={section}, township={township}, range={range_val}"
        )
        return None

    return SpatialKey(
        state=state,
        county=county,
        section=section,
        township=township,
        range=range_val,
        aliquot=aliquot,
    )


def normalize_party_name(name: str) -> NormalizedParty:
    """
    Normalize party name for matching across documents.

    Removes entity suffixes, punctuation, and extra whitespace.
    Detects entity type from original name.

    Examples:
        "Smith Oil, LLC" → NormalizedParty(normalized_name="SMITH OIL", entity_type="llc")
        "JONES, JOHN ET UX" → NormalizedParty(normalized_name="JONES JOHN", entity_type="individual")

    Args:
        name: Original party name

    Returns:
        NormalizedParty with original and normalized names
    """
    if not name:
        return NormalizedParty(original_name="", normalized_name="", entity_type=None)

    original = name.strip()
    text = original.upper()

    # Detect entity type before removing suffixes
    entity_type = _detect_entity_type(text)

    # Remove entity suffixes
    for suffix_pattern in ENTITY_SUFFIXES:
        text = re.sub(suffix_pattern, "", text, flags=re.IGNORECASE)

    # Remove punctuation except hyphens in names
    text = re.sub(r"[^\w\s-]", " ", text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Remove standalone single letters (often initials that got separated)
    text = re.sub(r"\b[A-Z]\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    return NormalizedParty(
        original_name=original,
        normalized_name=text,
        entity_type=entity_type,
    )


def _detect_entity_type(text: str) -> Optional[str]:
    """
    Detect entity type from party name.

    Args:
        text: Party name (uppercase)

    Returns:
        Entity type string or None
    """
    text_upper = text.upper()

    # Check for corporate indicators (order matters - more specific first)
    # LLC patterns
    if re.search(r"L\.?L\.?C\.?(?:\s|$|,)", text_upper) or re.search(r"\bLLC\b", text_upper):
        return "llc"

    # Limited partnership patterns
    if re.search(r"L\.?P\.?(?:\s|$|,)", text_upper) or re.search(r"\bLP\b", text_upper):
        return "limited_partnership"
    if re.search(r"LIMITED\s+PARTNERSHIP", text_upper):
        return "limited_partnership"

    # LLP patterns
    if re.search(r"L\.?L\.?P\.?(?:\s|$|,)", text_upper) or re.search(r"\bLLP\b", text_upper):
        return "llp"

    # Corporation patterns
    if re.search(r"\b(INC|INCORPORATED|CORP|CORPORATION)\b", text_upper):
        return "corporation"

    # PLLC patterns
    if re.search(r"P\.?L\.?L\.?C\.?(?:\s|$|,)", text_upper) or re.search(r"\bPLLC\b", text_upper):
        return "pllc"

    # Company indicator (but not if it's part of a larger pattern)
    if re.search(r"\bCO\.(?:\s|$|,)", text_upper) and not re.search(r"COMPANY", text_upper):
        return "company"

    # Check for trust indicators
    if re.search(r"\bTRUST\b", text_upper):
        return "trust"

    # Check for estate indicators
    if re.search(r"\bESTATE\b", text_upper):
        return "estate"

    # Check for individual indicators
    if re.search(r"\b(ET\s+UX|ET\s+VIR|ET\s+AL)\b", text_upper):
        return "individual"

    # Default to individual for simple names
    # (Names with commas like "SMITH, JOHN" or just words)
    if re.match(r"^[A-Z\s,.\'-]+$", text_upper):
        words = text_upper.replace(",", " ").split()
        if len(words) <= 4:  # Reasonable length for a person's name
            return "individual"

    return None


def normalize_recording_info(
    book: Optional[str] = None,
    page: Optional[str] = None,
    doc_number: Optional[str] = None,
) -> str:
    """
    Normalize recording information to standard format.

    Args:
        book: Book number
        page: Page number
        doc_number: Document number

    Returns:
        Normalized recording info string
    """
    parts = []

    if book and page:
        # Normalize book/page format
        book_clean = re.sub(r"[^\d]", "", str(book))
        page_clean = re.sub(r"[^\d]", "", str(page))
        if book_clean and page_clean:
            parts.append(f"Bk {book_clean}/Pg {page_clean}")

    if doc_number:
        doc_clean = str(doc_number).strip()
        if doc_clean:
            parts.append(f"Doc# {doc_clean}")

    return "; ".join(parts) if parts else ""


def parse_recording_string(recording_str: str) -> dict:
    """
    Parse a recording string into components.

    Handles formats like:
    - "Bk 450/Pg 123"
    - "Book 450, Page 123"
    - "Doc# 2024-001234"
    - "Bk 450/Pg 123; Doc# 2024-001234"

    Args:
        recording_str: Recording information string

    Returns:
        Dict with book, page, doc_number keys
    """
    result = {"book": None, "page": None, "doc_number": None}

    if not recording_str:
        return result

    text = recording_str.upper()

    # Extract book/page
    bp_match = re.search(r"B(?:OO)?K\.?\s*(\d+)\s*[/,]\s*P(?:A?GE?)?\.?\s*(\d+)", text)
    if bp_match:
        result["book"] = bp_match.group(1)
        result["page"] = bp_match.group(2)

    # Extract document number
    doc_match = re.search(r"DOC(?:UMENT)?\.?\s*#?\s*([\d-]+)", text)
    if doc_match:
        result["doc_number"] = doc_match.group(1)

    # Also check for instrument number
    inst_match = re.search(r"INST(?:RUMENT)?\.?\s*#?\s*([\d-]+)", text)
    if inst_match and not result["doc_number"]:
        result["doc_number"] = inst_match.group(1)

    return result


# CLI interface for testing
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG)

    # Test legal description parsing
    test_descriptions = [
        "NW/4 of Section 15, Township 154 North, Range 97 West, Williams County, ND",
        "Sec 14-3N-4W, Garfield County, OK",
        "T154N-R97W, Section 15, Williams County, North Dakota",
        "The South Half of Section 10, T3N, R4W, Texas County, Oklahoma",
    ]

    print("Legal Description Normalization:")
    print("-" * 60)
    for desc in test_descriptions:
        result = generate_spatial_key(desc)
        if result:
            print(f"Input: {desc[:50]}...")
            print(f"Key:   {result.key}")
            print()
        else:
            print(f"Could not parse: {desc[:50]}...")
            print()

    # Test party name normalization
    test_names = [
        "Smith Oil Company, LLC",
        "JONES, JOHN ET UX",
        "Acme Energy Partners, L.P.",
        "The Mary Smith Family Trust",
        "Estate of Robert Brown, Deceased",
    ]

    print("\nParty Name Normalization:")
    print("-" * 60)
    for name in test_names:
        result = normalize_party_name(name)
        print(f"Original:   {result.original_name}")
        print(f"Normalized: {result.normalized_name}")
        print(f"Type:       {result.entity_type}")
        print()
