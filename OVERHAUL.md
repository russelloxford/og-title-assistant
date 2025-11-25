# RealPropAI Complete System Overhaul
## A Ground-Up Redesign for Scanned Document Processing

**Created:** 2025-01-25
**Status:** Proposal
**Version:** 3.0

---

## Executive Summary

This document proposes a **complete architectural overhaul** of the Real Property Document Analyzer to address fundamental limitations in the current system. The redesign is driven by three critical realities:

1. **All uploaded PDFs are scanned images** - Any embedded text layers are unreliable and must be ignored
2. **Large documents with exhibits are the norm** - 50-400 page assignments with hundreds of lease schedules are common
3. **Token limits make single-pass AI extraction impossible** - Claude's 16K output token limit cannot handle 150+ tract extractions

### Proposed New Stack

| Component | Current | Proposed | Rationale |
|-----------|---------|----------|-----------|
| **Backend Runtime** | Node.js/Firebase Functions | Python/Cloud Run | Better ML/OCR ecosystem |
| **OCR (Quick Scan)** | pdf-parse (unreliable) | Tesseract (local) | Free, fast, reliable for splitting decisions |
| **OCR (Tables)** | Claude Vision | AWS Textract | Purpose-built for tabular data extraction |
| **AI Extraction** | Claude (single-pass) | Claude (targeted) | Only process document body, not exhibits |
| **Database** | Firestore (document) | Neo4j Aura (graph) | Native chain of title modeling |
| **Frontend** | React SPA | Streamlit (MVP) → React | Faster iteration, attorney feedback |

### Expected Outcomes

- **100% OCR reliability** - Treat all documents as images, no text layer assumptions
- **95%+ extraction completeness** - Split body from exhibits, process appropriately
- **70% cost reduction** - Textract for tables is cheaper than Claude Vision
- **Native chain of title** - Graph queries replace complex recursive Firestore queries

---

## Part 1: The Problem Statement

### 1.1 Current Architecture Failures

#### Failure #1: Text Layer Assumptions

The current system uses `pdf-parse` as the primary OCR method, falling back to Claude Vision only when text quality is poor. This is fundamentally flawed because:

```
ASSUMPTION: Some PDFs have usable embedded text
REALITY: ALL documents are scanned images; any text layers are:
  - OCR artifacts from scanning software (often incorrect)
  - Overlays added by county recorders (incomplete)
  - Searchable PDF conversions (unreliable for legal precision)

CONSEQUENCE: 30-40% of documents get incorrect extractions due to bad text layers
```

**Evidence from production:**
- Documents with "high quality" pdf-parse text still have party name errors
- Legal descriptions are garbled due to OCR artifacts in text layers
- Recording info extraction fails on documents with overlay text

#### Failure #2: Single-Pass Extraction

The current pipeline sends entire documents to Claude for extraction:

```
CURRENT FLOW:
  400-page PDF → Claude Vision → Extract everything → JSON output

PROBLEM:
  - Claude's output limit: 16,384 tokens
  - 150 leases × ~100 tokens each = 15,000 tokens (just for lease data)
  - Plus parties, dates, legal descriptions = 20,000+ tokens needed
  - Result: Truncated output, 15% completeness on large documents
```

**The multi-stage extraction attempts (stagedExtractor.ts, hybridExtractor.ts) are band-aids on a fundamentally broken approach.**

#### Failure #3: Wrong Tool for Tables

Oil & gas exhibits are predominantly **tabular data**:

```
EXHIBIT A - SCHEDULE OF LEASES
┌──────────────┬──────────────┬─────────────┬──────────────────────┐
│ Lessor       │ Lessee       │ Recording   │ Lands                │
├──────────────┼──────────────┼─────────────┼──────────────────────┤
│ Smith, John  │ Acme Oil Co  │ Bk 450/Pg 1 │ NW/4 Sec 15-154N-97W │
│ Jones, Mary  │ Acme Oil Co  │ Bk 450/Pg 5 │ SW/4 Sec 15-154N-97W │
│ ... (148 more rows)                                              │
└──────────────┴──────────────┴─────────────┴──────────────────────┘
```

**Claude Vision is the wrong tool for this:**
- LLMs process text sequentially, not spatially
- Table structure often lost in extraction
- Expensive: $0.15+ per 30 pages
- No native table detection

**AWS Textract is purpose-built for tables:**
- Preserves row/column structure
- Returns structured JSON with cell coordinates
- Cheaper: ~$0.015 per page for tables
- 90%+ accuracy on typed tabular data

#### Failure #4: Document Database for Graph Data

Chain of title is inherently a **graph problem**:

```
          Surface Owner (1900)
                 │
         ┌───────┴───────┐
    Deed (1920)     Deed (1925)
         │               │
    Owner A         Owner B
         │               │
    Lease (1950)   Lease (1955)
         │               │
   Assignment      Assignment
         │               │
    Current WI     Current WI
```

**Firestore limitations:**
- Requires multiple queries to traverse chain
- Recursive queries are expensive and slow
- No native path-finding algorithms
- Complex aggregations require Cloud Functions

**Neo4j advantages:**
- Single Cypher query traces entire chain
- Built-in shortest path algorithms
- Native support for ownership percentage calculations
- Graph visualization out of the box

### 1.2 The Documents We Actually Process

Understanding the actual document types is critical:

