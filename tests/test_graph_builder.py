"""
Tests for the Graph Builder Module
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.graph_builder import (
    ConveyedRelationship,
    CoversRelationship,
    GraphBuilder,
    GraphConfig,
    InstrumentNode,
    PartyNode,
    ReferencesRelationship,
    SectionNode,
    TractNode,
    _parse_date,
    _parse_fraction,
    build_graph_from_extraction,
)


class TestGraphConfig:
    """Tests for GraphConfig dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = GraphConfig()
        assert config.uri == ""
        assert config.user == "neo4j"
        assert config.password == ""
        assert config.database == "neo4j"

    @patch.dict(
        "os.environ",
        {
            "NEO4J_URI": "neo4j+s://test.databases.neo4j.io",
            "NEO4J_USER": "testuser",
            "NEO4J_PASSWORD": "testpass",
            "NEO4J_DATABASE": "testdb",
        },
    )
    def test_from_env(self):
        """Should load config from environment variables."""
        config = GraphConfig.from_env()
        assert config.uri == "neo4j+s://test.databases.neo4j.io"
        assert config.user == "testuser"
        assert config.password == "testpass"
        assert config.database == "testdb"


class TestPartyNode:
    """Tests for PartyNode dataclass."""

    def test_creation(self):
        """Should create with required fields."""
        party = PartyNode(
            name="Smith Oil, LLC",
            normalized_name="SMITH OIL",
            entity_type="llc",
        )
        assert party.name == "Smith Oil, LLC"
        assert party.normalized_name == "SMITH OIL"
        assert party.entity_type == "llc"
        assert party.aliases == []
        assert party.id is not None

    def test_auto_generated_id(self):
        """Should generate unique IDs."""
        party1 = PartyNode(name="Test 1", normalized_name="TEST 1")
        party2 = PartyNode(name="Test 2", normalized_name="TEST 2")
        assert party1.id != party2.id


class TestInstrumentNode:
    """Tests for InstrumentNode dataclass."""

    def test_creation(self):
        """Should create with all fields."""
        instrument = InstrumentNode(
            document_type="Assignment of Oil and Gas Leases",
            recording_info="Bk 450/Pg 123",
            document_number="2024-001234",
            book="450",
            page="123",
            county="Williams",
            state="ND",
            execution_date=date(2024, 1, 15),
            recording_date=date(2024, 1, 20),
            extraction_confidence=0.95,
        )
        assert instrument.document_type == "Assignment of Oil and Gas Leases"
        assert instrument.book == "450"
        assert instrument.recording_date == date(2024, 1, 20)


class TestTractNode:
    """Tests for TractNode dataclass."""

    def test_creation(self):
        """Should create with spatial key."""
        tract = TractNode(
            spatial_key="ND-WILLIAMS-15-154N-97W-NW4",
            section="15",
            township="154N",
            range="97W",
            county="WILLIAMS",
            state="ND",
            aliquot_part="NW4",
            acres=160.0,
        )
        assert tract.spatial_key == "ND-WILLIAMS-15-154N-97W-NW4"
        assert tract.acres == 160.0


class TestSectionNode:
    """Tests for SectionNode dataclass."""

    def test_creation(self):
        """Should create with section key."""
        section = SectionNode(
            section_key="ND-WILLIAMS-15-154N-97W",
            section="15",
            township="154N",
            range="97W",
            county="WILLIAMS",
            state="ND",
        )
        assert section.section_key == "ND-WILLIAMS-15-154N-97W"


class TestRelationshipDataclasses:
    """Tests for relationship dataclasses."""

    def test_conveyed_relationship(self):
        """Should create CONVEYED relationship."""
        rel = ConveyedRelationship(
            from_party_id="party-1",
            to_party_id="party-2",
            instrument_id="inst-1",
            interest_type="leasehold",
            interest_fraction=1.0,
            reservations="1/16 ORRI",
        )
        assert rel.from_party_id == "party-1"
        assert rel.interest_fraction == 1.0

    def test_covers_relationship(self):
        """Should create COVERS relationship."""
        rel = CoversRelationship(
            instrument_id="inst-1",
            tract_id="tract-1",
            interest_conveyed="All mineral rights",
        )
        assert rel.instrument_id == "inst-1"

    def test_references_relationship(self):
        """Should create REFERENCES relationship."""
        rel = ReferencesRelationship(
            from_instrument_id="inst-2",
            to_instrument_id="inst-1",
            reference_type="assigns",
        )
        assert rel.reference_type == "assigns"


