"""
Body Extractor Module

Extracts structured metadata from document body using Claude AI.
Designed to process 3-15 page document bodies (not exhibits).

This module handles:
- Parties (grantor/grantee/assignor/assignee)
- Dates (execution, recording, effective)
- Recording information (book, page, document number)
- Interests conveyed and reserved
- Key clauses (Pugh, depth severance, etc.)
- Lease terms (for oil & gas leases)
- Exhibit references
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional

from anthropic import Anthropic
from pydantic import ValidationError

from .schemas import DocumentExtraction

# Configure logging
logger = logging.getLogger(__name__)

# Extraction prompt template
BODY_EXTRACTION_PROMPT = """You are analyzing the BODY of an oil & gas legal document (NOT the exhibits).

Your task is to extract structured data from this document. Extract ONLY what is clearly present - do not guess or infer.

## IMPORTANT INSTRUCTIONS:
1. Extract ONLY from the document body - do NOT attempt to extract individual items from exhibits
2. Note references to exhibits (what each exhibit contains) but don't extract exhibit contents
3. For dates, use YYYY-MM-DD format
4. For parties, capture the full legal name as written
5. Be precise with fractions (1/8, 3/16, etc.) and interest types
6. Set confidence scores based on how clearly information was presented

## EXTRACT THE FOLLOWING:

### 1. Document Type and Title
- Identify the document type: Deed, Assignment, Oil and Gas Lease, Mortgage, Ratification, Partial Release, etc.
- Note the exact title if present

### 2. All Parties
- Grantors/Assignors/Lessors (those conveying)
- Grantees/Assignees/Lessees (those receiving)
- Include addresses if present
- Note entity type (individual, LLC, corporation, trust, estate)

### 3. Dates
- Execution date (when signed)
- Recording date (when filed with county)
- Effective date (if different from execution)
- Expiration date (for leases)

### 4. Recording Information
- Book and page numbers
- Document/instrument number
- Reception number
- County and state

### 5. Interests
- What interest is being conveyed (working interest, royalty, ORRI, mineral, leasehold, etc.)
- Fractional amount conveyed
- Any interest reserved (e.g., "reserving 1/16th ORRI")

### 6. Key Clauses (for assignments/leases)
- Pugh clause (vertical/horizontal)
- Depth severance (with depths/formations)
- Continuous development
- Pooling/unitization
- Surface damages

### 7. Lease Terms (for Oil & Gas Leases only)
- Primary term
- Royalty fraction
- Bonus amount
- Delay rental

### 8. Legal Description
- Only if in body (not exhibits)
- Section, Township, Range
- County, State
- Aliquot parts (NW/4, S/2, etc.)
- Acreage

### 9. Exhibit References
- What exhibits are attached
- Brief description of each exhibit's contents

### 10. Confidence Scores (0.0 to 1.0)
- Overall extraction confidence
- Per-field confidence where applicable

## OUTPUT FORMAT:
Return a JSON object with this exact structure (omit null/empty fields):

```json
{
  "document_type": "Assignment of Oil and Gas Leases",
  "document_title": "ASSIGNMENT OF OIL AND GAS LEASES",
  "parties": {
    "grantors": [
      {
        "name": "SMITH OIL COMPANY, LLC",
        "address": "123 Main St, Williston, ND 58801",
        "role": "Assignor",
        "entity_type": "llc"
      }
    ],
    "grantees": [
      {
        "name": "JONES ENERGY PARTNERS, LP",
        "address": null,
        "role": "Assignee",
        "entity_type": "limited_partnership"
      }
    ]
  },
  "dates": {
    "execution": "2024-01-15",
    "recording": "2024-01-20",
    "effective": null,
    "expiration": null
  },
  "recording_info": {
    "book": "450",
    "page": "123",
    "document_number": "2024-000123",
    "reception_number": null,
    "county": "Williams",
    "state": "ND"
  },
  "interests": {
    "conveyed": "All of Assignor's right, title and interest in and to the oil and gas leases",
    "conveyed_fraction": "100%",
    "reserved": "1/16th overriding royalty interest",
    "reserved_fraction": "1/16",
    "interest_type": "leasehold"
  },
  "clauses": {
    "pugh_clause": true,
    "pugh_description": "Horizontal Pugh clause releasing non-pooled acreage",
    "depth_severance": {
      "has_depth_severance": true,
      "shallow_depth": "surface to 100 feet below Bakken formation",
      "deep_depth": null,
      "formation": "Bakken",
      "description": "Assignment covers only rights above 100 feet below base of Bakken"
    },
    "continuous_development": false,
    "continuous_development_description": null,
    "surface_damages": false,
    "pooling_unitization": true,
    "other_clauses": ["Proportionate reduction clause"]
  },
  "lease_terms": null,
  "legal_description": null,
  "exhibit_references": [
    {
      "name": "Exhibit A",
      "description": "Schedule of 150 oil and gas leases being assigned",
      "exhibit_type": "schedule"
    },
    {
      "name": "Exhibit B",
      "description": "Legal descriptions of lands covered",
      "exhibit_type": "legal_description"
    }
  ],
  "confidence": {
    "overall": 0.95,
    "parties": 0.98,
    "dates": 0.90,
    "recording_info": 0.95,
    "interests": 0.85
  },
  "extraction_notes": [
    "Exhibit A contains detailed lease schedule - not extracted here",
    "Some recording information partially illegible"
  ]
}
```

