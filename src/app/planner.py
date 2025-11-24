"""Plan generation from text summary with prioritized treatment recommendations."""

import json
import logging
from pathlib import Path
from typing import List, Optional

try:
    from pydantic import ValidationError
except ImportError:
    # Fallback for older Pydantic versions
    ValidationError = ValueError

from app.llm import LLMClient, LLMError
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


def _clean_plan_response(response: dict) -> dict:
    """Clean up LLM response to fix invalid or missing fields.
    
    The LLM sometimes returns 'priority' instead of 'confidence', or may omit
    required fields. This function normalizes the response to match the schema.
    
    Args:
        response: Raw LLM response dictionary
        
    Returns:
        Cleaned response dictionary with valid fields
    """
    cleaned = response.copy()
    
    # Clean recommendations if present
    if "recommendations" in cleaned and isinstance(cleaned["recommendations"], list):
        cleaned_recs = []
        for rec in cleaned["recommendations"]:
            if isinstance(rec, dict):
                cleaned_rec = rec.copy()
                
                # Convert priority to confidence if confidence is missing
                if "confidence" not in cleaned_rec or cleaned_rec.get("confidence") is None:
                    if "priority" in cleaned_rec:
                        # Convert priority (1, 2, 3...) to confidence (0.0-1.0)
                        # Higher priority (lower number) = higher confidence
                        priority = cleaned_rec["priority"]
                        if isinstance(priority, (int, float)) and priority > 0:
                            # Inverse mapping: priority 1 -> 0.9, priority 2 -> 0.8, etc.
                            # Cap at 0.5 minimum for lower priorities
                            confidence = max(0.5, 1.0 - (priority - 1) * 0.1)
                        else:
                            confidence = 0.8  # Default confidence
                        cleaned_rec["confidence"] = confidence
                    else:
                        # No priority or confidence - use default
                        cleaned_rec["confidence"] = 0.8
                
                # Ensure confidence is a float between 0.0 and 1.0
                confidence = cleaned_rec.get("confidence")
                if confidence is not None:
                    try:
                        confidence = float(confidence)
                        cleaned_rec["confidence"] = max(0.0, min(1.0, confidence))
                    except (ValueError, TypeError):
                        cleaned_rec["confidence"] = 0.8
                else:
                    cleaned_rec["confidence"] = 0.8
                
                # Ensure hallucination_guard_note is None if not provided
                if "hallucination_guard_note" not in cleaned_rec:
                    cleaned_rec["hallucination_guard_note"] = None
                elif cleaned_rec["hallucination_guard_note"] == "":
                    cleaned_rec["hallucination_guard_note"] = None
                
                cleaned_recs.append(cleaned_rec)
            else:
                cleaned_recs.append(rec)
        cleaned["recommendations"] = cleaned_recs
    
    return cleaned


def _validate_plan_citations_against_summary(
    response: dict, 
    structured_summary: Optional[StructuredSummary]
) -> List[str]:
    """Validate plan citations against summary's citation section names.
    
    Plan recommendations should cite sections that exist in the summary.
    This validates that cited section names match those used in the summary.
    
    Args:
        response: LLM plan response dictionary with citations
        structured_summary: StructuredSummary object to validate against
        
    Returns:
        List[str]: List of error messages for citation mismatches
    """
    from app.evaluation import parse_citation_from_text
    
    errors = []
    
    if structured_summary is None:
        return errors  # Can't validate without summary
    
    # Extract all valid section names from summary citations
    valid_section_names = set()
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
            # Parse citation to extract section name
            citation_info = parse_citation_from_text(item.source)
            if citation_info:
                chunk_id, start_char, end_char, section_name = citation_info
                if section_name:
                    valid_section_names.add(section_name.upper())
    
    # Validate plan recommendations' citations
    if "recommendations" in response and isinstance(response["recommendations"], list):
        for rec in response["recommendations"]:
            if not isinstance(rec, dict) or "source" not in rec:
                continue
                
            source = rec.get("source", "")
            if not isinstance(source, str) or not source.strip():
                continue
            
            # Parse citation
            citation_info = parse_citation_from_text(source)
            if citation_info is None:
                continue
                
            chunk_id, start_char, end_char, cited_section_name = citation_info
            
            # Check if cited section name exists in summary
            if cited_section_name and cited_section_name.upper() not in valid_section_names:
                errors.append(
                    f"Plan recommendation cites section '{cited_section_name}' "
                    f"which does not exist in the summary. Valid sections: {', '.join(sorted(valid_section_names)[:5])}..."
                )
    
    return errors