| Document Type | Pages | Structure | Current Success | Key Challenge |
|--------------|-------|-----------|-----------------|---------------|
| **Simple Deed** | 2-5 | Narrative | 95% | None |
| **Mortgage** | 10-30 | Narrative + Exhibits | 70% | Exhibit A legal descriptions |
| **Oil & Gas Lease** | 3-8 | Narrative + Addendum | 85% | Addendum terms |
| **Assignment** | 5-400 | 5pg body + 395pg exhibits | **15%** | Exhibit tables |
| **Partial Release** | 3-20 | Narrative + Schedule | 60% | Schedule parsing |
| **Ratification** | 2-10 | Narrative | 90% | None |

**The critical insight:** 80% of extraction failures are on **Assignment documents** with large exhibit schedules.

---

## Part 2: The New Architecture

### 2.1 High-Level Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                               │
│                    (Streamlit MVP → React)                          │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      CLOUD RUN ORCHESTRATOR                          │
│                         (Python 3.11)                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │  Splitter   │  │  Extractor  │  │  Graph      │                  │
│  │  Service    │  │  Service    │  │  Builder    │                  │
│  └─────────────┘  └─────────────┘  └─────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   Tesseract  │   │    Claude    │   │   Neo4j      │
│   (Local)    │   │   (Body)     │   │   Aura       │
└──────────────┘   └──────────────┘   └──────────────┘
                           │
                   ┌───────┴───────┐
                   ▼               ▼
            ┌──────────┐   ┌──────────────┐
            │ Textract │   │ Cloud Storage│
            │ (Tables) │   │   (PDFs)     │
            └──────────┘   └──────────────┘
```

### 2.2 The "Zero-Cost" Intelligent Splitter

**Purpose:** Identify document structure before expensive processing

**Key Innovation:** Process only the **top 20% of each page** (where headers/titles appear) using local OCR to make splitting decisions.

```python
# splitter.py - Core splitting logic

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io

EXHIBIT_MARKERS = [
    "EXHIBIT A", "EXHIBIT B", "EXHIBIT C",
    "SCHEDULE OF LEASES", "SCHEDULE 1", "SCHEDULE A",
    "ATTACHED HERETO", "LEASE SCHEDULE",
    "DESCRIPTION OF LANDS", "LEGAL DESCRIPTION"
]

def find_split_points(pdf_path: str) -> dict:
    """
    Scan top 20% of first 25 pages to identify document structure.
    Cost: $0 (local Tesseract)
    Time: ~2-3 seconds for 400-page document
    """
    doc = fitz.open(pdf_path)
    split_points = {
        "body_end": None,
        "exhibits": []
    }

    # Only scan first 25 pages (exhibits start within first 20 typically)
    scan_pages = min(25, len(doc))

    for page_num in range(scan_pages):
        page = doc[page_num]

        # Render only top 20% of page as image
        clip = fitz.Rect(0, 0, page.rect.width, page.rect.height * 0.20)
        mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR
        pix = page.get_pixmap(matrix=mat, clip=clip)

        # Convert to PIL Image for Tesseract
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(img).upper()

        # Check for exhibit markers
        for marker in EXHIBIT_MARKERS:
            if marker in text:
                if split_points["body_end"] is None:
                    split_points["body_end"] = page_num

                split_points["exhibits"].append({
                    "marker": marker,
                    "start_page": page_num,
                    "type": classify_exhibit_type(marker, text)
                })
                break

    # If no exhibits found, entire document is body
    if split_points["body_end"] is None:
        split_points["body_end"] = len(doc)

    doc.close()
    return split_points


def classify_exhibit_type(marker: str, text: str) -> str:
    """Classify exhibit type for routing to appropriate processor"""
    if "SCHEDULE" in marker or "LEASE" in text:
        return "table"  # Route to Textract
    elif "LEGAL DESCRIPTION" in text or "LANDS" in marker:
        return "legal_descriptions"  # Route to Claude
    elif "PLAT" in text or "MAP" in text:
        return "image"  # Skip or specialized processing
    else:
        return "narrative"  # Route to Claude


def split_document(pdf_path: str, split_points: dict) -> dict:
    """
    Split document into body and exhibit files.
    Returns paths to temporary split files.
    """
    doc = fitz.open(pdf_path)
    output = {"body": None, "exhibits": []}

    # Extract body (pages 0 to body_end)
    body_doc = fitz.open()
    for page_num in range(split_points["body_end"]):
        body_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

    body_path = f"/tmp/body_{hash(pdf_path)}.pdf"
    body_doc.save(body_path)
    body_doc.close()
    output["body"] = body_path

    # Extract each exhibit
    for i, exhibit in enumerate(split_points["exhibits"]):
        start = exhibit["start_page"]
        # End is either next exhibit or end of document
        if i + 1 < len(split_points["exhibits"]):
            end = split_points["exhibits"][i + 1]["start_page"] - 1
        else:
            end = len(doc) - 1

        exhibit_doc = fitz.open()
        for page_num in range(start, end + 1):
            exhibit_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

        exhibit_path = f"/tmp/exhibit_{i}_{hash(pdf_path)}.pdf"
        exhibit_doc.save(exhibit_path)
        exhibit_doc.close()

        output["exhibits"].append({
            **exhibit,
            "path": exhibit_path,
            "page_count": end - start + 1
        })

    doc.close()
    return output
```

### 2.3 Dual-Track Extraction Pipeline

**Track 1: Document Body → Claude Sonnet**

The document body (typically 3-15 pages) contains:
- Parties (Grantor/Grantee/Assignor/Assignee)
- Execution and recording dates
- Interest conveyed/reserved
- Clauses and terms
- Main legal description (if not in exhibits)

```python
# body_extractor.py - Claude extraction for document body

