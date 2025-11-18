"""Evaluation metrics for summary and plan quality."""

import json
import logging
import re
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.ingestion import CanonicalNote
from app.schemas import Citation

logger = logging.getLogger(__name__)


def parse_citation_from_text(citation_text: str) -> Optional[Tuple[str, Optional[int], Optional[int]]]:
    """Parse citation from text format.
    
    Handles formats like:
    - "chunk_0:123-456"
    - "Overview, chunk_0"
    - "ASSESSMENT, chunk_5"
    - "PLAN (chunk_6)"
    - "None mentioned"
    
    Args:
        citation_text: Citation text to parse
        
    Returns:
        Optional[Tuple[str, Optional[int], Optional[int]]]: (chunk_id, start_char, end_char) or None
    """
    citation_text = citation_text.strip()
    
    # Handle "None mentioned" or empty
    if not citation_text or "none" in citation_text.lower():
        return None
    
    # Try to extract chunk ID and character spans: "chunk_0:123-456"
    chunk_span_match = re.search(r'chunk_(\d+)(?::(\d+)-(\d+))?', citation_text)
    if chunk_span_match:
        chunk_id = f"chunk_{chunk_span_match.group(1)}"
        start_char = int(chunk_span_match.group(2)) if chunk_span_match.group(2) else None
        end_char = int(chunk_span_match.group(3)) if chunk_span_match.group(3) else None
        return (chunk_id, start_char, end_char)
    
    # Try to extract just chunk ID: "chunk_0" or "chunk_5"
    chunk_match = re.search(r'chunk_(\d+)', citation_text)
    if chunk_match:
        chunk_id = f"chunk_{chunk_match.group(1)}"
        return (chunk_id, None, None)
    
    return None


def extract_items_from_summary(summary_text: str) -> List[Dict]:
    """Extract items (facts) from summary.txt with their sources.
    
    Args:
        summary_text: Content of summary.txt
        
    Returns:
        List[Dict]: List of items with text and source information
    """
    items = []
    lines = summary_text.split("\n")
    
    current_section = None
    current_item_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Check for section headers
        if stripped.startswith("**") and stripped.endswith("**"):
            # Save previous item if exists
            if current_item_lines:
                # Try to find source in the last few lines
                item_text_lines = []
                source_text = None
                for i, item_line in enumerate(current_item_lines):
                    if item_line.strip().startswith("- Source:"):
                        source_text = item_line.strip().replace("- Source:", "").strip()
                        # All lines before this are item text
                        item_text_lines = current_item_lines[:i]
                        break
                
                if item_text_lines:
                    item_text = "\n".join(item_text_lines).strip()
                    if item_text:
                        items.append({
                            "text": item_text,
                            "section": current_section,
                            "source": source_text,
                        })
            
            current_section = stripped.strip("*").strip()
            current_item_lines = []
            continue
        
        # Accumulate lines until we hit a source line
        if stripped.startswith("- Source:"):
            # This is the source for the current item
            source_text = stripped.replace("- Source:", "").strip()
            if current_item_lines:
                # All previous lines are the item text
                item_text = "\n".join(current_item_lines).strip()
                if item_text:
                    items.append({
                        "text": item_text,
                        "section": current_section,
                        "source": source_text,
                    })
                current_item_lines = []
        elif stripped:  # Non-empty line
            current_item_lines.append(line)  # Keep original line (with indentation)
        elif not stripped and current_item_lines:
            # Empty line - keep it as part of the item (for formatting)
            current_item_lines.append("")
    
    # Handle last item if exists
    if current_item_lines:
        item_text_lines = []
        source_text = None
        for i, item_line in enumerate(current_item_lines):
            if item_line.strip().startswith("- Source:"):
                source_text = item_line.strip().replace("- Source:", "").strip()
                item_text_lines = current_item_lines[:i]
                break
        
        if not source_text and item_text_lines:
            # No source found, use all lines as text
            item_text_lines = current_item_lines
        
        if item_text_lines:
            item_text = "\n".join(item_text_lines).strip()
            if item_text:
                items.append({
                    "text": item_text,
                    "section": current_section,
                    "source": source_text,
                })
    
    return items


