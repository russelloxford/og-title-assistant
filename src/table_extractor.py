"""
Table Extractor Module

Extracts tabular data from exhibit PDFs using AWS Textract.
Designed for processing lease schedules, tract lists, and other
tabular exhibits in oil & gas documents.

Cost: ~$0.015 per page (vs $0.15 for Claude Vision)
Accuracy: 90%+ on typed tabular data
"""

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger(__name__)

# Column name mappings for common lease schedule formats
COLUMN_MAPPINGS = {
    "lessor": ["lessor", "grantor", "owner", "mineral owner", "landowner"],
    "lessee": ["lessee", "grantee", "operator", "oil company"],
    "recording": [
        "recording",
        "book/page",
        "bk/pg",
        "doc no",
        "instrument",
        "recorded",
        "filing",
        "book",
        "page",
    ],
    "lands": [
        "lands",
        "legal",
        "description",
        "property",
        "tract",
        "location",
        "land description",
    ],
    "date": ["date", "effective", "execution", "dated", "lease date"],
    "county": ["county", "parish"],
    "state": ["state", "st"],
    "acres": ["acres", "acreage", "gross acres", "net acres"],
    "interest": ["interest", "wi", "working interest", "nri", "net revenue"],
}


@dataclass
class TableCell:
    """A single cell in a table."""

    text: str
    row_index: int
    column_index: int
    confidence: float = 0.0


@dataclass
class ExtractedTable:
    """A table extracted from a document."""

    page_number: int
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class LeaseRecord:
    """A parsed lease record from a schedule."""

    lessor: Optional[str] = None
    lessee: Optional[str] = None
    recording_info: Optional[str] = None
    lands: Optional[str] = None
    date: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    acres: Optional[str] = None
    interest: Optional[str] = None
    raw_row: list[str] = field(default_factory=list)


@dataclass
class TableExtractionResult:
    """Result of table extraction from a document."""

    tables: list[ExtractedTable] = field(default_factory=list)
    lease_records: list[LeaseRecord] = field(default_factory=list)
    page_count: int = 0
    source_path: str = ""


def _get_s3_client():
    """Get S3 client with credentials from environment."""
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


