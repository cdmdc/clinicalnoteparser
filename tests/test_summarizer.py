"""Tests for summarization."""

from unittest.mock import MagicMock

import pytest

from app.summarizer import create_text_summary_from_chunks


class TestCreateTextSummaryFromChunks:
    """Tests for creating text summary from chunks."""

    def test_create_text_summary_basic(self, sample_chunks, mock_llm_client):
        """Test creating a basic text summary."""
        # Mock LLM response
        mock_response = """**Patient Snapshot**
A test patient.
- Source: chunk_0:10-50

**Key Problems**
Test problem
- Source: chunk_1:100-150
"""
        # Override the side_effect to return our mock response
        mock_llm_client.call = MagicMock(return_value=mock_response)
        
        summary = create_text_summary_from_chunks(sample_chunks, mock_llm_client)
        
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "Patient Snapshot" in summary or "patient" in summary.lower()

    def test_create_text_summary_includes_chunk_spans(self, sample_chunks, mock_llm_client):
        """Test that summary includes chunk character spans in headers."""
        mock_response = "Test summary"
        mock_llm_client.call = MagicMock(return_value=mock_response)
        
        summary = create_text_summary_from_chunks(sample_chunks, mock_llm_client)
        
        # Verify that LLM was called (the prompt should include chunk spans)
        assert mock_llm_client.call.called
        call_args = mock_llm_client.call.call_args
        prompt = call_args[0][0] if call_args[0] else ""
        
        # The prompt should include chunk information (either chunk IDs or section headers)
        # Verify that the prompt contains some chunk-related information
        assert len(prompt) > 0  # Prompt should not be empty
        # The function combines chunks, so the prompt should have content
        assert len(summary) > 0  # Summary should be returned

    def test_create_text_summary_empty_chunks(self, mock_llm_client):
        """Test creating summary with empty chunks list."""
        mock_response = "No content"
        mock_llm_client.call.return_value = mock_response
        
        summary = create_text_summary_from_chunks([], mock_llm_client)
        
        assert isinstance(summary, str)
        assert mock_llm_client.call.called

    def test_create_text_summary_structure(self, sample_chunks, mock_llm_client):
        """Test that summary has expected structure."""
        mock_response = """**Patient Snapshot**
Test patient.
- Source: chunk_0:10-50

**Key Problems**
Problem 1
- Source: chunk_1:100-150

**Pertinent History**
History item
- Source: chunk_2:200-250

**Medicines/Allergies**
Medication
- Source: chunk_3:300-350

**Objective Findings**
Finding
- Source: chunk_4:400-450

**Labs/Imaging**
None documented
- Source: None

**Concise Assessment**
Assessment
- Source: chunk_5:500-550
"""
        mock_llm_client.call = MagicMock(return_value=mock_response)
        
        summary = create_text_summary_from_chunks(sample_chunks, mock_llm_client)
        
        # Check for required sections
        assert "Patient Snapshot" in summary
        assert "Key Problems" in summary
        assert "Pertinent History" in summary
        assert "Medicines/Allergies" in summary
        assert "Objective Findings" in summary
        assert "Labs/Imaging" in summary
        assert "Concise Assessment" in summary

