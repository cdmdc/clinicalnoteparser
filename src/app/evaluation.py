"""Evaluation metrics for summary and plan quality."""

import json
import logging
import os
import re
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None

from app.config import Config, get_config
from app.ingestion import CanonicalNote
from app.llm import _configure_mps_for_ollama
from app.schemas import Citation, StructuredPlan, StructuredSummary

logger = logging.getLogger(__name__)

# Configure MPS for Ollama at module import time (for embedding calls)
# This ensures environment variables are set before any Ollama API calls
_configure_mps_for_ollama()


def parse_citation_from_text(citation_text: str) -> Optional[Tuple[str, Optional[int], Optional[int], Optional[str]]]:
    """Parse citation from text format.
    
    Handles formats like:
    - "chunk_0:123-456"
    - "Overview, chunk_0"
    - "ASSESSMENT, chunk_5"
    - "HISTORY section, chunk_1:215-220"
    - "PLAN (chunk_6)"
    - "None mentioned"
    
    Args:
        citation_text: Citation text to parse
        
    Returns:
        Optional[Tuple[str, Optional[int], Optional[int], Optional[str]]]: 
            (chunk_id, start_char, end_char, section_name) or None
    """
    citation_text = citation_text.strip()
    
    # Handle "None mentioned" or empty
    if not citation_text or "none" in citation_text.lower():
        return None
    
    # Extract section name if present (before chunk reference)
    # Patterns: "SECTION_NAME, chunk_X", "SECTION_NAME section, chunk_X", "SECTION_NAME (chunk_X)"
    section_name = None
    section_match = re.search(r'^([A-Z][A-Z\s]+?)(?:\s+section)?[,\(]', citation_text)
    if section_match:
        section_name = section_match.group(1).strip()
    
    # Try to extract chunk ID and character spans: "chunk_0:123-456"
    chunk_span_match = re.search(r'chunk_(\d+)(?::(\d+)-(\d+))?', citation_text)
    if chunk_span_match:
        chunk_id = f"chunk_{chunk_span_match.group(1)}"
        start_char = int(chunk_span_match.group(2)) if chunk_span_match.group(2) else None
        end_char = int(chunk_span_match.group(3)) if chunk_span_match.group(3) else None
        return (chunk_id, start_char, end_char, section_name)
    
    # Try to extract just chunk ID: "chunk_0" or "chunk_5"
    chunk_match = re.search(r'chunk_(\d+)', citation_text)
    if chunk_match:
        chunk_id = f"chunk_{chunk_match.group(1)}"
        return (chunk_id, None, None, section_name)
    
    return None


def extract_items_from_structured_summary(structured_summary: StructuredSummary) -> List[Dict]:
    """Extract items (facts) from structured summary with their sources.
    
    Args:
        structured_summary: StructuredSummary object
        
    Returns:
        List[Dict]: List of items with text and source information
    """
    items = []
    
    # Extract items from all sections
    sections = [
        structured_summary.patient_snapshot,
        structured_summary.key_problems,
        structured_summary.pertinent_history,
        structured_summary.medicines_allergies,
        structured_summary.objective_findings,
        structured_summary.labs_imaging,
        structured_summary.assessment,
    ]
    
    for section_items in sections:
        for item in section_items:
            items.append({
                "text": item.text,
                "source": item.source,
            })
    
    return items


def extract_items_from_summary(summary_text: str) -> List[Dict]:
    """Extract items (facts) from summary.txt with their sources (DEPRECATED - use extract_items_from_structured_summary).
    
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


def extract_recommendations_from_structured_plan(structured_plan: StructuredPlan) -> List[Dict]:
    """Extract recommendations from structured plan with their sources.
    
    Args:
        structured_plan: StructuredPlan object
        
    Returns:
        List[Dict]: List of recommendations with text and source information
    """
    recommendations = []
    
    # Extract from prioritized recommendations list
    for rec in structured_plan.recommendations:
        recommendations.append({
            "text": rec.recommendation,
            "source": rec.source,
            "number": rec.number,
            "confidence": rec.confidence,
        })
    
    return recommendations


def extract_recommendations_from_plan(plan_text: str) -> List[Dict]:
    """Extract recommendations from plan.txt with their sources and confidence (DEPRECATED - use extract_recommendations_from_structured_plan).
    
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


