"""Tests for Pydantic schema models."""

import json
import pytest
from pydantic import ValidationError

from app.schemas import (
    CanonicalNote,
    Chunk,
    Citation,
    PageSpan,
    Section,
)


class TestPageSpan:
    """Tests for PageSpan model."""

    def test_valid_page_span(self):
        """Test creating a valid PageSpan."""
        span = PageSpan(start_char=0, end_char=100, page_index=0)
        assert span.start_char == 0
        assert span.end_char == 100
        assert span.page_index == 0

    def test_invalid_page_span_end_before_start(self):
        """Test that end_char must be greater than start_char."""
        with pytest.raises(ValidationError) as exc_info:
            PageSpan(start_char=100, end_char=50, page_index=0)
        assert "end_char must be greater than start_char" in str(exc_info.value)

    def test_invalid_page_span_equal_start_end(self):
        """Test that end_char cannot equal start_char."""
        with pytest.raises(ValidationError) as exc_info:
            PageSpan(start_char=100, end_char=100, page_index=0)
        assert "end_char must be greater than start_char" in str(exc_info.value)


class TestCanonicalNote:
    """Tests for CanonicalNote model."""

    def test_valid_canonical_note(self):
        """Test creating a valid CanonicalNote."""
        text = "Sample text"
        page_spans = [PageSpan(start_char=0, end_char=len(text), page_index=0)]
        note = CanonicalNote(text=text, page_spans=page_spans)
        assert note.text == text
        assert len(note.page_spans) == 1

    def test_canonical_note_serialization(self):
        """Test serializing CanonicalNote to dict."""
        text = "Sample text"
        page_spans = [PageSpan(start_char=0, end_char=len(text), page_index=0)]
        note = CanonicalNote(text=text, page_spans=page_spans)
        data = note.model_dump()
        assert data["text"] == text
        assert len(data["page_spans"]) == 1


class TestSection:
    """Tests for Section model."""

    def test_valid_section(self):
        """Test creating a valid Section."""
        section = Section(
            title="SUBJECTIVE",
            start_char=0,
            end_char=100,
            start_page=0,
            end_page=0,
        )
        assert section.title == "SUBJECTIVE"
        assert section.start_char == 0
        assert section.end_char == 100

    def test_invalid_section_end_before_start(self):
        """Test that end_char must be greater than start_char."""
        with pytest.raises(ValidationError) as exc_info:
            Section(
                title="SUBJECTIVE",
                start_char=100,
                end_char=50,
                start_page=0,
                end_page=0,
            )
        assert "end_char must be greater than start_char" in str(exc_info.value)

    def test_section_serialization(self):
        """Test serializing Section to dict."""
        section = Section(
            title="SUBJECTIVE",
            start_char=0,
            end_char=100,
            start_page=0,
            end_page=0,
        )
        data = section.model_dump()
        assert data["title"] == "SUBJECTIVE"
        assert data["start_char"] == 0
        assert data["end_char"] == 100


class TestChunk:
    """Tests for Chunk model."""

    def test_valid_chunk(self):
        """Test creating a valid Chunk."""
        chunk = Chunk(
            chunk_id="chunk_0",
            text="Sample chunk text",
            start_char=0,
            end_char=17,
            section_title="SUBJECTIVE",
        )
        assert chunk.chunk_id == "chunk_0"
        assert chunk.text == "Sample chunk text"
        assert chunk.section_title == "SUBJECTIVE"

    def test_invalid_chunk_end_before_start(self):
        """Test that end_char must be greater than start_char."""
        with pytest.raises(ValidationError) as exc_info:
            Chunk(
                chunk_id="chunk_0",
                text="Sample",
                start_char=10,
                end_char=5,
                section_title="SUBJECTIVE",
            )
        assert "end_char must be greater than start_char" in str(exc_info.value)

    def test_chunk_serialization(self):
        """Test serializing Chunk to dict."""
        chunk = Chunk(
            chunk_id="chunk_0",
            text="Sample chunk text",
            start_char=0,
            end_char=17,
            section_title="SUBJECTIVE",
        )
        data = chunk.model_dump()
        assert data["chunk_id"] == "chunk_0"
        assert data["text"] == "Sample chunk text"


class TestCitation:
    """Tests for Citation model."""

    def test_valid_citation(self):
        """Test creating a valid Citation."""
        citation = Citation(start_char=0, end_char=100, page=1)
        assert citation.start_char == 0
        assert citation.end_char == 100
        assert citation.page == 1

    def test_invalid_citation_end_before_start(self):
        """Test that end_char must be greater than start_char."""
        with pytest.raises(ValidationError) as exc_info:
            Citation(start_char=100, end_char=50, page=1)
        assert "end_char must be greater than start_char" in str(exc_info.value)

    def test_citation_serialization(self):
        """Test serializing Citation to dict."""
        citation = Citation(start_char=0, end_char=100, page=1)
        data = citation.model_dump()
        assert data["start_char"] == 0
        assert data["end_char"] == 100
        assert data["page"] == 1

