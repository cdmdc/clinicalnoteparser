"""Pydantic models for clinical note parsing pipeline."""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class PageSpan(BaseModel):
    """Represents a character span mapping to a page in the source document."""

    start_char: int = Field(..., description="Starting character position (inclusive)")
    end_char: int = Field(..., description="Ending character position (exclusive)")
    page_index: int = Field(..., description="Zero-based page index")

    @field_validator("end_char")
    @classmethod
    def validate_end_after_start(cls, v: int, info) -> int:
        """Ensure end_char is greater than start_char."""
        if "start_char" in info.data and v <= info.data["start_char"]:
            raise ValueError("end_char must be greater than start_char")
        return v


class CanonicalNote(BaseModel):
    """Canonical text representation of a clinical note with page mapping."""

    text: str = Field(..., description="Full normalized text content")
    page_spans: List[PageSpan] = Field(
        ..., description="List of page spans mapping character positions to pages"
    )


class Section(BaseModel):
    """Represents a section in the document table of contents."""

    title: str = Field(..., description="Section title/header")
    start_char: int = Field(..., description="Starting character position (inclusive)")
    end_char: int = Field(..., description="Ending character position (exclusive)")
    start_page: int = Field(..., description="Starting page index (zero-based)")
    end_page: int = Field(..., description="Ending page index (zero-based)")

    @field_validator("end_char")
    @classmethod
    def validate_end_after_start(cls, v: int, info) -> int:
        """Ensure end_char is greater than start_char."""
        if "start_char" in info.data and v <= info.data["start_char"]:
            raise ValueError("end_char must be greater than start_char")
        return v


class Chunk(BaseModel):
    """Represents a text chunk for LLM processing."""

    chunk_id: str = Field(..., description="Unique identifier for the chunk")
    text: str = Field(..., description="Chunk text content")
    start_char: int = Field(..., description="Starting character position (inclusive)")
    end_char: int = Field(..., description="Ending character position (exclusive)")
    section_title: str = Field(..., description="Title of the section this chunk belongs to")

    @field_validator("end_char")
    @classmethod
    def validate_end_after_start(cls, v: int, info) -> int:
        """Ensure end_char is greater than start_char."""
        if "start_char" in info.data and v <= info.data["start_char"]:
            raise ValueError("end_char must be greater than start_char")
        return v


class Citation(BaseModel):
    """Represents a citation linking a fact to source text."""

    start_char: int = Field(..., description="Starting character position (inclusive, global)")
    end_char: int = Field(..., description="Ending character position (exclusive, global)")
    page: int = Field(..., description="Page number (one-based)")

    @field_validator("end_char")
    @classmethod
    def validate_end_after_start(cls, v: int, info) -> int:
        """Ensure end_char is greater than start_char."""
        if "start_char" in info.data and v <= info.data["start_char"]:
            raise ValueError("end_char must be greater than start_char")
        return v


class SpanFact(BaseModel):
    """Represents a fact extracted from text with citation spans."""

    fact_text: str = Field(..., description="The extracted fact text")
    category: str = Field(..., description="Category of fact (e.g., 'problem', 'medication', 'allergy')")
    citations: List[Citation] = Field(default_factory=list, description="List of citations linking to source text")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score [0, 1]")
    uncertainty_note: Optional[str] = Field(default=None, description="Note explaining uncertainty if confidence is low")


class ChunkExtraction(BaseModel):
    """Represents facts extracted from a single chunk."""

    chunk_id: str = Field(..., description="ID of the chunk this extraction is from")
    facts: List[SpanFact] = Field(default_factory=list, description="List of facts extracted from the chunk")


class PatientSnapshot(BaseModel):
    """Represents a patient snapshot with basic demographics."""

    age: Optional[str] = Field(default=None, description="Patient age (as string, e.g., '45', 'unknown')")
    sex: Optional[str] = Field(default=None, description="Patient sex/gender (e.g., 'M', 'F', 'unknown')")
    summary: Optional[str] = Field(default=None, description="Brief patient summary")


class Summary(BaseModel):
    """Represents the complete summary of a clinical note."""

    patient_snapshot: PatientSnapshot = Field(..., description="Patient demographics and summary")
    problems: List[SpanFact] = Field(default_factory=list, description="List of problems/diagnoses")
    medications: List[SpanFact] = Field(default_factory=list, description="List of medications")
    allergies: List[SpanFact] = Field(default_factory=list, description="List of allergies")
    history: List[SpanFact] = Field(default_factory=list, description="List of historical facts")
    exam: List[SpanFact] = Field(default_factory=list, description="List of examination findings")
    labs_imaging: List[SpanFact] = Field(default_factory=list, description="List of lab results and imaging findings")
    other_facts: List[SpanFact] = Field(default_factory=list, description="Other facts that don't fit above categories")


class SummaryItem(BaseModel):
    """Represents a single item in a summary section with its source citation."""

    text: str = Field(..., description="The item text/content")
    source: str = Field(..., description="Source citation (e.g., 'chunk_0:10-50' or 'Section Name, paragraph X')")


class StructuredSummary(BaseModel):
    """Structured summary matching the text summary format with 7 sections."""

    patient_snapshot: List[SummaryItem] = Field(
        default_factory=list, description="Patient snapshot items (age, sex, overview)"
    )
    key_problems: List[SummaryItem] = Field(
        default_factory=list, description="Key problems, diagnoses, or chief complaints"
    )
    pertinent_history: List[SummaryItem] = Field(
        default_factory=list, description="Relevant medical, family, and social history"
    )
    medicines_allergies: List[SummaryItem] = Field(
        default_factory=list, description="Current medications and known allergies"
    )
    objective_findings: List[SummaryItem] = Field(
        default_factory=list, description="Physical examination findings, vital signs, clinical observations"
    )
    labs_imaging: List[SummaryItem] = Field(
        default_factory=list, description="Laboratory results or imaging findings"
    )
    concise_assessment: List[SummaryItem] = Field(
        default_factory=list, description="Assessment, diagnosis, treatment plans, follow-ups, and next steps"
    )

