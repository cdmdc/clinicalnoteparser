"""Pydantic models for clinical note parsing pipeline."""

from typing import List

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