from anthropic import Anthropic
import json

client = Anthropic()

BODY_EXTRACTION_PROMPT = """
You are analyzing the BODY of an oil & gas document (NOT the exhibits).

Extract ONLY:
1. Document type and title
2. All parties (grantor/grantee with roles)
3. Execution date, recording date, filing date
4. Recording info (book, page, document number, county, state)
5. Interest conveyed and interest reserved
6. Key clauses (Pugh, depth severance, continuous development, etc.)
7. Primary term and royalty (for leases)
8. References to exhibits (note what each exhibit contains)

DO NOT attempt to extract:
- Individual lease schedules (in exhibits)
- Long lists of legal descriptions (in exhibits)
- Tract-by-tract breakdowns

Return JSON in this exact format:
{
  "documentType": "Assignment of Oil and Gas Leases",
  "parties": {
    "grantors": [{"name": "...", "address": "..."}],
    "grantees": [{"name": "...", "address": "..."}]
  },
  "dates": {
    "execution": "YYYY-MM-DD",
    "recording": "YYYY-MM-DD",
    "effective": "YYYY-MM-DD"
  },
  "recordingInfo": {
    "book": "...",
    "page": "...",
    "documentNumber": "...",
    "county": "...",
    "state": "..."
  },
  "interests": {
    "conveyed": "All of Assignor's right, title and interest...",
    "reserved": "None / 1/16th overriding royalty..."
  },
  "clauses": {
    "pughClause": true/false,
    "depthSeverance": {...},
    "continuousDevelopment": {...},
    "otherClauses": [...]
  },
  "exhibitReferences": [
    {"name": "Exhibit A", "description": "Schedule of 150 leases"},
    {"name": "Exhibit B", "description": "Legal descriptions"}
  ],
  "confidence": {
    "overall": 0.95,
    "parties": 0.98,
    "dates": 0.92
  }
}
"""

def extract_body(pdf_path: str) -> dict:
    """
    Extract structured data from document body using Claude.
    Expects body PDF (3-15 pages), NOT full document.
    """
    # Read PDF as base64
    with open(pdf_path, "rb") as f:
        pdf_base64 = base64.b64encode(f.read()).decode()

    response = client.messages.create(
        model="claude-sonnet-4-5-20250514",
        max_tokens=4096,  # Body extraction needs ~2K tokens max
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_base64
                    }
                },
                {
                    "type": "text",
                    "text": BODY_EXTRACTION_PROMPT
                }
            ]
        }]
    )

    return json.loads(response.content[0].text)
```

**Track 2: Exhibit Tables → AWS Textract**

Lease schedules and tract lists are tabular data:

```python
# table_extractor.py - AWS Textract for exhibit tables

import boto3
from amazon_textract_response_parser import TextractDocument
import time

textract = boto3.client('textract', region_name='us-east-1')
s3 = boto3.client('s3')

def extract_tables(pdf_path: str, bucket: str) -> list:
    """
    Extract tabular data from exhibit PDF using AWS Textract.

    Cost: ~$0.015 per page (vs $0.15 for Claude Vision)
    Accuracy: 90%+ on typed tabular data

    IMPORTANT: Multi-page documents return paginated results.
    We must follow NextToken to get ALL blocks.
    """
    # Upload to S3 (Textract requires S3 for multi-page)
    key = f"textract-temp/{hash(pdf_path)}.pdf"
    s3.upload_file(pdf_path, bucket, key)

    # Start async analysis
    response = textract.start_document_analysis(
        DocumentLocation={
            'S3Object': {
                'Bucket': bucket,
                'Name': key
            }
        },
        FeatureTypes=['TABLES']
    )
    job_id = response['JobId']

    # Poll for completion (initial status check only)
    while True:
        result = textract.get_document_analysis(JobId=job_id)
        status = result['JobStatus']

        if status == 'SUCCEEDED':
            break
        elif status == 'FAILED':
            raise Exception(f"Textract failed: {result.get('StatusMessage')}")

        time.sleep(5)

    # CRITICAL: Collect ALL blocks from paginated responses
    # Multi-page exhibits may return results across many pages
    all_blocks = result.get('Blocks', [])
    next_token = result.get('NextToken')

    while next_token:
        result = textract.get_document_analysis(
            JobId=job_id,
            NextToken=next_token
        )
        all_blocks.extend(result.get('Blocks', []))
        next_token = result.get('NextToken')

    # Build complete response for parser
    complete_response = {
        'Blocks': all_blocks,
        'DocumentMetadata': result.get('DocumentMetadata', {})
    }

    # Parse results with ALL blocks
    doc = TextractDocument(complete_response)
    tables = []

    for page in doc.pages:
        for table in page.tables:
            parsed_table = {
                "page": page.page_number,
                "rows": []
            }

            for row in table.rows:
                parsed_row = [cell.text for cell in row.cells]
                parsed_table["rows"].append(parsed_row)

            # Identify column headers (first row usually)
            if parsed_table["rows"]:
                parsed_table["headers"] = parsed_table["rows"][0]
                parsed_table["data"] = parsed_table["rows"][1:]

            tables.append(parsed_table)

    # Cleanup S3
    s3.delete_object(Bucket=bucket, Key=key)

    return tables


