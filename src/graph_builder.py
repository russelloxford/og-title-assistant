"""
Graph Builder Module

Constructs Neo4j graph from extracted document data.
Creates nodes for Party, Instrument, Tract, Section
and relationships for CONVEYED, COVERS, REFERENCES.

Neo4j Aura Free Tier: 50K nodes, 175K relationships
"""

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class GraphConfig:
    """Configuration for Neo4j connection."""

    uri: str = ""
    user: str = "neo4j"
    password: str = ""
    database: str = "neo4j"

    @classmethod
    def from_env(cls) -> "GraphConfig":
        """Load configuration from environment variables."""
        return cls(
            uri=os.environ.get("NEO4J_URI", ""),
            user=os.environ.get("NEO4J_USER", "neo4j"),
            password=os.environ.get("NEO4J_PASSWORD", ""),
            database=os.environ.get("NEO4J_DATABASE", "neo4j"),
        )


@dataclass
class PartyNode:
    """A party (person or entity) in the chain of title."""

    name: str
    normalized_name: str
    entity_type: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class InstrumentNode:
    """A recorded legal instrument (deed, lease, assignment, etc.)."""

    document_type: str
    recording_info: Optional[str] = None
    document_number: Optional[str] = None
    book: Optional[str] = None
    page: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    execution_date: Optional[date] = None
    recording_date: Optional[date] = None
    pdf_url: Optional[str] = None
    extraction_confidence: float = 0.0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class TractNode:
    """A specific parcel of land."""

    spatial_key: str
    section: Optional[str] = None
    township: Optional[str] = None
    range: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    aliquot_part: Optional[str] = None
    acres: Optional[float] = None
    raw_description: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class SectionNode:
    """Aggregation of tracts (full section)."""

    section_key: str
    section: str
    township: str
    range: str
    county: str
    state: str


@dataclass
class ConveyedRelationship:
    """Ownership transfer between parties."""

    from_party_id: str
    to_party_id: str
    instrument_id: str
    interest_type: Optional[str] = None  # fee simple, mineral, leasehold, etc.
    interest_fraction: Optional[float] = None  # 1.0, 0.5, 0.125, etc.
    reservations: Optional[str] = None
    conveyance_date: Optional[date] = None


@dataclass
class CoversRelationship:
    """Instrument covers a tract of land."""

    instrument_id: str
    tract_id: str
    interest_conveyed: Optional[str] = None
    interest_reserved: Optional[str] = None


@dataclass
class ReferencesRelationship:
    """Document references another document."""

    from_instrument_id: str
    to_instrument_id: str
    reference_type: str  # assigns, releases, ratifies, amends


