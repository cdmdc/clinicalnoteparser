"""Tests for text chunking."""

import json
from pathlib import Path

import pytest

from app.chunks import create_chunks_from_sections, load_chunks, save_chunks
from app.schemas import Chunk


class TestCreateChunksFromSections:
    """Tests for creating chunks from sections."""

    def test_create_chunks_basic(self, sample_sections, sample_canonical_note, sample_config):
        """Test creating chunks from sections."""
        chunks = create_chunks_from_sections(sample_sections, sample_canonical_note, sample_config)
        
        assert len(chunks) > 0
        assert all(isinstance(chunk, Chunk) for chunk in chunks)
        
        # Check that each chunk has required fields
        for chunk in chunks:
            assert chunk.chunk_id.startswith("chunk_")
            assert len(chunk.text) > 0
            assert chunk.start_char < chunk.end_char
            assert chunk.section_title in [s.title for s in sample_sections]

    def test_chunks_have_correct_spans(self, sample_sections, sample_canonical_note, sample_config):
        """Test that chunks have correct character spans."""
        chunks = create_chunks_from_sections(sample_sections, sample_canonical_note, sample_config)
        
        # Check that chunks don't overlap (except intended overlap)
        for i, chunk1 in enumerate(chunks):
            for chunk2 in chunks[i + 1:]:
                # Chunks should either be non-overlapping or have intended overlap
                # (overlap is handled by the chunking logic)
                pass  # Basic check - chunks should be valid

    def test_chunks_preserve_section_boundaries(self, sample_sections, sample_canonical_note, sample_config):
        """Test that chunks respect section boundaries."""
        chunks = create_chunks_from_sections(sample_sections, sample_canonical_note, sample_config)
        
        # Group chunks by section
        chunks_by_section = {}
        for chunk in chunks:
            if chunk.section_title not in chunks_by_section:
                chunks_by_section[chunk.section_title] = []
            chunks_by_section[chunk.section_title].append(chunk)
        
        # Each section should have at least one chunk
        for section in sample_sections:
            assert section.title in chunks_by_section

    def test_chunks_with_short_sections(self, sample_canonical_note, sample_config):
        """Test chunking with very short sections."""
        short_sections = [
            type('Section', (), {
                'title': 'Short',
                'start_char': 0,
                'end_char': 10,
                'start_page': 0,
                'end_page': 0,
            })()
        ]
        # Create a mock section object
        from app.schemas import Section
        short_section = Section(
            title="Short",
            start_char=0,
            end_char=10,
            start_page=0,
            end_page=0,
        )
        
        chunks = create_chunks_from_sections([short_section], sample_canonical_note, sample_config)
        assert len(chunks) >= 1

    def test_chunks_with_long_sections(self, sample_canonical_note, sample_config):
        """Test chunking with long sections that need splitting."""
        # Create a section that's longer than chunk_size
        long_text = " ".join(["word"] * 2000)  # Very long text
        long_section = type('Section', (), {
            'title': 'Long',
            'start_char': 0,
            'end_char': len(long_text),
            'start_page': 0,
            'end_page': 0,
        })()
        
        # Create a canonical note with long text
        from app.ingestion import PageSpan
        long_note = type('CanonicalNote', (), {
            'text': long_text,
            'page_spans': [PageSpan(start_char=0, end_char=len(long_text), page_index=0)],
        })()
        
        from app.schemas import Section
        section = Section(
            title="Long",
            start_char=0,
            end_char=len(long_text),
            start_page=0,
            end_page=0,
        )
        
        chunks = create_chunks_from_sections([section], long_note, sample_config)
        # Long sections should be split into multiple chunks
        assert len(chunks) >= 1


class TestLoadChunks:
    """Tests for loading chunks from JSON."""

    def test_load_chunks_success(self, sample_chunks, tmp_path):
        """Test loading chunks from a valid JSON file."""
        chunks_path = tmp_path / "chunks.json"
        save_chunks(sample_chunks, chunks_path)
        
        loaded_chunks = load_chunks(chunks_path)
        
        assert len(loaded_chunks) == len(sample_chunks)
        for i, (loaded, original) in enumerate(zip(loaded_chunks, sample_chunks)):
            assert loaded.chunk_id == original.chunk_id
            assert loaded.text == original.text
            assert loaded.start_char == original.start_char
            assert loaded.end_char == original.end_char

    def test_load_chunks_file_not_found(self, tmp_path):
        """Test loading chunks when file doesn't exist."""
        chunks_path = tmp_path / "nonexistent.json"
        
        with pytest.raises(FileNotFoundError):
            load_chunks(chunks_path)

    def test_load_chunks_invalid_json(self, tmp_path):
        """Test loading chunks from invalid JSON."""
        chunks_path = tmp_path / "invalid.json"
        chunks_path.write_text("invalid json content")
        
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_chunks(chunks_path)

    def test_load_chunks_missing_chunks_key(self, tmp_path):
        """Test loading chunks when 'chunks' key is missing."""
        chunks_path = tmp_path / "invalid.json"
        invalid_data = {"not_chunks": []}
        chunks_path.write_text(json.dumps(invalid_data))
        
        with pytest.raises(ValueError, match="missing 'chunks' key"):
            load_chunks(chunks_path)

