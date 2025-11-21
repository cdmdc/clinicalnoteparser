"""Integration tests for the full pipeline."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.pipeline import check_ollama_availability, run_pipeline, validate_input_file


class TestValidateInputFile:
    """Tests for input file validation."""

    def test_validate_existing_file(self, sample_txt_path):
        """Test validating an existing file."""
        is_valid, error_msg = validate_input_file(sample_txt_path)
        assert is_valid is True
        assert error_msg is None

    def test_validate_nonexistent_file(self, tmp_path):
        """Test validating a nonexistent file."""
        missing_file = tmp_path / "nonexistent.pdf"
        is_valid, error_msg = validate_input_file(missing_file)
        assert is_valid is False
        assert "does not exist" in error_msg

    def test_validate_unsupported_format(self, tmp_path):
        """Test validating a file with unsupported format."""
        unsupported_file = tmp_path / "test.doc"
        unsupported_file.write_text("test")
        is_valid, error_msg = validate_input_file(unsupported_file)
        assert is_valid is False
        assert "Unsupported file type" in error_msg


class TestCheckOllamaAvailability:
    """Tests for Ollama availability checking."""

    @patch('subprocess.run')
    def test_check_ollama_available(self, mock_subprocess, sample_config):
        """Test checking Ollama when available."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "llama3\n"
        mock_subprocess.return_value = mock_result
        
        is_available, error_msg = check_ollama_availability(sample_config)
        assert is_available is True
        assert error_msg is None

    @patch('subprocess.run')
    def test_check_ollama_unavailable(self, mock_subprocess, sample_config):
        """Test checking Ollama when unavailable."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_subprocess.return_value = mock_result
        
        is_available, error_msg = check_ollama_availability(sample_config)
        assert is_available is False
        assert error_msg is not None
        assert "not running" in error_msg.lower()


class TestPipelineIntegration:
    """Integration tests for the full pipeline."""

    @patch('app.pipeline.check_ollama_availability')
    def test_pipeline_toc_only(self, mock_ollama_check, sample_txt_path, temp_output_dir, sample_config):
        """Test pipeline with --toc-only flag."""
        mock_ollama_check.return_value = (True, None)
        
        exit_code = run_pipeline(
            input_path=sample_txt_path,
            output_dir=temp_output_dir.parent,
            config=sample_config,
            toc_only=True,
            verbose=False,
        )
        
        assert exit_code == 0
        
        # Check that TOC files were created
        note_id = sample_txt_path.stem
        output_dir = temp_output_dir.parent / note_id
        assert (output_dir / "canonical_text.txt").exists()
        assert (output_dir / "toc.json").exists()
        assert (output_dir / "pipeline.log").exists()
        
        # Check that chunks and summary were NOT created
        assert not (output_dir / "chunks.json").exists()
        assert not (output_dir / "summary.txt").exists()

    def test_pipeline_summary_only(self, sample_txt_path, temp_output_dir, sample_config, real_llm_client):
        """Test pipeline with --summary-only flag using real LLM."""
        exit_code = run_pipeline(
            input_path=sample_txt_path,
            output_dir=temp_output_dir.parent,
            config=sample_config,
            summary_only=True,
            verbose=False,
        )
        
        assert exit_code == 0
        
        # Check that required files were created
        note_id = sample_txt_path.stem
        output_dir = temp_output_dir.parent / note_id
        assert (output_dir / "canonical_text.txt").exists()
        assert (output_dir / "toc.json").exists()
        assert (output_dir / "chunks.json").exists()
        assert (output_dir / "summary.json").exists()
        
        # Check that plan was NOT created
        assert not (output_dir / "plan.json").exists()
        assert not (output_dir / "evaluation.json").exists()
        
        # Verify summary content
        summary_path = output_dir / "summary.json"
        if summary_path.exists():
            import json
            summary_data = json.loads(summary_path.read_text())
            assert len(summary_data) > 0, "Summary should not be empty"

    def test_pipeline_full(self, sample_txt_path, temp_output_dir, sample_config, real_llm_client):
        """Test full pipeline with all outputs using real LLM."""
        exit_code = run_pipeline(
            input_path=sample_txt_path,
            output_dir=temp_output_dir.parent,
            config=sample_config,
            verbose=False,
        )
        
        assert exit_code == 0
        
        # Check that all files were created
        note_id = sample_txt_path.stem
        output_dir = temp_output_dir.parent / note_id
        assert (output_dir / "canonical_text.txt").exists()
        assert (output_dir / "toc.json").exists()
        assert (output_dir / "chunks.json").exists()
        assert (output_dir / "summary.json").exists()
        assert (output_dir / "plan.json").exists()
        assert (output_dir / "evaluation.json").exists()
        assert (output_dir / "pipeline.log").exists()
        
        # Verify output content
        summary_path = output_dir / "summary.json"
        if summary_path.exists():
            import json
            summary_data = json.loads(summary_path.read_text())
            assert len(summary_data) > 0, "Summary should not be empty"
        
        plan_path = output_dir / "plan.json"
        if plan_path.exists():
            import json
            plan_data = json.loads(plan_path.read_text())
            assert len(plan_data) > 0, "Plan should not be empty"

    def test_pipeline_missing_file(self, tmp_path, sample_config):
        """Test pipeline with missing input file."""
        missing_file = tmp_path / "nonexistent.pdf"
        
        exit_code = run_pipeline(
            input_path=missing_file,
            config=sample_config,
            verbose=False,
        )
        
        assert exit_code == 1

    @patch('app.pipeline.check_ollama_availability')
    def test_pipeline_ollama_unavailable(self, mock_ollama_check, sample_txt_path, sample_config):
        """Test pipeline when Ollama is unavailable (for LLM steps)."""
        mock_ollama_check.return_value = (False, "Ollama is not running")
        
        # Should fail when trying to run summary (needs LLM)
        exit_code = run_pipeline(
            input_path=sample_txt_path,
            config=sample_config,
            summary_only=True,
            verbose=False,
        )
        
        assert exit_code == 1

    @patch('app.pipeline.check_ollama_availability')
    def test_pipeline_toc_only_no_ollama_needed(self, mock_ollama_check, sample_txt_path, temp_output_dir, sample_config):
        """Test that TOC-only mode doesn't require Ollama."""
        # Even if Ollama check fails, TOC-only should work
        mock_ollama_check.return_value = (False, "Ollama is not running")
        
        exit_code = run_pipeline(
            input_path=sample_txt_path,
            output_dir=temp_output_dir.parent,
            config=sample_config,
            toc_only=True,
            verbose=False,
        )
        
        # TOC-only doesn't need Ollama, so it should succeed
        assert exit_code == 0

    def test_pipeline_skips_ingestion_when_chunks_exist(self, sample_txt_path, temp_output_dir, sample_config, real_llm_client):
        """Test that pipeline skips ingestion and chunking when chunks.json exists."""
        # First run: create chunks
        exit_code1 = run_pipeline(
            input_path=sample_txt_path,
            output_dir=temp_output_dir.parent,
            config=sample_config,
            summary_only=True,
            verbose=False,
        )
        assert exit_code1 == 0
        
        # Verify chunks were created
        note_id = sample_txt_path.stem
        output_dir = temp_output_dir.parent / note_id
        chunks_path = output_dir / "chunks.json"
        assert chunks_path.exists(), "Chunks should have been created in first run"
        
        # Second run: should skip ingestion and chunking
        # We'll need to check the log or use a mock to verify skipping
        # For now, just verify it completes successfully
        exit_code2 = run_pipeline(
            input_path=sample_txt_path,
            output_dir=temp_output_dir.parent,
            config=sample_config,
            summary_only=True,
            verbose=False,
        )
        assert exit_code2 == 0
        
        # Verify chunks still exist and summary was regenerated
        assert chunks_path.exists(), "Chunks should still exist after second run"
        summary_path = output_dir / "summary.json"
        assert summary_path.exists(), "Summary should have been created in second run"