def parse_lease_schedule(tables: list) -> list:
    """
    Convert raw Textract tables into structured lease records.
    Handles common column name variations.
    """
    COLUMN_MAPPINGS = {
        "lessor": ["lessor", "grantor", "owner", "mineral owner"],
        "lessee": ["lessee", "grantee", "operator"],
        "recording": ["recording", "book/page", "bk/pg", "doc no", "instrument"],
        "lands": ["lands", "legal", "description", "property", "tract"],
        "date": ["date", "effective", "execution"],
        "county": ["county", "parish"],
        "state": ["state", "st"]
    }

    leases = []

    for table in tables:
        if not table.get("headers"):
            continue

        # Map columns
        column_map = {}
        headers_lower = [h.lower().strip() for h in table["headers"]]

        for field, variations in COLUMN_MAPPINGS.items():
            for i, header in enumerate(headers_lower):
                if any(v in header for v in variations):
                    column_map[field] = i
                    break

        # Extract data rows
        for row in table["data"]:
            if len(row) < 2:
                continue

            lease = {}
            for field, col_idx in column_map.items():
                if col_idx < len(row):
                    lease[field] = row[col_idx].strip()

            if lease.get("lessor") or lease.get("lands"):
                leases.append(lease)

    return leases
```

### 2.4 Legal Description Normalization

All legal descriptions must be normalized for graph queries:

```python
# normalizer.py - Legal description standardization

import re

def generate_spatial_key(legal_desc: str) -> str:
    """
    Convert legal description to normalized spatial key.
    Format: {STATE}-{COUNTY}-{SECTION}-{TOWNSHIP}-{RANGE}[-{ALIQUOT}]

    Examples:
      "NW/4 of Section 15, T154N, R97W, Williams County, ND"
      → "ND-WILLIAMS-15-154N-97W-NW4"

      "Sec 14-3N-4W, Garfield County, OK"
      → "OK-GARFIELD-14-3N-4W"
    """
    text = legal_desc.upper()

    # Extract state (2-letter or full name)
    state = None
    STATE_PATTERNS = [
        r'\b(ND|NORTH DAKOTA)\b',
        r'\b(SD|SOUTH DAKOTA)\b',
        r'\b(MT|MONTANA)\b',
        r'\b(OK|OKLAHOMA)\b',
        r'\b(TX|TEXAS)\b',
        r'\b(WY|WYOMING)\b',
        r'\b(CO|COLORADO)\b',
        r'\b(NM|NEW MEXICO)\b',
        r'\b(KS|KANSAS)\b',
        r'\b(NE|NEBRASKA)\b',
    ]
    STATE_ABBREV = {
        "NORTH DAKOTA": "ND", "SOUTH DAKOTA": "SD",
        "MONTANA": "MT", "OKLAHOMA": "OK", "TEXAS": "TX",
        "WYOMING": "WY", "COLORADO": "CO", "NEW MEXICO": "NM",
        "KANSAS": "KS", "NEBRASKA": "NE"
    }
    for pattern in STATE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            state = match.group(1)
            if len(state) > 2:
                state = STATE_ABBREV.get(state, state[:2])
            break

    # Extract county
    county = None
    county_match = re.search(r'(\w+)\s+COUNTY', text)
    if county_match:
        county = county_match.group(1)

    # Extract Section/Township/Range - multiple patterns
    section, township, range_dir = None, None, None

    # Pattern 1: "Section 15, Township 154 North, Range 97 West"
    p1 = re.search(r'SECTION\s+(\d+).*TOWNSHIP\s+(\d+)\s*(N|NORTH|S|SOUTH).*RANGE\s+(\d+)\s*(W|WEST|E|EAST)', text)
    if p1:
        section = p1.group(1)
        township = f"{p1.group(2)}{p1.group(3)[0]}"
        range_dir = f"{p1.group(4)}{p1.group(5)[0]}"

    # Pattern 2: "Sec 14-3N-4W" or "S14-T3N-R4W"
    if not section:
        p2 = re.search(r'S(?:EC(?:TION)?)?\s*(\d+)[-,\s]+T?(\d+[NS])[-,\s]+R?(\d+[EW])', text)
        if p2:
            section = p2.group(1)
            township = p2.group(2)
            range_dir = p2.group(3)

    # Pattern 3: "T154N-R97W, Section 15" (reversed order)
    if not section:
        p3 = re.search(r'T(\d+[NS])[-,\s]+R(\d+[EW]).*S(?:EC(?:TION)?)?\s*(\d+)', text)
        if p3:
            township = p3.group(1)
            range_dir = p3.group(2)
            section = p3.group(3)

    # Extract aliquot parts
    aliquot = None
    aliquot_patterns = [
        r'((?:N|S|E|W|NE|NW|SE|SW)[/\s]*(?:1/)?[24])',  # NW/4, S/2, etc.
        r'((?:NORTH|SOUTH|EAST|WEST)\s+(?:HALF|QUARTER))',
    ]
    for pattern in aliquot_patterns:
        match = re.search(pattern, text)
        if match:
            aliquot = match.group(1).replace("/", "").replace(" ", "")
            break

    # Build key
    if not all([state, county, section, township, range_dir]):
        return None  # Cannot normalize

    key = f"{state}-{county}-{section}-{township}-{range_dir}"
    if aliquot:
        key += f"-{aliquot}"

    return key


