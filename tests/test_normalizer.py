"""
Tests for the Normalizer Module
"""

import pytest

from src.normalizer import (
    NormalizedParty,
    SpatialKey,
    _detect_entity_type,
    _extract_aliquot,
    _extract_county,
    _extract_section_township_range,
    _extract_state,
    generate_spatial_key,
    normalize_party_name,
    normalize_recording_info,
    parse_recording_string,
)


class TestExtractState:
    """Tests for state extraction."""

    def test_two_letter_abbreviation(self):
        """Should extract two-letter state codes."""
        assert _extract_state("WILLIAMS COUNTY, ND") == "ND"
        assert _extract_state("SOMETHING IN OK") == "OK"
        assert _extract_state("TEXAS COUNTY, TX") == "TX"

    def test_full_state_name(self):
        """Should extract full state names."""
        assert _extract_state("WILLIAMS COUNTY, NORTH DAKOTA") == "ND"
        assert _extract_state("SOMEWHERE IN OKLAHOMA") == "OK"
        assert _extract_state("NEW MEXICO LANDS") == "NM"

    def test_no_state_found(self):
        """Should return None when no state found."""
        assert _extract_state("SOME RANDOM TEXT") is None
        assert _extract_state("") is None


class TestExtractCounty:
    """Tests for county extraction."""

    def test_single_word_county(self):
        """Should extract single-word county names."""
        assert _extract_county("WILLIAMS COUNTY, ND") == "WILLIAMS"
        assert _extract_county("GARFIELD COUNTY") == "GARFIELD"

    def test_multi_word_county(self):
        """Should extract multi-word county names."""
        assert _extract_county("SAN JUAN COUNTY") == "SAN JUAN"

    def test_parish_louisiana(self):
        """Should extract Louisiana parishes."""
        assert _extract_county("CADDO PARISH, LA") == "CADDO"

    def test_no_county_found(self):
        """Should return None when no county found."""
        assert _extract_county("SOME RANDOM TEXT") is None


class TestExtractSectionTownshipRange:
    """Tests for section/township/range extraction."""

    def test_verbose_format(self):
        """Should parse verbose format."""
        result = _extract_section_township_range(
            "SECTION 15, TOWNSHIP 154 NORTH, RANGE 97 WEST"
        )
        assert result == ("15", "154N", "97W")

    def test_compact_format(self):
        """Should parse compact format."""
        result = _extract_section_township_range("SEC 14-3N-4W")
        assert result == ("14", "3N", "4W")

    def test_with_prefixes(self):
        """Should handle T and R prefixes."""
        result = _extract_section_township_range("S14-T3N-R4W")
        assert result == ("14", "3N", "4W")

    def test_reversed_format(self):
        """Should handle township/range before section."""
        result = _extract_section_township_range("T154N-R97W, SECTION 15")
        assert result == ("15", "154N", "97W")

    def test_hyphenated_format(self):
        """Should parse hyphenated format."""
        result = _extract_section_township_range("15-154N-97W")
        assert result == ("15", "154N", "97W")

    def test_south_and_east(self):
        """Should handle South and East directions."""
        result = _extract_section_township_range("SEC 10-5S-3E")
        assert result == ("10", "5S", "3E")

    def test_no_match(self):
        """Should return None tuple when not found."""
        result = _extract_section_township_range("RANDOM TEXT")
        assert result == (None, None, None)


class TestExtractAliquot:
    """Tests for aliquot extraction."""

    def test_quarter_sections(self):
        """Should extract quarter sections."""
        assert _extract_aliquot("NW/4 OF SECTION 15") == "NW4"
        assert _extract_aliquot("THE SE/4") == "SE4"

    def test_half_sections(self):
        """Should extract half sections."""
        assert _extract_aliquot("N/2 OF SECTION 10") == "N2"
        assert _extract_aliquot("THE S/2") == "S2"

    def test_spelled_out(self):
        """Should handle spelled out aliquots."""
        assert _extract_aliquot("THE NORTH HALF") == "N2"
        assert _extract_aliquot("SOUTHWEST QUARTER") == "SW4"

    def test_multiple_aliquots(self):
        """Should handle multiple aliquots."""
        result = _extract_aliquot("NW/4 AND NE/4")
        assert "NE4" in result
        assert "NW4" in result

    def test_no_aliquot(self):
        """Should return None when no aliquot found."""
        assert _extract_aliquot("SECTION 15") is None