def extract_recommendations_from_plan(plan_text: str) -> List[Dict]:
    """Extract recommendations from plan.txt with their sources and confidence.
    
    Args:
        plan_text: Content of plan.txt
        
    Returns:
        List[Dict]: List of recommendations with text, source, and confidence
    """
    recommendations = []
    lines = plan_text.split("\n")
    
    current_category = None
    current_rec = None
    collecting_text = False
    
    for line in lines:
        stripped = line.strip()
        
        # Check for category headers: "**1. Diagnostics**", "**2. Therapeutics**", etc.
        if re.match(r'\*\*\d+\.\s+\w+\*\*', stripped):
            current_category = stripped.strip("*").strip()
            # Save previous recommendation if exists
            if current_rec:
                recommendations.append(current_rec)
            current_rec = None
            collecting_text = False
            continue
        
        # Check for recommendation start: "[Recommendation X]"
        if stripped.startswith("[Recommendation"):
            # Save previous recommendation if exists
            if current_rec:
                recommendations.append(current_rec)
            current_rec = {
                "text": "",
                "category": current_category,
                "source": None,
                "confidence": None,
            }
            collecting_text = False
            continue
        
        # Check for source line: "- Source: ..."
        if stripped.startswith("- Source:"):
            source_text = stripped.replace("- Source:", "").strip()
            # Remove backticks if present
            source_text = source_text.strip("`")
            if current_rec:
                current_rec["source"] = source_text
            collecting_text = False
            continue
        
        # Check for confidence line: "- Confidence: ..."
        if stripped.startswith("- Confidence:"):
            conf_text = stripped.replace("- Confidence:", "").strip()
            try:
                if current_rec:
                    current_rec["confidence"] = float(conf_text)
            except ValueError:
                pass
            collecting_text = False
            continue
        
        # Check for other metadata lines (Risks/Benefits, Hallucination Guard Note)
        if stripped.startswith("- ") and current_rec:
            collecting_text = False
            continue
        
        # Check for recommendation text (starts with "*")
        if stripped.startswith("*") and current_rec:
            rec_text = stripped.lstrip("*").strip()
            if current_rec["text"]:
                current_rec["text"] += "\n" + rec_text
            else:
                current_rec["text"] = rec_text
            collecting_text = True
        elif collecting_text and stripped and current_rec:
            # Continuation of recommendation text (shouldn't happen with current format, but handle it)
            current_rec["text"] += " " + stripped
    
    # Add last recommendation if it exists
    if current_rec:
        recommendations.append(current_rec)
    
    return recommendations


def validate_citation_span(
    start_char: Optional[int],
    end_char: Optional[int],
    text_length: int,
) -> bool:
    """Validate that citation span is within text bounds.
    
    Args:
        start_char: Start character position (None if not specified)
        end_char: End character position (None if not specified)
        text_length: Length of the text
        
    Returns:
        bool: True if valid, False otherwise
    """
    if start_char is None or end_char is None:
        return True  # Can't validate without positions
    
    if start_char < 0 or end_char < 0:
        return False
    
    if start_char >= end_char:
        return False
    
    if end_char > text_length:
        return False
    
    return True


def calculate_jaccard_similarity(span1: Tuple[int, int], span2: Tuple[int, int]) -> float:
    """Calculate Jaccard similarity between two citation spans.
    
    Args:
        span1: (start_char, end_char) for first span
        span2: (start_char, end_char) for second span
        
    Returns:
        float: Jaccard similarity [0, 1]
    """
    start1, end1 = span1
    start2, end2 = span2
    
    # Calculate intersection
    intersection_start = max(start1, start2)
    intersection_end = min(end1, end2)
    
    if intersection_start >= intersection_end:
        return 0.0
    
    intersection = intersection_end - intersection_start
    
    # Calculate union
    union_start = min(start1, start2)
    union_end = max(end1, end2)
    union = union_end - union_start
    
    if union == 0:
        return 0.0
    
    return intersection / union