class GraphBuilder:
    """Builds and queries Neo4j graph for chain of title."""

    def __init__(self, config: Optional[GraphConfig] = None):
        """
        Initialize graph builder.

        Args:
            config: Neo4j connection config. If None, loads from environment.
        """
        self.config = config or GraphConfig.from_env()
        self._driver = None

    @property
    def driver(self):
        """Lazy-load Neo4j driver."""
        if self._driver is None:
            if not self.config.uri:
                raise ValueError(
                    "Neo4j URI not configured. Set NEO4J_URI environment variable."
                )
            self._driver = GraphDatabase.driver(
                self.config.uri,
                auth=(self.config.user, self.config.password),
            )
        return self._driver

    def close(self):
        """Close the database connection."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def verify_connection(self) -> bool:
        """Test database connectivity."""
        try:
            with self.driver.session(database=self.config.database) as session:
                result = session.run("RETURN 1 AS test")
                return result.single()["test"] == 1
        except ServiceUnavailable as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            return False

    def create_schema(self) -> None:
        """
        Create constraints and indexes for optimal performance.
        Should be run once during initial setup.
        """
        with self.driver.session(database=self.config.database) as session:
            # Constraints (unique + index)
            constraints = [
                "CREATE CONSTRAINT party_id IF NOT EXISTS FOR (p:Party) REQUIRE p.id IS UNIQUE",
                "CREATE CONSTRAINT instrument_id IF NOT EXISTS FOR (i:Instrument) REQUIRE i.id IS UNIQUE",
                "CREATE CONSTRAINT tract_id IF NOT EXISTS FOR (t:Tract) REQUIRE t.id IS UNIQUE",
                "CREATE CONSTRAINT tract_spatial_key IF NOT EXISTS FOR (t:Tract) REQUIRE t.spatialKey IS UNIQUE",
                "CREATE CONSTRAINT section_key IF NOT EXISTS FOR (s:Section) REQUIRE s.sectionKey IS UNIQUE",
            ]

            # Additional indexes for query performance
            indexes = [
                "CREATE INDEX party_normalized_name IF NOT EXISTS FOR (p:Party) ON (p.normalizedName)",
                "CREATE INDEX instrument_doc_number IF NOT EXISTS FOR (i:Instrument) ON (i.documentNumber)",
                "CREATE INDEX instrument_recording IF NOT EXISTS FOR (i:Instrument) ON (i.book, i.page)",
                "CREATE INDEX instrument_type IF NOT EXISTS FOR (i:Instrument) ON (i.documentType)",
                "CREATE INDEX tract_county IF NOT EXISTS FOR (t:Tract) ON (t.county, t.state)",
                "CREATE INDEX section_county IF NOT EXISTS FOR (s:Section) ON (s.county, s.state)",
            ]

            for constraint in constraints:
                try:
                    session.run(constraint)
                    logger.debug(f"Created constraint: {constraint[:50]}...")
                except Exception as e:
                    logger.debug(f"Constraint may already exist: {e}")

            for index in indexes:
                try:
                    session.run(index)
                    logger.debug(f"Created index: {index[:50]}...")
                except Exception as e:
                    logger.debug(f"Index may already exist: {e}")

            logger.info("Schema creation complete")

    # =========================================================================
    # Node Creation
    # =========================================================================

    def create_party(self, party: PartyNode) -> str:
        """
        Create or update a Party node.
        Uses normalized_name for matching to handle aliases.

        Returns:
            The party's id
        """
        with self.driver.session(database=self.config.database) as session:
            result = session.run(
                """
                MERGE (p:Party {normalizedName: $normalized_name})
                ON CREATE SET
                    p.id = $id,
                    p.name = $name,
                    p.entityType = $entity_type,
                    p.aliases = $aliases
                ON MATCH SET
                    p.name = CASE WHEN size($name) > size(p.name) THEN $name ELSE p.name END,
                    p.entityType = COALESCE($entity_type, p.entityType),
                    p.aliases = CASE
                        WHEN NOT $name IN p.aliases AND $name <> p.name
                        THEN p.aliases + $name
                        ELSE p.aliases
                    END
                RETURN p.id AS id
                """,
                id=party.id,
                name=party.name,
                normalized_name=party.normalized_name,
                entity_type=party.entity_type,
                aliases=party.aliases,
            )
            record = result.single()
            return record["id"] if record else party.id

    def create_instrument(self, instrument: InstrumentNode) -> str:
        """
        Create or update an Instrument node.

        Returns:
            The instrument's id
        """
        with self.driver.session(database=self.config.database) as session:
            # Convert dates to ISO strings for Neo4j
            exec_date = (
                instrument.execution_date.isoformat()
                if instrument.execution_date
                else None
            )
            rec_date = (
                instrument.recording_date.isoformat()
                if instrument.recording_date
                else None
            )

            result = session.run(
                """
                MERGE (i:Instrument {id: $id})
                SET i.documentType = $document_type,
                    i.recordingInfo = $recording_info,
                    i.documentNumber = $document_number,
                    i.book = $book,
                    i.page = $page,
                    i.county = $county,
                    i.state = $state,
                    i.executionDate = CASE WHEN $execution_date IS NOT NULL
                        THEN date($execution_date) ELSE NULL END,
                    i.recordingDate = CASE WHEN $recording_date IS NOT NULL
                        THEN date($recording_date) ELSE NULL END,
                    i.pdfUrl = $pdf_url,
                    i.extractionConfidence = $extraction_confidence
                RETURN i.id AS id
                """,
                id=instrument.id,
                document_type=instrument.document_type,
                recording_info=instrument.recording_info,
                document_number=instrument.document_number,
                book=instrument.book,
                page=instrument.page,
                county=instrument.county,
                state=instrument.state,
                execution_date=exec_date,
                recording_date=rec_date,
                pdf_url=instrument.pdf_url,
                extraction_confidence=instrument.extraction_confidence,
            )
            record = result.single()
            return record["id"] if record else instrument.id

    def create_tract(self, tract: TractNode) -> str:
        """
        Create or update a Tract node.
        Uses spatial_key for deduplication.

        Returns:
            The tract's id
        """
        with self.driver.session(database=self.config.database) as session:
            result = session.run(
                """
                MERGE (t:Tract {spatialKey: $spatial_key})
                ON CREATE SET
                    t.id = $id,
                    t.section = $section,
                    t.township = $township,
                    t.range = $range,
                    t.county = $county,
                    t.state = $state,
                    t.aliquotPart = $aliquot_part,
                    t.acres = $acres,
                    t.rawDescription = $raw_description
                ON MATCH SET
                    t.acres = COALESCE($acres, t.acres),
                    t.rawDescription = COALESCE($raw_description, t.rawDescription)
                RETURN t.id AS id
                """,
                id=tract.id,
                spatial_key=tract.spatial_key,
                section=tract.section,
                township=tract.township,
                range=tract.range,
                county=tract.county,
                state=tract.state,
                aliquot_part=tract.aliquot_part,
                acres=tract.acres,
                raw_description=tract.raw_description,
            )
            record = result.single()
            return record["id"] if record else tract.id

    def create_section(self, section: SectionNode) -> str:
        """
        Create or update a Section node (aggregation of tracts).

        Returns:
            The section key
        """
        with self.driver.session(database=self.config.database) as session:
            session.run(
                """
                MERGE (s:Section {sectionKey: $section_key})
                SET s.section = $section,
                    s.township = $township,
                    s.range = $range,
                    s.county = $county,
                    s.state = $state
                """,
                section_key=section.section_key,
                section=section.section,
                township=section.township,
                range=section.range,
                county=section.county,
                state=section.state,
            )
            return section.section_key

    # =========================================================================
    # Relationship Creation
    # =========================================================================

    def create_conveyed_relationship(self, rel: ConveyedRelationship) -> None:
        """
        Create CONVEYED relationship between parties.
        Stores instrument reference on the relationship.
        """
        with self.driver.session(database=self.config.database) as session:
            conv_date = (
                rel.conveyance_date.isoformat() if rel.conveyance_date else None
            )

            session.run(
                """
                MATCH (from:Party {id: $from_id})
                MATCH (to:Party {id: $to_id})
                MERGE (from)-[c:CONVEYED {instrumentId: $instrument_id}]->(to)
                SET c.interestType = $interest_type,
                    c.interestFraction = $interest_fraction,
                    c.reservations = $reservations,
                    c.date = CASE WHEN $conveyance_date IS NOT NULL
                        THEN date($conveyance_date) ELSE NULL END
                """,
                from_id=rel.from_party_id,
                to_id=rel.to_party_id,
                instrument_id=rel.instrument_id,
                interest_type=rel.interest_type,
                interest_fraction=rel.interest_fraction,
                reservations=rel.reservations,
                conveyance_date=conv_date,
            )

    def create_covers_relationship(self, rel: CoversRelationship) -> None:
        """Create COVERS relationship between instrument and tract."""
        with self.driver.session(database=self.config.database) as session:
            session.run(
                """
                MATCH (i:Instrument {id: $instrument_id})
                MATCH (t:Tract {id: $tract_id})
                MERGE (i)-[c:COVERS]->(t)
                SET c.interestConveyed = $interest_conveyed,
                    c.interestReserved = $interest_reserved
                """,
                instrument_id=rel.instrument_id,
                tract_id=rel.tract_id,
                interest_conveyed=rel.interest_conveyed,
                interest_reserved=rel.interest_reserved,
            )

    def create_in_section_relationship(
        self, tract_id: str, section_key: str
    ) -> None:
        """Create IN_SECTION relationship between tract and section."""
        with self.driver.session(database=self.config.database) as session:
            session.run(
                """
                MATCH (t:Tract {id: $tract_id})
                MATCH (s:Section {sectionKey: $section_key})
                MERGE (t)-[:IN_SECTION]->(s)
                """,
                tract_id=tract_id,
                section_key=section_key,
            )

    def create_references_relationship(self, rel: ReferencesRelationship) -> None:
        """Create REFERENCES relationship between instruments."""
        with self.driver.session(database=self.config.database) as session:
            session.run(
                """
                MATCH (from:Instrument {id: $from_id})
                MATCH (to:Instrument {id: $to_id})
                MERGE (from)-[r:REFERENCES]->(to)
                SET r.referenceType = $reference_type
                """,
                from_id=rel.from_instrument_id,
                to_id=rel.to_instrument_id,
                reference_type=rel.reference_type,
            )

    # =========================================================================
    # Query Methods
    # =========================================================================

    def get_chain_of_title(self, tract_spatial_key: str) -> list[dict]:
        """
        Get full chain of title for a tract.
        Returns all conveyances related to instruments covering this tract.
        """
        with self.driver.session(database=self.config.database) as session:
            result = session.run(
                """
                MATCH (t:Tract {spatialKey: $tract_key})<-[:COVERS]-(i:Instrument)
                WITH collect(i.id) AS instrumentIds
                MATCH path = (grantor:Party)-[c:CONVEYED]->(grantee:Party)
                WHERE c.instrumentId IN instrumentIds
                WITH grantor, grantee, c,
                     MATCH (i:Instrument {id: c.instrumentId})
                RETURN grantor.name AS grantor,
                       grantee.name AS grantee,
                       c.interestType AS interest_type,
                       c.interestFraction AS interest_fraction,
                       i.documentType AS document_type,
                       i.recordingDate AS recording_date,
                       i.recordingInfo AS recording_info
                ORDER BY i.recordingDate
                """,
                tract_key=tract_spatial_key,
            )
            return [dict(record) for record in result]

    def get_instruments_for_section(self, section_key: str) -> list[dict]:
        """Get all instruments affecting a section."""
        with self.driver.session(database=self.config.database) as session:
            result = session.run(
                """
                MATCH (i:Instrument)-[:COVERS]->(t:Tract)-[:IN_SECTION]->(s:Section)
                WHERE s.sectionKey = $section_key
                RETURN DISTINCT i.id AS id,
                       i.documentType AS document_type,
                       i.recordingInfo AS recording_info,
                       i.recordingDate AS recording_date,
                       collect(t.spatialKey) AS tracts
                ORDER BY i.recordingDate
                """,
                section_key=section_key,
            )
            return [dict(record) for record in result]

    def get_party_instruments(
        self, normalized_name: str, as_grantor: bool = True
    ) -> list[dict]:
        """Get all instruments where party is grantor or grantee."""
        direction = "-[c:CONVEYED]->" if as_grantor else "<-[c:CONVEYED]-"
        with self.driver.session(database=self.config.database) as session:
            result = session.run(
                f"""
                MATCH (p:Party {{normalizedName: $name}}){direction}(other:Party)
                MATCH (i:Instrument {{id: c.instrumentId}})-[:COVERS]->(t:Tract)
                RETURN i.id AS id,
                       i.documentType AS document_type,
                       i.recordingInfo AS recording_info,
                       other.name AS other_party,
                       c.interestFraction AS interest_fraction,
                       collect(t.spatialKey) AS tracts
                ORDER BY i.recordingDate
                """,
                name=normalized_name,
            )
            return [dict(record) for record in result]

    def find_chain_gaps(self, tract_spatial_key: str) -> list[dict]:
        """
        Find gaps in the chain of title for a tract.
        Returns pairs of sequential instruments with no connecting party.
        """
        with self.driver.session(database=self.config.database) as session:
            result = session.run(
                """
                MATCH (t:Tract {spatialKey: $tract_key})
                MATCH (i1:Instrument)-[:COVERS]->(t)<-[:COVERS]-(i2:Instrument)
                WHERE i1.recordingDate < i2.recordingDate
                WITH t, i1, i2
                // Get grantee from earlier instrument
                OPTIONAL MATCH (g1:Party)-[c1:CONVEYED]->(grantee1:Party)
                WHERE c1.instrumentId = i1.id
                WITH t, i1, i2, grantee1
                // Get grantor from later instrument
                OPTIONAL MATCH (grantor2:Party)-[c2:CONVEYED]->(g2:Party)
                WHERE c2.instrumentId = i2.id
                WITH i1, i2, grantee1, grantor2
                WHERE grantee1 IS NULL OR grantor2 IS NULL
                      OR grantee1.normalizedName <> grantor2.normalizedName
                RETURN i1.recordingInfo AS prior_instrument,
                       i1.recordingDate AS prior_date,
                       grantee1.name AS prior_grantee,
                       i2.recordingInfo AS later_instrument,
                       i2.recordingDate AS later_date,
                       grantor2.name AS later_grantor
                ORDER BY i1.recordingDate
                """,
                tract_key=tract_spatial_key,
            )
            return [dict(record) for record in result]

    def calculate_current_ownership(self, tract_spatial_key: str) -> list[dict]:
        """
        Calculate current ownership interests for a tract.
        Traces conveyances and multiplies interest fractions.
        """
        with self.driver.session(database=self.config.database) as session:
            result = session.run(
                """
                MATCH (t:Tract {spatialKey: $tract_key})<-[:COVERS]-(i:Instrument)
                WITH t, collect(i.id) AS instrumentIds
                MATCH path = (root:Party)-[conveyances:CONVEYED*]->(owner:Party)
                WHERE ALL(c IN conveyances WHERE c.instrumentId IN instrumentIds)
                  AND NOT EXISTS {
                    MATCH (owner)-[c2:CONVEYED]->(:Party)
                    WHERE c2.instrumentId IN instrumentIds
                  }
                RETURN owner.name AS current_owner,
                       owner.normalizedName AS normalized_name,
                       reduce(interest = 1.0, c IN conveyances |
                         interest * COALESCE(c.interestFraction, 1.0)
                       ) AS ownership_interest
                """,
                tract_key=tract_spatial_key,
            )
            return [dict(record) for record in result]

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_stats(self) -> dict:
        """Get graph statistics."""
        with self.driver.session(database=self.config.database) as session:
            result = session.run(
                """
                MATCH (p:Party) WITH count(p) AS parties
                MATCH (i:Instrument) WITH parties, count(i) AS instruments
                MATCH (t:Tract) WITH parties, instruments, count(t) AS tracts
                MATCH (s:Section) WITH parties, instruments, tracts, count(s) AS sections
                MATCH ()-[c:CONVEYED]->() WITH parties, instruments, tracts, sections, count(c) AS conveyances
                MATCH ()-[r:COVERS]->() WITH parties, instruments, tracts, sections, conveyances, count(r) AS covers
                RETURN parties, instruments, tracts, sections, conveyances, covers
                """
            )
            record = result.single()
            return dict(record) if record else {}

    def clear_all(self) -> None:
        """
        Delete all nodes and relationships.
        WARNING: This is destructive! Use only for testing.
        """
        with self.driver.session(database=self.config.database) as session:
            session.run("MATCH (n) DETACH DELETE n")
            logger.warning("Cleared all data from graph")


def build_graph_from_extraction(
    builder: GraphBuilder,
    body_extraction: dict,
    lease_records: list[dict],
    pdf_url: Optional[str] = None,
) -> dict:
    """
    Build graph nodes and relationships from extraction results.

    Args:
        builder: GraphBuilder instance
        body_extraction: Result from body_extractor
        lease_records: Results from table_extractor lease schedule parsing
        pdf_url: Optional URL to stored PDF

    Returns:
        Dictionary with created node IDs
    """
    from .normalizer import generate_spatial_key, normalize_party_name

    created = {
        "instrument_id": None,
        "party_ids": [],
        "tract_ids": [],
    }

    # Create instrument node
    recording = body_extraction.get("recording_info", {})
    dates = body_extraction.get("dates", {})
    confidence = body_extraction.get("confidence", {})

    instrument = InstrumentNode(
        document_type=body_extraction.get("document_type", "Unknown"),
        recording_info=f"Bk {recording.get('book')}/Pg {recording.get('page')}"
        if recording.get("book")
        else None,
        document_number=recording.get("document_number"),
        book=recording.get("book"),
        page=recording.get("page"),
        county=recording.get("county"),
        state=recording.get("state"),
        execution_date=_parse_date(dates.get("execution")),
        recording_date=_parse_date(dates.get("recording")),
        pdf_url=pdf_url,
        extraction_confidence=confidence.get("overall", 0.0),
    )
    created["instrument_id"] = builder.create_instrument(instrument)

    # Create party nodes
    parties = body_extraction.get("parties", {})
    grantor_ids = []
    grantee_ids = []

    for grantor_data in parties.get("grantors", []):
        name = grantor_data.get("name", "")
        if not name:
            continue
        normalized = normalize_party_name(name)
        party = PartyNode(
            name=name,
            normalized_name=normalized.normalized_name,
            entity_type=grantor_data.get("entity_type") or normalized.entity_type,
        )
        party_id = builder.create_party(party)
        grantor_ids.append(party_id)
        created["party_ids"].append(party_id)

    for grantee_data in parties.get("grantees", []):
        name = grantee_data.get("name", "")
        if not name:
            continue
        normalized = normalize_party_name(name)
        party = PartyNode(
            name=name,
            normalized_name=normalized.normalized_name,
            entity_type=grantee_data.get("entity_type") or normalized.entity_type,
        )
        party_id = builder.create_party(party)
        grantee_ids.append(party_id)
        created["party_ids"].append(party_id)

    # Create CONVEYED relationships
    interests = body_extraction.get("interests", {})
    for grantor_id in grantor_ids:
        for grantee_id in grantee_ids:
            rel = ConveyedRelationship(
                from_party_id=grantor_id,
                to_party_id=grantee_id,
                instrument_id=created["instrument_id"],
                interest_type=interests.get("interest_type"),
                interest_fraction=_parse_fraction(interests.get("conveyed_fraction")),
                reservations=interests.get("reserved"),
                conveyance_date=_parse_date(dates.get("execution")),
            )
            builder.create_conveyed_relationship(rel)

    # Create tracts from lease records
    for lease in lease_records:
        lands = lease.get("lands") or lease.get("legal")
        if not lands:
            continue

        spatial_result = generate_spatial_key(lands)
        if not spatial_result:
            continue

        tract = TractNode(
            spatial_key=spatial_result.key,
            section=spatial_result.section,
            township=spatial_result.township,
            range=spatial_result.range,
            county=spatial_result.county or lease.get("county"),
            state=spatial_result.state or lease.get("state"),
            aliquot_part=spatial_result.aliquot,
            raw_description=lands,
        )
        tract_id = builder.create_tract(tract)
        created["tract_ids"].append(tract_id)

        # Create COVERS relationship
        covers = CoversRelationship(
            instrument_id=created["instrument_id"],
            tract_id=tract_id,
            interest_conveyed=interests.get("conveyed"),
            interest_reserved=interests.get("reserved"),
        )
        builder.create_covers_relationship(covers)

        # Create Section node and IN_SECTION relationship
        section_key = f"{spatial_result.state}-{spatial_result.county}-{spatial_result.section}-{spatial_result.township}-{spatial_result.range}"
        section = SectionNode(
            section_key=section_key,
            section=spatial_result.section,
            township=spatial_result.township,
            range=spatial_result.range,
            county=spatial_result.county,
            state=spatial_result.state,
        )
        builder.create_section(section)
        builder.create_in_section_relationship(tract_id, section_key)

    logger.info(
        f"Built graph: 1 instrument, {len(created['party_ids'])} parties, "
        f"{len(created['tract_ids'])} tracts"
    )

    return created


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse date string to date object."""
    if not date_str:
        return None
    try:
        if isinstance(date_str, date):
            return date_str
        # Try ISO format
        return date.fromisoformat(date_str)
    except ValueError:
        return None