Now analyze the document and return ONLY the JSON object (no other text):"""


def _load_pdf_as_base64(pdf_path: str) -> str:
    """Load PDF file and encode as base64."""
    with open(pdf_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _parse_extraction_response(response_text: str) -> dict:
    """
    Parse Claude's response to extract JSON.

    Handles cases where response might include markdown code blocks.
    """
    text = response_text.strip()

    # Remove markdown code blocks if present
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]

    if text.endswith("```"):
        text = text[:-3]

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.debug(f"Response text: {text[:500]}...")
        raise ValueError(f"Invalid JSON in Claude response: {e}")


def extract_body(
    pdf_path: str,
    api_key: Optional[str] = None,
    model: str = "claude-sonnet-4-5-20250514",
    max_tokens: int = 4096,
) -> DocumentExtraction:
    """
    Extract structured data from document body using Claude.

    Args:
        pdf_path: Path to the body PDF file (3-15 pages typically)
        api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        model: Claude model to use
        max_tokens: Maximum tokens for response

    Returns:
        DocumentExtraction object with validated extracted data

    Raises:
        FileNotFoundError: If PDF file not found
        ValueError: If extraction fails or returns invalid data
        ValidationError: If extracted data doesn't match schema
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    logger.info(f"Extracting body from: {pdf_path}")

    # Initialize client
    if api_key:
        client = Anthropic(api_key=api_key)
    else:
        client = Anthropic()  # Uses ANTHROPIC_API_KEY env var

    # Load PDF as base64
    pdf_base64 = _load_pdf_as_base64(pdf_path)

    # Get file size for logging
    file_size = os.path.getsize(pdf_path)
    logger.debug(f"PDF size: {file_size / 1024:.1f} KB")

    # Call Claude API
    logger.info("Calling Claude API for extraction...")
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": BODY_EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    )

    # Log usage
    logger.info(
        f"API usage - Input tokens: {response.usage.input_tokens}, "
        f"Output tokens: {response.usage.output_tokens}"
    )

    # Parse response
    response_text = response.content[0].text
    extracted_data = _parse_extraction_response(response_text)

    # Validate with Pydantic schema
    try:
        result = DocumentExtraction(**extracted_data)
        logger.info(
            f"Extraction successful - Document type: {result.document_type}, "
            f"Confidence: {result.confidence.overall:.2f}"
        )
        return result
    except ValidationError as e:
        logger.error(f"Validation failed: {e}")
        # Try to return partial data with notes about validation issues
        extracted_data["extraction_notes"] = extracted_data.get("extraction_notes", [])
        extracted_data["extraction_notes"].append(f"Validation warning: {str(e)[:200]}")

        # Set defaults for missing required fields
        if "document_type" not in extracted_data:
            extracted_data["document_type"] = "Unknown"

        return DocumentExtraction(**extracted_data)


def extract_body_with_retry(
    pdf_path: str,
    api_key: Optional[str] = None,
    max_retries: int = 2,
    **kwargs,
) -> DocumentExtraction:
    """
    Extract body with retry logic for transient failures.

    Args:
        pdf_path: Path to the body PDF file
        api_key: Anthropic API key
        max_retries: Maximum retry attempts
        **kwargs: Additional arguments for extract_body

    Returns:
        DocumentExtraction object

    Raises:
        Exception: If all retries fail
    """
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return extract_body(pdf_path, api_key=api_key, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(f"Extraction attempt {attempt + 1} failed: {e}, retrying...")
            else:
                logger.error(f"All {max_retries + 1} extraction attempts failed")

    raise last_error


def extraction_to_dict(extraction: DocumentExtraction) -> dict:
    """Convert DocumentExtraction to dictionary for serialization."""
    return extraction.model_dump(exclude_none=True)


def extraction_to_json(extraction: DocumentExtraction, indent: int = 2) -> str:
    """Convert DocumentExtraction to JSON string."""
    return extraction.model_dump_json(indent=indent, exclude_none=True)


# CLI interface for testing
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: python body_extractor.py <pdf_path>")
        print("\nEnvironment: ANTHROPIC_API_KEY must be set")
        sys.exit(1)

    pdf_path = sys.argv[1]
    print(f"\nExtracting from: {pdf_path}")
    print("-" * 60)

    try:
        result = extract_body(pdf_path)

        print(f"\nDocument Type: {result.document_type}")
        print(f"Title: {result.document_title}")

        print(f"\nGrantors ({len(result.parties.grantors)}):")
        for p in result.parties.grantors:
            print(f"  - {p.name} ({p.entity_type or 'unknown'})")

        print(f"\nGrantees ({len(result.parties.grantees)}):")
        for p in result.parties.grantees:
            print(f"  - {p.name} ({p.entity_type or 'unknown'})")

        print(f"\nDates:")
        print(f"  Execution: {result.dates.execution}")
        print(f"  Recording: {result.dates.recording}")

        print(f"\nRecording Info:")
        print(f"  Book/Page: {result.recording_info.book}/{result.recording_info.page}")
        print(f"  Doc #: {result.recording_info.document_number}")
        print(f"  County: {result.recording_info.county}, {result.recording_info.state}")

        print(f"\nInterests:")
        print(f"  Conveyed: {result.interests.conveyed_fraction} - {result.interests.interest_type}")
        print(f"  Reserved: {result.interests.reserved}")

        print(f"\nExhibit References ({len(result.exhibit_references)}):")
        for ex in result.exhibit_references:
            print(f"  - {ex.name}: {ex.description}")

        print(f"\nConfidence: {result.confidence.overall:.2f}")

        if result.extraction_notes:
            print(f"\nNotes:")
            for note in result.extraction_notes:
                print(f"  - {note}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