def normalize_party_name(name: str) -> str:
    """
    Normalize party names for matching.
    "Smith Oil, LLC" and "SMITH OIL LLC" → "SMITH OIL"
    """
    text = name.upper().strip()

    # Remove entity suffixes
    SUFFIXES = [
        r',?\s*LLC\.?$', r',?\s*L\.?L\.?C\.?$',
        r',?\s*INC\.?$', r',?\s*INCORPORATED$',
        r',?\s*LTD\.?$', r',?\s*LIMITED$',
        r',?\s*LP\.?$', r',?\s*L\.?P\.?$',
        r',?\s*CORP\.?$', r',?\s*CORPORATION$',
        r',?\s*CO\.?$', r',?\s*COMPANY$',
        r',?\s*ET\s+(AL|UX|VIR)\.?$',
    ]
    for suffix in SUFFIXES:
        text = re.sub(suffix, '', text)

    # Remove punctuation and extra spaces
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()

    return text
```

### 2.5 Neo4j Graph Model

**Schema Design:**

```cypher
// Node Types

// Party - Any entity that can own or convey interests
(:Party {
  id: string,           // UUID
  name: string,         // "SMITH OIL LLC"
  normalizedName: string, // "SMITH OIL"
  type: string,         // "individual" | "corporation" | "trust" | "estate"
  aliases: [string]     // Alternative names found in documents
})

// Instrument - A recorded document
(:Instrument {
  id: string,           // UUID
  documentType: string, // "Deed" | "Lease" | "Assignment" | etc.
  recordingInfo: string, // "Book 450, Page 123"
  documentNumber: string,
  county: string,
  state: string,
  executionDate: date,
  recordingDate: date,
  pdfUrl: string,
  extractionConfidence: float
})

// Tract - A specific parcel of land
(:Tract {
  id: string,           // UUID
  spatialKey: string,   // "ND-WILLIAMS-15-154N-97W-NW4"
  section: string,
  township: string,
  range: string,
  county: string,
  state: string,
  aliquotPart: string,  // "NW/4"
  acres: float,
  rawDescription: string
})

// Section - Aggregation of tracts
(:Section {
  sectionKey: string,   // "ND-WILLIAMS-15-154N-97W"
  section: string,
  township: string,
  range: string,
  county: string,
  state: string
})

// Relationships

// Ownership/Conveyance chain
(grantor:Party)-[:CONVEYED {
  instrumentId: string,
  interestType: string,    // "fee simple" | "mineral" | "leasehold"
  interestFraction: float, // 1.0, 0.5, 0.125, etc.
  reservations: string,
  date: date
}]->(grantee:Party)

// Instrument covers tract
(instrument:Instrument)-[:COVERS {
  interestConveyed: string,
  interestReserved: string
}]->(tract:Tract)

// Tract belongs to section
(tract:Tract)-[:IN_SECTION]->(section:Section)

// Document references another document
(instrument:Instrument)-[:REFERENCES {
  referenceType: string  // "assigns" | "releases" | "ratifies" | "amends"
}]->(referenced:Instrument)
```

**Key Queries:**

```cypher
// 1. Full chain of title for a tract
// Find all conveyances related to instruments covering this tract
MATCH (t:Tract {spatialKey: $tractKey})<-[:COVERS]-(i:Instrument)
WITH collect(i.id) AS instrumentIds
MATCH path = (original:Party)-[c:CONVEYED*]->(current:Party)
WHERE ALL(conv IN c WHERE conv.instrumentId IN instrumentIds)
RETURN path
ORDER BY length(path) DESC
LIMIT 1

// 2. All instruments affecting a section
MATCH (i:Instrument)-[:COVERS]->(t:Tract)-[:IN_SECTION]->(s:Section)
WHERE s.sectionKey = $sectionKey
RETURN i, t
ORDER BY i.recordingDate

// 3. Current ownership of a tract (calculate from chain)
// First find instruments covering this tract, then trace ownership through
// conveyances linked to those instruments
MATCH (t:Tract {spatialKey: $tractKey})<-[:COVERS]-(i:Instrument)
WITH t, collect(i.id) AS instrumentIds
MATCH path = (root:Party)-[conveyances:CONVEYED*]->(owner:Party)
WHERE ALL(c IN conveyances WHERE c.instrumentId IN instrumentIds)
  AND NOT EXISTS {
    MATCH (owner)-[c2:CONVEYED]->(:Party)
    WHERE c2.instrumentId IN instrumentIds
  }
RETURN owner.name AS currentOwner,
       reduce(interest = 1.0, c IN conveyances |
         interest * c.interestFraction) AS ownershipInterest

// 4. Find all leases for a party (as lessor)
// Uses instrumentId property to link conveyance to instrument
MATCH (p:Party {normalizedName: $partyName})-[c:CONVEYED]->(lessee:Party)
MATCH (i:Instrument {id: c.instrumentId})-[:COVERS]->(t:Tract)
WHERE i.documentType = 'Oil and Gas Lease'
RETURN i, t, lessee, c.interestFraction AS leasedInterest