class TestParseFraction:
    """Tests for fraction parsing utility."""

    def test_percentage(self):
        """Should parse percentages."""
        assert _parse_fraction("100%") == 1.0
        assert _parse_fraction("50%") == 0.5
        assert _parse_fraction("6.25%") == 0.0625

    def test_fraction(self):
        """Should parse fractions."""
        assert _parse_fraction("1/8") == 0.125
        assert _parse_fraction("3/16") == 0.1875
        assert _parse_fraction("1/2") == 0.5

    def test_decimal(self):
        """Should parse decimals."""
        assert _parse_fraction("0.5") == 0.5
        assert _parse_fraction("1.0") == 1.0

    def test_none_values(self):
        """Should handle None and invalid values."""
        assert _parse_fraction(None) is None
        assert _parse_fraction("") is None
        assert _parse_fraction("invalid") is None


class TestParseDate:
    """Tests for date parsing utility."""

    def test_iso_format(self):
        """Should parse ISO format."""
        result = _parse_date("2024-01-15")
        assert result == date(2024, 1, 15)

    def test_date_object(self):
        """Should pass through date objects."""
        d = date(2024, 1, 15)
        assert _parse_date(d) == d

    def test_none_values(self):
        """Should handle None and invalid values."""
        assert _parse_date(None) is None
        assert _parse_date("") is None
        assert _parse_date("invalid") is None


class TestGraphBuilder:
    """Tests for GraphBuilder class."""

    def test_config_from_env(self):
        """Should create builder with config from environment."""
        with patch.dict("os.environ", {"NEO4J_URI": ""}):
            builder = GraphBuilder()
            assert builder.config.uri == ""

    def test_context_manager(self):
        """Should support context manager protocol."""
        mock_driver = MagicMock()
        with patch.object(GraphBuilder, "driver", mock_driver):
            with GraphBuilder() as builder:
                pass  # Just test it doesn't error

    @patch("src.graph_builder.GraphDatabase")
    def test_driver_lazy_load(self, mock_db):
        """Should lazy-load driver on first access."""
        mock_db.driver.return_value = MagicMock()
        config = GraphConfig(
            uri="neo4j+s://test.neo4j.io",
            user="neo4j",
            password="test",
        )
        builder = GraphBuilder(config)

        # Driver not created yet
        assert builder._driver is None

        # Access driver property
        _ = builder.driver

        # Now driver should be created
        mock_db.driver.assert_called_once()

    def test_driver_requires_uri(self):
        """Should raise error if URI not configured."""
        builder = GraphBuilder(GraphConfig())
        with pytest.raises(ValueError, match="Neo4j URI not configured"):
            _ = builder.driver