def validate_section_name(
    cited_section_name: Optional[str],
    chunk_section_title: str,
) -> bool:
    """Validate that cited section name matches chunk's section title.
    
    Args:
        cited_section_name: Section name extracted from citation (None if not present)
        chunk_section_title: Actual section title of the chunk
        
    Returns:
        bool: True if valid (matches or no section name cited), False if mismatch
    """
    if cited_section_name is None:
        return True  # No section name cited, can't validate
    
    # Normalize both for comparison (case-insensitive, strip whitespace)
    cited_normalized = cited_section_name.strip().upper()
    chunk_normalized = chunk_section_title.strip().upper()
    
    return cited_normalized == chunk_normalized


def validate_span_within_chunk(
    start_char: Optional[int],
    end_char: Optional[int],
    chunk_start_char: int,
    chunk_end_char: int,
) -> bool:
    """Validate that citation span is within chunk bounds.
    
    Args:
        start_char: Start character position (local to chunk, None if not specified)
        end_char: End character position (local to chunk, None if not specified)
        chunk_start_char: Global start character of the chunk
        chunk_end_char: Global end character of the chunk
        
    Returns:
        bool: True if valid (within bounds or no spans provided), False otherwise
    """
    if start_char is None or end_char is None:
        return True  # Can't validate without positions
    
    chunk_length = chunk_end_char - chunk_start_char
    
    # Spans are local to chunk, so they should be within [0, chunk_length]
    if start_char < 0 or end_char < 0:
        return False
    
    if start_char >= end_char:
        return False
    
    if end_char > chunk_length:
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


