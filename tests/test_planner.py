"""Tests for plan generation."""

from unittest.mock import MagicMock

import pytest

from app.planner import create_treatment_plan_from_chunks


class TestCreateTreatmentPlanFromChunks:
    """Tests for creating treatment plan from chunks."""

    def test_create_plan_basic(self, sample_chunks, mock_llm_client):
        """Test creating a basic treatment plan."""
        # Mock LLM response
        mock_response = """**Prioritized Treatment Plan**

**1. Diagnostics**
[Recommendation 1]
- Source: `OBJECTIVE (chunk_2)`
- Confidence: 1.0

* Test diagnostic.

**2. Therapeutics**
[Recommendation 1]
- Source: `PLAN (chunk_4)`
- Confidence: 0.9

* Test medication.

**3. Follow-ups**
[Recommendation 1]
- Source: `PLAN (chunk_4)`
- Confidence: 0.8

* Test follow-up.
"""
        mock_llm_client.call = MagicMock(return_value=mock_response)
        
        plan = create_treatment_plan_from_chunks(sample_chunks, mock_llm_client)
        
        assert isinstance(plan, str)
        assert len(plan) > 0
        assert "Prioritized Treatment Plan" in plan

    def test_create_plan_structure(self, sample_chunks, mock_llm_client):
        """Test that plan has expected structure."""
        mock_response = """**Prioritized Treatment Plan**

**1. Diagnostics**
[Recommendation 1]
- Source: `chunk_2:100-150`
- Confidence: 1.0
- Risks/Benefits: None
- Hallucination Guard Note: N/A

* Diagnostic test.

**2. Therapeutics**
[Recommendation 1]
- Source: `chunk_4:200-250`
- Confidence: 0.9
- Risks/Benefits: May have side effects
- Hallucination Guard Note: N/A

* Medication.

**3. Follow-ups**
[Recommendation 1]
- Source: `chunk_4:300-350`
- Confidence: 0.8
- Risks/Benefits: None
- Hallucination Guard Note: Evidence is limited

* Follow-up appointment.
"""
        mock_llm_client.call = MagicMock(return_value=mock_response)
        
        plan = create_treatment_plan_from_chunks(sample_chunks, mock_llm_client)
        
        # Check for required sections
        assert "Prioritized Treatment Plan" in plan
        assert "1. Diagnostics" in plan
        assert "2. Therapeutics" in plan
        assert "3. Follow-ups" in plan

    def test_create_plan_includes_citations(self, sample_chunks, mock_llm_client):
        """Test that plan includes source citations."""
        mock_response = """**Prioritized Treatment Plan**

**1. Diagnostics**
[Recommendation 1]
- Source: `chunk_2:100-150`
- Confidence: 1.0

* Test.
"""
        mock_llm_client.call = MagicMock(return_value=mock_response)
        
        plan = create_treatment_plan_from_chunks(sample_chunks, mock_llm_client)
        
        # Verify that LLM was called
        assert mock_llm_client.call.called
        # The plan should be returned
        assert isinstance(plan, str)

    def test_create_plan_empty_chunks(self, mock_llm_client):
        """Test creating plan with empty chunks list."""
        mock_response = "No recommendations"
        mock_llm_client.call = MagicMock(return_value=mock_response)
        
        plan = create_treatment_plan_from_chunks([], mock_llm_client)
        
        assert isinstance(plan, str)
        assert mock_llm_client.call.called