def _get_textract_client():
    """Get Textract client with credentials from environment."""
    return boto3.client(
        "textract",
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


def _upload_to_s3(pdf_path: str, bucket: str, key: Optional[str] = None) -> str:
    """
    Upload PDF to S3 for Textract processing.

    Args:
        pdf_path: Local path to PDF file
        bucket: S3 bucket name
        key: Optional S3 key (generates UUID-based key if not provided)

    Returns:
        S3 key of uploaded file
    """
    if key is None:
        key = f"textract-temp/{uuid.uuid4()}.pdf"

    s3 = _get_s3_client()
    logger.info(f"Uploading {pdf_path} to s3://{bucket}/{key}")

    s3.upload_file(pdf_path, bucket, key)
    return key


def _delete_from_s3(bucket: str, key: str) -> None:
    """Delete file from S3."""
    s3 = _get_s3_client()
    try:
        s3.delete_object(Bucket=bucket, Key=key)
        logger.debug(f"Deleted s3://{bucket}/{key}")
    except ClientError as e:
        logger.warning(f"Failed to delete s3://{bucket}/{key}: {e}")


def _start_textract_job(bucket: str, key: str) -> str:
    """
    Start async Textract document analysis job.

    Args:
        bucket: S3 bucket name
        key: S3 object key

    Returns:
        Job ID for polling
    """
    textract = _get_textract_client()

    response = textract.start_document_analysis(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
        FeatureTypes=["TABLES"],
    )

    job_id = response["JobId"]
    logger.info(f"Started Textract job: {job_id}")
    return job_id


def _poll_textract_job(
    job_id: str,
    poll_interval: int = 5,
    max_wait: int = 300,
) -> dict:
    """
    Poll Textract job until completion.

    Args:
        job_id: Textract job ID
        poll_interval: Seconds between polls
        max_wait: Maximum seconds to wait

    Returns:
        Complete Textract response with all blocks

    Raises:
        TimeoutError: If job doesn't complete in time
        RuntimeError: If job fails
    """
    textract = _get_textract_client()
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed > max_wait:
            raise TimeoutError(f"Textract job {job_id} timed out after {max_wait}s")

        result = textract.get_document_analysis(JobId=job_id)
        status = result["JobStatus"]

        if status == "SUCCEEDED":
            logger.info(f"Textract job {job_id} completed in {elapsed:.1f}s")
            break
        elif status == "FAILED":
            raise RuntimeError(
                f"Textract job failed: {result.get('StatusMessage', 'Unknown error')}"
            )

        logger.debug(f"Job status: {status}, waiting {poll_interval}s...")
        time.sleep(poll_interval)

    # CRITICAL: Collect ALL blocks from paginated responses
    # Multi-page exhibits may return results across many pages
    all_blocks = result.get("Blocks", [])
    next_token = result.get("NextToken")

    while next_token:
        logger.debug("Fetching additional result pages...")
        result = textract.get_document_analysis(JobId=job_id, NextToken=next_token)
        all_blocks.extend(result.get("Blocks", []))
        next_token = result.get("NextToken")

    logger.info(f"Retrieved {len(all_blocks)} total blocks")

    return {
        "Blocks": all_blocks,
        "DocumentMetadata": result.get("DocumentMetadata", {}),
    }


def _parse_textract_tables(textract_response: dict) -> list[ExtractedTable]:
    """
    Parse Textract response to extract tables.

    Args:
        textract_response: Complete Textract response

    Returns:
        List of ExtractedTable objects
    """
    blocks = textract_response.get("Blocks", [])

    # Build block lookup maps
    block_map = {block["Id"]: block for block in blocks}

    # Find all TABLE blocks
    table_blocks = [b for b in blocks if b["BlockType"] == "TABLE"]
    logger.info(f"Found {len(table_blocks)} tables")

    tables = []

    for table_block in table_blocks:
        page_number = table_block.get("Page", 1)
        confidence = table_block.get("Confidence", 0.0)

        # Get cell relationships
        cell_ids = []
        for rel in table_block.get("Relationships", []):
            if rel["Type"] == "CHILD":
                cell_ids.extend(rel["Ids"])

        # Parse cells into grid
        cells = []
        for cell_id in cell_ids:
            cell_block = block_map.get(cell_id)
            if cell_block and cell_block["BlockType"] == "CELL":
                row_idx = cell_block.get("RowIndex", 1) - 1  # Convert to 0-indexed
                col_idx = cell_block.get("ColumnIndex", 1) - 1

                # Get cell text from child WORD blocks
                cell_text = _get_block_text(cell_block, block_map)
                cell_confidence = cell_block.get("Confidence", 0.0)

                cells.append(
                    TableCell(
                        text=cell_text,
                        row_index=row_idx,
                        column_index=col_idx,
                        confidence=cell_confidence,
                    )
                )

        # Convert cells to row/column grid
        if not cells:
            continue

        max_row = max(c.row_index for c in cells) + 1
        max_col = max(c.column_index for c in cells) + 1

        grid = [["" for _ in range(max_col)] for _ in range(max_row)]
        for cell in cells:
            grid[cell.row_index][cell.column_index] = cell.text

        # First row is typically headers
        headers = grid[0] if grid else []
        data_rows = grid[1:] if len(grid) > 1 else []

        tables.append(
            ExtractedTable(
                page_number=page_number,
                headers=headers,
                rows=data_rows,
                confidence=confidence,
            )
        )

    return tables


def _get_block_text(block: dict, block_map: dict) -> str:
    """Extract text from a block by traversing WORD children."""
    text_parts = []

    for rel in block.get("Relationships", []):
        if rel["Type"] == "CHILD":
            for child_id in rel["Ids"]:
                child = block_map.get(child_id)
                if child and child["BlockType"] == "WORD":
                    text_parts.append(child.get("Text", ""))

    return " ".join(text_parts)


def _map_columns(headers: list[str]) -> dict[str, int]:
    """
    Map standard field names to column indices based on header text.

    Args:
        headers: List of header strings from table

    Returns:
        Dict mapping field names to column indices
    """
    column_map = {}
    headers_lower = [h.lower().strip() for h in headers]

    for field_name, variations in COLUMN_MAPPINGS.items():
        for i, header in enumerate(headers_lower):
            if any(v in header for v in variations):
                column_map[field_name] = i
                break

    logger.debug(f"Column mapping: {column_map}")
    return column_map


def parse_lease_schedule(tables: list[ExtractedTable]) -> list[LeaseRecord]:
    """
    Parse extracted tables into structured lease records.

    Args:
        tables: List of ExtractedTable objects

    Returns:
        List of LeaseRecord objects
    """
    lease_records = []

    for table in tables:
        if not table.headers:
            logger.debug(f"Skipping table on page {table.page_number} - no headers")
            continue

        column_map = _map_columns(table.headers)

        if not column_map:
            logger.debug(
                f"Skipping table on page {table.page_number} - "
                "no recognized columns"
            )
            continue

        for row in table.rows:
            # Skip empty or too-short rows
            if len(row) < 2 or all(not cell.strip() for cell in row):
                continue

            record = LeaseRecord(raw_row=row)

            # Extract fields based on column mapping
            if "lessor" in column_map and column_map["lessor"] < len(row):
                record.lessor = row[column_map["lessor"]].strip() or None

            if "lessee" in column_map and column_map["lessee"] < len(row):
                record.lessee = row[column_map["lessee"]].strip() or None

            if "recording" in column_map and column_map["recording"] < len(row):
                record.recording_info = row[column_map["recording"]].strip() or None

            if "lands" in column_map and column_map["lands"] < len(row):
                record.lands = row[column_map["lands"]].strip() or None

            if "date" in column_map and column_map["date"] < len(row):
                record.date = row[column_map["date"]].strip() or None

            if "county" in column_map and column_map["county"] < len(row):
                record.county = row[column_map["county"]].strip() or None

            if "state" in column_map and column_map["state"] < len(row):
                record.state = row[column_map["state"]].strip() or None

            if "acres" in column_map and column_map["acres"] < len(row):
                record.acres = row[column_map["acres"]].strip() or None

            if "interest" in column_map and column_map["interest"] < len(row):
                record.interest = row[column_map["interest"]].strip() or None

            # Only add if we got some meaningful data
            if record.lessor or record.lands or record.recording_info:
                lease_records.append(record)

    logger.info(f"Parsed {len(lease_records)} lease records from {len(tables)} tables")
    return lease_records


def extract_tables(
    pdf_path: str,
    bucket: Optional[str] = None,
    cleanup: bool = True,
) -> TableExtractionResult:
    """
    Extract tables from a PDF using AWS Textract.

    Args:
        pdf_path: Path to the PDF file
        bucket: S3 bucket for temporary storage (uses TEXTRACT_S3_BUCKET env var if not provided)
        cleanup: Whether to delete S3 file after processing

    Returns:
        TableExtractionResult with tables and parsed lease records

    Raises:
        FileNotFoundError: If PDF file not found
        ValueError: If no S3 bucket configured
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if bucket is None:
        bucket = os.environ.get("TEXTRACT_S3_BUCKET")
        if not bucket:
            raise ValueError(
                "No S3 bucket specified. Set TEXTRACT_S3_BUCKET environment variable "
                "or pass bucket parameter."
            )

    logger.info(f"Extracting tables from: {pdf_path}")

    # Upload to S3
    s3_key = _upload_to_s3(pdf_path, bucket)

    try:
        # Start and poll Textract job
        job_id = _start_textract_job(bucket, s3_key)
        response = _poll_textract_job(job_id)

        # Parse tables
        tables = _parse_textract_tables(response)

        # Parse lease records
        lease_records = parse_lease_schedule(tables)

        # Get page count
        page_count = response.get("DocumentMetadata", {}).get("Pages", 0)

        return TableExtractionResult(
            tables=tables,
            lease_records=lease_records,
            page_count=page_count,
            source_path=pdf_path,
        )

    finally:
        if cleanup:
            _delete_from_s3(bucket, s3_key)


def tables_to_dict(result: TableExtractionResult) -> dict:
    """Convert TableExtractionResult to dictionary for serialization."""
    return {
        "page_count": result.page_count,
        "source_path": result.source_path,
        "table_count": len(result.tables),
        "lease_record_count": len(result.lease_records),
        "tables": [
            {
                "page_number": t.page_number,
                "headers": t.headers,
                "rows": t.rows,
                "confidence": t.confidence,
            }
            for t in result.tables
        ],
        "lease_records": [
            {
                "lessor": r.lessor,
                "lessee": r.lessee,
                "recording_info": r.recording_info,
                "lands": r.lands,
                "date": r.date,
                "county": r.county,
                "state": r.state,
                "acres": r.acres,
                "interest": r.interest,
            }
            for r in result.lease_records
        ],
    }


# CLI interface for testing
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if len(sys.argv) < 2:
        print("Usage: python table_extractor.py <pdf_path> [bucket]")
        print("\nEnvironment variables:")
        print("  AWS_ACCESS_KEY_ID - AWS access key")
        print("  AWS_SECRET_ACCESS_KEY - AWS secret key")
        print("  AWS_DEFAULT_REGION - AWS region (default: us-east-1)")
        print("  TEXTRACT_S3_BUCKET - S3 bucket for temp storage")
        sys.exit(1)

    pdf_path = sys.argv[1]
    bucket = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"\nExtracting tables from: {pdf_path}")
    print("-" * 60)

    try:
        result = extract_tables(pdf_path, bucket=bucket)

        print(f"\nPages processed: {result.page_count}")
        print(f"Tables found: {len(result.tables)}")
        print(f"Lease records parsed: {len(result.lease_records)}")

        for i, table in enumerate(result.tables):
            print(f"\nTable {i + 1} (Page {table.page_number}):")
            print(f"  Headers: {table.headers}")
            print(f"  Rows: {len(table.rows)}")
            print(f"  Confidence: {table.confidence:.2f}")

        if result.lease_records:
            print(f"\nSample lease records (first 5):")
            for record in result.lease_records[:5]:
                print(f"  - Lessor: {record.lessor}")
                print(f"    Lands: {record.lands}")
                print(f"    Recording: {record.recording_info}")
                print()

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