def _get_ollama_embedding(text: str, model: str = "nomic-embed-text", base_url: str = "http://127.0.0.1:11434") -> Optional[List[float]]:
    """Get embedding for text using Ollama embeddings API.
    
    Note: MPS/GPU acceleration is automatically used by Ollama if configured.
    The _configure_mps_for_ollama() function should be called at module import
    or before first use to ensure environment variables are set.
    
    Args:
        text: Text to embed
        model: Ollama embedding model name (default: "nomic-embed-text")
        base_url: Ollama API base URL (default: "http://127.0.0.1:11434")
        
    Returns:
        List of floats representing the embedding, or None if failed
    """
    if not REQUESTS_AVAILABLE:
        logger.warning("requests library not available. Install with: pip install requests")
        return None
    
    try:
        response = requests.post(
            f"{base_url}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("embedding")
    except Exception as e:
        logger.warning(f"Failed to get embedding from Ollama: {e}")
        return None


def evaluate_semantic_accuracy(
    structured_plan: StructuredPlan,
    chunks: List,
    similarity_threshold: float = 0.7,
    embedding_model: str = "nomic-embed-text",
    config: Optional[Config] = None,
) -> Optional[Dict]:
    """Evaluate semantic accuracy of plan recommendations using Ollama embeddings.
    
    For each recommendation, computes semantic similarity between the recommendation
    text and the cited chunk text to verify the recommendation is supported.
    
    Args:
        structured_plan: StructuredPlan object with recommendations
        chunks: List of Chunk objects for citation mapping
        similarity_threshold: Threshold for considering a recommendation "well supported" (default: 0.7)
        embedding_model: Ollama embedding model name (default: "nomic-embed-text")
        config: Optional Config object (uses global config if None)
        
    Returns:
        Dict with semantic accuracy metrics, or None if embeddings not available
    """
    if not REQUESTS_AVAILABLE:
        logger.warning(
            "requests library not available. Install with: pip install requests"
        )
        return None
    
    if not NUMPY_AVAILABLE:
        logger.warning(
            "numpy not available. Install with: pip install numpy"
        )
        return None
    
    if config is None:
        config = get_config()
    
    # Use default Ollama base URL (can be overridden via environment variable if needed)
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    
    # Create chunk mapping
    chunk_map = {chunk.chunk_id: chunk for chunk in chunks}
    
    # Extract recommendations with sources
    plan_recommendations = extract_recommendations_from_structured_plan(structured_plan)
    plan_recs_with_source = [rec for rec in plan_recommendations if rec.get("source")]
    
    if not plan_recs_with_source:
        return {
            "average_similarity": None,
            "well_supported": 0,
            "poorly_supported": 0,
            "total_recommendations": 0,
            "support_rate": None,
            "per_recommendation": [],
        }
    
    per_recommendation = []
    similarity_scores = []
    
    for rec in plan_recs_with_source:
        rec_text = rec.get("text", "")
        citation_info = parse_citation_from_text(rec.get("source", ""))
        
        if not citation_info:
            # No valid citation, skip
            continue
        
        chunk_id, start_char, end_char, _ = citation_info
        
        if chunk_id not in chunk_map:
            # Chunk doesn't exist, skip
            continue
        
        chunk = chunk_map[chunk_id]
        
        # Extract cited text
        if start_char is not None and end_char is not None:
            # Use specific span (spans are global)
            if start_char >= chunk.start_char and end_char <= chunk.end_char:
                # Extract from chunk text using local offsets
                local_start = start_char - chunk.start_char
                local_end = end_char - chunk.start_char
                cited_text = chunk.text[local_start:local_end]
            else:
                # Span out of bounds, use entire chunk
                cited_text = chunk.text
        else:
            # No specific span, use entire chunk
            cited_text = chunk.text
        
        if not cited_text.strip():
            # Empty cited text, skip
            continue
        
        # Compute semantic similarity
        try:
            # Get embeddings from Ollama
            rec_embedding = _get_ollama_embedding(rec_text, model=embedding_model, base_url=base_url)
            cited_embedding = _get_ollama_embedding(cited_text, model=embedding_model, base_url=base_url)
            
            if rec_embedding is None or cited_embedding is None:
                logger.warning(f"Failed to get embeddings for recommendation {rec.get('number')}, skipping")
                continue
            
            # Convert to numpy arrays for computation
            rec_vec = np.array(rec_embedding)
            cited_vec = np.array(cited_embedding)
            
            # Compute cosine similarity
            similarity = float(np.dot(rec_vec, cited_vec) / 
                             (np.linalg.norm(rec_vec) * np.linalg.norm(cited_vec)))
            
            similarity_scores.append(similarity)
            is_supported = similarity >= similarity_threshold
            
            per_recommendation.append({
                "number": rec.get("number"),
                "similarity_score": round(similarity, 4),
                "is_supported": is_supported,
                "cited_chunk_id": chunk_id,
                "cited_text_preview": cited_text[:100] + "..." if len(cited_text) > 100 else cited_text,
            })
        except Exception as e:
            logger.warning(f"Failed to compute similarity for recommendation {rec.get('number')}: {e}")
            continue
    
    # Compute aggregate metrics
    well_supported = sum(1 for item in per_recommendation if item["is_supported"])
    poorly_supported = len(per_recommendation) - well_supported
    average_similarity = sum(similarity_scores) / len(similarity_scores) if similarity_scores else None
    support_rate = well_supported / len(per_recommendation) if per_recommendation else None
    
    return {
        "average_similarity": round(average_similarity, 4) if average_similarity is not None else None,
        "well_supported": well_supported,
        "poorly_supported": poorly_supported,
        "total_recommendations": len(per_recommendation),
        "support_rate": round(support_rate, 4) if support_rate is not None else None,
        "similarity_threshold": similarity_threshold,
        "per_recommendation": per_recommendation,
    }


def evaluate_summary_and_plan(
    structured_summary: StructuredSummary,
    structured_plan: StructuredPlan,
    canonical_note: CanonicalNote,
    chunks: List,
    config: Optional[Config] = None,
) -> Dict:
    """Evaluate summary and plan quality metrics.
    
    Args:
        structured_summary: StructuredSummary object
        structured_plan: StructuredPlan object
        canonical_note: CanonicalNote for text validation
        chunks: List of Chunk objects for citation mapping
        config: Optional Config object (uses global config if None)
        
    Returns:
        Dict: Evaluation metrics
    """
    text_length = len(canonical_note.text)
    
    # Semantic Accuracy Evaluation (always enabled)
    logger.info("Evaluating semantic accuracy of plan recommendations using Ollama embeddings...")
    if config is None:
        from app.config import get_config
        config = get_config()
    semantic_accuracy = evaluate_semantic_accuracy(structured_plan, chunks, config=config)
    
    # Extract items from structured summary
    summary_items = extract_items_from_structured_summary(structured_summary)
    
    # Extract recommendations from structured plan
    plan_recommendations = extract_recommendations_from_structured_plan(structured_plan)
    
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
    
    # Track new validation metrics separately for summary and plan
    summary_section_mismatches = 0
    summary_span_out_of_bounds = 0
    plan_section_mismatches = 0
    plan_span_out_of_bounds = 0
    
    for item in summary_items_with_source:
        citation_info = parse_citation_from_text(item.get("source", ""))
        if citation_info:
            chunk_id, start_char, end_char, section_name = citation_info
            total_citations += 1
            citation_invalid = False
            
            if chunk_id in chunk_map:
                chunk = chunk_map[chunk_id]
                
                # Validate section name if provided
                if section_name is not None:
                    if not validate_section_name(section_name, chunk.section_title):
                        summary_section_mismatches += 1
                        citation_invalid = True
                
                # Validate span bounds within chunk if spans provided
                # Note: spans in citations are GLOBAL, not local to chunk
                if start_char is not None and end_char is not None:
                    # Validate spans are within chunk's global bounds
                    if start_char < chunk.start_char or end_char > chunk.end_char:
                        summary_span_out_of_bounds += 1
                        citation_invalid = True
                    # Also validate against global text length
                    if not validate_citation_span(start_char, end_char, text_length):
                        citation_invalid = True
                else:
                    # Validate chunk bounds
                    if chunk.start_char < 0 or chunk.end_char > text_length:
                        citation_invalid = True
            else:
                # Chunk doesn't exist
                citation_invalid = True
            
            if citation_invalid:
                invalid_citations += 1
    
    for rec in plan_recs_with_source:
        citation_info = parse_citation_from_text(rec.get("source", ""))
        if citation_info:
            chunk_id, start_char, end_char, section_name = citation_info
            total_citations += 1
            citation_invalid = False
            
            if chunk_id in chunk_map:
                chunk = chunk_map[chunk_id]
                
                # Validate section name if provided
                if section_name is not None:
                    if not validate_section_name(section_name, chunk.section_title):
                        plan_section_mismatches += 1
                        citation_invalid = True
                
                # Validate span bounds within chunk if spans provided
                # Note: spans in citations are GLOBAL, not local to chunk
                if start_char is not None and end_char is not None:
                    # Validate spans are within chunk's global bounds
                    if start_char < chunk.start_char or end_char > chunk.end_char:
                        plan_span_out_of_bounds += 1
                        citation_invalid = True
                    # Also validate against global text length
                    if not validate_citation_span(start_char, end_char, text_length):
                        citation_invalid = True
                else:
                    # Validate chunk bounds
                    if chunk.start_char < 0 or chunk.end_char > text_length:
                        citation_invalid = True
            else:
                # Chunk doesn't exist
                citation_invalid = True
            
            if citation_invalid:
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
            chunk_id, start_char, end_char, _ = citation_info  # Ignore section_name for Jaccard
            if chunk_id in chunk_map:
                chunk = chunk_map[chunk_id]
                # Use character spans if available, otherwise use chunk spans
                # Note: spans in citations are already GLOBAL, not local to chunk
                if start_char is not None and end_char is not None:
                    all_citations.append({
                        "span": (start_char, end_char),
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
            chunk_id, start_char, end_char, _ = citation_info  # Ignore section_name for Jaccard
            if chunk_id in chunk_map:
                chunk = chunk_map[chunk_id]
                # Note: spans in citations are already GLOBAL, not local to chunk
                if start_char is not None and end_char is not None:
                    all_citations.append({
                        "span": (start_char, end_char),
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
            chunk_id, start_char, end_char, _ = citation_info  # Ignore section_name for span consistency
            if chunk_id in chunk_map:
                chunk = chunk_map[chunk_id]
                span_consistency_checks += 1
                # Check if chunk text is not empty
                if chunk.text and len(chunk.text) > 0:
                    span_consistency_passed += 1
    
    for rec in plan_recs_with_source:
        citation_info = parse_citation_from_text(rec.get("source", ""))
        if citation_info:
            chunk_id, start_char, end_char, _ = citation_info  # Ignore section_name for span consistency
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
        "section_name_mismatches": {
            "summary": summary_section_mismatches,
            "plan": plan_section_mismatches,
            "total": summary_section_mismatches + plan_section_mismatches,
        },
        "span_out_of_chunk_bounds": {
            "summary": summary_span_out_of_bounds,
            "plan": plan_span_out_of_bounds,
            "total": summary_span_out_of_bounds + plan_span_out_of_bounds,
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
    
    # Add semantic accuracy (always included)
    if semantic_accuracy is not None:
        evaluation["semantic_accuracy"] = semantic_accuracy
    
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

