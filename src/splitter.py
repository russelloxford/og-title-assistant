"""
Document Splitter Module

Intelligently splits PDF documents into body and exhibit sections using
local Tesseract OCR. Processes only the top 20% of each page (where headers
typically appear) to make splitting decisions at zero cost.

Cost: $0 (local Tesseract)
Time: ~2-3 seconds for 400-page document
"""

import io
import os
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

# Configure logging
logger = logging.getLogger(__name__)

# Exhibit markers - phrases that typically indicate the start of an exhibit section
EXHIBIT_MARKERS = [
    # Standard exhibit labels
    "EXHIBIT A",
    "EXHIBIT B",
    "EXHIBIT C",
    "EXHIBIT D",
    "EXHIBIT E",
    "EXHIBIT 1",
    "EXHIBIT 2",
    "EXHIBIT 3",
    # Schedule variations
    "SCHEDULE OF LEASES",
    "SCHEDULE 1",
    "SCHEDULE 2",
    "SCHEDULE A",
    "SCHEDULE B",
    "LEASE SCHEDULE",
    "SCHEDULE OF LANDS",
    # Attachment language
    "ATTACHED HERETO",
    "ATTACHMENT A",
    "ATTACHMENT 1",
    # Description headers
    "DESCRIPTION OF LANDS",
    "LEGAL DESCRIPTION",
    "PROPERTY DESCRIPTION",
    # Oil & gas specific
    "SCHEDULE OF INTERESTS",
    "TRACT SCHEDULE",
    "WELL SCHEDULE",
    "UNIT SCHEDULE",
]

# Words that help classify exhibit type
TABLE_INDICATORS = [
    "SCHEDULE",
    "LEASES",
    "TRACT",
    "INTERESTS",
    "WELLS",
    "UNITS",
    "LESSOR",
    "LESSEE",
]

LEGAL_DESC_INDICATORS = [
    "LEGAL DESCRIPTION",
    "LANDS",
    "PROPERTY",
    "SECTION",
    "TOWNSHIP",
    "RANGE",
    "QUARTER",
    "METES AND BOUNDS",
]

IMAGE_INDICATORS = [
    "PLAT",
    "MAP",
    "SURVEY",
    "DRAWING",
    "DIAGRAM",
]


@dataclass
class ExhibitInfo:
    """Information about a detected exhibit section."""

    marker: str
    start_page: int
    exhibit_type: str  # "table", "legal_descriptions", "image", "narrative"
    end_page: Optional[int] = None
    path: Optional[str] = None
    page_count: int = 0


@dataclass
class SplitPoints:
    """Document split point information."""

    body_end: Optional[int] = None
    exhibits: list[ExhibitInfo] = field(default_factory=list)
    total_pages: int = 0


@dataclass
class SplitResult:
    """Result of document splitting operation."""

    body_path: Optional[str] = None
    exhibits: list[ExhibitInfo] = field(default_factory=list)
    original_path: str = ""
    total_pages: int = 0
    body_pages: int = 0


def _generate_file_hash(file_path: str) -> str:
    """Generate a short hash for temp file naming."""
    return hashlib.md5(file_path.encode()).hexdigest()[:12]


def _classify_exhibit_type(marker: str, text: str) -> str:
    """
    Classify exhibit type for routing to appropriate processor.

    Args:
        marker: The exhibit marker found
        text: The OCR text from the page header

    Returns:
        One of: "table", "legal_descriptions", "image", "narrative"
    """
    text_upper = text.upper()
    marker_upper = marker.upper()

    # Check for table indicators (lease schedules, tract lists)
    if any(ind in marker_upper or ind in text_upper for ind in TABLE_INDICATORS):
        return "table"

    # Check for legal description indicators
    if any(ind in marker_upper or ind in text_upper for ind in LEGAL_DESC_INDICATORS):
        return "legal_descriptions"

    # Check for image/map indicators
    if any(ind in marker_upper or ind in text_upper for ind in IMAGE_INDICATORS):
        return "image"

    # Default to narrative for other exhibits
    return "narrative"


def _get_base_marker(marker: str) -> str:
    """
    Extract the base marker name (e.g., 'EXHIBIT A' from 'EXHIBIT A (continued)').

    This helps consolidate multi-page exhibits that have the same base marker.
    """
    # Remove common continuation indicators
    marker_upper = marker.upper().strip()
    for suffix in ["(CONTINUED)", "(CONT.)", "(CONT)", "- CONTINUED", "CONTINUED"]:
        if suffix in marker_upper:
            marker_upper = marker_upper.replace(suffix, "").strip()
    return marker_upper