class TestGraphBuilderMocked:
    """Tests for GraphBuilder with mocked Neo4j driver."""

    @pytest.fixture
    def mock_session(self):
        """Create mock session."""
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        return session

    @pytest.fixture
    def builder(self, mock_session):
        """Create builder with mocked driver."""
        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session

        config = GraphConfig(
            uri="neo4j+s://test.neo4j.io",
            user="neo4j",
            password="test",
        )
        builder = GraphBuilder(config)
        builder._driver = mock_driver
        return builder

    def test_verify_connection_success(self, builder, mock_session):
        """Should verify connection successfully."""
        mock_result = MagicMock()
        mock_result.single.return_value = {"test": 1}
        mock_session.run.return_value = mock_result

        assert builder.verify_connection() is True
        mock_session.run.assert_called_with("RETURN 1 AS test")

    def test_create_schema(self, builder, mock_session):
        """Should create schema constraints and indexes."""
        builder.create_schema()

        # Verify multiple calls for constraints and indexes
        assert mock_session.run.call_count >= 10

    def test_create_party(self, builder, mock_session):
        """Should create party node."""
        mock_result = MagicMock()
        mock_result.single.return_value = {"id": "party-123"}
        mock_session.run.return_value = mock_result

        party = PartyNode(
            name="Smith Oil, LLC",
            normalized_name="SMITH OIL",
            entity_type="llc",
        )
        result = builder.create_party(party)

        assert result == "party-123"
        mock_session.run.assert_called_once()
        call_args = mock_session.run.call_args
        assert "MERGE (p:Party" in call_args[0][0]

    def test_create_instrument(self, builder, mock_session):
        """Should create instrument node."""
        mock_result = MagicMock()
        mock_result.single.return_value = {"id": "inst-123"}
        mock_session.run.return_value = mock_result

        instrument = InstrumentNode(
            document_type="Deed",
            book="450",
            page="123",
            execution_date=date(2024, 1, 15),
        )
        result = builder.create_instrument(instrument)

        assert result == "inst-123"
        call_args = mock_session.run.call_args
        assert "MERGE (i:Instrument" in call_args[0][0]

    def test_create_tract(self, builder, mock_session):
        """Should create tract node."""
        mock_result = MagicMock()
        mock_result.single.return_value = {"id": "tract-123"}
        mock_session.run.return_value = mock_result

        tract = TractNode(
            spatial_key="ND-WILLIAMS-15-154N-97W",
            section="15",
            township="154N",
            range="97W",
        )
        result = builder.create_tract(tract)

        assert result == "tract-123"
        call_args = mock_session.run.call_args
        assert "MERGE (t:Tract" in call_args[0][0]

    def test_create_section(self, builder, mock_session):
        """Should create section node."""
        section = SectionNode(
            section_key="ND-WILLIAMS-15-154N-97W",
            section="15",
            township="154N",
            range="97W",
            county="WILLIAMS",
            state="ND",
        )
        result = builder.create_section(section)

        assert result == "ND-WILLIAMS-15-154N-97W"
        call_args = mock_session.run.call_args
        assert "MERGE (s:Section" in call_args[0][0]

    def test_create_conveyed_relationship(self, builder, mock_session):
        """Should create CONVEYED relationship."""
        rel = ConveyedRelationship(
            from_party_id="party-1",
            to_party_id="party-2",
            instrument_id="inst-1",
            interest_fraction=1.0,
        )
        builder.create_conveyed_relationship(rel)

        call_args = mock_session.run.call_args
        assert "CONVEYED" in call_args[0][0]

    def test_create_covers_relationship(self, builder, mock_session):
        """Should create COVERS relationship."""
        rel = CoversRelationship(
            instrument_id="inst-1",
            tract_id="tract-1",
        )
        builder.create_covers_relationship(rel)

        call_args = mock_session.run.call_args
        assert "COVERS" in call_args[0][0]

    def test_create_in_section_relationship(self, builder, mock_session):
        """Should create IN_SECTION relationship."""
        builder.create_in_section_relationship("tract-1", "ND-WILLIAMS-15-154N-97W")

        call_args = mock_session.run.call_args
        assert "IN_SECTION" in call_args[0][0]

    def test_create_references_relationship(self, builder, mock_session):
        """Should create REFERENCES relationship."""
        rel = ReferencesRelationship(
            from_instrument_id="inst-2",
            to_instrument_id="inst-1",
            reference_type="assigns",
        )
        builder.create_references_relationship(rel)

        call_args = mock_session.run.call_args
        assert "REFERENCES" in call_args[0][0]

    def test_get_stats(self, builder, mock_session):
        """Should get graph statistics."""
        mock_result = MagicMock()
        mock_result.single.return_value = {
            "parties": 10,
            "instruments": 5,
            "tracts": 20,
            "sections": 3,
            "conveyances": 8,
            "covers": 25,
        }
        mock_session.run.return_value = mock_result

        stats = builder.get_stats()

        assert stats["parties"] == 10
        assert stats["instruments"] == 5
        assert stats["tracts"] == 20

    def test_clear_all(self, builder, mock_session):
        """Should clear all data."""
        builder.clear_all()

        mock_session.run.assert_called_with("MATCH (n) DETACH DELETE n")


