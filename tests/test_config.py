"""Tests for configuration management."""

import os
from pathlib import Path

import pytest

from app.config import Config, get_config


class TestConfig:
    """Tests for Config class."""

    def test_default_config(self):
        """Test creating Config with default values."""
        config = Config()
        assert config.model_name == "llama3"
        assert config.temperature == 0.1
        assert config.chunk_size == 1500
        assert config.chunk_overlap == 200
        assert config.max_paragraph_size == 3000
        assert config.min_sections_for_success == 2
        assert config.enable_llm_fallback is True
        assert config.max_retries == 3
        assert config.max_chunk_failure_rate == 0.3
        assert config.max_pages_warning == 30

    def test_config_from_env(self, monkeypatch):
        """Test creating Config from environment variables."""
        monkeypatch.setenv("CLINICAL_NOTE_MODEL", "llama3.2")
        monkeypatch.setenv("CLINICAL_NOTE_TEMPERATURE", "0.5")
        monkeypatch.setenv("CLINICAL_NOTE_CHUNK_SIZE", "2000")
        monkeypatch.setenv("CLINICAL_NOTE_CHUNK_OVERLAP", "300")
        
        config = Config.from_env()
        assert config.model_name == "llama3.2"
        assert config.temperature == 0.5
        assert config.chunk_size == 2000
        assert config.chunk_overlap == 300

    def test_config_validation_chunk_overlap(self):
        """Test that chunk_overlap must be less than chunk_size."""
        with pytest.raises(ValueError, match="chunk_overlap must be less than chunk_size"):
            Config(chunk_size=1000, chunk_overlap=1000)

    def test_config_validation_chunk_overlap_equal(self):
        """Test that chunk_overlap cannot equal chunk_size."""
        with pytest.raises(ValueError, match="chunk_overlap must be less than chunk_size"):
            Config(chunk_size=1000, chunk_overlap=1000)

    def test_config_output_dir_conversion(self):
        """Test that output_dir string is converted to Path."""
        config = Config(output_dir="test_results")
        assert isinstance(config.output_dir, Path)
        assert config.output_dir.name == "test_results"

    def test_get_config_singleton(self):
        """Test that get_config() returns a singleton."""
        # Reset the global config
        import app.config
        app.config._config = None
        
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_config_temperature_bounds(self):
        """Test that temperature is within valid bounds."""
        # Valid temperatures
        config1 = Config(temperature=0.0)
        assert config1.temperature == 0.0
        
        config2 = Config(temperature=2.0)
        assert config2.temperature == 2.0
        
        # Invalid temperatures should raise ValidationError
        with pytest.raises(Exception):  # Pydantic validation error
            Config(temperature=-0.1)
        
        with pytest.raises(Exception):  # Pydantic validation error
            Config(temperature=2.1)