def _extract_validation_errors(error: Exception) -> str:
    """Extract concise, actionable error messages from Pydantic ValidationError.
    
    Args:
        error: Exception (typically ValidationError or ValueError)
        
    Returns:
        str: Concise error message with actionable feedback
    """
    # Check if it's a Pydantic ValidationError
    if hasattr(error, 'errors') and callable(error.errors):
        try:
            errors = error.errors()
            error_messages = []
            # Limit to first 3 errors to keep feedback concise
            for err in errors[:3]:
                field_path = '.'.join(str(x) for x in err.get('loc', []))
                msg = err.get('msg', 'Unknown error')
                error_type = err.get('type', '')
                
                # Format error message
                if field_path:
                    error_messages.append(f"{field_path}: {msg}")
                else:
                    error_messages.append(f"{msg}")
            
            if error_messages:
                return "; ".join(error_messages)
        except Exception:
            # If error.errors() fails, fall back to string representation
            pass
    
    # Fallback: use string representation, truncated
    error_str = str(error)
    # Truncate long error messages
    if len(error_str) > 300:
        return error_str[:300] + "..."
    return error_str


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

    # Call LLM with validation retry wrapper
    # Try with existing cleaning function first, retry with feedback on validation errors
    current_prompt = prompt
    max_validation_retries = 2  # Limit validation retries to avoid token waste
    
    for validation_attempt in range(1, max_validation_retries + 1):
        try:
            # Call LLM - request JSON output (return_text=False will parse JSON)
            response = llm_client.call(current_prompt, logger_instance=logger, return_text=False)

            # Response should be a dict when return_text=False
            if isinstance(response, dict):
                # Clean up response: fix invalid or missing fields
                cleaned_response = _clean_plan_response(response)
                
                try:
                    structured_plan = StructuredPlan(**cleaned_response)
                    # Success - return the structured plan
                    return structured_plan
                    
                except (ValueError, ValidationError) as e:
                    if validation_attempt < max_validation_retries:
                        # Extract actionable error info from Pydantic
                        error_msg = _extract_validation_errors(e)
                        
                        logger.warning(f"Validation failed (attempt {validation_attempt}/{max_validation_retries}): {error_msg[:200]}...")
                        logger.info("Retrying with validation error feedback...")
                        
                        # Append error feedback to prompt
                        current_prompt = f"{prompt}\n\nERROR: The previous response failed validation. Please fix the following issues:\n{error_msg}\n\nPlease provide a corrected JSON response that addresses all validation errors."
                        continue  # Retry with feedback
                    else:
                        raise ValueError(f"Could not parse LLM response as StructuredPlan: {e}. Response: {cleaned_response}") from e

            # Fallback: try to parse as string
            if isinstance(response, str):
                try:
                    data = json.loads(response)
                    # Clean up response: fix invalid or missing fields
                    if isinstance(data, dict):
                        data = _clean_plan_response(data)
                        structured_plan = StructuredPlan(**data)
                        return structured_plan
                    else:
                        raise ValueError(f"Expected dict, got {type(data)}")
                except (json.JSONDecodeError, ValueError, ValidationError) as e:
                    if validation_attempt < max_validation_retries:
                        error_msg = _extract_validation_errors(e)
                        
                        
                        logger.warning(f"Validation failed (attempt {validation_attempt}/{max_validation_retries}): {error_msg[:200]}...")
                        logger.info("Retrying with validation error feedback...")
                        current_prompt = f"{prompt}\n\nERROR: The previous response failed validation. Please fix the following issues:\n{error_msg}\n\nPlease provide a corrected JSON response that addresses all validation errors."
                        continue
                    raise ValueError(f"Could not parse LLM response as StructuredPlan: {e}") from e
            
            raise ValueError(f"Unexpected response type from LLM: {type(response)}")
            
        except LLMError:
            # LLM call failed (network/parsing errors) - don't retry validation, re-raise
            raise


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
    section_titles = set()
    for chunk in chunks:
        chunks_text.append(f"## {chunk.section_title} ({chunk.chunk_id})")
        chunks_text.append(chunk.text)
        chunks_text.append("")
        section_titles.add(chunk.section_title)
    
    combined_text = "\n".join(chunks_text)
    
    # Extract section titles for prompt template
    section_titles_list = sorted(list(section_titles))
    section_titles_text = "\n".join([f"- \"{title} section\"" for title in section_titles_list])
    
    # Use the same prompt as summary-based planning
    try:
        prompt_template = llm_client.load_prompt("plan_generation.md")
        prompt = prompt_template.format(summary_sections=combined_text, section_titles_list=section_titles_text)
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

