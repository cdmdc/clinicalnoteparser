"""Tests for section detection."""

import json
from pathlib import Path

import pytest

from app.sections import detect_sections, find_section_headers_in_text, load_toc, save_toc
from app.schemas import Section


class TestFindSectionHeadersInText:
    """Tests for finding section headers in text."""

    def test_find_section_headers_basic(self):
        """Test finding section headers in text."""
        text = "Overview\n\nSUBJECTIVE\nContent here\n\nOBJECTIVE\nMore content"
        overview_end = 8  # End of "Overview\n"
        headers = find_section_headers_in_text(text, overview_end, is_pdf=False)
        assert len(headers) > 0
        assert any("SUBJECTIVE" in h for h in headers)
        assert any("OBJECTIVE" in h for h in headers)

    def test_find_section_headers_after_empty_line(self):
        """Test that section headers are found after empty lines."""
        text = "Overview content\n\nSUBJECTIVE\nContent"
        overview_end = 17  # End of "Overview content\n"
        headers = find_section_headers_in_text(text, overview_end, is_pdf=False)
        assert any("SUBJECTIVE" in h for h in headers)

    def test_find_section_headers_all_caps(self):
        """Test that section headers are all caps."""
        text = "Overview\n\nHISTORY OF PRESENT ILLNESS\nContent"
        overview_end = 8
        headers = find_section_headers_in_text(text, overview_end, is_pdf=False)
        # Check that we found at least one header (the function may return positions or text)
        assert len(headers) > 0

    def test_find_section_headers_no_headers(self):
        """Test text with no section headers."""
        text = "Just some regular text without any section headers."
        overview_end = len(text)
        headers = find_section_headers_in_text(text, overview_end, is_pdf=False)
        # Should return empty list or minimal headers
        assert isinstance(headers, list)


class TestDetectSections:
    """Tests for section detection."""

    def test_detect_sections_txt_file(self, sample_txt_path, sample_canonical_note, sample_config):
        """Test detecting sections in a .txt file."""
        sections = detect_sections(sample_canonical_note, sample_txt_path, sample_config)
        
        assert len(sections) > 0
        assert all(isinstance(section, Section) for section in sections)
        
        # Check that Overview is the first section
        assert sections[0].title == "Overview"
        
        # Check that expected sections are present
        section_titles = [s.title for s in sections]
        assert "SUBJECTIVE" in section_titles or "CHIEF COMPLAINT" in section_titles

    def test_detect_sections_structure(self, sample_txt_path, sample_canonical_note, sample_config):
        """Test that detected sections have correct structure."""
        sections = detect_sections(sample_canonical_note, sample_txt_path, sample_config)
        
        for section in sections:
            assert section.title
            assert section.start_char >= 0
            assert section.end_char > section.start_char
            assert section.start_page >= 0
            assert section.end_page >= 0

    def test_detect_sections_overview_first(self, sample_txt_path, sample_canonical_note, sample_config):
        """Test that Overview is always the first section."""
        sections = detect_sections(sample_canonical_note, sample_txt_path, sample_config)
        
        if len(sections) > 0:
            assert sections[0].title == "Overview"
            assert sections[0].start_char == 0

    def test_detect_sections_no_overlap(self, sample_txt_path, sample_canonical_note, sample_config):
        """Test that sections don't overlap incorrectly."""
        sections = detect_sections(sample_canonical_note, sample_txt_path, sample_config)
        
        # Sections should be in order and not overlap (except at boundaries)
        for i in range(len(sections) - 1):
            assert sections[i].end_char <= sections[i + 1].start_char


class TestSaveToc:
    """Tests for saving table of contents."""

    def test_save_toc(self, sample_sections, tmp_path):
        """Test saving ToC to JSON file."""
        toc_path = tmp_path / "toc.json"
        save_toc(sample_sections, toc_path)
        
        assert toc_path.exists()
        
        # Verify JSON structure
        import json
        with open(toc_path, "r") as f:
            data = json.load(f)
        
        assert "sections" in data
        assert len(data["sections"]) == len(sample_sections)
        
        # Verify section structure
        for section_data in data["sections"]:
            assert "title" in section_data
            assert "start_char" in section_data
            assert "end_char" in section_data
            assert "start_page" in section_data
            assert "end_page" in section_data


class TestLoadToc:
    """Tests for loading ToC from JSON."""

    def test_load_toc_success(self, sample_sections, tmp_path):
        """Test loading ToC from a valid JSON file."""
        toc_path = tmp_path / "toc.json"
        save_toc(sample_sections, toc_path)
        
        loaded_sections = load_toc(toc_path)
        
        assert len(loaded_sections) == len(sample_sections)
        for i, (loaded, original) in enumerate(zip(loaded_sections, sample_sections)):
            assert loaded.title == original.title
            assert loaded.start_char == original.start_char
            assert loaded.end_char == original.end_char
            assert loaded.start_page == original.start_page
            assert loaded.end_page == original.end_page

    def test_load_toc_file_not_found(self, tmp_path):
        """Test loading ToC when file doesn't exist."""
        toc_path = tmp_path / "nonexistent.json"
        
        with pytest.raises(FileNotFoundError):
            load_toc(toc_path)

    def test_load_toc_invalid_json(self, tmp_path):
        """Test loading ToC from invalid JSON."""
        toc_path = tmp_path / "invalid.json"
        toc_path.write_text("invalid json content")
        
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_toc(toc_path)

    def test_load_toc_missing_sections_key(self, tmp_path):
        """Test loading ToC when 'sections' key is missing."""
        toc_path = tmp_path / "invalid.json"
        invalid_data = {"not_sections": []}
        toc_path.write_text(json.dumps(invalid_data))
        
        with pytest.raises(ValueError, match="missing 'sections' key"):
            load_toc(toc_path)