class TestGenerateSpatialKey:
    """Tests for full spatial key generation."""

    def test_complete_description(self):
        """Should generate key from complete description."""
        result = generate_spatial_key(
            "NW/4 of Section 15, Township 154 North, Range 97 West, Williams County, ND"
        )
        assert result is not None
        assert result.state == "ND"
        assert result.county == "WILLIAMS"
        assert result.section == "15"
        assert result.township == "154N"
        assert result.range == "97W"
        assert result.aliquot == "NW4"
        assert result.key == "ND-WILLIAMS-15-154N-97W-NW4"

    def test_compact_description(self):
        """Should generate key from compact description."""
        result = generate_spatial_key("Sec 14-3N-4W, Garfield County, OK")
        assert result is not None
        assert result.key == "OK-GARFIELD-14-3N-4W"

    def test_no_aliquot(self):
        """Should generate key without aliquot."""
        result = generate_spatial_key(
            "Section 10, T5N, R3W, Texas County, Oklahoma"
        )
        assert result is not None
        assert result.aliquot is None
        assert result.key == "OK-TEXAS-10-5N-3W"

    def test_incomplete_description(self):
        """Should return None for incomplete descriptions."""
        assert generate_spatial_key("Some land in Oklahoma") is None
        assert generate_spatial_key("Section 15") is None
        assert generate_spatial_key("") is None
        assert generate_spatial_key(None) is None


class TestNormalizePartyName:
    """Tests for party name normalization."""

    def test_remove_llc(self):
        """Should remove LLC suffix."""
        result = normalize_party_name("Smith Oil, LLC")
        assert result.normalized_name == "SMITH OIL"
        assert result.entity_type == "llc"

    def test_remove_inc(self):
        """Should remove Inc suffix."""
        result = normalize_party_name("Acme Energy, Inc.")
        assert result.normalized_name == "ACME ENERGY"
        assert result.entity_type == "corporation"

    def test_remove_lp(self):
        """Should remove LP suffix."""
        result = normalize_party_name("Jones Partners, L.P.")
        assert result.normalized_name == "JONES PARTNERS"
        assert result.entity_type == "limited_partnership"

    def test_remove_et_ux(self):
        """Should remove et ux suffix."""
        result = normalize_party_name("SMITH, JOHN ET UX")
        assert result.normalized_name == "SMITH JOHN"
        assert result.entity_type == "individual"

    def test_remove_et_al(self):
        """Should remove et al suffix."""
        result = normalize_party_name("Brown, Robert, et al.")
        assert result.normalized_name == "BROWN ROBERT"

    def test_preserve_original(self):
        """Should preserve original name."""
        result = normalize_party_name("Smith Oil, LLC")
        assert result.original_name == "Smith Oil, LLC"

    def test_trust_detection(self):
        """Should detect trust entity type."""
        result = normalize_party_name("The Smith Family Trust")
        assert result.entity_type == "trust"

    def test_estate_detection(self):
        """Should detect estate entity type."""
        result = normalize_party_name("Estate of John Smith")
        assert result.entity_type == "estate"

    def test_empty_name(self):
        """Should handle empty name."""
        result = normalize_party_name("")
        assert result.normalized_name == ""
        assert result.original_name == ""

    def test_punctuation_removal(self):
        """Should remove punctuation."""
        result = normalize_party_name("O'Brien & Associates, LLC")
        assert "'" not in result.normalized_name
        assert "&" not in result.normalized_name


