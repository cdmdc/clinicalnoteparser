"""Shared pytest fixtures for testing."""

import json
import sys
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest

# Add src directory to Python path
_project_root = Path(__file__).parent.parent
_src_dir = _project_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from app.chunks import Chunk
from app.config import Config
from app.ingestion import CanonicalNote, PageSpan
from app.llm import LLMClient, OllamaNotAvailableError
from app.schemas import Section


@pytest.fixture
def sample_pdf_path(tmp_path: Path) -> Path:
    """Create a sample PDF file for testing.
    
    Note: This creates a minimal text file that can be used for .txt testing.
    For actual PDF testing, you would need to create a real PDF file.
    """
    pdf_file = tmp_path / "sample.pdf"
    # For now, create a text file - in real tests, this would be a PDF
    pdf_file.write_text("Sample PDF content")
    return pdf_file


@pytest.fixture
def sample_txt_path(tmp_path: Path) -> Path:
    """Create a sample .txt file for testing."""
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text(
        "Medical Specialty: Cardiology\n"
        "Sample Name: Heart Failure\n"
        "Description: Patient with heart failure\n\n"
        "SUBJECTIVE\n"
        "Patient presents with shortness of breath.\n\n"
        "OBJECTIVE\n"
        "Blood pressure: 140/90\n"
        "Heart rate: 90 bpm\n\n"
        "ASSESSMENT\n"
        "Heart failure\n\n"
        "PLAN\n"
        "Continue medications.\n"
    )
    return txt_file


@pytest.fixture
def sample_canonical_note() -> CanonicalNote:
    """Create a sample CanonicalNote for testing."""
    text = (
        "Medical Specialty: Cardiology\n"
        "Sample Name: Heart Failure\n"
        "Description: Patient with heart failure\n\n"
        "SUBJECTIVE\n"
        "Patient presents with shortness of breath.\n\n"
        "OBJECTIVE\n"
        "Blood pressure: 140/90\n"
        "Heart rate: 90 bpm\n\n"
        "ASSESSMENT\n"
        "Heart failure\n\n"
        "PLAN\n"
        "Continue medications.\n"
    )
    page_spans = [
        PageSpan(start_char=0, end_char=len(text), page_index=0)
    ]
    return CanonicalNote(text=text, page_spans=page_spans)


@pytest.fixture
def sample_sections() -> list[Section]:
    """Create sample sections for testing."""
    return [
        Section(
            title="Overview",
            start_char=0,
            end_char=50,
            start_page=0,
            end_page=0,
        ),
        Section(
            title="SUBJECTIVE",
            start_char=50,
            end_char=100,
            start_page=0,
            end_page=0,
        ),
        Section(
            title="OBJECTIVE",
            start_char=100,
            end_char=150,
            start_page=0,
            end_page=0,
        ),
        Section(
            title="ASSESSMENT",
            start_char=150,
            end_char=200,
            start_page=0,
            end_page=0,
        ),
        Section(
            title="PLAN",
            start_char=200,
            end_char=250,
            start_page=0,
            end_page=0,
        ),
    ]


@pytest.fixture
def sample_chunks(sample_canonical_note: CanonicalNote) -> list[Chunk]:
    """Create sample chunks for testing."""
    text = sample_canonical_note.text
    return [
        Chunk(
            chunk_id="chunk_0",
            text=text[0:50],
            start_char=0,
            end_char=50,
            section_title="Overview",
        ),
        Chunk(
            chunk_id="chunk_1",
            text=text[50:100],
            start_char=50,
            end_char=100,
            section_title="SUBJECTIVE",
        ),
        Chunk(
            chunk_id="chunk_2",
            text=text[100:150],
            start_char=100,
            end_char=150,
            section_title="OBJECTIVE",
        ),
        Chunk(
            chunk_id="chunk_3",
            text=text[150:200],
            start_char=150,
            end_char=200,
            section_title="ASSESSMENT",
        ),
        Chunk(
            chunk_id="chunk_4",
            text=text[200:250],
            start_char=200,
            end_char=250,
            section_title="PLAN",
        ),
    ]


@pytest.fixture
def mock_llm_client(monkeypatch) -> MagicMock:
    """Create a mock LLM client for testing."""
    mock_client = MagicMock(spec=LLMClient)
    
    # Mock the call method to return a simple response by default
    # Tests can override this by setting mock_client.call.return_value
    def mock_call(prompt, system_message=None, logger_instance=None, return_text=False):
        if return_text:
            return "Mock LLM response text"
        return {"mock": "response"}
    
    mock_client.call = MagicMock(side_effect=mock_call)
    mock_client.check_ollama_available = MagicMock(return_value=True)
    mock_client.load_prompt = MagicMock(return_value="Mock prompt template")
    
    return mock_client


@pytest.fixture
def real_llm_client(sample_config) -> LLMClient:
    """Create a real LLM client for integration testing.
    
    Skips test if Ollama is not available.
    """
    try:
        client = LLMClient(sample_config)
        if not client.check_ollama_available():
            pytest.skip("Ollama is not available or model not found")
        return client
    except OllamaNotAvailableError:
        pytest.skip("Ollama is not available or model not found")


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """Create a temporary output directory for testing."""
    output_dir = tmp_path / "results" / "test_note"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


@pytest.fixture
def sample_config() -> Config:
    """Create a sample configuration for testing."""
    return Config(
        model_name="llama3",
        temperature=0.1,
        chunk_size=1500,
        chunk_overlap=200,
        max_paragraph_size=3000,
        min_sections_for_success=2,
        enable_llm_fallback=True,
        max_retries=3,
        max_chunk_failure_rate=0.3,
        max_pages_warning=30,
        output_dir=Path("results"),
    )

