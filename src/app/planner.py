"""Plan generation from chunks with prioritized treatment recommendations."""

import logging
from pathlib import Path
from typing import List

from app.chunks import Chunk
from app.llm import LLMClient

logger = logging.getLogger(__name__)


def create_treatment_plan_from_chunks(
    chunks: List[Chunk],
    llm_client: LLMClient,
) -> str:
    """Create a prioritized treatment plan from all chunks.

    Args:
        chunks: List of chunks to generate plan from
        llm_client: LLM client instance

    Returns:
        str: Structured treatment plan text

    Raises:
        LLMError: If LLM call fails
    """
    # Combine chunks with section headers and chunk IDs for citation
    chunks_text = []
    for chunk in chunks:
        # Add section header with chunk ID for citation
        # chunk.chunk_id is already in format "chunk_0", "chunk_1", etc.
        chunks_text.append(f"## {chunk.section_title} ({chunk.chunk_id})")
        chunks_text.append(chunk.text)
        chunks_text.append("")  # Empty line between sections

    combined_text = "\n".join(chunks_text)

    # Load prompt template
    try:
        prompt_template = llm_client.load_prompt("plan_generation.md")
        prompt = prompt_template.format(chunks_with_headers=combined_text)
    except FileNotFoundError:
        # Fallback prompt if template doesn't exist
        prompt = f"""Generate a prioritized treatment plan based on the following clinical note.

The note is organized into sections with chunk IDs for citation:

{combined_text}

Provide a structured treatment plan with:
1. Diagnostics (tests, imaging, procedures)
2. Therapeutics (medications, treatments, interventions)
3. Follow-ups (monitoring, appointments, re-evaluations)

For each recommendation, include:
- Rationale with explicit citations (chunk_ID:start-end or "Section Name, paragraph X")
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

