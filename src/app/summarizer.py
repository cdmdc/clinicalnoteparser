"""Chunk-level fact extraction and aggregation with deduplication."""

import json
import logging
import re
from pathlib import Path
from typing import List, Optional

from app.chunks import Chunk
from app.config import Config, get_config
from app.ingestion import char_span_to_page
from app.llm import LLMClient, LLMError
from app.schemas import (
    CanonicalNote,
    ChunkExtraction,
    Citation,
    PatientSnapshot,
    SpanFact,
    Summary,
)

logger = logging.getLogger(__name__)


def extract_facts_from_chunk(
    chunk: Chunk,
    llm_client: LLMClient,
    canonical_note: CanonicalNote,
) -> ChunkExtraction:
    """Extract facts from a single chunk using LLM.

    Args:
        chunk: Chunk to extract facts from
        llm_client: LLM client instance
        canonical_note: CanonicalNote for page mapping

    Returns:
        ChunkExtraction: Extracted facts with validated citations

    Raises:
        LLMError: If LLM call fails
        ValueError: If extraction cannot be parsed or validated
    """
    try:
        # Load prompt template
        prompt_template = llm_client.load_prompt("summary_extraction.md")

        # Format prompt with chunk data
        prompt = prompt_template.format(
            chunk_id=chunk.chunk_id,
            section_title=chunk.section_title,
            chunk_text=chunk.text,
        )

        # Call LLM
        response = llm_client.call(prompt, logger_instance=logger)

        # Parse response - the LLM returns dict with facts containing citation dicts
        # We need to convert citation dicts to proper format before creating ChunkExtraction
        facts_data = response.get("facts", [])
        parsed_facts = []
        for fact_data in facts_data:
            # Citations come as dicts with start_char_local/end_char_local
            # We'll process them in the validation step below
            parsed_facts.append(fact_data)
        response["facts"] = parsed_facts
        
        # Create ChunkExtraction - but we'll need to handle citations specially
        # since SpanFact expects Citation objects, not dicts
        # For now, we'll parse manually
        extraction_facts = []
        for fact_data in facts_data:
            # Extract citation data (will be converted to Citation objects later)
            extraction_facts.append({
                "fact_text": fact_data.get("fact_text", ""),
                "category": fact_data.get("category", "other"),
                "citations": fact_data.get("citations", []),  # Keep as dicts for now
                "confidence": fact_data.get("confidence", 1.0),
                "uncertainty_note": fact_data.get("uncertainty_note"),
            })
        
        # Create a temporary structure for processing
        class TempExtraction:
            def __init__(self, chunk_id, facts):
                self.chunk_id = chunk_id
                self.facts = facts
        
        extraction = TempExtraction(response.get("chunk_id", chunk.chunk_id), extraction_facts)

        # Validate and convert citations
        validated_facts = []
        for fact_data in extraction.facts:
            validated_citations = []
            citations_data = fact_data.get("citations", [])

            for citation in citations_data:
                # Citations come as dicts with start_char_local/end_char_local
                start_local = citation.get("start_char_local", 0)
                end_local = citation.get("end_char_local", 0)

                if not (0 <= start_local < end_local <= len(chunk.text)):
                    logger.warning(
                        f"Invalid citation span in chunk {chunk.chunk_id}: "
                        f"start={start_local}, end={end_local}, chunk_len={len(chunk.text)}"
                    )
                    continue

                # Convert local spans to global spans
                start_global = chunk.start_char + start_local
                end_global = chunk.start_char + end_local

                # Get page number
                page = char_span_to_page(start_global, end_global, canonical_note.page_spans)

                validated_citations.append(
                    Citation(
                        start_char=start_global,
                        end_char=end_global,
                        page=page,
                    )
                )

            # Only include facts with at least one valid citation
            if validated_citations:
                fact = SpanFact(
                    fact_text=fact_data.get("fact_text", ""),
                    category=fact_data.get("category", "other"),
                    citations=validated_citations,
                    confidence=fact_data.get("confidence", 1.0),
                    uncertainty_note=fact_data.get("uncertainty_note"),
                )
                validated_facts.append(fact)
            else:
                logger.warning(
                    f"Fact '{fact_data.get('fact_text', '')[:50]}...' in chunk {chunk.chunk_id} "
                    "has no valid citations, skipping"
                )

        # Return ChunkExtraction with validated facts
        return ChunkExtraction(chunk_id=extraction.chunk_id, facts=validated_facts)

    except Exception as e:
        logger.error(f"Error extracting facts from chunk {chunk.chunk_id}: {e}")
        raise


