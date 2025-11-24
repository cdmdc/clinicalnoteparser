"""Configuration management for the clinical note parser."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

load_dotenv()


class Config(BaseModel):
    """Configuration settings for the clinical note parser pipeline."""

    model_name: str = Field(default="qwen2.5:7b", description="Ollama model name")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0, description="Temperature for LLM")
    ollama_base_url: Optional[str] = Field(default="http://localhost:11434", description="Ollama base URL")
    chunk_size: int = Field(default=1500, gt=0, description="Target chunk size")
    chunk_overlap: int = Field(default=200, ge=0, description="Overlap between chunks")
    max_paragraph_size: int = Field(default=3000, gt=0, description="Max paragraph size")
    min_sections_for_success: int = Field(default=2, ge=1, description="Min sections for success")
    enable_llm_fallback: bool = Field(default=True, description="Enable LLM fallback")
    max_retries: int = Field(default=2, ge=0, description="Max retries for LLM calls")
    max_chunk_failure_rate: float = Field(default=0.3, ge=0.0, le=1.0, description="Max chunk failure rate")
    max_pages_warning: int = Field(default=30, gt=0, description="Page count warning threshold")
    output_dir: Path = Field(default=Path("results"), description="Output directory")

    @field_validator("chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, v: int, info) -> int:
        """Ensure chunk_overlap is less than chunk_size."""
        if "chunk_size" in info.data and v >= info.data["chunk_size"]:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return v

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, v: Path) -> Path:
        """Convert string to Path and ensure it's absolute."""
        if isinstance(v, str):
            v = Path(v)
        return v.resolve()

    @classmethod
    def from_env(cls) -> "Config":
        """Create Config instance from environment variables with defaults."""
        return cls(
            model_name=os.getenv("CLINICAL_NOTE_MODEL", "qwen2.5:7b"),
            temperature=float(os.getenv("CLINICAL_NOTE_TEMPERATURE", "0.1")),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            chunk_size=int(os.getenv("CLINICAL_NOTE_CHUNK_SIZE", "1500")),
            chunk_overlap=int(os.getenv("CLINICAL_NOTE_CHUNK_OVERLAP", "200")),
            max_paragraph_size=int(os.getenv("CLINICAL_NOTE_MAX_PARAGRAPH_SIZE", "3000")),
            min_sections_for_success=int(os.getenv("CLINICAL_NOTE_MIN_SECTIONS", "2")),
            enable_llm_fallback=os.getenv("CLINICAL_NOTE_ENABLE_LLM_FALLBACK", "true").lower() in ("true", "1", "yes"),
            max_retries=int(os.getenv("CLINICAL_NOTE_MAX_RETRIES", "2")),
            max_chunk_failure_rate=float(os.getenv("CLINICAL_NOTE_MAX_CHUNK_FAILURE_RATE", "0.3")),
            max_pages_warning=int(os.getenv("CLINICAL_NOTE_MAX_PAGES_WARNING", "30")),
            output_dir=Path(os.getenv("CLINICAL_NOTE_OUTPUT_DIR", "results")),
        )


_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config