class TestDetectEntityType:
    """Tests for entity type detection."""

    def test_llc(self):
        """Should detect LLC."""
        assert _detect_entity_type("SMITH OIL, LLC") == "llc"
        assert _detect_entity_type("ACME L.L.C.") == "llc"

    def test_corporation(self):
        """Should detect corporation."""
        assert _detect_entity_type("ACME CORP") == "corporation"
        assert _detect_entity_type("SMITH INCORPORATED") == "corporation"
        assert _detect_entity_type("JONES, INC.") == "corporation"

    def test_limited_partnership(self):
        """Should detect limited partnership."""
        assert _detect_entity_type("SMITH PARTNERS, LP") == "limited_partnership"
        assert _detect_entity_type("JONES L.P.") == "limited_partnership"

    def test_trust(self):
        """Should detect trust."""
        assert _detect_entity_type("SMITH FAMILY TRUST") == "trust"

    def test_estate(self):
        """Should detect estate."""
        assert _detect_entity_type("ESTATE OF JOHN DOE") == "estate"

    def test_individual(self):
        """Should detect individual."""
        assert _detect_entity_type("SMITH, JOHN ET UX") == "individual"
        assert _detect_entity_type("JONES, MARY") == "individual"


class TestNormalizeRecordingInfo:
    """Tests for recording info normalization."""

    def test_book_and_page(self):
        """Should format book and page."""
        result = normalize_recording_info(book="450", page="123")
        assert result == "Bk 450/Pg 123"

    def test_with_doc_number(self):
        """Should include document number."""
        result = normalize_recording_info(
            book="450", page="123", doc_number="2024-001234"
        )
        assert "Bk 450/Pg 123" in result
        assert "Doc# 2024-001234" in result

    def test_only_doc_number(self):
        """Should handle only document number."""
        result = normalize_recording_info(doc_number="2024-001234")
        assert result == "Doc# 2024-001234"

    def test_empty_values(self):
        """Should handle empty values."""
        result = normalize_recording_info()
        assert result == ""

    def test_clean_numbers(self):
        """Should clean non-numeric characters from book/page."""
        result = normalize_recording_info(book="Book 450", page="Page 123")
        assert result == "Bk 450/Pg 123"


class TestParseRecordingString:
    """Tests for recording string parsing."""

    def test_book_page_format(self):
        """Should parse book/page format."""
        result = parse_recording_string("Bk 450/Pg 123")
        assert result["book"] == "450"
        assert result["page"] == "123"

    def test_verbose_format(self):
        """Should parse verbose format."""
        result = parse_recording_string("Book 450, Page 123")
        assert result["book"] == "450"
        assert result["page"] == "123"

    def test_doc_number(self):
        """Should parse document number."""
        result = parse_recording_string("Doc# 2024-001234")
        assert result["doc_number"] == "2024-001234"

    def test_combined(self):
        """Should parse combined format."""
        result = parse_recording_string("Bk 450/Pg 123; Doc# 2024-001234")
        assert result["book"] == "450"
        assert result["page"] == "123"
        assert result["doc_number"] == "2024-001234"

    def test_instrument_number(self):
        """Should parse instrument number as doc number."""
        result = parse_recording_string("Instrument# 12345")
        assert result["doc_number"] == "12345"

    def test_empty_string(self):
        """Should handle empty string."""
        result = parse_recording_string("")
        assert result["book"] is None
        assert result["page"] is None
        assert result["doc_number"] is None


class TestSpatialKeyDataClass:
    """Tests for SpatialKey dataclass."""

    def test_auto_generate_key(self):
        """Should auto-generate key on creation."""
        key = SpatialKey(
            state="ND",
            county="WILLIAMS",
            section="15",
            township="154N",
            range="97W",
        )
        assert key.key == "ND-WILLIAMS-15-154N-97W"

    def test_with_aliquot(self):
        """Should include aliquot in key."""
        key = SpatialKey(
            state="ND",
            county="WILLIAMS",
            section="15",
            township="154N",
            range="97W",
            aliquot="NW4",
        )
        assert key.key == "ND-WILLIAMS-15-154N-97W-NW4"


class TestNormalizedPartyDataClass:
    """Tests for NormalizedParty dataclass."""

    def test_creation(self):
        """Should create with all fields."""
        party = NormalizedParty(
            original_name="Smith Oil, LLC",
            normalized_name="SMITH OIL",
            entity_type="llc",
        )
        assert party.original_name == "Smith Oil, LLC"
        assert party.normalized_name == "SMITH OIL"
        assert party.entity_type == "llc"

    def test_optional_entity_type(self):
        """Should allow None entity type."""
        party = NormalizedParty(
            original_name="Unknown",
            normalized_name="UNKNOWN",
        )
        assert party.entity_type is None
