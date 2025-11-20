"""Plan generation from text summary with prioritized treatment recommendations."""

import json
import logging
from pathlib import Path
from typing import List, Optional

from app.llm import LLMClient
from app.schemas import PlanRecommendation, StructuredPlan, StructuredSummary
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
    structured_summary: Optional[StructuredSummary] = None,
) -> StructuredPlan:
    """Create a prioritized treatment plan from text summary.

    Args:
        summary_text: Text summary content to generate plan from
        llm_client: LLM client instance
        structured_summary: Optional StructuredSummary object (if available, will be included as JSON in prompt)

    Returns:
        StructuredPlan: Structured treatment plan with recommendations

    Raises:
        LLMError: If LLM call fails
        ValueError: If plan cannot be parsed or validated
    """
    # Format summary for prompt - include both text and JSON if available
    section_titles_text = "(extract from summary sources)"
    
    if structured_summary:
        # Extract all unique section titles from source fields
        import re
        section_titles = set()
        for section_items in [
            structured_summary.patient_snapshot,
            structured_summary.key_problems,
            structured_summary.pertinent_history,
            structured_summary.medicines_allergies,
            structured_summary.objective_findings,
            structured_summary.labs_imaging,
            structured_summary.assessment,
        ]:
            for item in section_items:
                # Extract section title from source (format: "SECTION_NAME section, chunk_X:Y-Z")
                match = re.match(r'^([^,]+?)\s+section,', item.source)
                if match:
                    section_titles.add(match.group(1))
        
        section_titles_list = sorted(list(section_titles))
        section_titles_text = "\n".join([f"- \"{title} section\"" for title in section_titles_list])
        
        # Include JSON representation so LLM can see exact structure and source fields
        summary_json = json.dumps(structured_summary.model_dump(), indent=2, ensure_ascii=False)
        combined_text = f"{summary_text}\n\n**Summary JSON (for reference):**\n```json\n{summary_json}\n```"
    else:
        combined_text = summary_text

    # Load prompt template
    try:
        prompt_template = llm_client.load_prompt("plan_generation.md")
        prompt = prompt_template.format(summary_sections=combined_text, section_titles_list=section_titles_text)
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
            lines.append(f"{rec.recommendation}")
            lines.append(f"  Source: {rec.source}")
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

