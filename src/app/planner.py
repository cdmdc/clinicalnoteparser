"""Plan generation from text summary with prioritized treatment recommendations."""

import json
import logging
from pathlib import Path
from typing import List

from app.llm import LLMClient
from app.schemas import PlanField, PlanRecommendation, StructuredPlan
from app.summarizer import format_structured_summary_as_text

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
) -> StructuredPlan:
    """Create a prioritized treatment plan from text summary.

    Args:
        summary_text: Text summary content to generate plan from
        llm_client: LLM client instance

    Returns:
        StructuredPlan: Structured treatment plan with recommendations

    Raises:
        LLMError: If LLM call fails
        ValueError: If plan cannot be parsed or validated
    """
    # Use the text summary directly - it already has the proper format with sections and citations
    combined_text = summary_text

    # Load prompt template
    try:
        prompt_template = llm_client.load_prompt("plan_generation.md")
        prompt = prompt_template.format(summary_sections=combined_text)
    except FileNotFoundError:
        # Fallback prompt if template doesn't exist
        prompt = f"""Generate a prioritized treatment plan based on the following clinical summary in JSON format.

The summary is organized into sections with source citations:

{combined_text}

Provide a structured treatment plan as JSON with:
1. Diagnostics (tests, imaging, procedures)
2. Therapeutics (medications, treatments, interventions)
3. Follow-ups (monitoring, appointments, re-evaluations)

For each recommendation, include:
- Source with explicit citations (use the source citations provided in the summary)
- Confidence score [0, 1]
- Risks/Benefits (if applicable)
- Hallucination Guard Note (if confidence < 0.8 or evidence is weak)

Order recommendations by clinical urgency, evidence strength, and logical sequence."""

    # Call LLM - request JSON output (return_text=False will parse JSON)
    response = llm_client.call(prompt, logger_instance=logger, return_text=False)

    # Response should be a dict when return_text=False
    if isinstance(response, dict):
        try:
            return StructuredPlan(**response)
        except Exception as e:
            raise ValueError(f"Could not parse LLM response as StructuredPlan: {e}. Response: {response}") from e

    # Fallback: try to parse as string
    if isinstance(response, str):
        try:
            data = json.loads(response)
            return StructuredPlan(**data)
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Could not parse LLM response as StructuredPlan: {e}") from e

    raise ValueError(f"Unexpected response type from LLM: {type(response)}")


def save_plan(structured_plan: StructuredPlan, output_path: Path) -> None:
    """Save structured treatment plan to JSON file.

    Args:
        structured_plan: StructuredPlan to save
        output_path: Path to save plan JSON file

    Raises:
        ValueError: If plan cannot be validated
    """
    # Validate plan
    try:
        # Pydantic validation happens automatically on model creation
        pass
    except Exception as e:
        raise ValueError(f"Invalid structured plan: {e}") from e

    # Convert to dict for JSON serialization
    plan_data = structured_plan.model_dump()

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved structured plan to {output_path}")


def load_plan(plan_json_path: Path) -> StructuredPlan:
    """Load structured plan from JSON file.

    Args:
        plan_json_path: Path to plan.json file

    Returns:
        StructuredPlan: Structured plan object

    Raises:
        FileNotFoundError: If plan file doesn't exist
        ValueError: If plan file cannot be parsed or validated
    """
    if not plan_json_path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_json_path}")

    try:
        with open(plan_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        structured_plan = StructuredPlan(**data)
        logger.info(f"Loaded structured plan from {plan_json_path}")
        return structured_plan

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in plan file: {e}") from e
    except Exception as e:
        raise ValueError(f"Error loading structured plan: {e}") from e


def format_plan_as_text(structured_plan: StructuredPlan) -> str:
    """Format structured plan as readable text for display.

    Args:
        structured_plan: StructuredPlan to format

    Returns:
        str: Formatted text plan
    """
    lines = []
    lines.append("**Prioritized Treatment Plan**")
    lines.append("")

    if not structured_plan.recommendations:
        lines.append("No recommendations identified.")
        lines.append("")
    else:
        for rec in structured_plan.recommendations:
            lines.append(f"**Recommendation {rec.number}**")
            lines.append("")
            
            if rec.diagnostics:
                lines.append(f"Diagnostics: {rec.diagnostics.content}")
                lines.append(f"  Source: {rec.diagnostics.source}")
            if rec.therapeutics:
                lines.append(f"Therapeutics: {rec.therapeutics.content}")
                lines.append(f"  Source: {rec.therapeutics.source}")
            if rec.risks_benefits:
                lines.append(f"Risks/Benefits: {rec.risks_benefits.content}")
                lines.append(f"  Source: {rec.risks_benefits.source}")
            if rec.follow_ups:
                lines.append(f"Follow-ups: {rec.follow_ups.content}")
                lines.append(f"  Source: {rec.follow_ups.source}")
            
            lines.append(f"Confidence: {rec.confidence}")
            if rec.hallucination_guard_note:
                lines.append(f"Hallucination Guard Note: {rec.hallucination_guard_note}")
            lines.append("")

    return "\n".join(lines)


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

