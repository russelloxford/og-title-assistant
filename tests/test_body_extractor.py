"""
Tests for the Body Extractor Module
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.body_extractor import (
    _load_pdf_as_base64,
    _parse_extraction_response,
    extract_body,
    extraction_to_dict,
    extraction_to_json,
)
from src.schemas import (
    ConfidenceScores,
    DatesInfo,
    DocumentExtraction,
    ExhibitReference,
    InterestsInfo,
    PartiesInfo,
    PartyInfo,
    RecordingInfo,
)


class TestParseExtractionResponse:
    """Tests for JSON parsing from Claude response."""

    def test_plain_json(self):
        """Should parse plain JSON."""
        response = '{"document_type": "Deed", "confidence": {"overall": 0.9}}'
        result = _parse_extraction_response(response)
        assert result["document_type"] == "Deed"

    def test_json_with_code_block(self):
        """Should handle JSON wrapped in markdown code block."""
        response = '```json\n{"document_type": "Deed"}\n```'
        result = _parse_extraction_response(response)
        assert result["document_type"] == "Deed"

    def test_json_with_plain_code_block(self):
        """Should handle JSON wrapped in plain code block."""
        response = '```\n{"document_type": "Deed"}\n```'
        result = _parse_extraction_response(response)
        assert result["document_type"] == "Deed"

    def test_invalid_json_raises(self):
        """Should raise ValueError for invalid JSON."""
        response = "This is not JSON"
        with pytest.raises(ValueError, match="Invalid JSON"):
            _parse_extraction_response(response)

    def test_whitespace_handling(self):
        """Should handle extra whitespace."""
        response = '\n\n  {"document_type": "Deed"}  \n\n'
        result = _parse_extraction_response(response)
        assert result["document_type"] == "Deed"


class TestDocumentExtractionSchema:
    """Tests for the DocumentExtraction Pydantic model."""

    def test_minimal_extraction(self):
        """Should create with only required fields."""
        extraction = DocumentExtraction(document_type="Deed")
        assert extraction.document_type == "Deed"
        assert extraction.parties.grantors == []
        assert extraction.parties.grantees == []

    def test_full_extraction(self):
        """Should create with all fields populated."""
        extraction = DocumentExtraction(
            document_type="Assignment of Oil and Gas Leases",
            document_title="ASSIGNMENT",
            parties=PartiesInfo(
                grantors=[PartyInfo(name="Smith Oil LLC", entity_type="llc")],
                grantees=[PartyInfo(name="Jones Energy LP", entity_type="limited_partnership")],
            ),
            dates=DatesInfo(
                execution=date(2024, 1, 15),
                recording=date(2024, 1, 20),
            ),
            recording_info=RecordingInfo(
                book="450",
                page="123",
                county="Williams",
                state="ND",
            ),
            interests=InterestsInfo(
                conveyed="All right, title and interest",
                conveyed_fraction="100%",
                reserved="1/16 ORRI",
                interest_type="leasehold",
            ),
            exhibit_references=[
                ExhibitReference(name="Exhibit A", description="Lease schedule"),
            ],
            confidence=ConfidenceScores(overall=0.95, parties=0.98),
        )

        assert extraction.document_type == "Assignment of Oil and Gas Leases"
        assert len(extraction.parties.grantors) == 1
        assert extraction.parties.grantors[0].name == "Smith Oil LLC"
        assert extraction.dates.execution == date(2024, 1, 15)
        assert extraction.recording_info.book == "450"
        assert extraction.confidence.overall == 0.95


class TestDatesInfo:
    """Tests for date parsing in DatesInfo."""

    def test_date_from_iso_string(self):
        """Should parse ISO format dates."""
        dates = DatesInfo(execution="2024-01-15")
        assert dates.execution == date(2024, 1, 15)

    def test_date_from_us_format(self):
        """Should parse US format dates."""
        dates = DatesInfo(execution="01/15/2024")
        assert dates.execution == date(2024, 1, 15)

    def test_date_from_long_format(self):
        """Should parse long format dates."""
        dates = DatesInfo(execution="January 15, 2024")
        assert dates.execution == date(2024, 1, 15)

    def test_null_date(self):
        """Should handle null dates."""
        dates = DatesInfo(execution=None)
        assert dates.execution is None

    def test_empty_string_date(self):
        """Should handle empty string as null."""
        dates = DatesInfo(execution="")
        assert dates.execution is None

    def test_invalid_date_format(self):
        """Should return None for unrecognized formats."""
        dates = DatesInfo(execution="invalid date")
        assert dates.execution is None


class TestExtractionToDict:
    """Tests for conversion utilities."""

    def test_extraction_to_dict(self):
        """Should convert extraction to dictionary."""
        extraction = DocumentExtraction(
            document_type="Deed",
            document_title="WARRANTY DEED",
        )
        result = extraction_to_dict(extraction)

        assert isinstance(result, dict)
        assert result["document_type"] == "Deed"
        assert result["document_title"] == "WARRANTY DEED"

    def test_extraction_to_json(self):
        """Should convert extraction to JSON string."""
        extraction = DocumentExtraction(
            document_type="Deed",
            confidence=ConfidenceScores(overall=0.9),
        )
        result = extraction_to_json(extraction)

        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["document_type"] == "Deed"


class TestExtractBody:
    """Tests for the main extract_body function."""

    def test_file_not_found(self):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            extract_body("/nonexistent/file.pdf")

    @patch("src.body_extractor.Anthropic")
    @patch("src.body_extractor._load_pdf_as_base64")
    @patch("os.path.exists")
    @patch("os.path.getsize")
    def test_successful_extraction(
        self, mock_getsize, mock_exists, mock_load_pdf, mock_anthropic
    ):
        """Should successfully extract from PDF."""
        # Setup mocks
        mock_exists.return_value = True
        mock_getsize.return_value = 1024
        mock_load_pdf.return_value = "base64encodedpdf"

        # Mock Claude response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({
            "document_type": "Assignment",
            "parties": {
                "grantors": [{"name": "Test Grantor"}],
                "grantees": [{"name": "Test Grantee"}],
            },
            "confidence": {"overall": 0.9},
        })
        mock_response.usage.input_tokens = 1000
        mock_response.usage.output_tokens = 500

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        # Call function
        result = extract_body("/fake/path.pdf")

        # Verify
        assert result.document_type == "Assignment"
        assert len(result.parties.grantors) == 1
        assert result.parties.grantors[0].name == "Test Grantor"
        assert result.confidence.overall == 0.9

    @patch("src.body_extractor.Anthropic")
    @patch("src.body_extractor._load_pdf_as_base64")
    @patch("os.path.exists")
    @patch("os.path.getsize")
    def test_uses_api_key_from_param(
        self, mock_getsize, mock_exists, mock_load_pdf, mock_anthropic
    ):
        """Should use API key from parameter."""
        mock_exists.return_value = True
        mock_getsize.return_value = 1024
        mock_load_pdf.return_value = "base64"

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = '{"document_type": "Deed"}'
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        extract_body("/fake/path.pdf", api_key="test-key-123")

        mock_anthropic.assert_called_with(api_key="test-key-123")


class TestConfidenceScores:
    """Tests for confidence score validation."""

    def test_valid_scores(self):
        """Should accept valid scores between 0 and 1."""
        scores = ConfidenceScores(overall=0.95, parties=0.98)
        assert scores.overall == 0.95
        assert scores.parties == 0.98

    def test_boundary_scores(self):
        """Should accept boundary values."""
        scores = ConfidenceScores(overall=0.0, parties=1.0)
        assert scores.overall == 0.0
        assert scores.parties == 1.0

    def test_invalid_score_too_high(self):
        """Should reject scores above 1."""
        with pytest.raises(Exception):  # Pydantic validation error
            ConfidenceScores(overall=1.5)

    def test_invalid_score_negative(self):
        """Should reject negative scores."""
        with pytest.raises(Exception):  # Pydantic validation error
            ConfidenceScores(overall=-0.1)


class TestPartyInfo:
    """Tests for party information."""

    def test_minimal_party(self):
        """Should create with just name."""
        party = PartyInfo(name="John Doe")
        assert party.name == "John Doe"
        assert party.address is None

    def test_full_party(self):
        """Should create with all fields."""
        party = PartyInfo(
            name="Smith Oil Company, LLC",
            address="123 Main St, Williston, ND 58801",
            role="Assignor",
            entity_type="llc",
        )
        assert party.name == "Smith Oil Company, LLC"
        assert party.address == "123 Main St, Williston, ND 58801"
        assert party.role == "Assignor"
        assert party.entity_type == "llc"


# Integration test marker
@pytest.mark.integration
class TestIntegration:
    """Integration tests requiring actual API calls."""

    @pytest.fixture
    def sample_pdf_path(self):
        """Path to sample PDF for testing."""
        from pathlib import Path

        path = Path(__file__).parent.parent / "test_documents" / "sample_deed.pdf"
        if path.exists():
            return str(path)
        pytest.skip("Sample PDF not found")

    def test_real_extraction(self, sample_pdf_path):
        """Test extraction with real PDF and API."""
        import os

        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")

        result = extract_body(sample_pdf_path)

        assert result.document_type is not None
        assert result.confidence.overall > 0