// 5. Detect gaps in chain (missing link between sequential instruments)
MATCH (t:Tract {spatialKey: $tractKey})
MATCH (i1:Instrument)-[:COVERS]->(t)<-[:COVERS]-(i2:Instrument)
WHERE i1.recordingDate < i2.recordingDate
WITH t, i1, i2
// Check if there's a conveyance chain connecting the two instruments
OPTIONAL MATCH (grantee1:Party)<-[c1:CONVEYED]-(grantor2:Party)
WHERE c1.instrumentId = i1.id
WITH t, i1, i2, grantee1
OPTIONAL MATCH (grantor2:Party)-[c2:CONVEYED]->(grantee2:Party)
WHERE c2.instrumentId = i2.id AND grantor2 = grantee1
WITH i1, i2, grantee2
WHERE grantee2 IS NULL  // No connecting party found = gap
RETURN i1 AS priorInstrument, i2 AS laterInstrument
```

### 2.6 Processing Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DOCUMENT PROCESSING PIPELINE                      │
└─────────────────────────────────────────────────────────────────────┘

                         ┌──────────────┐
                         │  PDF Upload  │
                         └──────┬───────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  1. INTELLIGENT SPLIT  │ ← Tesseract (FREE)
                    │  - Scan top 20% of    │   ~2-3 seconds
                    │    pages 1-25         │
                    │  - Find exhibit markers│
                    │  - Classify sections  │
                    └───────────┬───────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
              ▼                 ▼                 ▼
     ┌────────────────┐ ┌─────────────┐ ┌─────────────────┐
     │  Body PDF      │ │ Exhibit A   │ │ Exhibit B       │
     │  (3-15 pages)  │ │ (table)     │ │ (legal desc)    │
     └───────┬────────┘ └──────┬──────┘ └───────┬─────────┘
             │                 │                 │
             ▼                 ▼                 ▼
     ┌────────────────┐ ┌─────────────┐ ┌─────────────────┐
     │  2a. CLAUDE    │ │ 2b. TEXTRACT│ │ 2c. CLAUDE      │
     │  Body Extract  │ │ Table Parse │ │ Legal Desc OCR  │
     │  ~$0.15        │ │ ~$0.015/pg  │ │ ~$0.05/10pg     │
     │  ~30 seconds   │ │ ~60 seconds │ │ ~20 seconds     │
     └───────┬────────┘ └──────┬──────┘ └───────┬─────────┘
             │                 │                 │
             └─────────────────┼─────────────────┘
                               │
                               ▼
                    ┌───────────────────────┐
                    │  3. NORMALIZATION     │
                    │  - Party name cleanup │
                    │  - Legal desc → key   │
                    │  - Date standardization│
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  4. GRAPH CONSTRUCTION │ ← Neo4j Aura
                    │  - Create/update nodes │
                    │  - Create relationships│
                    │  - Link to tracts     │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  5. VALIDATION        │
                    │  - Chain consistency  │
                    │  - Missing links      │
                    │  - Confidence scores  │
                    └───────────┬───────────┘
                                │
                                ▼
                         ┌──────────────┐
                         │  Complete!   │
                         └──────────────┘
```

---

## Part 3: Implementation Plan

### Phase 1: Environment & Splitter (Days 1-3)

**Goal:** Process any PDF and intelligently split body from exhibits for $0.

#### Day 1: Development Environment

```bash
# Create project structure
mkdir realprop-v3 && cd realprop-v3
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install \
  pymupdf \
  pytesseract \
  pillow \
  boto3 \
  anthropic \
  neo4j \
  pandas \
  streamlit \
  amazon-textract-response-parser

# Install Tesseract binary
# Mac: brew install tesseract
# Ubuntu: sudo apt-get install tesseract-ocr
# Windows: Download from UB-Mannheim GitHub
```

#### Day 2: Splitter Implementation

- Implement `splitter.py` (code above)
- Test with sample documents (small deed, large assignment)
- Tune exhibit markers for accuracy

#### Day 3: Integration Testing

- Process 10 diverse documents through splitter
- Validate split points are correct
- Measure timing (target: <3 seconds per document)

**Deliverable:** Working splitter that correctly identifies body/exhibit boundaries.

### Phase 2: Body Extraction (Days 4-5)

**Goal:** Extract document metadata from body using Claude.

#### Day 4: Claude Integration

- Implement `body_extractor.py` (code above)
- Craft and refine extraction prompt
- Add structured JSON validation

#### Day 5: Testing & Refinement

- Test on 20 document bodies
- Refine prompt for edge cases
- Add confidence scoring

**Deliverable:** Body extraction achieving 95%+ accuracy on metadata fields.

### Phase 3: Table Extraction (Days 6-7)

**Goal:** Extract lease schedules from exhibits using Textract.

#### Day 6: Textract Integration

- Implement `table_extractor.py` (code above)
- Set up S3 bucket with lifecycle rules (auto-delete after 1 day)
- Handle async polling

#### Day 7: Table Parsing

- Implement column mapping logic
- Handle variations in header names
- Add validation for extracted lease records

**Deliverable:** Table extraction achieving 90%+ accuracy on tabular exhibits.

### Phase 4: Normalization (Days 8-10)

**Goal:** Standardize all extracted data for graph storage.

#### Day 8: Legal Description Normalizer

- Implement `normalizer.py` (code above)
- Test all 5+ legal description formats
- Handle edge cases (partial sections, metes and bounds)

#### Day 9: Party Name Normalizer

- Implement party name cleaning
- Build alias detection (same entity, different names)
- Test with real party names from documents

#### Day 10: Integration

- Connect body + table extraction to normalizers
- Add unit tests for all patterns
- Document handling for unrecognized formats

**Deliverable:** All extracted data normalized with spatial keys and party identifiers.

### Phase 5: Graph Construction (Days 11-13)

**Goal:** Build chain of title in Neo4j.

#### Day 11: Neo4j Setup

