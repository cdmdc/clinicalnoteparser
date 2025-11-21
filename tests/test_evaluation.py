"""Tests for evaluation metrics."""

import json
from pathlib import Path

import pytest

from app.evaluation import (
    calculate_jaccard_similarity,
    evaluate_summary_and_plan,
    extract_items_from_summary,
    extract_recommendations_from_plan,
    parse_citation_from_text,
    validate_citation_span,
)
from app.ingestion import CanonicalNote, PageSpan
from app.schemas import Chunk


class TestCitationParsing:
    """Tests for citation parsing."""

    def test_parse_citation_with_spans(self):
        """Test parsing citation with character spans."""
        result = parse_citation_from_text("chunk_0:123-456")
        assert result is not None
        chunk_id, start_char, end_char, section_name = result
        assert chunk_id == "chunk_0"
        assert start_char == 123
        assert end_char == 456
        assert section_name is None

    def test_parse_citation_without_spans(self):
        """Test parsing citation without character spans."""
        result = parse_citation_from_text("chunk_0")
        assert result is not None
        chunk_id, start_char, end_char, section_name = result
        assert chunk_id == "chunk_0"
        assert start_char is None
        assert end_char is None
        assert section_name is None

    def test_parse_citation_with_section_name(self):
        """Test parsing citation with section name."""
        result = parse_citation_from_text("PLAN, chunk_6")
        assert result is not None
        chunk_id, start_char, end_char, section_name = result
        assert chunk_id == "chunk_6"
        assert start_char is None
        assert end_char is None
        assert section_name == "PLAN"

    def test_parse_citation_none(self):
        """Test parsing 'None mentioned' citation."""
        result = parse_citation_from_text("None mentioned")
        assert result is None

    def test_parse_citation_empty(self):
        """Test parsing empty citation."""
        result = parse_citation_from_text("")
        assert result is None


class TestCitationValidation:
    """Tests for citation span validation."""

    def test_validate_valid_span(self):
        """Test validating a valid citation span."""
        assert validate_citation_span(0, 100, 200) is True

    def test_validate_span_out_of_bounds(self):
        """Test validating a span that's out of bounds."""
        assert validate_citation_span(0, 300, 200) is False

    def test_validate_span_negative_start(self):
        """Test validating a span with negative start."""
        assert validate_citation_span(-10, 100, 200) is False

    def test_validate_span_end_before_start(self):
        """Test validating a span where end < start."""
        assert validate_citation_span(100, 50, 200) is False

    def test_validate_span_none_values(self):
        """Test validating a span with None values (should pass)."""
        assert validate_citation_span(None, None, 200) is True


class TestJaccardSimilarity:
    """Tests for Jaccard similarity calculation."""

    def test_jaccard_identical_spans(self):
        """Test Jaccard similarity for identical spans."""
        similarity = calculate_jaccard_similarity((0, 100), (0, 100))
        assert similarity == 1.0

    def test_jaccard_no_overlap(self):
        """Test Jaccard similarity for non-overlapping spans."""
        similarity = calculate_jaccard_similarity((0, 50), (100, 150))
        assert similarity == 0.0

    def test_jaccard_partial_overlap(self):
        """Test Jaccard similarity for partially overlapping spans."""
        # Spans: [0, 100] and [50, 150]
        # Intersection: [50, 100] = 50
        # Union: [0, 150] = 150
        # Jaccard = 50/150 = 0.333...
        similarity = calculate_jaccard_similarity((0, 100), (50, 150))
        assert abs(similarity - 0.333333) < 0.001

    def test_jaccard_one_contains_other(self):
        """Test Jaccard similarity when one span contains the other."""
        # Spans: [0, 200] and [50, 100]
        # Intersection: [50, 100] = 50
        # Union: [0, 200] = 200
        # Jaccard = 50/200 = 0.25
        similarity = calculate_jaccard_similarity((0, 200), (50, 100))
        assert similarity == 0.25


class TestSummaryExtraction:
    """Tests for extracting items from summary."""

    def test_extract_items_from_summary(self):
        """Test extracting items from summary text."""
        summary_text = """**Patient Snapshot**
A 23-year-old patient.
- Source: chunk_0:10-50

**Key Problems**
Heart failure
- Source: chunk_5:100-150
"""
        items = extract_items_from_summary(summary_text)
        assert len(items) == 2
        assert items[0]["section"] == "Patient Snapshot"
        assert items[0]["text"] == "A 23-year-old patient."
        assert items[0]["source"] == "chunk_0:10-50"
        assert items[1]["section"] == "Key Problems"
        assert items[1]["text"] == "Heart failure"
        assert items[1]["source"] == "chunk_5:100-150"


class TestPlanExtraction:
    """Tests for extracting recommendations from plan."""

    def test_extract_recommendations_from_plan(self):
        """Test extracting recommendations from plan text."""
        plan_text = """**1. Diagnostics**
[Recommendation 1]
- Source: `OBJECTIVE (chunk_4)`
- Confidence: 1.0

* Vitals check.

**2. Therapeutics**
[Recommendation 1]
- Source: `PLAN (chunk_6)`
- Confidence: 0.9

* Continue medications.
"""
        recommendations = extract_recommendations_from_plan(plan_text)
        assert len(recommendations) == 2
        assert recommendations[0]["category"] == "1. Diagnostics"
        assert recommendations[0]["text"] == "Vitals check."
        assert recommendations[0]["source"] == "OBJECTIVE (chunk_4)"
        assert recommendations[0]["confidence"] == 1.0
        assert recommendations[1]["category"] == "2. Therapeutics"
        assert recommendations[1]["text"] == "Continue medications."
        assert recommendations[1]["confidence"] == 0.9


class TestEvaluation:
    """Tests for evaluation metrics."""

    def test_evaluate_summary_and_plan(self, sample_canonical_note, sample_chunks):
        """Test full evaluation with sample data."""
        from app.schemas import StructuredSummary, SummaryItem, StructuredPlan, PlanRecommendation
        
        structured_summary = StructuredSummary(
            patient_snapshot=[
                SummaryItem(text="A 23-year-old patient.", source="chunk_0:10-50")
            ],
            key_problems=[
                SummaryItem(text="Heart failure", source="chunk_2:100-150")
            ],
            pertinent_history=[],
            medicines_allergies=[],
            objective_findings=[],
            labs_imaging=[],
            assessment=[],
        )
        
        structured_plan = StructuredPlan(
            recommendations=[
                PlanRecommendation(
                    number=1,
                    recommendation="Vitals check.",
                    source="OBJECTIVE (chunk_2)",
                    confidence=1.0,
                    hallucination_guard_note=None
                )
            ]
        )
        
        evaluation = evaluate_summary_and_plan(
            structured_summary, structured_plan, sample_canonical_note, sample_chunks
        )
        
        # Check that evaluation has all required keys
        assert "citation_coverage" in evaluation
        assert "citation_validity" in evaluation
        assert "orphan_claims" in evaluation
        assert "citation_overlap_jaccard" in evaluation
        assert "span_consistency" in evaluation
        assert "summary_statistics" in evaluation
        
        # Check citation coverage
        assert evaluation["citation_coverage"]["summary_total_facts"] > 0
        assert evaluation["citation_coverage"]["plan_total_recommendations"] > 0
        
        # Check summary statistics
        assert evaluation["summary_statistics"]["total_facts_extracted"] > 0
        assert evaluation["summary_statistics"]["total_recommendations_generated"] > 0

