"""
Chain of Title Visualization Page

Query and visualize chain of title from Neo4j graph database.
"""

import logging
import os

import streamlit as st

st.set_page_config(
    page_title="Chain of Title - OG Title Assistant",
    page_icon="🔗",
    layout="wide",
)

logger = logging.getLogger(__name__)

st.title("Chain of Title Query")

st.markdown(
    """
    Query the chain of title graph to trace ownership history,
    find gaps, and calculate current interests.
    """
)

# Check Neo4j connection
neo4j_configured = bool(os.environ.get("NEO4J_URI"))

if not neo4j_configured:
    st.warning(
        """
        **Neo4j not configured.**

        Set the following environment variables:
        - `NEO4J_URI` - Connection URI (e.g., `neo4j+s://xxx.databases.neo4j.io`)
        - `NEO4J_USER` - Username (default: `neo4j`)
        - `NEO4J_PASSWORD` - Password
        """
    )
else:
    # Query type selection
    query_type = st.selectbox(
        "Query Type",
        [
            "Chain of Title by Tract",
            "Instruments by Section",
            "Party Search",
            "Gap Detection",
            "Graph Statistics",
        ],
    )

    st.markdown("---")

    # =========================================================================
    # Chain of Title by Tract
    # =========================================================================
    if query_type == "Chain of Title by Tract":
        st.subheader("Trace Ownership for a Tract")

        col1, col2 = st.columns(2)

        with col1:
            state = st.selectbox("State", ["ND", "OK", "TX", "MT", "WY", "CO", "NM", "SD", "KS", "NE"])
            county = st.text_input("County", placeholder="WILLIAMS").upper()
            section = st.text_input("Section", placeholder="15")

        with col2:
            township = st.text_input("Township", placeholder="154N")
            range_val = st.text_input("Range", placeholder="97W")
            aliquot = st.text_input("Aliquot (optional)", placeholder="NW4")

        if st.button("Search Chain of Title", key="chain_search"):
            if not all([county, section, township, range_val]):
                st.error("Please fill in County, Section, Township, and Range")
            else:
                # Build spatial key
                spatial_key = f"{state}-{county}-{section}-{township}-{range_val}"
                if aliquot:
                    spatial_key += f"-{aliquot}"

                st.info(f"Searching for: `{spatial_key}`")

                try:
                    from src.graph_builder import GraphBuilder

                    with GraphBuilder() as builder:
                        if not builder.verify_connection():
                            st.error("Cannot connect to Neo4j")
                        else:
                            # Get chain of title
                            with st.spinner("Querying chain of title..."):
                                chain = builder.get_chain_of_title(spatial_key)

                            if not chain:
                                st.warning(f"No records found for tract: {spatial_key}")
                            else:
                                st.success(f"Found {len(chain)} conveyances")

                                # Display chain as timeline
                                st.markdown("### Ownership Chain")

                                for i, record in enumerate(chain):
                                    with st.container():
                                        col1, col2, col3 = st.columns([2, 1, 2])

                                        with col1:
                                            st.markdown(f"**From:** {record['grantor']}")

                                        with col2:
                                            date_str = (
                                                str(record["recording_date"])
                                                if record.get("recording_date")
                                                else "Unknown"
                                            )
                                            st.markdown(f"**{record['document_type']}**")
                                            st.caption(date_str)

                                        with col3:
                                            st.markdown(f"**To:** {record['grantee']}")

                                        if record.get("recording_info"):
                                            st.caption(f"Recording: {record['recording_info']}")

                                        if i < len(chain) - 1:
                                            st.markdown("↓")

                except Exception as e:
                    st.error(f"Query error: {str(e)}")
                    logger.exception("Chain of title query error")

    # =========================================================================
    # Instruments by Section
    # =========================================================================
    elif query_type == "Instruments by Section":
        st.subheader("Find All Instruments in a Section")

        col1, col2 = st.columns(2)

        with col1:
            state = st.selectbox("State", ["ND", "OK", "TX", "MT", "WY", "CO", "NM", "SD", "KS", "NE"])
            county = st.text_input("County", placeholder="WILLIAMS").upper()

        with col2:
            section = st.text_input("Section", placeholder="15")
            township = st.text_input("Township", placeholder="154N")
            range_val = st.text_input("Range", placeholder="97W")

        if st.button("Search Section", key="section_search"):
            if not all([county, section, township, range_val]):
                st.error("Please fill in all fields")
            else:
                section_key = f"{state}-{county}-{section}-{township}-{range_val}"

                try:
                    from src.graph_builder import GraphBuilder

                    with GraphBuilder() as builder:
                        if not builder.verify_connection():
                            st.error("Cannot connect to Neo4j")
                        else:
                            with st.spinner("Searching..."):
                                instruments = builder.get_instruments_for_section(section_key)

                            if not instruments:
                                st.warning(f"No instruments found for section: {section_key}")
                            else:
                                st.success(f"Found {len(instruments)} instruments")

                                for inst in instruments:
                                    with st.expander(
                                        f"{inst['document_type']} - {inst.get('recording_info', 'No recording info')}"
                                    ):
                                        st.markdown(f"**ID:** `{inst['id'][:8]}...`")
                                        if inst.get("recording_date"):
                                            st.markdown(f"**Recorded:** {inst['recording_date']}")
                                        st.markdown(f"**Tracts:** {', '.join(inst.get('tracts', []))}")

                except Exception as e:
                    st.error(f"Query error: {str(e)}")
                    logger.exception("Section query error")

    # =========================================================================
    # Party Search
    # =========================================================================
    elif query_type == "Party Search":
        st.subheader("Search by Party Name")

        party_name = st.text_input("Party Name", placeholder="SMITH OIL")
        search_as = st.radio("Search as", ["Grantor", "Grantee"], horizontal=True)

        if st.button("Search Party", key="party_search"):
            if not party_name:
                st.error("Please enter a party name")
            else:
                try:
                    from src.graph_builder import GraphBuilder
                    from src.normalizer import normalize_party_name

                    normalized = normalize_party_name(party_name)

                    with GraphBuilder() as builder:
                        if not builder.verify_connection():
                            st.error("Cannot connect to Neo4j")
                        else:
                            with st.spinner("Searching..."):
                                instruments = builder.get_party_instruments(
                                    normalized.normalized_name,
                                    as_grantor=(search_as == "Grantor"),
                                )

                            if not instruments:
                                st.warning(
                                    f"No instruments found for: {normalized.normalized_name}"
                                )
                            else:
                                st.success(f"Found {len(instruments)} instruments")

                                for inst in instruments:
                                    with st.expander(
                                        f"{inst['document_type']} with {inst['other_party']}"
                                    ):
                                        st.markdown(f"**ID:** `{inst['id'][:8]}...`")
                                        st.markdown(
                                            f"**Recording:** {inst.get('recording_info', 'N/A')}"
                                        )
                                        if inst.get("interest_fraction"):
                                            st.markdown(
                                                f"**Interest:** {inst['interest_fraction']:.2%}"
                                            )
                                        st.markdown(
                                            f"**Tracts:** {', '.join(inst.get('tracts', []))}"
                                        )

                except Exception as e:
                    st.error(f"Query error: {str(e)}")
                    logger.exception("Party query error")

    # =========================================================================
    # Gap Detection
    # =========================================================================
    elif query_type == "Gap Detection":
        st.subheader("Find Gaps in Chain of Title")

        st.markdown(
            """
            Identifies where the grantee of one instrument doesn't match
            the grantor of the next instrument in the chain.
            """
        )

        col1, col2 = st.columns(2)

        with col1:
            state = st.selectbox("State", ["ND", "OK", "TX", "MT", "WY", "CO", "NM", "SD", "KS", "NE"])
            county = st.text_input("County", placeholder="WILLIAMS").upper()
            section = st.text_input("Section", placeholder="15")

        with col2:
            township = st.text_input("Township", placeholder="154N")
            range_val = st.text_input("Range", placeholder="97W")
            aliquot = st.text_input("Aliquot (optional)", placeholder="NW4")

        if st.button("Find Gaps", key="gap_search"):
            if not all([county, section, township, range_val]):
                st.error("Please fill in County, Section, Township, and Range")
            else:
                spatial_key = f"{state}-{county}-{section}-{township}-{range_val}"
                if aliquot:
                    spatial_key += f"-{aliquot}"

                try:
                    from src.graph_builder import GraphBuilder

                    with GraphBuilder() as builder:
                        if not builder.verify_connection():
                            st.error("Cannot connect to Neo4j")
                        else:
                            with st.spinner("Analyzing chain..."):
                                gaps = builder.find_chain_gaps(spatial_key)

                            if not gaps:
                                st.success("No gaps detected in chain of title!")
                            else:
                                st.warning(f"Found {len(gaps)} potential gaps")

                                for gap in gaps:
                                    st.markdown("---")
                                    col1, col2 = st.columns(2)

                                    with col1:
                                        st.markdown("**Prior Instrument:**")
                                        st.markdown(f"Recording: {gap['prior_instrument']}")
                                        st.markdown(f"Date: {gap['prior_date']}")
                                        st.markdown(f"Grantee: {gap['prior_grantee'] or 'Unknown'}")

                                    with col2:
                                        st.markdown("**Later Instrument:**")
                                        st.markdown(f"Recording: {gap['later_instrument']}")
                                        st.markdown(f"Date: {gap['later_date']}")
                                        st.markdown(f"Grantor: {gap['later_grantor'] or 'Unknown'}")

                except Exception as e:
                    st.error(f"Query error: {str(e)}")
                    logger.exception("Gap detection error")

    # =========================================================================
    # Graph Statistics
    # =========================================================================
    elif query_type == "Graph Statistics":
        st.subheader("Database Statistics")

        if st.button("Load Statistics", key="stats_btn"):
            try:
                from src.graph_builder import GraphBuilder

                with GraphBuilder() as builder:
                    if not builder.verify_connection():
                        st.error("Cannot connect to Neo4j")
                    else:
                        with st.spinner("Loading statistics..."):
                            stats = builder.get_stats()

                        if stats:
                            col1, col2, col3 = st.columns(3)

                            with col1:
                                st.metric("Parties", stats.get("parties", 0))
                                st.metric("Instruments", stats.get("instruments", 0))

                            with col2:
                                st.metric("Tracts", stats.get("tracts", 0))
                                st.metric("Sections", stats.get("sections", 0))

                            with col3:
                                st.metric("Conveyances", stats.get("conveyances", 0))
                                st.metric("Covers", stats.get("covers", 0))

                            # Free tier limits
                            st.markdown("---")
                            st.markdown("### Neo4j Aura Free Tier Limits")

                            total_nodes = (
                                stats.get("parties", 0)
                                + stats.get("instruments", 0)
                                + stats.get("tracts", 0)
                                + stats.get("sections", 0)
                            )
                            total_rels = stats.get("conveyances", 0) + stats.get("covers", 0)

                            node_pct = total_nodes / 50000 * 100
                            rel_pct = total_rels / 175000 * 100

                            col1, col2 = st.columns(2)

                            with col1:
                                st.progress(min(node_pct / 100, 1.0))
                                st.caption(f"Nodes: {total_nodes:,} / 50,000 ({node_pct:.1f}%)")

                            with col2:
                                st.progress(min(rel_pct / 100, 1.0))
                                st.caption(f"Relationships: {total_rels:,} / 175,000 ({rel_pct:.1f}%)")

                        else:
                            st.info("No statistics available - database may be empty")

            except Exception as e:
                st.error(f"Error: {str(e)}")
                logger.exception("Stats error")

# Sidebar info
st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    ### Query Tips

    **Spatial Key Format:**
    `{STATE}-{COUNTY}-{SEC}-{TWP}-{RNG}[-{ALIQUOT}]`

    Example: `ND-WILLIAMS-15-154N-97W-NW4`

    **Party Names:**
    - Names are normalized (uppercase, no suffixes)
    - Use normalized form for best results
    """
)