def _consolidate_exhibits(exhibits: list[ExhibitInfo]) -> list[ExhibitInfo]:
    """
    Consolidate consecutive pages with the same exhibit marker into single exhibits.

    This handles multi-page exhibits where each page has a header like
    "EXHIBIT A" or "EXHIBIT A (continued)".

    Args:
        exhibits: List of ExhibitInfo objects (one per page with marker found)

    Returns:
        Consolidated list where consecutive same-marker pages are merged
    """
    if not exhibits:
        return []

    consolidated = []
    current_exhibit = None

    for exhibit in exhibits:
        base_marker = _get_base_marker(exhibit.marker)

        if current_exhibit is None:
            # Start first exhibit
            current_exhibit = ExhibitInfo(
                marker=base_marker,
                start_page=exhibit.start_page,
                exhibit_type=exhibit.exhibit_type,
            )
        elif _get_base_marker(current_exhibit.marker) == base_marker:
            # Same exhibit continues - just extend (end_page set later)
            pass
        else:
            # New exhibit found - save current and start new
            consolidated.append(current_exhibit)
            current_exhibit = ExhibitInfo(
                marker=base_marker,
                start_page=exhibit.start_page,
                exhibit_type=exhibit.exhibit_type,
            )

    # Don't forget the last exhibit
    if current_exhibit is not None:
        consolidated.append(current_exhibit)

    return consolidated


def find_split_points(
    pdf_path: str,
    scan_pages: int = 25,
    header_ratio: float = 0.20,
    zoom_factor: float = 2.0,
) -> SplitPoints:
    """
    Scan top portion of first N pages to identify document structure.

    This function processes only the top 20% of each page (where headers/titles
    typically appear) using local Tesseract OCR. This makes the splitting
    decision essentially free in terms of API costs.

    Args:
        pdf_path: Path to the PDF file
        scan_pages: Maximum number of pages to scan (default: 25)
        header_ratio: Portion of page height to scan (default: 0.20 = top 20%)
        zoom_factor: Zoom factor for better OCR quality (default: 2.0)

    Returns:
        SplitPoints object containing body_end page and list of exhibits

    Cost: $0 (local Tesseract)
    Time: ~2-3 seconds for 400-page document
    """
    logger.info(f"Finding split points in: {pdf_path}")

    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    split_points = SplitPoints(total_pages=total_pages)

    # Only scan first N pages (exhibits typically start within first 20 pages)
    pages_to_scan = min(scan_pages, total_pages)
    logger.debug(f"Scanning {pages_to_scan} of {total_pages} pages")

    for page_num in range(pages_to_scan):
        page = doc[page_num]

        # Render only top portion of page as image
        clip = fitz.Rect(0, 0, page.rect.width, page.rect.height * header_ratio)
        mat = fitz.Matrix(zoom_factor, zoom_factor)
        pix = page.get_pixmap(matrix=mat, clip=clip)

        # Convert to PIL Image for Tesseract
        img = Image.open(io.BytesIO(pix.tobytes("png")))

        try:
            text = pytesseract.image_to_string(img).upper()
        except Exception as e:
            logger.warning(f"OCR failed on page {page_num}: {e}")
            continue

        # Check for exhibit markers
        for marker in EXHIBIT_MARKERS:
            if marker in text:
                logger.info(f"Found exhibit marker '{marker}' on page {page_num + 1}")

                # First exhibit found marks end of body
                if split_points.body_end is None:
                    split_points.body_end = page_num

                exhibit = ExhibitInfo(
                    marker=marker,
                    start_page=page_num,
                    exhibit_type=_classify_exhibit_type(marker, text),
                )
                split_points.exhibits.append(exhibit)
                break  # Only match first marker per page

    doc.close()

    # Consolidate consecutive pages with same marker into single exhibits
    split_points.exhibits = _consolidate_exhibits(split_points.exhibits)

    # If no exhibits found, entire document is body
    if split_points.body_end is None:
        split_points.body_end = total_pages
        logger.info("No exhibits found - entire document is body")
    else:
        logger.info(
            f"Body ends at page {split_points.body_end + 1}, "
            f"found {len(split_points.exhibits)} exhibit(s)"
        )

    return split_points


