"""
Tests for the Table Extractor Module
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.table_extractor import (
    COLUMN_MAPPINGS,
    ExtractedTable,
    LeaseRecord,
    TableCell,
    TableExtractionResult,
    _get_block_text,
    _map_columns,
    _parse_textract_tables,
    extract_tables,
    parse_lease_schedule,
    tables_to_dict,
)


class TestColumnMappings:
    """Tests for column mapping configuration."""

    def test_lessor_variations(self):
        """Should have common lessor column variations."""
        assert "lessor" in COLUMN_MAPPINGS["lessor"]
        assert "grantor" in COLUMN_MAPPINGS["lessor"]
        assert "owner" in COLUMN_MAPPINGS["lessor"]

    def test_lessee_variations(self):
        """Should have common lessee column variations."""
        assert "lessee" in COLUMN_MAPPINGS["lessee"]
        assert "grantee" in COLUMN_MAPPINGS["lessee"]
        assert "operator" in COLUMN_MAPPINGS["lessee"]

    def test_lands_variations(self):
        """Should have common lands column variations."""
        assert "lands" in COLUMN_MAPPINGS["lands"]
        assert "legal" in COLUMN_MAPPINGS["lands"]
        assert "description" in COLUMN_MAPPINGS["lands"]


class TestMapColumns:
    """Tests for column mapping function."""

    def test_exact_match(self):
        """Should map exact column name matches."""
        headers = ["Lessor", "Lessee", "Recording", "Lands"]
        result = _map_columns(headers)

        assert result["lessor"] == 0
        assert result["lessee"] == 1
        assert result["recording"] == 2
        assert result["lands"] == 3

    def test_partial_match(self):
        """Should map partial matches."""
        headers = ["Mineral Owner Name", "Oil Company", "Book/Page", "Land Description"]
        result = _map_columns(headers)

        assert result["lessor"] == 0  # "owner" in "Mineral Owner Name"
        assert result["lessee"] == 1  # "oil company" matches
        assert result["recording"] == 2  # "book" in "Book/Page"
        assert result["lands"] == 3  # "land description" matches

    def test_case_insensitive(self):
        """Should be case insensitive."""
        headers = ["LESSOR", "LESSEE", "RECORDING INFO", "LANDS"]
        result = _map_columns(headers)

        assert "lessor" in result
        assert "lessee" in result
        assert "recording" in result
        assert "lands" in result

    def test_no_matches(self):
        """Should return empty dict for unrecognized headers."""
        headers = ["Column A", "Column B", "Column C"]
        result = _map_columns(headers)

        assert result == {}

    def test_mixed_matches(self):
        """Should map only recognized columns."""
        headers = ["Lessor", "Unknown", "Lands", "Random"]
        result = _map_columns(headers)

        assert "lessor" in result
        assert "lands" in result
        assert len(result) == 2


class TestDataClasses:
    """Tests for data classes."""

    def test_table_cell(self):
        """Should create TableCell with all fields."""
        cell = TableCell(
            text="Smith, John",
            row_index=1,
            column_index=0,
            confidence=0.95,
        )
        assert cell.text == "Smith, John"
        assert cell.row_index == 1
        assert cell.column_index == 0
        assert cell.confidence == 0.95

    def test_extracted_table_defaults(self):
        """Should have sensible defaults."""
        table = ExtractedTable(page_number=1)
        assert table.page_number == 1
        assert table.headers == []
        assert table.rows == []
        assert table.confidence == 0.0

    def test_lease_record_defaults(self):
        """Should have None defaults for optional fields."""
        record = LeaseRecord()
        assert record.lessor is None
        assert record.lessee is None
        assert record.lands is None
        assert record.raw_row == []

    def test_table_extraction_result(self):
        """Should hold extraction results."""
        result = TableExtractionResult(
            tables=[ExtractedTable(page_number=1)],
            lease_records=[LeaseRecord(lessor="Test")],
            page_count=5,
            source_path="/test/path.pdf",
        )
        assert len(result.tables) == 1
        assert len(result.lease_records) == 1
        assert result.page_count == 5
        assert result.source_path == "/test/path.pdf"


class TestParseLeaseSchedule:
    """Tests for lease schedule parsing."""

    def test_basic_parsing(self):
        """Should parse basic lease table."""
        tables = [
            ExtractedTable(
                page_number=1,
                headers=["Lessor", "Lessee", "Recording", "Lands"],
                rows=[
                    ["Smith, John", "Acme Oil Co", "Bk 450/Pg 1", "NW/4 Sec 15-154N-97W"],
                    ["Jones, Mary", "Acme Oil Co", "Bk 450/Pg 5", "SW/4 Sec 15-154N-97W"],
                ],
            )
        ]

        records = parse_lease_schedule(tables)

        assert len(records) == 2
        assert records[0].lessor == "Smith, John"
        assert records[0].lessee == "Acme Oil Co"
        assert records[0].recording_info == "Bk 450/Pg 1"
        assert records[0].lands == "NW/4 Sec 15-154N-97W"

    def test_skip_empty_rows(self):
        """Should skip empty rows."""
        tables = [
            ExtractedTable(
                page_number=1,
                headers=["Lessor", "Lands"],
                rows=[
                    ["Smith, John", "NW/4 Sec 15"],
                    ["", ""],
                    ["Jones, Mary", "SW/4 Sec 15"],
                ],
            )
        ]

        records = parse_lease_schedule(tables)

        assert len(records) == 2

    def test_skip_tables_without_headers(self):
        """Should skip tables without headers."""
        tables = [
            ExtractedTable(
                page_number=1,
                headers=[],
                rows=[["Data1", "Data2"]],
            )
        ]

        records = parse_lease_schedule(tables)

        assert len(records) == 0

    def test_skip_unrecognized_tables(self):
        """Should skip tables with unrecognized columns."""
        tables = [
            ExtractedTable(
                page_number=1,
                headers=["Column A", "Column B"],
                rows=[["Data1", "Data2"]],
            )
        ]

        records = parse_lease_schedule(tables)

        assert len(records) == 0

    def test_multiple_tables(self):
        """Should parse multiple tables."""
        tables = [
            ExtractedTable(
                page_number=1,
                headers=["Lessor", "Lands"],
                rows=[["Smith, John", "NW/4 Sec 15"]],
            ),
            ExtractedTable(
                page_number=2,
                headers=["Lessor", "Lands"],
                rows=[["Jones, Mary", "SW/4 Sec 15"]],
            ),
        ]

        records = parse_lease_schedule(tables)

        assert len(records) == 2

    def test_all_field_types(self):
        """Should parse all recognized field types."""
        tables = [
            ExtractedTable(
                page_number=1,
                headers=[
                    "Lessor",
                    "Lessee",
                    "Recording",
                    "Lands",
                    "Date",
                    "County",
                    "State",
                    "Acres",
                    "Interest",
                ],
                rows=[
                    [
                        "Smith, John",
                        "Acme Oil",
                        "Bk 450/Pg 1",
                        "NW/4 Sec 15",
                        "01/15/2024",
                        "Williams",
                        "ND",
                        "160.00",
                        "100%",
                    ]
                ],
            )
        ]

        records = parse_lease_schedule(tables)

        assert len(records) == 1
        record = records[0]
        assert record.lessor == "Smith, John"
        assert record.lessee == "Acme Oil"
        assert record.recording_info == "Bk 450/Pg 1"
        assert record.lands == "NW/4 Sec 15"
        assert record.date == "01/15/2024"
        assert record.county == "Williams"
        assert record.state == "ND"
        assert record.acres == "160.00"
        assert record.interest == "100%"


class TestParseTextractTables:
    """Tests for Textract response parsing."""

    def test_parse_simple_table(self):
        """Should parse simple Textract response."""
        # Mock Textract response structure
        response = {
            "Blocks": [
                {
                    "Id": "table-1",
                    "BlockType": "TABLE",
                    "Page": 1,
                    "Confidence": 98.5,
                    "Relationships": [{"Type": "CHILD", "Ids": ["cell-1", "cell-2"]}],
                },
                {
                    "Id": "cell-1",
                    "BlockType": "CELL",
                    "RowIndex": 1,
                    "ColumnIndex": 1,
                    "Confidence": 99.0,
                    "Relationships": [{"Type": "CHILD", "Ids": ["word-1"]}],
                },
                {
                    "Id": "cell-2",
                    "BlockType": "CELL",
                    "RowIndex": 1,
                    "ColumnIndex": 2,
                    "Confidence": 99.0,
                    "Relationships": [{"Type": "CHILD", "Ids": ["word-2"]}],
                },
                {"Id": "word-1", "BlockType": "WORD", "Text": "Header1"},
                {"Id": "word-2", "BlockType": "WORD", "Text": "Header2"},
            ]
        }

        tables = _parse_textract_tables(response)

        assert len(tables) == 1
        assert tables[0].page_number == 1
        assert tables[0].confidence == 98.5
        assert len(tables[0].headers) == 2
        assert tables[0].headers[0] == "Header1"
        assert tables[0].headers[1] == "Header2"

    def test_empty_response(self):
        """Should handle empty response."""
        response = {"Blocks": []}
        tables = _parse_textract_tables(response)
        assert tables == []

    def test_no_tables(self):
        """Should handle response with no tables."""
        response = {
            "Blocks": [
                {"Id": "line-1", "BlockType": "LINE", "Text": "Some text"},
            ]
        }
        tables = _parse_textract_tables(response)
        assert tables == []


class TestTablesToDict:
    """Tests for serialization."""

    def test_conversion(self):
        """Should convert result to dictionary."""
        result = TableExtractionResult(
            tables=[
                ExtractedTable(
                    page_number=1,
                    headers=["Lessor", "Lands"],
                    rows=[["Smith", "NW/4"]],
                    confidence=0.95,
                )
            ],
            lease_records=[
                LeaseRecord(lessor="Smith", lands="NW/4"),
            ],
            page_count=5,
            source_path="/test.pdf",
        )

        data = tables_to_dict(result)

        assert data["page_count"] == 5
        assert data["source_path"] == "/test.pdf"
        assert data["table_count"] == 1
        assert data["lease_record_count"] == 1
        assert len(data["tables"]) == 1
        assert len(data["lease_records"]) == 1
        assert data["lease_records"][0]["lessor"] == "Smith"


class TestExtractTables:
    """Tests for main extraction function."""

    def test_file_not_found(self):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            extract_tables("/nonexistent/file.pdf")

    def test_no_bucket_configured(self):
        """Should raise ValueError if no bucket configured."""
        # Temporarily clear environment variable
        old_bucket = os.environ.pop("TEXTRACT_S3_BUCKET", None)

        try:
            with pytest.raises(ValueError, match="No S3 bucket"):
                # Create a temp file that exists
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                    f.write(b"%PDF-1.4 test")
                    temp_path = f.name

                try:
                    extract_tables(temp_path, bucket=None)
                finally:
                    os.unlink(temp_path)
        finally:
            if old_bucket:
                os.environ["TEXTRACT_S3_BUCKET"] = old_bucket

    @patch("src.table_extractor._delete_from_s3")
    @patch("src.table_extractor._poll_textract_job")
    @patch("src.table_extractor._start_textract_job")
    @patch("src.table_extractor._upload_to_s3")
    @patch("os.path.exists")
    def test_successful_extraction(
        self,
        mock_exists,
        mock_upload,
        mock_start,
        mock_poll,
        mock_delete,
    ):
        """Should successfully extract tables."""
        mock_exists.return_value = True
        mock_upload.return_value = "test-key.pdf"
        mock_start.return_value = "job-123"
        mock_poll.return_value = {
            "Blocks": [
                {
                    "Id": "table-1",
                    "BlockType": "TABLE",
                    "Page": 1,
                    "Confidence": 95.0,
                    "Relationships": [{"Type": "CHILD", "Ids": ["cell-1"]}],
                },
                {
                    "Id": "cell-1",
                    "BlockType": "CELL",
                    "RowIndex": 1,
                    "ColumnIndex": 1,
                    "Relationships": [{"Type": "CHILD", "Ids": ["word-1"]}],
                },
                {"Id": "word-1", "BlockType": "WORD", "Text": "Lessor"},
            ],
            "DocumentMetadata": {"Pages": 5},
        }

        result = extract_tables("/fake/path.pdf", bucket="test-bucket")

        assert result.page_count == 5
        assert len(result.tables) == 1
        mock_delete.assert_called_once()

    @patch("src.table_extractor._delete_from_s3")
    @patch("src.table_extractor._poll_textract_job")
    @patch("src.table_extractor._start_textract_job")
    @patch("src.table_extractor._upload_to_s3")
    @patch("os.path.exists")
    def test_cleanup_on_success(
        self,
        mock_exists,
        mock_upload,
        mock_start,
        mock_poll,
        mock_delete,
    ):
        """Should cleanup S3 file after processing."""
        mock_exists.return_value = True
        mock_upload.return_value = "test-key.pdf"
        mock_start.return_value = "job-123"
        mock_poll.return_value = {"Blocks": [], "DocumentMetadata": {"Pages": 1}}

        extract_tables("/fake/path.pdf", bucket="test-bucket", cleanup=True)

        mock_delete.assert_called_once_with("test-bucket", "test-key.pdf")

    @patch("src.table_extractor._delete_from_s3")
    @patch("src.table_extractor._poll_textract_job")
    @patch("src.table_extractor._start_textract_job")
    @patch("src.table_extractor._upload_to_s3")
    @patch("os.path.exists")
    def test_no_cleanup_when_disabled(
        self,
        mock_exists,
        mock_upload,
        mock_start,
        mock_poll,
        mock_delete,
    ):
        """Should not cleanup when disabled."""
        mock_exists.return_value = True
        mock_upload.return_value = "test-key.pdf"
        mock_start.return_value = "job-123"
        mock_poll.return_value = {"Blocks": [], "DocumentMetadata": {"Pages": 1}}

        extract_tables("/fake/path.pdf", bucket="test-bucket", cleanup=False)

        mock_delete.assert_not_called()


# Integration test marker
@pytest.mark.integration
class TestIntegration:
    """Integration tests requiring actual AWS services."""

    @pytest.fixture
    def sample_exhibit_path(self):
        """Path to sample exhibit PDF for testing."""
        from pathlib import Path

        path = Path(__file__).parent.parent / "test_documents" / "sample_assignment.pdf"
        if path.exists():
            return str(path)
        pytest.skip("Sample PDF not found")

    def test_real_extraction(self, sample_exhibit_path):
        """Test extraction with real PDF and AWS services."""
        if not os.environ.get("AWS_ACCESS_KEY_ID"):
            pytest.skip("AWS credentials not configured")
        if not os.environ.get("TEXTRACT_S3_BUCKET"):
            pytest.skip("TEXTRACT_S3_BUCKET not set")

        result = extract_tables(sample_exhibit_path)

        assert result.page_count > 0
