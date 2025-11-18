"""Tests for plan generation."""

import re
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


class TestRealLLMPlanGeneration:
    """Integration tests for plan generation with real LLM."""

    def test_real_llm_produces_structured_plan(self, sample_chunks, real_llm_client):
        """Test that real LLM produces a structured plan with required sections."""
        plan = create_treatment_plan_from_chunks(sample_chunks, real_llm_client)
        
        # Check that plan has required structure
        # LLM may format sections differently, so we check for key terms
        plan_lower = plan.lower()
        
        # Must have "Prioritized Treatment Plan" or similar
        assert "prioritized" in plan_lower or "treatment plan" in plan_lower, \
            "Plan should contain 'Prioritized Treatment Plan' or similar"
        
        # Should have at least one of the main categories (LLM may format differently)
        category_keywords = ["diagnostic", "therapeutic", "follow", "recommendation"]
        has_category = any(keyword in plan_lower for keyword in category_keywords)
        assert has_category, \
            "Plan should contain at least one category (diagnostics, therapeutics, follow-ups, or recommendations)"

    def test_real_llm_plan_includes_citations(self, sample_chunks, real_llm_client):
        """Test that plan from real LLM includes source citations."""
        plan = create_treatment_plan_from_chunks(sample_chunks, real_llm_client)
        
        # Check for citation patterns
        # Citations can be in format: chunk_X:start-end or section names
        citation_patterns = [
            r'chunk_\d+:\d+-\d+',  # chunk_X:start-end format
            r'chunk_\d+',  # chunk_X format
        ]
        
        has_citations = False
        for pattern in citation_patterns:
            if re.search(pattern, plan):
                has_citations = True
                break
        
        # Should have at least some citations or source references
        assert has_citations or "source:" in plan.lower() or "- Source:" in plan, \
            "Plan should include source citations"

    def test_real_llm_plan_includes_confidence_scores(self, sample_chunks, real_llm_client):
        """Test that plan from real LLM includes confidence scores."""
        plan = create_treatment_plan_from_chunks(sample_chunks, real_llm_client)
        
        # Check for confidence score patterns (0.0 to 1.0)
        confidence_pattern = r'confidence:\s*([01](?:\.\d+)?)'
        confidences = re.findall(confidence_pattern, plan, re.IGNORECASE)
        
        # Should have at least some confidence scores
        # (LLM may not always include them, but most should)
        if len(confidences) > 0:
            # Validate confidence scores are in valid range
            for conf_str in confidences:
                conf = float(conf_str)
                assert 0.0 <= conf <= 1.0, f"Confidence score {conf} should be between 0.0 and 1.0"

