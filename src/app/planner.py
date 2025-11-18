"""Plan generation from text summary with prioritized treatment recommendations."""

import json
import logging
from pathlib import Path
from typing import List

from app.llm import LLMClient

logger = logging.getLogger(__name__)


def load_text_summary(summary_txt_path: Path) -> str:
    """Load text summary from file.
    
    Args:
        summary_txt_path: Path to summary.txt file
        
    Returns:
        str: Text summary content
        
    Raises:
        FileNotFoundError: If summary file doesn't exist
        ValueError: If summary file is empty or cannot be read
    """
    if not summary_txt_path.exists():
        raise FileNotFoundError(f"Summary file not found: {summary_txt_path}")
    
    try:
        summary_text = summary_txt_path.read_text(encoding="utf-8")
        
        if not summary_text or not summary_text.strip():
            raise ValueError("Summary file is empty")
        
        logger.info(f"Loaded text summary from {summary_txt_path} ({len(summary_text)} characters)")
        return summary_text
    
    except Exception as e:
        raise ValueError(f"Error loading text summary: {e}") from e


def create_treatment_plan_from_summary(
    summary_text: str,
    llm_client: LLMClient,
) -> str:
    """Create a prioritized treatment plan from text summary.

    Args:
        summary_text: Text summary content to generate plan from
        llm_client: LLM client instance

    Returns:
        str: Structured treatment plan text

    Raises:
        LLMError: If LLM call fails
    """
    # Use the text summary directly - it already has the proper format with sections and citations
    combined_text = summary_text

    # Load prompt template
    try:
        prompt_template = llm_client.load_prompt("plan_generation.md")
        prompt = prompt_template.format(summary_sections=combined_text)
    except FileNotFoundError:
        # Fallback prompt if template doesn't exist
        prompt = f"""Generate a prioritized treatment plan based on the following clinical summary.

The summary is organized into sections with source citations:

{combined_text}

Provide a structured treatment plan with:
1. Diagnostics (tests, imaging, procedures)
2. Therapeutics (medications, treatments, interventions)
3. Follow-ups (monitoring, appointments, re-evaluations)

For each recommendation, include:
- Source with explicit citations (use the source citations provided in the summary, e.g., "chunk_0:10-50" or "Section Name, paragraph X")
- Confidence score [0, 1]
- Risks/Benefits (if applicable)
- Hallucination Guard Note (if confidence < 0.8 or evidence is weak)

Order recommendations by clinical urgency, evidence strength, and logical sequence."""

    # Call LLM - return plain text
    response = llm_client.call(prompt, logger_instance=logger, return_text=True)

    # Response should be a string when return_text=True
    if isinstance(response, str):
        return response

    # Fallback: convert to string
    return str(response)


def save_plan(plan_text: str, output_path: Path) -> None:
    """Save treatment plan to text file.

    Args:
        plan_text: Treatment plan text
        output_path: Path to save plan text file

    Raises:
        ValueError: If plan text is empty
    """
    if not plan_text or not plan_text.strip():
        raise ValueError("Plan text is empty")

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(plan_text, encoding="utf-8")

    logger.info(f"Saved treatment plan to {output_path}")


def create_treatment_plan_from_chunks(
    chunks: List,
    llm_client: LLMClient,
) -> str:
    """Create a prioritized treatment plan from chunks (DEPRECATED - use create_treatment_plan_from_summary instead).
    
    This function is kept for backward compatibility. It formats chunks and calls
    create_treatment_plan_from_summary internally.

    Args:
        chunks: List of chunks to generate plan from
        llm_client: LLM client instance

    Returns:
        str: Structured treatment plan text

    Raises:
        LLMError: If LLM call fails
    """
    from app.chunks import Chunk
    
    # Format chunks as a simple summary structure for backward compatibility
    # This is a simplified conversion - ideally use structured summary
    chunks_text = []
    for chunk in chunks:
        chunks_text.append(f"## {chunk.section_title} ({chunk.chunk_id})")
        chunks_text.append(chunk.text)
        chunks_text.append("")
    
    combined_text = "\n".join(chunks_text)
    
    # Use the same prompt as summary-based planning
    try:
        prompt_template = llm_client.load_prompt("plan_generation.md")
        prompt = prompt_template.format(summary_sections=combined_text)
    except FileNotFoundError:
        prompt = f"""Generate a prioritized treatment plan based on the following clinical note.

The note is organized into sections with chunk IDs for citation:

{combined_text}

Provide a structured treatment plan with:
1. Diagnostics (tests, imaging, procedures)
2. Therapeutics (medications, treatments, interventions)
3. Follow-ups (monitoring, appointments, re-evaluations)

For each recommendation, include:
- Source with explicit citations (chunk_ID:start-end or "Section Name, paragraph X")
- Confidence score [0, 1]
- Risks/Benefits (if applicable)
- Hallucination Guard Note (if confidence < 0.8 or evidence is weak)

Order recommendations by clinical urgency, evidence strength, and logical sequence."""

    # Call LLM - return plain text
    response = llm_client.call(prompt, logger_instance=logger, return_text=True)

    if isinstance(response, str):
        return response

    return str(response)