- Create Neo4j Aura Free instance
- Define schema constraints and indexes
- Implement connection utilities

#### Day 12: Node Creation

- Implement Party, Instrument, Tract, Section node creation
- Handle upsert logic (create or update)
- Add deduplication by spatial key

#### Day 13: Relationship Creation

- Implement CONVEYED relationships with properties
- Implement COVERS relationships
- Add REFERENCES for document cross-references

**Deliverable:** Working graph construction from extracted data.

### Phase 6: Streamlit UI (Day 14)

**Goal:** Basic UI for attorney testing.

```python
# app.py - Streamlit MVP

import streamlit as st
from splitter import find_split_points, split_document
from body_extractor import extract_body
from table_extractor import extract_tables, parse_lease_schedule
from graph_builder import build_graph
from neo4j import GraphDatabase

st.set_page_config(page_title="RealProp v3", layout="wide")

# Sidebar - File Upload
st.sidebar.title("Document Upload")
uploaded_file = st.sidebar.file_uploader("Upload PDF", type=['pdf'])

# Main area
if uploaded_file:
    # Save to temp file
    temp_path = f"/tmp/{uploaded_file.name}"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # Processing log
    st.header("Processing Log")
    log = st.empty()

    with st.spinner("Processing..."):
        # Step 1: Split
        log.text("Finding split points...")
        splits = find_split_points(temp_path)
        st.success(f"Found {len(splits['exhibits'])} exhibits")

        # Step 2: Split files
        log.text("Splitting document...")
        files = split_document(temp_path, splits)

        # Step 3: Body extraction
        log.text("Extracting document body...")
        body_data = extract_body(files['body'])

        # Step 4: Table extraction
        tables_data = []
        for exhibit in files['exhibits']:
            if exhibit['type'] == 'table':
                log.text(f"Extracting tables from {exhibit['marker']}...")
                tables = extract_tables(exhibit['path'], "your-bucket")
                leases = parse_lease_schedule(tables)
                tables_data.extend(leases)

        # Step 5: Build graph
        log.text("Building graph...")
        build_graph(body_data, tables_data)

        st.success("Processing complete!")

    # Display results
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Document Metadata")
        st.json(body_data)

    with col2:
        st.subheader("Extracted Leases")
        if tables_data:
            st.dataframe(tables_data)
        else:
            st.info("No lease schedules found")

    # Chain visualization (if neo4j connected)
    st.subheader("Chain of Title")
    # Use streamlit-agraph or pyvis for visualization

else:
    st.info("Upload a PDF to begin processing")
```

**Deliverable:** Working Streamlit app that processes documents end-to-end.

---

## Part 4: Migration Strategy

### 4.1 Data Migration

**Phase 1: Export from Firestore**

```python
# migrate_firestore.py

import firebase_admin
from firebase_admin import firestore
import json

firebase_admin.initialize_app()
db = firestore.client()

def export_instruments():
    """Export all instruments to JSON for migration"""
    instruments = []
    for doc in db.collection('instruments').stream():
        data = doc.to_dict()
        data['_id'] = doc.id
        instruments.append(data)

    with open('instruments_export.json', 'w') as f:
        json.dump(instruments, f)

    return len(instruments)
```

**Phase 2: Import to Neo4j**

```python
# import_neo4j.py

from neo4j import GraphDatabase
import json

driver = GraphDatabase.driver(
    "neo4j+s://xxxx.databases.neo4j.io",
    auth=("neo4j", "password")
)

def import_instruments():
    with open('instruments_export.json') as f:
        instruments = json.load(f)

    with driver.session() as session:
        for inst in instruments:
            # Create instrument node
            session.run("""
                MERGE (i:Instrument {id: $id})
                SET i.documentType = $documentType,
                    i.recordingInfo = $recordingInfo,
                    i.executionDate = date($executionDate),
                    i.pdfUrl = $pdfUrl
            """, **inst)

            # Create party nodes and relationships
            for grantor in inst.get('extractedData', {}).get('grantors', []):
                session.run("""
                    MERGE (p:Party {normalizedName: $normalizedName})
                    SET p.name = $name
                    WITH p
                    MATCH (i:Instrument {id: $instrumentId})
                    MERGE (p)-[:CONVEYED {instrumentId: $instrumentId}]->(i)
                """,
                    name=grantor['name'],
                    normalizedName=normalize_party_name(grantor['name']),
                    instrumentId=inst['_id']
                )
```

### 4.2 Parallel Operation

During migration, both systems run in parallel:

```
Week 1-2: New system in development
Week 3:   New system deployed to staging
Week 4:   Migrate historical data to Neo4j
Week 5:   New uploads go to BOTH systems
Week 6:   Validate data consistency
Week 7:   Switch primary UI to new system
Week 8:   Decommission old system
```

### 4.3 Rollback Plan

If issues arise:
1. Firestore remains read-only during transition
2. All new data is also written to Firestore
3. UI can switch back to Firestore-backed views
4. Neo4j data can be regenerated from Firestore export

---

## Part 5: Cost Analysis

### 5.1 Per-Document Costs

| Document Type | Current Cost | New Cost | Savings |
|--------------|--------------|----------|---------|
| **Simple Deed (5 pages)** | $0.15 | $0.08 | 47% |
| Body: Claude | $0.15 | $0.08 | |
| Exhibits: None | - | - | |
| **Assignment (400 pages)** | $2.50 | $0.65 | 74% |
| Body: Claude | $0.15 | $0.08 | |
| Exhibits (390 pages): Claude Vision | $2.35 | - | |
| Exhibits: Textract | - | $0.57 | |
| **Mortgage (30 pages)** | $0.45 | $0.18 | 60% |
| Body: Claude | $0.15 | $0.08 | |
| Exhibits (20 pages): Claude Vision | $0.30 | - | |
| Exhibits: Textract | - | $0.10 | |