def evaluate_summary_and_plan(
    summary_text: str,
    plan_text: str,
    canonical_note: CanonicalNote,
    chunks: List,
) -> Dict:
    """Evaluate summary and plan quality metrics.
    
    Args:
        summary_text: Content of summary.txt
        plan_text: Content of plan.txt
        canonical_note: CanonicalNote for text validation
        chunks: List of Chunk objects for citation mapping
        
    Returns:
        Dict: Evaluation metrics
    """
    text_length = len(canonical_note.text)
    
    # Extract items from summary
    summary_items = extract_items_from_summary(summary_text)
    
    # Extract recommendations from plan
    plan_recommendations = extract_recommendations_from_plan(plan_text)
    
    # Create chunk mapping for citation validation
    chunk_map = {chunk.chunk_id: chunk for chunk in chunks}
    
    # Citation Coverage
    summary_items_with_source = [item for item in summary_items if item.get("source")]
    plan_recs_with_source = [rec for rec in plan_recommendations if rec.get("source")]
    
    summary_coverage = (
        len(summary_items_with_source) / len(summary_items) * 100
        if summary_items else 0.0
    )
    plan_coverage = (
        len(plan_recs_with_source) / len(plan_recommendations) * 100
        if plan_recommendations else 0.0
    )
    overall_coverage = (
        (len(summary_items_with_source) + len(plan_recs_with_source))
        / (len(summary_items) + len(plan_recommendations)) * 100
        if (summary_items or plan_recommendations) else 0.0
    )
    
    # Citation Validity
    invalid_citations = 0
    total_citations = 0
    
    for item in summary_items_with_source:
        citation_info = parse_citation_from_text(item.get("source", ""))
        if citation_info:
            chunk_id, start_char, end_char = citation_info
            total_citations += 1
            if start_char is not None and end_char is not None:
                if not validate_citation_span(start_char, end_char, text_length):
                    invalid_citations += 1
            elif chunk_id in chunk_map:
                # Validate chunk exists
                chunk = chunk_map[chunk_id]
                if chunk.start_char < 0 or chunk.end_char > text_length:
                    invalid_citations += 1
    
    for rec in plan_recs_with_source:
        citation_info = parse_citation_from_text(rec.get("source", ""))
        if citation_info:
            chunk_id, start_char, end_char = citation_info
            total_citations += 1
            if start_char is not None and end_char is not None:
                if not validate_citation_span(start_char, end_char, text_length):
                    invalid_citations += 1
            elif chunk_id in chunk_map:
                chunk = chunk_map[chunk_id]
                if chunk.start_char < 0 or chunk.end_char > text_length:
                    invalid_citations += 1
    
    # Orphan Claims (Hallucination Rate)
    summary_orphans = len(summary_items) - len(summary_items_with_source)
    plan_orphans = len(plan_recommendations) - len(plan_recs_with_source)
    total_claims = len(summary_items) + len(plan_recommendations)
    hallucination_rate = (
        (summary_orphans + plan_orphans) / total_claims * 100
        if total_claims > 0 else 0.0
    )
    
    # Citation Overlap Jaccard
    # Calculate Jaccard similarity between citation spans
    # For items with multiple citations, calculate pairwise Jaccard
    # Also calculate Jaccard between citations from different items that reference the same chunks
    jaccard_scores = []
    
    # Collect all citations with their spans
    all_citations = []
    
    # Process summary items
    for item in summary_items_with_source:
        citation_info = parse_citation_from_text(item.get("source", ""))
        if citation_info:
            chunk_id, start_char, end_char = citation_info
            if chunk_id in chunk_map:
                chunk = chunk_map[chunk_id]
                # Use character spans if available, otherwise use chunk spans
                if start_char is not None and end_char is not None:
                    # Convert local chunk spans to global spans
                    global_start = chunk.start_char + start_char
                    global_end = chunk.start_char + end_char
                    all_citations.append({
                        "span": (global_start, global_end),
                        "chunk_id": chunk_id,
                        "item_text": item.get("text", "")[:50],  # First 50 chars for reference
                    })
                else:
                    # Use entire chunk span
                    all_citations.append({
                        "span": (chunk.start_char, chunk.end_char),
                        "chunk_id": chunk_id,
                        "item_text": item.get("text", "")[:50],
                    })
    
    # Process plan recommendations
    for rec in plan_recs_with_source:
        citation_info = parse_citation_from_text(rec.get("source", ""))
        if citation_info:
            chunk_id, start_char, end_char = citation_info
            if chunk_id in chunk_map:
                chunk = chunk_map[chunk_id]
                if start_char is not None and end_char is not None:
                    global_start = chunk.start_char + start_char
                    global_end = chunk.start_char + end_char
                    all_citations.append({
                        "span": (global_start, global_end),
                        "chunk_id": chunk_id,
                        "item_text": rec.get("text", "")[:50],
                    })
                else:
                    all_citations.append({
                        "span": (chunk.start_char, chunk.end_char),
                        "chunk_id": chunk_id,
                        "item_text": rec.get("text", "")[:50],
                    })
    
    # Calculate pairwise Jaccard similarity
    # Compare all pairs of citations
    for i in range(len(all_citations)):
        for j in range(i + 1, len(all_citations)):
            span1 = all_citations[i]["span"]
            span2 = all_citations[j]["span"]
            jaccard = calculate_jaccard_similarity(span1, span2)
            jaccard_scores.append(jaccard)
    
    # Calculate average Jaccard score
    avg_jaccard = (
        sum(jaccard_scores) / len(jaccard_scores)
        if jaccard_scores else 0.0
    )
    
    # Span Consistency
    span_consistency_checks = 0
    span_consistency_passed = 0
    
    for item in summary_items_with_source:
        citation_info = parse_citation_from_text(item.get("source", ""))
        if citation_info:
            chunk_id, start_char, end_char = citation_info
            if chunk_id in chunk_map:
                chunk = chunk_map[chunk_id]
                span_consistency_checks += 1
                # Check if chunk text is not empty
                if chunk.text and len(chunk.text) > 0:
                    span_consistency_passed += 1
    
    for rec in plan_recs_with_source:
        citation_info = parse_citation_from_text(rec.get("source", ""))
        if citation_info:
            chunk_id, start_char, end_char = citation_info
            if chunk_id in chunk_map:
                chunk = chunk_map[chunk_id]
                span_consistency_checks += 1
                if chunk.text and len(chunk.text) > 0:
                    span_consistency_passed += 1
    
    span_consistency_rate = (
        span_consistency_passed / span_consistency_checks * 100
        if span_consistency_checks > 0 else 0.0
    )
    
    # Summary Statistics
    total_facts = len(summary_items)
    total_recommendations = len(plan_recommendations)
    
    # Average citations per fact/recommendation
    avg_citations_per_fact = (
        len(summary_items_with_source) / total_facts
        if total_facts > 0 else 0.0
    )
    avg_citations_per_rec = (
        len(plan_recs_with_source) / total_recommendations
        if total_recommendations > 0 else 0.0
    )
    
    # Confidence score distribution (from plan)
    confidence_scores = [
        rec["confidence"]
        for rec in plan_recommendations
        if rec.get("confidence") is not None
    ]
    
    confidence_distribution = {
        "count": len(confidence_scores),
        "mean": sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0,
        "median": statistics.median(confidence_scores) if confidence_scores else None,
        "min": min(confidence_scores) if confidence_scores else None,
        "max": max(confidence_scores) if confidence_scores else None,
    }
    
    # Build evaluation report
    evaluation = {
        "citation_coverage": {
            "summary_facts_with_citations": len(summary_items_with_source),
            "summary_total_facts": total_facts,
            "summary_coverage_percentage": round(summary_coverage, 2),
            "plan_recommendations_with_citations": len(plan_recs_with_source),
            "plan_total_recommendations": total_recommendations,
            "plan_coverage_percentage": round(plan_coverage, 2),
            "overall_coverage_percentage": round(overall_coverage, 2),
        },
        "citation_validity": {
            "total_citations_checked": total_citations,
            "invalid_citations": invalid_citations,
            "validity_percentage": round(
                (total_citations - invalid_citations) / total_citations * 100
                if total_citations > 0 else 100.0,
                2
            ),
        },
        "orphan_claims": {
            "summary_orphans": summary_orphans,
            "plan_orphans": plan_orphans,
            "total_orphans": summary_orphans + plan_orphans,
            "total_claims": total_claims,
            "hallucination_rate_percentage": round(hallucination_rate, 2),
        },
        "citation_overlap_jaccard": {
            "total_citation_pairs": len(jaccard_scores),
            "average_jaccard_similarity": round(avg_jaccard, 4),
            "min_jaccard": round(min(jaccard_scores), 4) if jaccard_scores else None,
            "max_jaccard": round(max(jaccard_scores), 4) if jaccard_scores else None,
        },
        "span_consistency": {
            "checks_performed": span_consistency_checks,
            "checks_passed": span_consistency_passed,
            "consistency_percentage": round(span_consistency_rate, 2),
        },
        "summary_statistics": {
            "total_facts_extracted": total_facts,
            "total_recommendations_generated": total_recommendations,
            "average_citations_per_fact": round(avg_citations_per_fact, 2),
            "average_citations_per_recommendation": round(avg_citations_per_rec, 2),
            "confidence_score_distribution": confidence_distribution,
        },
    }
    
    return evaluation


def save_evaluation(evaluation: Dict, output_path: Path) -> None:
    """Save evaluation report to JSON file.
    
    Args:
        evaluation: Evaluation metrics dictionary
        output_path: Path to save evaluation JSON file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(evaluation, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved evaluation report to {output_path}")

