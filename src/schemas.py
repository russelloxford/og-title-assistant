"""
Pydantic schemas for document extraction data validation.

These schemas define the structure of extracted data from oil & gas documents
and provide validation for the JSON output from Claude.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class PartyInfo(BaseModel):
    """Information about a party (grantor/grantee/assignor/assignee)."""

    name: str = Field(..., description="Full name of the party")
    address: Optional[str] = Field(None, description="Address if available")
    role: Optional[str] = Field(
        None, description="Role in transaction (e.g., 'Grantor', 'Assignor')"
    )
    entity_type: Optional[str] = Field(
        None,
        description="Entity type: individual, corporation, llc, trust, estate, etc.",
    )


class PartiesInfo(BaseModel):
    """All parties involved in the document."""

    grantors: list[PartyInfo] = Field(
        default_factory=list,
        description="List of grantors/assignors/lessors",
    )
    grantees: list[PartyInfo] = Field(
        default_factory=list,
        description="List of grantees/assignees/lessees",
    )


class DatesInfo(BaseModel):
    """Important dates from the document."""

    execution: Optional[date] = Field(None, description="Date document was executed/signed")
    recording: Optional[date] = Field(None, description="Date recorded with county")
    effective: Optional[date] = Field(None, description="Effective date if different")
    expiration: Optional[date] = Field(None, description="Expiration date (for leases)")

    @field_validator("execution", "recording", "effective", "expiration", mode="before")
    @classmethod
    def parse_date(cls, v):
        """Parse date from string if needed."""
        if v is None or v == "":
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            # Handle various date formats
            from datetime import datetime

            for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"]:
                try:
                    return datetime.strptime(v, fmt).date()
                except ValueError:
                    continue
            return None
        return None


class RecordingInfo(BaseModel):
    """Recording/filing information."""

    book: Optional[str] = Field(None, description="Book number")
    page: Optional[str] = Field(None, description="Page number")
    document_number: Optional[str] = Field(
        None, description="Document/instrument number"
    )
    reception_number: Optional[str] = Field(None, description="Reception number")
    county: Optional[str] = Field(None, description="County where recorded")
    state: Optional[str] = Field(None, description="State where recorded")


class InterestsInfo(BaseModel):
    """Interest conveyed and reserved."""

    conveyed: Optional[str] = Field(
        None,
        description="Description of interest conveyed",
    )
    conveyed_fraction: Optional[str] = Field(
        None,
        description="Fractional interest conveyed (e.g., '1/2', '100%')",
    )
    reserved: Optional[str] = Field(
        None,
        description="Description of interest reserved",
    )
    reserved_fraction: Optional[str] = Field(
        None,
        description="Fractional interest reserved (e.g., '1/16 ORRI')",
    )
    interest_type: Optional[str] = Field(
        None,
        description="Type: working interest, royalty, ORRI, mineral, etc.",
    )


class DepthSeveranceInfo(BaseModel):
    """Depth severance clause details."""

    has_depth_severance: bool = False
    shallow_depth: Optional[str] = Field(None, description="Shallow zone depth limit")
    deep_depth: Optional[str] = Field(None, description="Deep zone depth limit")
    formation: Optional[str] = Field(None, description="Formation name if specified")
    description: Optional[str] = Field(None, description="Full clause description")


class ClausesInfo(BaseModel):
    """Important clauses found in the document."""

    pugh_clause: bool = Field(False, description="Whether Pugh clause is present")
    pugh_description: Optional[str] = Field(None, description="Pugh clause details")
    depth_severance: Optional[DepthSeveranceInfo] = Field(
        None, description="Depth severance details"
    )
    continuous_development: bool = Field(
        False, description="Whether continuous development clause is present"
    )
    continuous_development_description: Optional[str] = Field(
        None, description="Continuous development clause details"
    )
    surface_damages: bool = Field(
        False, description="Whether surface damages clause is present"
    )
    pooling_unitization: bool = Field(
        False, description="Whether pooling/unitization clause is present"
    )
    other_clauses: list[str] = Field(
        default_factory=list, description="Other notable clauses"
    )


class LeaseTermsInfo(BaseModel):
    """Lease-specific terms (for Oil & Gas Leases)."""

    primary_term: Optional[str] = Field(None, description="Primary term (e.g., '3 years')")
    royalty_fraction: Optional[str] = Field(
        None, description="Royalty fraction (e.g., '1/8', '3/16')"
    )
    bonus_amount: Optional[str] = Field(None, description="Bonus consideration")
    delay_rental: Optional[str] = Field(None, description="Delay rental amount")
    shut_in_royalty: Optional[str] = Field(None, description="Shut-in royalty provisions")


class ExhibitReference(BaseModel):
    """Reference to an exhibit attached to the document."""

    name: str = Field(..., description="Exhibit name (e.g., 'Exhibit A')")
    description: Optional[str] = Field(
        None, description="Description of exhibit contents"
    )
    exhibit_type: Optional[str] = Field(
        None, description="Type: schedule, legal_description, plat, etc."
    )


class LegalDescriptionInfo(BaseModel):
    """Legal description from the document body."""

    raw_description: Optional[str] = Field(
        None, description="Full legal description text"
    )
    section: Optional[str] = Field(None, description="Section number")
    township: Optional[str] = Field(None, description="Township")
    range: Optional[str] = Field(None, description="Range")
    county: Optional[str] = Field(None, description="County")
    state: Optional[str] = Field(None, description="State")
    aliquot_parts: list[str] = Field(
        default_factory=list, description="Aliquot parts (NW/4, S/2, etc.)"
    )
    acres: Optional[float] = Field(None, description="Acreage if specified")


class ConfidenceScores(BaseModel):
    """Confidence scores for extraction quality."""

    overall: float = Field(
        0.0, ge=0.0, le=1.0, description="Overall extraction confidence"
    )
    parties: float = Field(0.0, ge=0.0, le=1.0, description="Party extraction confidence")
    dates: float = Field(0.0, ge=0.0, le=1.0, description="Date extraction confidence")
    recording_info: float = Field(
        0.0, ge=0.0, le=1.0, description="Recording info confidence"
    )
    interests: float = Field(
        0.0, ge=0.0, le=1.0, description="Interest extraction confidence"
    )


class DocumentExtraction(BaseModel):
    """Complete extraction result from a document body."""

    # Document identification
    document_type: str = Field(
        ...,
        description="Type: Deed, Assignment, Oil and Gas Lease, Mortgage, etc.",
    )
    document_title: Optional[str] = Field(
        None, description="Title as it appears on document"
    )

    # Core data
    parties: PartiesInfo = Field(default_factory=PartiesInfo)
    dates: DatesInfo = Field(default_factory=DatesInfo)
    recording_info: RecordingInfo = Field(default_factory=RecordingInfo)
    interests: InterestsInfo = Field(default_factory=InterestsInfo)

    # Clauses and terms
    clauses: ClausesInfo = Field(default_factory=ClausesInfo)
    lease_terms: Optional[LeaseTermsInfo] = Field(
        None, description="Lease terms (only for leases)"
    )

    # Legal description (if in body, not exhibits)
    legal_description: Optional[LegalDescriptionInfo] = Field(
        None, description="Legal description if in document body"
    )

    # Exhibit references
    exhibit_references: list[ExhibitReference] = Field(
        default_factory=list,
        description="References to attached exhibits",
    )

    # Quality metrics
    confidence: ConfidenceScores = Field(default_factory=ConfidenceScores)

    # Raw extraction notes
    extraction_notes: list[str] = Field(
        default_factory=list,
        description="Notes about extraction quality or issues",
    )