### 5.2 Monthly Cost Projection

**1,000 documents/month mix:**
- 60% Simple (600 docs): 600 × $0.08 = $48
- 30% Mortgage (300 docs): 300 × $0.18 = $54
- 10% Assignment (100 docs): 100 × $0.65 = $65

**New monthly total: ~$167**
**Current monthly total: ~$450**
**Savings: 63%**

### 5.3 Infrastructure Costs

| Service | Current | New | Notes |
|---------|---------|-----|-------|
| Firebase Blaze | ~$50/mo | $0 | Decommissioned |
| Cloud Run | $0 | ~$20/mo | Pay-per-use |
| Neo4j Aura Free | $0 | $0 | Free tier sufficient |
| S3 (temp storage) | $0 | ~$5/mo | Lifecycle rules |
| Claude API | ~$300/mo | ~$120/mo | Less usage |
| Textract | $0 | ~$50/mo | New expense |
| **TOTAL** | **~$350/mo** | **~$195/mo** | **44% reduction** |

---

## Part 6: Success Metrics

### 6.1 Extraction Quality

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| **Body extraction accuracy** | 90% | 98% | Sample 100 documents, manual verification |
| **Table extraction completeness** | 15% | 95% | Count extracted vs actual lease rows |
| **Legal description parsing** | 70% | 95% | Spatial key generation success rate |
| **Party name matching** | 80% | 95% | Cross-reference accuracy |

### 6.2 Performance

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| **Simple document processing** | 45s | 30s | End-to-end timing |
| **Large assignment processing** | 10min | 3min | End-to-end timing |
| **Chain of title query** | 2-5s | <100ms | Neo4j query timing |
| **Batch processing throughput** | 20/min | 50/min | Documents per minute |

### 6.3 Business Impact

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| **Attorney manual corrections** | 40% of docs | 5% of docs | UI edit tracking |
| **Title opinion turnaround** | 2-3 weeks | 3-5 days | Project completion dates |
| **Cost per document** | $0.35 avg | $0.15 avg | API cost tracking |
| **System reliability** | 95% | 99.5% | Processing success rate |

---

## Part 7: Risk Assessment

### 7.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Textract table accuracy** | Medium | High | Fall back to Claude for complex tables |
| **Neo4j learning curve** | Medium | Medium | Team training, documentation |
| **Tesseract OCR quality** | Low | Medium | Only used for splitting, not extraction |
| **Python migration complexity** | Medium | Medium | Parallel operation period |

### 7.2 Business Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Attorney adoption** | Low | High | Involve attorneys in testing |
| **Data migration errors** | Medium | High | Validation scripts, rollback plan |
| **Cost overruns** | Low | Medium | Budget monitoring, alerts |
| **Timeline delays** | Medium | Medium | MVP-first approach |

---

## Part 8: Decision Matrix

### Why This Overhaul is Necessary

| Factor | Stick with Current | Overhaul | Winner |
|--------|-------------------|----------|--------|
| **Extraction completeness** | 15% on large docs | 95%+ | Overhaul |
| **Cost efficiency** | $0.35/doc average | $0.15/doc average | Overhaul |
| **Chain of title queries** | Complex, slow | Native, fast | Overhaul |
| **OCR reliability** | Text layer dependent | Image-only | Overhaul |
| **Development velocity** | TypeScript/Firebase | Python/Streamlit | Overhaul |
| **Short-term stability** | Proven | New system | Current |
| **Migration effort** | None | 4-6 weeks | Current |

**Recommendation:** Proceed with overhaul. The current system fundamentally cannot handle large documents, which are the majority of valuable use cases for title attorneys.

---

## Appendices

### A. Sample Documents for Testing

1. **Simple Deed** (5 pages) - Baseline accuracy test
2. **Oil & Gas Lease** (8 pages) - Clause extraction test
3. **Assignment with 50 leases** (60 pages) - Medium complexity
4. **Assignment with 150 leases** (400 pages) - Stress test
5. **Partial Release** (15 pages) - Schedule parsing
6. **Mortgage with legal descriptions** (30 pages) - Exhibit handling

### B. API Cost Reference

**Claude Sonnet 4.5:**
- Input: $3.00 / MTok
- Output: $15.00 / MTok
- Cache write: $3.75 / MTok
- Cache read: $0.30 / MTok

**AWS Textract:**
- Tables: $0.015 / page
- Forms: $0.050 / page
- Queries: $0.015 / page

**Neo4j Aura:**
- Free tier: 50K nodes, 175K relationships
- Professional: $65/month (1M nodes)

### C. Contact & Resources

- **Neo4j Aura:** https://neo4j.com/cloud/aura/
- **AWS Textract:** https://aws.amazon.com/textract/
- **Anthropic Claude:** https://www.anthropic.com/
- **Tesseract:** https://github.com/tesseract-ocr/tesseract
- **PyMuPDF:** https://pymupdf.readthedocs.io/

---

**Document Status:** Ready for Review
**Next Steps:**
1. Stakeholder review and approval
2. Finalize technology decisions
3. Begin Phase 1 implementation
