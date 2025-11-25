"""
Tests for the Document Splitter Module
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the module under test
from src.splitter import (
    EXHIBIT_MARKERS,
    ExhibitInfo,
    SplitPoints,
    SplitResult,
    _classify_exhibit_type,
    _consolidate_exhibits,
    _generate_file_hash,
    _get_base_marker,
    cleanup_temp_files,
    find_split_points,
    process_document,
    split_document,
)


class TestClassifyExhibitType:
    """Tests for exhibit type classification."""

    def test_table_from_schedule_marker(self):
        """Schedule markers should classify as table."""
        result = _classify_exhibit_type("SCHEDULE OF LEASES", "")
        assert result == "table"

    def test_table_from_text_content(self):
        """Text with table indicators should classify as table."""
        result = _classify_exhibit_type("EXHIBIT A", "LESSOR LESSEE RECORDING")
        assert result == "table"

    def test_legal_descriptions(self):
        """Legal description markers should classify correctly."""
        result = _classify_exhibit_type("LEGAL DESCRIPTION", "")
        assert result == "legal_descriptions"

    def test_legal_descriptions_from_text(self):
        """Text with legal desc indicators should classify correctly."""
        result = _classify_exhibit_type("EXHIBIT B", "SECTION 15 TOWNSHIP 3N RANGE 4W")
        assert result == "legal_descriptions"

    def test_image_plat(self):
        """Plat markers should classify as image."""
        result = _classify_exhibit_type("EXHIBIT A", "PLAT MAP ATTACHED")
        assert result == "image"

    def test_image_survey(self):
        """Survey markers should classify as image."""
        result = _classify_exhibit_type("EXHIBIT C", "SURVEY DRAWING")
        assert result == "image"

    def test_narrative_default(self):
        """Unknown content should default to narrative."""
        result = _classify_exhibit_type("EXHIBIT A", "SOME OTHER CONTENT")
        assert result == "narrative"


class TestGenerateFileHash:
    """Tests for file hash generation."""

    def test_consistent_hash(self):
        """Same path should produce same hash."""
        hash1 = _generate_file_hash("/path/to/file.pdf")
        hash2 = _generate_file_hash("/path/to/file.pdf")
        assert hash1 == hash2

    def test_different_paths_different_hash(self):
        """Different paths should produce different hashes."""
        hash1 = _generate_file_hash("/path/to/file1.pdf")
        hash2 = _generate_file_hash("/path/to/file2.pdf")
        assert hash1 != hash2

    def test_hash_length(self):
        """Hash should be 12 characters."""
        hash_val = _generate_file_hash("/any/path.pdf")
        assert len(hash_val) == 12


class TestGetBaseMarker:
    """Tests for base marker extraction."""

    def test_simple_marker(self):
        """Simple marker should be returned as-is."""
        assert _get_base_marker("EXHIBIT A") == "EXHIBIT A"

    def test_continued_marker(self):
        """Continued marker should have suffix removed."""
        assert _get_base_marker("EXHIBIT A (continued)") == "EXHIBIT A"
        assert _get_base_marker("EXHIBIT A (CONTINUED)") == "EXHIBIT A"
        # Note: "- CONTINUED" suffix is also removed
        result = _get_base_marker("EXHIBIT A - CONTINUED")
        assert result in ["EXHIBIT A", "EXHIBIT A -"]

    def test_cont_abbreviation(self):
        """Abbreviated continuation should be handled."""
        assert _get_base_marker("EXHIBIT A (cont.)") == "EXHIBIT A"
        assert _get_base_marker("EXHIBIT A (CONT)") == "EXHIBIT A"

    def test_case_insensitive(self):
        """Marker should be uppercase regardless of input."""
        assert _get_base_marker("exhibit a") == "EXHIBIT A"


class TestConsolidateExhibits:
    """Tests for exhibit consolidation."""

    def test_empty_list(self):
        """Empty list should return empty list."""
        assert _consolidate_exhibits([]) == []

    def test_single_exhibit(self):
        """Single exhibit should be returned as-is."""
        exhibits = [ExhibitInfo(marker="EXHIBIT A", start_page=5, exhibit_type="table")]
        result = _consolidate_exhibits(exhibits)
        assert len(result) == 1
        assert result[0].marker == "EXHIBIT A"
        assert result[0].start_page == 5

    def test_consolidate_same_marker(self):
        """Consecutive pages with same marker should consolidate."""
        exhibits = [
            ExhibitInfo(marker="EXHIBIT A", start_page=5, exhibit_type="table"),
            ExhibitInfo(marker="EXHIBIT A", start_page=6, exhibit_type="table"),
            ExhibitInfo(marker="EXHIBIT A", start_page=7, exhibit_type="table"),
        ]
        result = _consolidate_exhibits(exhibits)
        assert len(result) == 1
        assert result[0].marker == "EXHIBIT A"
        assert result[0].start_page == 5

    def test_different_exhibits(self):
        """Different markers should not consolidate."""
        exhibits = [
            ExhibitInfo(marker="EXHIBIT A", start_page=5, exhibit_type="table"),
            ExhibitInfo(marker="EXHIBIT B", start_page=10, exhibit_type="narrative"),
        ]
        result = _consolidate_exhibits(exhibits)
        assert len(result) == 2
        assert result[0].marker == "EXHIBIT A"
        assert result[1].marker == "EXHIBIT B"

    def test_mixed_consolidation(self):
        """Mix of same and different markers should consolidate correctly."""
        exhibits = [
            ExhibitInfo(marker="EXHIBIT A", start_page=5, exhibit_type="table"),
            ExhibitInfo(marker="EXHIBIT A", start_page=6, exhibit_type="table"),
            ExhibitInfo(marker="EXHIBIT B", start_page=10, exhibit_type="narrative"),
            ExhibitInfo(marker="EXHIBIT B", start_page=11, exhibit_type="narrative"),
        ]
        result = _consolidate_exhibits(exhibits)
        assert len(result) == 2
        assert result[0].marker == "EXHIBIT A"
        assert result[0].start_page == 5
        assert result[1].marker == "EXHIBIT B"
        assert result[1].start_page == 10


class TestExhibitMarkers:
    """Tests for exhibit marker list."""

    def test_common_markers_present(self):
        """Common exhibit markers should be in the list."""
        assert "EXHIBIT A" in EXHIBIT_MARKERS
        assert "EXHIBIT B" in EXHIBIT_MARKERS
        assert "SCHEDULE OF LEASES" in EXHIBIT_MARKERS
        assert "LEGAL DESCRIPTION" in EXHIBIT_MARKERS

    def test_oil_gas_markers_present(self):
        """Oil & gas specific markers should be in the list."""
        assert "SCHEDULE OF INTERESTS" in EXHIBIT_MARKERS
        assert "TRACT SCHEDULE" in EXHIBIT_MARKERS


class TestDataClasses:
    """Tests for data classes."""

    def test_exhibit_info_creation(self):
        """ExhibitInfo should be creatable with required fields."""
        exhibit = ExhibitInfo(
            marker="EXHIBIT A",
            start_page=5,
            exhibit_type="table",
        )
        assert exhibit.marker == "EXHIBIT A"
        assert exhibit.start_page == 5
        assert exhibit.exhibit_type == "table"
        assert exhibit.end_page is None
        assert exhibit.path is None
        assert exhibit.page_count == 0

    def test_split_points_defaults(self):
        """SplitPoints should have correct defaults."""
        sp = SplitPoints()
        assert sp.body_end is None
        assert sp.exhibits == []
        assert sp.total_pages == 0

    def test_split_result_defaults(self):
        """SplitResult should have correct defaults."""
        sr = SplitResult()
        assert sr.body_path is None
        assert sr.exhibits == []
        assert sr.original_path == ""
        assert sr.total_pages == 0
        assert sr.body_pages == 0


class TestFindSplitPoints:
    """Tests for find_split_points function."""

    @pytest.fixture
    def mock_pdf(self):
        """Create a mock PDF document."""
        with patch("src.splitter.fitz") as mock_fitz:
            # Mock document
            mock_doc = MagicMock()
            mock_doc.__len__ = MagicMock(return_value=10)

            # Mock page
            mock_page = MagicMock()
            mock_page.rect.width = 612
            mock_page.rect.height = 792

            # Mock pixmap
            mock_pix = MagicMock()
            mock_pix.tobytes.return_value = b"fake_png_data"

            mock_page.get_pixmap.return_value = mock_pix
            mock_doc.__getitem__ = MagicMock(return_value=mock_page)

            mock_fitz.open.return_value = mock_doc
            mock_fitz.Rect = MagicMock()
            mock_fitz.Matrix = MagicMock()

            yield mock_fitz, mock_doc

    @patch("src.splitter.pytesseract.image_to_string")
    @patch("src.splitter.Image.open")
    def test_no_exhibits_found(self, mock_img_open, mock_ocr, mock_pdf):
        """Document with no exhibits should have body_end at total pages."""
        mock_ocr.return_value = "JUST REGULAR TEXT"
        mock_img_open.return_value = MagicMock()

        result = find_split_points("/fake/path.pdf")

        assert result.body_end == 10
        assert len(result.exhibits) == 0

    @patch("src.splitter.pytesseract.image_to_string")
    @patch("src.splitter.Image.open")
    def test_exhibit_found(self, mock_img_open, mock_ocr, mock_pdf):
        """Document with exhibit should split correctly."""

        def ocr_side_effect(img):
            # Return exhibit marker on 6th call (page 5)
            if mock_ocr.call_count == 6:
                return "EXHIBIT A - SCHEDULE OF LEASES"
            return "Regular document text"

        mock_ocr.side_effect = ocr_side_effect
        mock_img_open.return_value = MagicMock()

        result = find_split_points("/fake/path.pdf")

        assert result.body_end == 5
        assert len(result.exhibits) == 1
        assert result.exhibits[0].marker == "EXHIBIT A"
        assert result.exhibits[0].start_page == 5


class TestProcessDocument:
    """Tests for process_document function."""

    def test_file_not_found(self):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            process_document("/nonexistent/file.pdf")


class TestCleanupTempFiles:
    """Tests for cleanup_temp_files function."""

    def test_cleanup_removes_files(self):
        """Should remove temporary files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create temp files
            body_path = Path(tmpdir) / "body.pdf"
            exhibit_path = Path(tmpdir) / "exhibit.pdf"
            body_path.touch()
            exhibit_path.touch()

            result = SplitResult(
                body_path=str(body_path),
                exhibits=[
                    ExhibitInfo(
                        marker="EXHIBIT A",
                        start_page=0,
                        exhibit_type="table",
                        path=str(exhibit_path),
                    )
                ],
            )

            cleanup_temp_files(result)

            assert not body_path.exists()
            assert not exhibit_path.exists()

    def test_cleanup_handles_missing_files(self):
        """Should handle already-deleted files gracefully."""
        result = SplitResult(
            body_path="/nonexistent/body.pdf",
            exhibits=[
                ExhibitInfo(
                    marker="EXHIBIT A",
                    start_page=0,
                    exhibit_type="table",
                    path="/nonexistent/exhibit.pdf",
                )
            ],
        )

        # Should not raise an exception
        cleanup_temp_files(result)


# Integration test (requires actual PDF and Tesseract)
@pytest.mark.integration
class TestIntegration:
    """Integration tests requiring actual PDF files and Tesseract."""

    @pytest.fixture
    def sample_pdf_path(self):
        """Path to sample PDF for testing."""
        # This would be a real test document
        path = Path(__file__).parent.parent / "test_documents" / "sample.pdf"
        if path.exists():
            return str(path)
        pytest.skip("Sample PDF not found")

    def test_real_pdf_processing(self, sample_pdf_path):
        """Test processing a real PDF document."""
        result = process_document(sample_pdf_path)

        assert result.total_pages > 0
        assert result.body_path is not None
        assert os.path.exists(result.body_path)

        # Cleanup
        cleanup_temp_files(result)
