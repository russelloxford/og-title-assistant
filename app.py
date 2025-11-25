"""
OG Title Assistant - Streamlit MVP Application

A document processing application for oil & gas title analysis.
Extracts metadata from documents and builds chain of title graph.
"""

import logging
import os
import tempfile
from pathlib import Path

import streamlit as st

# Page config must be first Streamlit command
st.set_page_config(
    page_title="OG Title Assistant",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Check environment
def check_environment():
    """Check if required environment variables are set."""
    missing = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    return missing


# Sidebar
st.sidebar.title("OG Title Assistant")
st.sidebar.markdown("---")

# Environment check
missing_vars = check_environment()
if missing_vars:
    st.sidebar.warning(f"Missing: {', '.join(missing_vars)}")
else:
    st.sidebar.success("Environment configured")

st.sidebar.markdown("---")
st.sidebar.markdown("### About")
st.sidebar.markdown(
    """
    Extract structured data from oil & gas documents:
    - Deeds & Assignments
    - Oil & Gas Leases
    - Mortgages & Releases
    - Exhibit schedules
    """
)

# Main content
st.title("Document Processing")

# File uploader
uploaded_file = st.file_uploader(
    "Upload a PDF document",
    type=["pdf"],
    help="Upload scanned or digital PDF documents (max 200 pages)",
)

if uploaded_file is not None:
    # Show file info
    st.info(f"**File:** {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")

    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.getbuffer())
        temp_path = tmp_file.name

    # Processing tabs
    tab1, tab2, tab3, tab4 = st.tabs(
        ["1. Split Document", "2. Extract Body", "3. Extract Tables", "4. Build Graph"]
    )

    # =========================================================================
    # Tab 1: Document Splitting
    # =========================================================================
    with tab1:
        st.subheader("Document Splitting")
        st.markdown(
            """
            Identifies document structure using OCR to split body from exhibits.
            - **Cost:** $0 (local Tesseract OCR)
            - **Time:** ~2-3 seconds
            """
        )

        if st.button("Split Document", key="split_btn"):
            try:
                from src.splitter import process_document, cleanup_temp_files

                with st.spinner("Analyzing document structure..."):
                    result = process_document(temp_path)

                # Store result in session state
                st.session_state["split_result"] = result

                # Display results
                col1, col2 = st.columns(2)

                with col1:
                    st.metric("Body Pages", result.split_points.body_end_page)
                    st.metric("Exhibits Found", len(result.split_points.exhibits))

                with col2:
                    st.metric("Total Pages", result.total_pages)
                    if result.body_path:
                        st.success(f"Body extracted: {result.split_points.body_end_page} pages")

                # Show exhibit details
                if result.split_points.exhibits:
                    st.markdown("**Exhibits Found:**")
                    for i, exhibit in enumerate(result.split_points.exhibits):
                        st.markdown(
                            f"- **{exhibit.marker}** (page {exhibit.start_page + 1}) - {exhibit.exhibit_type}"
                        )
                else:
                    st.info("No exhibits detected - document appears to be body only")

            except Exception as e:
                st.error(f"Error: {str(e)}")
                logger.exception("Split error")

    # =========================================================================
    # Tab 2: Body Extraction
    # =========================================================================
    with tab2:
        st.subheader("Document Body Extraction")
        st.markdown(
            """
            Extracts structured metadata from document body using Claude AI.
            - **Cost:** ~$0.08-0.15 per document
            - **Time:** ~30 seconds
            """
        )

        # Check if split was done
        split_result = st.session_state.get("split_result")
        body_path = split_result.body_path if split_result else temp_path

        if st.button("Extract Body", key="body_btn"):
            if not os.environ.get("ANTHROPIC_API_KEY"):
                st.error("ANTHROPIC_API_KEY not configured")
            else:
                try:
                    from src.body_extractor import extract_body, extraction_to_dict

                    with st.spinner("Extracting document metadata with Claude..."):
                        extraction = extract_body(body_path)
                        result_dict = extraction_to_dict(extraction)

                    # Store in session state
                    st.session_state["body_extraction"] = result_dict

                    # Display results
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("### Document Info")
                        st.markdown(f"**Type:** {extraction.document_type}")
                        if extraction.document_title:
                            st.markdown(f"**Title:** {extraction.document_title}")

                        st.markdown("### Parties")
                        if extraction.parties.grantors:
                            st.markdown("**Grantors/Assignors:**")
                            for p in extraction.parties.grantors:
                                entity_type = f" ({p.entity_type})" if p.entity_type else ""
                                st.markdown(f"- {p.name}{entity_type}")

                        if extraction.parties.grantees:
                            st.markdown("**Grantees/Assignees:**")
                            for p in extraction.parties.grantees:
                                entity_type = f" ({p.entity_type})" if p.entity_type else ""
                                st.markdown(f"- {p.name}{entity_type}")

                    with col2:
                        st.markdown("### Dates")
                        if extraction.dates.execution:
                            st.markdown(f"**Execution:** {extraction.dates.execution}")
                        if extraction.dates.recording:
                            st.markdown(f"**Recording:** {extraction.dates.recording}")

                        st.markdown("### Recording Info")
                        if extraction.recording_info.book:
                            st.markdown(
                                f"**Book/Page:** {extraction.recording_info.book}/{extraction.recording_info.page}"
                            )
                        if extraction.recording_info.document_number:
                            st.markdown(f"**Doc #:** {extraction.recording_info.document_number}")
                        if extraction.recording_info.county:
                            st.markdown(
                                f"**Location:** {extraction.recording_info.county}, {extraction.recording_info.state}"
                            )

                        st.markdown("### Confidence")
                        confidence = extraction.confidence.overall
                        if confidence >= 0.9:
                            st.success(f"Overall: {confidence:.0%}")
                        elif confidence >= 0.7:
                            st.warning(f"Overall: {confidence:.0%}")
                        else:
                            st.error(f"Overall: {confidence:.0%}")

                    # Exhibit references
                    if extraction.exhibit_references:
                        st.markdown("### Exhibit References")
                        for ex in extraction.exhibit_references:
                            st.markdown(f"- **{ex.name}:** {ex.description}")

                    # Raw JSON expander
                    with st.expander("View Raw JSON"):
                        st.json(result_dict)

                except Exception as e:
                    st.error(f"Error: {str(e)}")
                    logger.exception("Body extraction error")

    # =========================================================================
    # Tab 3: Table Extraction
    # =========================================================================
    with tab3:
        st.subheader("Exhibit Table Extraction")
        st.markdown(
            """
            Extracts tabular data from exhibits using AWS Textract.
            - **Cost:** ~$0.015 per page
            - **Time:** ~60 seconds per exhibit
            """
        )

        # Check requirements
        split_result = st.session_state.get("split_result")
        has_table_exhibits = split_result and any(
            e.exhibit_type == "table" for e in split_result.split_points.exhibits
        )

        if not split_result:
            st.warning("Please split the document first (Tab 1)")
        elif not has_table_exhibits:
            st.info("No table exhibits detected in this document")
        else:
            # List table exhibits
            table_exhibits = [
                e for e in split_result.split_points.exhibits if e.exhibit_type == "table"
            ]
            st.markdown(f"**Found {len(table_exhibits)} table exhibit(s):**")
            for exhibit in table_exhibits:
                st.markdown(f"- {exhibit.marker} (starts page {exhibit.start_page + 1})")

            if st.button("Extract Tables", key="table_btn"):
                if not os.environ.get("AWS_ACCESS_KEY_ID"):
                    st.error("AWS credentials not configured")
                elif not os.environ.get("TEXTRACT_S3_BUCKET"):
                    st.error("TEXTRACT_S3_BUCKET not configured")
                else:
                    st.info(
                        "Table extraction requires AWS Textract and S3. "
                        "Ensure your AWS credentials and S3 bucket are configured."
                    )
                    # TODO: Implement actual Textract extraction
                    # This would use extract_tables from src.table_extractor

    # =========================================================================
    # Tab 4: Graph Building
    # =========================================================================
    with tab4:
        st.subheader("Graph Construction")
        st.markdown(
            """
            Builds Neo4j graph from extracted data for chain of title analysis.
            """
        )

        body_extraction = st.session_state.get("body_extraction")

        if not body_extraction:
            st.warning("Please extract document body first (Tab 2)")
        else:
            st.success("Body extraction data available")

            # Show what will be created
            parties = body_extraction.get("parties", {})
            grantor_count = len(parties.get("grantors", []))
            grantee_count = len(parties.get("grantees", []))

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Parties", grantor_count + grantee_count)
            with col2:
                st.metric("Instruments", 1)
            with col3:
                st.metric("Relationships", grantor_count * grantee_count)

            if st.button("Build Graph", key="graph_btn"):
                if not os.environ.get("NEO4J_URI"):
                    st.error("NEO4J_URI not configured")
                else:
                    try:
                        from src.graph_builder import GraphBuilder, build_graph_from_extraction

                        with st.spinner("Connecting to Neo4j..."):
                            builder = GraphBuilder()
                            if not builder.verify_connection():
                                st.error("Cannot connect to Neo4j. Check your credentials.")
                            else:
                                with st.spinner("Building graph..."):
                                    result = build_graph_from_extraction(
                                        builder,
                                        body_extraction,
                                        [],  # No lease records for now
                                    )
                                    builder.close()

                                st.success("Graph built successfully!")

                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Parties Created", len(result["party_ids"]))
                                with col2:
                                    st.metric("Instrument ID", result["instrument_id"][:8] + "...")
                                with col3:
                                    st.metric("Tracts Created", len(result["tract_ids"]))

                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                        logger.exception("Graph building error")

    # Cleanup temp file when done
    # Note: In production, implement proper cleanup

else:
    # No file uploaded - show instructions
    st.markdown(
        """
        ## Getting Started

        1. **Upload a PDF** - Drag and drop or click to browse
        2. **Split Document** - Identify body and exhibit sections
        3. **Extract Body** - Get structured metadata using Claude AI
        4. **Extract Tables** - Parse exhibit schedules with Textract
        5. **Build Graph** - Store in Neo4j for chain of title queries

        ### Supported Document Types

        | Type | Pages | Processing |
        |------|-------|------------|
        | Simple Deed | 2-5 | Body only |
        | Mortgage | 10-30 | Body + Legal Descriptions |
        | Oil & Gas Lease | 3-8 | Body + Addendum |
        | Assignment | 5-400 | Body + Lease Schedules |
        | Partial Release | 3-20 | Body + Schedule |

        ### Requirements

        - **ANTHROPIC_API_KEY** - For Claude document extraction
        - **AWS credentials** - For Textract table extraction (optional)
        - **NEO4J credentials** - For graph storage (optional)
        """
    )

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    **Version:** 0.1.0 (MVP)

    [Documentation](https://github.com/example/og-title-assistant)
    """
)