class TestBuildGraphFromExtraction:
    """Tests for build_graph_from_extraction function."""

    @pytest.fixture
    def mock_builder(self):
        """Create mock builder."""
        builder = MagicMock(spec=GraphBuilder)
        builder.create_instrument.return_value = "inst-123"
        builder.create_party.return_value = "party-123"
        builder.create_tract.return_value = "tract-123"
        return builder

    @pytest.fixture
    def sample_body_extraction(self):
        """Sample body extraction result."""
        return {
            "document_type": "Assignment of Oil and Gas Leases",
            "parties": {
                "grantors": [{"name": "Smith Oil, LLC", "entity_type": "llc"}],
                "grantees": [{"name": "Jones Energy LP", "entity_type": "limited_partnership"}],
            },
            "dates": {
                "execution": "2024-01-15",
                "recording": "2024-01-20",
            },
            "recording_info": {
                "book": "450",
                "page": "123",
                "county": "Williams",
                "state": "ND",
            },
            "interests": {
                "conveyed": "All right, title and interest",
                "conveyed_fraction": "100%",
                "reserved": "1/16 ORRI",
                "interest_type": "leasehold",
            },
            "confidence": {"overall": 0.95},
        }

    @pytest.fixture
    def sample_lease_records(self):
        """Sample lease records from table extraction."""
        return [
            {
                "lessor": "Smith, John",
                "lessee": "Acme Oil Co",
                "lands": "NW/4 of Section 15, T154N, R97W, Williams County, ND",
                "recording_info": "Bk 400/Pg 50",
            },
            {
                "lessor": "Jones, Mary",
                "lessee": "Acme Oil Co",
                "lands": "SW/4 of Section 15, T154N, R97W, Williams County, ND",
                "recording_info": "Bk 400/Pg 55",
            },
        ]

    def test_creates_instrument(
        self,
        mock_builder,
        sample_body_extraction,
        sample_lease_records,
    ):
        """Should create instrument node."""
        result = build_graph_from_extraction(
            mock_builder,
            sample_body_extraction,
            sample_lease_records,
        )

        mock_builder.create_instrument.assert_called_once()
        assert result["instrument_id"] == "inst-123"

    def test_creates_parties(
        self,
        mock_builder,
        sample_body_extraction,
    ):
        """Should create party nodes."""
        # Use the actual normalizer for a simpler test
        from src.normalizer import NormalizedParty

        with patch(
            "src.normalizer.normalize_party_name",
            return_value=NormalizedParty(
                original_name="Smith Oil, LLC",
                normalized_name="SMITH OIL",
                entity_type="llc",
            ),
        ):
            result = build_graph_from_extraction(
                mock_builder,
                sample_body_extraction,
                [],  # No lease records
            )

            # Should create 2 parties (1 grantor + 1 grantee)
            assert mock_builder.create_party.call_count == 2
            assert len(result["party_ids"]) == 2

    def test_creates_conveyed_relationships(
        self,
        mock_builder,
        sample_body_extraction,
    ):
        """Should create CONVEYED relationships between parties."""
        result = build_graph_from_extraction(
            mock_builder,
            sample_body_extraction,
            [],  # No lease records
        )

        # Should create 1 CONVEYED relationship (1 grantor → 1 grantee)
        mock_builder.create_conveyed_relationship.assert_called_once()

    def test_creates_tracts_from_lease_records(
        self,
        mock_builder,
        sample_body_extraction,
        sample_lease_records,
    ):
        """Should create tract nodes from lease records."""
        result = build_graph_from_extraction(
            mock_builder,
            sample_body_extraction,
            sample_lease_records,
        )

        # Should create 2 tracts (one per lease record)
        assert mock_builder.create_tract.call_count == 2
        assert len(result["tract_ids"]) == 2

    def test_creates_covers_relationships(
        self,
        mock_builder,
        sample_body_extraction,
        sample_lease_records,
    ):
        """Should create COVERS relationships for tracts."""
        build_graph_from_extraction(
            mock_builder,
            sample_body_extraction,
            sample_lease_records,
        )

        # Should create 2 COVERS relationships
        assert mock_builder.create_covers_relationship.call_count == 2

    def test_creates_sections_and_relationships(
        self,
        mock_builder,
        sample_body_extraction,
        sample_lease_records,
    ):
        """Should create section nodes and IN_SECTION relationships."""
        build_graph_from_extraction(
            mock_builder,
            sample_body_extraction,
            sample_lease_records,
        )

        # Should create sections and relationships
        assert mock_builder.create_section.call_count == 2
        assert mock_builder.create_in_section_relationship.call_count == 2

    def test_skips_invalid_legal_descriptions(
        self,
        mock_builder,
        sample_body_extraction,
    ):
        """Should skip lease records with invalid legal descriptions."""
        lease_records = [
            {"lessor": "Smith", "lands": "Some random text"},  # No valid legal desc
        ]

        result = build_graph_from_extraction(
            mock_builder,
            sample_body_extraction,
            lease_records,
        )

        # Should not create any tracts (invalid legal description)
        mock_builder.create_tract.assert_not_called()
        assert len(result["tract_ids"]) == 0

    def test_includes_pdf_url(
        self,
        mock_builder,
        sample_body_extraction,
    ):
        """Should include PDF URL in instrument."""
        build_graph_from_extraction(
            mock_builder,
            sample_body_extraction,
            [],
            pdf_url="https://storage.example.com/doc.pdf",
        )

        call_args = mock_builder.create_instrument.call_args
        instrument = call_args[0][0]
        assert instrument.pdf_url == "https://storage.example.com/doc.pdf"


# Integration test marker
@pytest.mark.integration
class TestGraphBuilderIntegration:
    """Integration tests requiring actual Neo4j connection."""

    @pytest.fixture
    def builder(self):
        """Create builder from environment."""
        import os

        if not os.environ.get("NEO4J_URI"):
            pytest.skip("NEO4J_URI not set")

        builder = GraphBuilder()
        if not builder.verify_connection():
            pytest.skip("Cannot connect to Neo4j")

        yield builder
        builder.close()

    def test_full_workflow(self, builder):
        """Test complete workflow with real database."""
        # Create schema
        builder.create_schema()

        # Create party
        party = PartyNode(
            name="Test Company, LLC",
            normalized_name="TEST COMPANY",
            entity_type="llc",
        )
        party_id = builder.create_party(party)
        assert party_id is not None

        # Get stats
        stats = builder.get_stats()
        assert stats["parties"] >= 1