def _parse_fraction(fraction_str: Optional[str]) -> Optional[float]:
    """Parse fraction string to float."""
    if not fraction_str:
        return None
    try:
        # Handle percentage
        if "%" in fraction_str:
            return float(fraction_str.replace("%", "")) / 100.0
        # Handle fraction
        if "/" in fraction_str:
            parts = fraction_str.split("/")
            return float(parts[0]) / float(parts[1])
        return float(fraction_str)
    except (ValueError, ZeroDivisionError):
        return None


# CLI interface for testing
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("Neo4j Graph Builder")
    print("-" * 60)

    # Check environment
    uri = os.environ.get("NEO4J_URI")
    if not uri:
        print("Error: NEO4J_URI environment variable not set")
        print("\nRequired environment variables:")
        print("  NEO4J_URI - Neo4j connection URI (neo4j+s://xxxx.databases.neo4j.io)")
        print("  NEO4J_USER - Username (default: neo4j)")
        print("  NEO4J_PASSWORD - Password")
        sys.exit(1)

    with GraphBuilder() as builder:
        # Test connection
        print("\nTesting connection...")
        if builder.verify_connection():
            print("Connected successfully!")
        else:
            print("Connection failed!")
            sys.exit(1)

        # Create schema
        print("\nCreating schema...")
        builder.create_schema()

        # Get stats
        print("\nGraph statistics:")
        stats = builder.get_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")