def normalize_text_for_dedup(text: str) -> str:
    """Normalize text for deduplication comparison.

    Args:
        text: Text to normalize

    Returns:
        str: Normalized text (lowercase, no punctuation, collapsed whitespace)
    """
    # Lowercase
    text = text.lower()
    # Remove punctuation
    text = re.sub(r"[^\w\s]", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def calculate_text_similarity(text1: str, text2: str) -> float:
    """Calculate simple character-based text similarity.

    Args:
        text1: First text
        text2: Second text

    Returns:
        float: Similarity score [0, 1]
    """
    norm1 = normalize_text_for_dedup(text1)
    norm2 = normalize_text_for_dedup(text2)

    if not norm1 or not norm2:
        return 0.0

    # Simple character-based similarity (Levenshtein-like)
    # For simplicity, use set intersection
    set1 = set(norm1.split())
    set2 = set(norm2.split())

    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def calculate_span_overlap(span1: Citation, span2: Citation) -> float:
    """Calculate overlap between two citation spans.

    Args:
        span1: First citation span
        span2: Second citation span

    Returns:
        float: Overlap ratio [0, 1]
    """
    # Calculate intersection
    start_overlap = max(span1.start_char, span2.start_char)
    end_overlap = min(span1.end_char, span2.end_char)

    if start_overlap >= end_overlap:
        return 0.0

    overlap_length = end_overlap - start_overlap
    span1_length = span1.end_char - span1.start_char
    span2_length = span2.end_char - span2.start_char

    # Return overlap as percentage of smaller span
    min_length = min(span1_length, span2_length)
    return overlap_length / min_length if min_length > 0 else 0.0


def deduplicate_facts(facts: List[SpanFact]) -> List[SpanFact]:
    """Deduplicate facts using span overlap and text similarity.

    Args:
        facts: List of facts to deduplicate

    Returns:
        List[SpanFact]: Deduplicated facts
    """
    if not facts:
        return []

    # Normalize and compare facts
    deduplicated = []
    seen = set()

    for fact in facts:
        # Check if we've already seen a similar fact
        is_duplicate = False

        for existing_fact in deduplicated:
            # Check text similarity
            similarity = calculate_text_similarity(fact.fact_text, existing_fact.fact_text)
            if similarity > 0.9:
                # Check span overlap
                max_overlap = 0.0
                for cit1 in fact.citations:
                    for cit2 in existing_fact.citations:
                        overlap = calculate_span_overlap(cit1, cit2)
                        max_overlap = max(max_overlap, overlap)

                if max_overlap > 0.8 or similarity > 0.9:
                    # Merge facts: keep the one with more citations
                    if len(fact.citations) > len(existing_fact.citations):
                        # Replace existing fact
                        deduplicated.remove(existing_fact)
                        deduplicated.append(fact)
                    # Otherwise, keep existing fact
                    is_duplicate = True
                    break

        if not is_duplicate:
            deduplicated.append(fact)

    logger.info(f"Deduplicated {len(facts)} facts to {len(deduplicated)} unique facts")
    return deduplicated


def categorize_facts(facts: List[SpanFact]) -> dict[str, List[SpanFact]]:
    """Categorize facts into groups.

    Args:
        facts: List of facts to categorize

    Returns:
        dict: Categorized facts by category name
    """
    categories = {
        "problems": [],
        "medications": [],
        "allergies": [],
        "history": [],
        "exam": [],
        "labs_imaging": [],
        "other": [],
    }

    for fact in facts:
        category = fact.category.lower()
        if category in categories:
            categories[category].append(fact)
        else:
            categories["other"].append(fact)

    return categories


def extract_patient_snapshot_from_facts(
    facts: List[SpanFact],
    llm_client: Optional[LLMClient] = None,
) -> PatientSnapshot:
    """Extract patient snapshot from facts.

    Args:
        facts: List of extracted facts
        llm_client: Optional LLM client for extraction (fallback to regex if None)

    Returns:
        PatientSnapshot: Patient demographics and summary
    """
    # Try LLM extraction first if available
    if llm_client:
        try:
            # Create a summary of facts for LLM
            facts_summary = "\n".join([f"- {f.fact_text}" for f in facts[:20]])  # Limit to first 20

            prompt = f"""Extract patient demographics from the following facts:
{facts_summary}

Return JSON:
{{
  "age": "age as string or null",
  "sex": "M/F/other or null",
  "summary": "brief patient summary or null"
}}"""

            response = llm_client.call(prompt, logger_instance=logger)
            return PatientSnapshot(**response)

        except Exception as e:
            logger.warning(f"LLM patient snapshot extraction failed: {e}, using regex fallback")

    # Regex fallback
    age = None
    sex = None
    summary = None

    # Look for age patterns
    age_pattern = r"(\d+)[-\s]*(?:year|yr|y\.o\.|yo)[-\s]*(?:old|male|female)"
    for fact in facts:
        match = re.search(age_pattern, fact.fact_text, re.IGNORECASE)
        if match:
            age = match.group(1)
            break

    # Look for sex patterns
    sex_patterns = [
        r"\b(male|m)\b",
        r"\b(female|f)\b",
    ]
    for fact in facts:
        for pattern in sex_patterns:
            match = re.search(pattern, fact.fact_text, re.IGNORECASE)
            if match:
                sex = match.group(1).upper()[0]  # M or F
                break
        if sex:
            break

    return PatientSnapshot(age=age, sex=sex, summary=summary)


def extract_summary(
    chunks: List[Chunk],
    canonical_note: CanonicalNote,
    config: Optional[Config] = None,
    llm_client: Optional[LLMClient] = None,
) -> Summary:
    """Extract summary from chunks with error handling and deduplication.

    Args:
        chunks: List of chunks to extract facts from
        canonical_note: CanonicalNote for page mapping
        config: Configuration instance (uses global config if None)
        llm_client: Optional LLM client (creates new one if None)

    Returns:
        Summary: Complete summary with all facts

    Raises:
        ValueError: If failure rate exceeds threshold
    """
    if config is None:
        config = get_config()

    if llm_client is None:
        llm_client = LLMClient(config)

    # Extract facts from chunks
    all_facts = []
    failed_chunks = []

    for chunk in chunks:
        try:
            extraction = extract_facts_from_chunk(chunk, llm_client, canonical_note)
            all_facts.extend(extraction.facts)
            logger.info(f"Extracted {len(extraction.facts)} facts from chunk {chunk.chunk_id}")

        except Exception as e:
            failed_chunks.append((chunk.chunk_id, str(e)))
            logger.error(f"Failed to extract facts from chunk {chunk.chunk_id}: {e}")

    # Check failure rate
    failure_rate = len(failed_chunks) / len(chunks) if chunks else 0.0
    if failure_rate >= config.max_chunk_failure_rate:
        raise ValueError(
            f"Chunk extraction failure rate ({failure_rate:.1%}) exceeds threshold "
            f"({config.max_chunk_failure_rate:.1%}). Failed chunks: {failed_chunks}"
        )

    if failure_rate > 0:
        logger.warning(
            f"Some chunks failed ({len(failed_chunks)}/{len(chunks)}), "
            f"but continuing with partial results"
        )

    # Deduplicate facts
    deduplicated_facts = deduplicate_facts(all_facts)

    # Categorize facts
    categorized = categorize_facts(deduplicated_facts)

    # Extract patient snapshot
    patient_snapshot = extract_patient_snapshot_from_facts(deduplicated_facts, llm_client)

    # Create summary
    summary = Summary(
        patient_snapshot=patient_snapshot,
        problems=categorized["problems"],
        medications=categorized["medications"],
        allergies=categorized["allergies"],
        history=categorized["history"],
        exam=categorized["exam"],
        labs_imaging=categorized["labs_imaging"],
        other_facts=categorized["other"],
    )

    logger.info(
        f"Created summary: {len(deduplicated_facts)} facts, "
        f"{len(categorized['problems'])} problems, "
        f"{len(categorized['medications'])} medications"
    )

    return summary


def create_text_summary_from_chunks(
    chunks: List[Chunk],
    llm_client: LLMClient,
) -> str:
    """Create a text summary from all chunks, preserving section headers.

    Args:
        chunks: List of chunks to summarize
        llm_client: LLM client instance

    Returns:
        str: Text summary with preserved section headers

    Raises:
        LLMError: If LLM call fails
    """
    # Combine chunks with section headers
    chunks_text = []
    for chunk in chunks:
        # Add section header
        chunks_text.append(f"## {chunk.section_title}")
        chunks_text.append(chunk.text)
        chunks_text.append("")  # Empty line between sections

    combined_text = "\n".join(chunks_text)

    # Load prompt template
    try:
        prompt_template = llm_client.load_prompt("text_summary.md")
        prompt = prompt_template.format(chunks_with_headers=combined_text)
    except FileNotFoundError:
        # Fallback prompt if template doesn't exist
        prompt = f"""Create a comprehensive summary of the following clinical note while preserving all section headers.

The note is organized into sections:

{combined_text}

Provide a well-structured summary that:
1. Preserves all section headers from the original document
2. Summarizes the content under each section
3. Maintains clinical accuracy and completeness
4. Uses clear, professional medical language

Start your response with the section headers and provide summaries under each."""

    # Call LLM - this time we want plain text, not JSON
    response = llm_client.call(prompt, logger_instance=logger, return_text=True)
    
    # Response should be a string when return_text=True
    if isinstance(response, str):
        return response
    
    # Fallback: convert to string
    return str(response)


def save_summary(summary: Summary, output_path: Path) -> None:
    """Save summary to JSON file.

    Args:
        summary: Summary to save
        output_path: Path to save summary JSON file

    Raises:
        ValueError: If summary cannot be validated
    """
    # Validate summary
    try:
        # Pydantic validation happens automatically on model creation
        # But we can do additional checks here if needed
        pass
    except Exception as e:
        raise ValueError(f"Invalid summary: {e}") from e

    # Convert to dict for JSON serialization
    summary_data = summary.model_dump()

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved summary to {output_path}")