def split_document(
    pdf_path: str,
    split_points: SplitPoints,
    output_dir: Optional[str] = None,
) -> SplitResult:
    """
    Split document into body and exhibit files based on split points.

    Args:
        pdf_path: Path to the original PDF file
        split_points: SplitPoints object from find_split_points()
        output_dir: Directory for output files (default: /tmp)

    Returns:
        SplitResult with paths to body and exhibit PDFs
    """
    if output_dir is None:
        output_dir = "/tmp"

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    file_hash = _generate_file_hash(pdf_path)
    doc = fitz.open(pdf_path)

    result = SplitResult(
        original_path=pdf_path,
        total_pages=len(doc),
    )

    # Extract body (pages 0 to body_end)
    if split_points.body_end and split_points.body_end > 0:
        body_doc = fitz.open()
        for page_num in range(split_points.body_end):
            body_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

        body_path = output_dir / f"body_{file_hash}.pdf"
        body_doc.save(str(body_path))
        body_doc.close()

        result.body_path = str(body_path)
        result.body_pages = split_points.body_end
        logger.info(f"Extracted body: {result.body_pages} pages -> {body_path}")
    else:
        # No body content (unusual case)
        logger.warning("No body content found in document")

    # Calculate end pages for each exhibit
    exhibits_with_ends = []
    for i, exhibit in enumerate(split_points.exhibits):
        # End is either next exhibit's start or end of document
        if i + 1 < len(split_points.exhibits):
            end_page = split_points.exhibits[i + 1].start_page - 1
        else:
            end_page = len(doc) - 1

        exhibit.end_page = end_page
        exhibit.page_count = end_page - exhibit.start_page + 1
        exhibits_with_ends.append(exhibit)

    # Extract each exhibit
    for i, exhibit in enumerate(exhibits_with_ends):
        exhibit_doc = fitz.open()

        for page_num in range(exhibit.start_page, exhibit.end_page + 1):
            exhibit_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

        exhibit_path = output_dir / f"exhibit_{i}_{file_hash}.pdf"
        exhibit_doc.save(str(exhibit_path))
        exhibit_doc.close()

        exhibit.path = str(exhibit_path)
        result.exhibits.append(exhibit)

        logger.info(
            f"Extracted exhibit {i + 1} ({exhibit.marker}): "
            f"{exhibit.page_count} pages -> {exhibit_path}"
        )

    doc.close()
    return result


def process_document(
    pdf_path: str,
    output_dir: Optional[str] = None,
    scan_pages: int = 25,
) -> SplitResult:
    """
    Convenience function to find split points and split document in one call.

    Args:
        pdf_path: Path to the PDF file
        output_dir: Directory for output files (default: /tmp)
        scan_pages: Maximum number of pages to scan for exhibits

    Returns:
        SplitResult with paths to body and exhibit PDFs
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    split_points = find_split_points(pdf_path, scan_pages=scan_pages)
    return split_document(pdf_path, split_points, output_dir=output_dir)


def cleanup_temp_files(result: SplitResult) -> None:
    """
    Remove temporary split files.

    Args:
        result: SplitResult from split_document()
    """
    if result.body_path and os.path.exists(result.body_path):
        os.remove(result.body_path)
        logger.debug(f"Removed: {result.body_path}")

    for exhibit in result.exhibits:
        if exhibit.path and os.path.exists(exhibit.path):
            os.remove(exhibit.path)
            logger.debug(f"Removed: {exhibit.path}")


# CLI interface for testing
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: python splitter.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    print(f"\nProcessing: {pdf_path}")
    print("-" * 60)

    try:
        result = process_document(pdf_path)

        print(f"\nTotal pages: {result.total_pages}")
        print(f"Body pages: {result.body_pages}")
        print(f"Body path: {result.body_path}")
        print(f"\nExhibits found: {len(result.exhibits)}")

        for i, exhibit in enumerate(result.exhibits):
            print(f"\n  Exhibit {i + 1}:")
            print(f"    Marker: {exhibit.marker}")
            print(f"    Type: {exhibit.exhibit_type}")
            print(f"    Pages: {exhibit.start_page + 1} - {exhibit.end_page + 1}")
            print(f"    Page count: {exhibit.page_count}")
            print(f"    Path: {exhibit.path}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
