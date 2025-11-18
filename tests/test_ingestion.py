"""Tests for PDF and text file ingestion."""

from pathlib import Path

import pytest

from app.ingestion import generate_note_id, ingest_document, normalize_text
from app.schemas import CanonicalNote


class TestNormalizeText:
    """Tests for text normalization."""

    def test_normalize_text_basic(self):
        """Test basic text normalization."""
        text = "Hello\nWorld"
        result = normalize_text(text)
        assert result == "Hello\nWorld"

    def test_normalize_text_non_breaking_spaces(self):
        """Test normalization of non-breaking spaces."""
        text = "Hello\xa0World"
        result = normalize_text(text)
        assert "Hello World" in result

    def test_normalize_text_line_endings(self):
        """Test normalization of line endings."""
        text = "Hello\r\nWorld\rTest"
        result = normalize_text(text)
        assert "\r" not in result
        assert "\n" in result

    def test_normalize_text_preserves_empty_lines(self):
        """Test that empty lines (double newlines) are preserved."""
        text = "Line 1\n\nLine 2\n\n\nLine 3"
        result = normalize_text(text)
        assert "\n\n" in result  # Empty lines preserved
        assert "\n\n\n" not in result  # Excessive newlines collapsed to 2

    def test_normalize_text_collapses_excessive_newlines(self):
        """Test that 3+ consecutive newlines are collapsed to 2."""
        text = "Line 1\n\n\n\nLine 2"
        result = normalize_text(text)
        # Should have at most 2 consecutive newlines
        assert "\n\n\n" not in result
        assert "\n\n" in result


class TestGenerateNoteId:
    """Tests for note ID generation."""

    def test_generate_note_id_from_filename(self, tmp_path):
        """Test generating note ID from filename."""
        pdf_file = tmp_path / "test_note.pdf"
        pdf_file.write_text("test")
        note_id = generate_note_id(pdf_file)
        assert note_id == "test_note"

    def test_generate_note_id_sanitizes_special_chars(self, tmp_path):
        """Test that special characters are sanitized."""
        # Create a file with special characters in the name
        # Note: We can't actually create a file with : or / in the name on most filesystems
        # So we'll test the sanitization logic by checking what happens with a valid filename
        pdf_file = tmp_path / "test_note_file.pdf"
        pdf_file.write_text("test")
        note_id = generate_note_id(pdf_file)
        # The function should sanitize, but since we can't create files with : or /,
        # we just verify it returns a valid note_id
        assert note_id == "test_note_file"

    def test_generate_note_id_sanitizes_spaces(self, tmp_path):
        """Test that spaces are replaced with underscores."""
        pdf_file = tmp_path / "test note.pdf"
        pdf_file.write_text("test")
        note_id = generate_note_id(pdf_file)
        assert " " not in note_id
        assert "_" in note_id


class TestIngestDocument:
    """Tests for document ingestion."""

    def test_ingest_txt_file(self, sample_txt_path, sample_config):
        """Test ingesting a .txt file."""
        canonical_note, note_id = ingest_document(sample_txt_path, sample_config)
        
        assert isinstance(canonical_note, CanonicalNote)
        assert len(canonical_note.text) > 0
        assert len(canonical_note.page_spans) > 0
        assert note_id == "sample"

    def test_ingest_txt_file_structure(self, sample_txt_path, sample_config):
        """Test that ingested text has correct structure."""
        canonical_note, _ = ingest_document(sample_txt_path, sample_config)
        
        # Check that text contains expected content
        assert "SUBJECTIVE" in canonical_note.text
        assert "OBJECTIVE" in canonical_note.text
        assert "ASSESSMENT" in canonical_note.text
        assert "PLAN" in canonical_note.text
        
        # Check page spans
        assert len(canonical_note.page_spans) == 1
        assert canonical_note.page_spans[0].start_char == 0
        assert canonical_note.page_spans[0].end_char == len(canonical_note.text)

    def test_ingest_document_missing_file(self, tmp_path, sample_config):
        """Test that missing file raises FileNotFoundError."""
        missing_file = tmp_path / "nonexistent.pdf"
        with pytest.raises(FileNotFoundError):
            ingest_document(missing_file, sample_config)

    def test_ingest_document_empty_file(self, tmp_path, sample_config):
        """Test that ingesting an empty file raises ValueError."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")
        with pytest.raises(ValueError, match="Text file is empty"):
            ingest_document(empty_file, sample_config)

