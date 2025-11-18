"""Main pipeline orchestration module.

This module coordinates the entire clinical note parsing pipeline, including
ingestion, section detection, chunking, summarization, planning, and evaluation.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

# Add src directory to Python path so imports work without PYTHONPATH=src
_script_dir = Path(__file__).parent
_project_root = _script_dir.parent.parent
_src_dir = _project_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from app.chunks import Chunk, create_chunks_from_sections, load_chunks, save_chunks
from app.config import Config, get_config
from app.evaluation import evaluate_summary_and_plan, save_evaluation
from app.ingestion import CanonicalNote, generate_note_id, ingest_document, load_canonical_note
from app.llm import LLMClient
from app.planner import create_treatment_plan_from_summary, load_text_summary, save_plan
from app.sections import Section, detect_sections, load_toc, save_toc
from app.summarizer import (
    create_text_summary_from_chunks,
    parse_text_summary_to_structured,
    save_structured_summary,
    save_text_summary,
)

logger = logging.getLogger(__name__)


def setup_logging(output_dir: Path, verbose: bool = False) -> None:
    """Set up logging to both file and console.
    
    Args:
        output_dir: Directory to save pipeline.log
        verbose: If True, use DEBUG level; otherwise use INFO
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Create log file path
    log_file = output_dir / "pipeline.log"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)  # Always INFO for console
    console_formatter = logging.Formatter("%(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    logger.info(f"Logging configured: file={log_file}, level={logging.getLevelName(log_level)}")


def check_ollama_availability(config: Config) -> tuple[bool, Optional[str]]:
    """Check if Ollama is available and model exists.
    
    Args:
        config: Configuration object
        
    Returns:
        tuple[bool, Optional[str]]: (is_available, error_message)
            - is_available: True if Ollama is available and model exists
            - error_message: Human-readable error message if not available, None otherwise
    """
    try:
        import subprocess
        
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        
        if result.returncode != 0:
            return False, "Ollama is not running. Please start Ollama service."
        
        # Check if model exists
        if config.model_name not in result.stdout:
            available_models = result.stdout.strip().split('\n')[1:] if result.stdout.strip() else []
            available_list = ', '.join([m.split()[0] for m in available_models if m.strip()]) if available_models else "none"
            return False, (
                f"Model '{config.model_name}' not found. "
                f"Available models: {available_list if available_list else 'none'}. "
                f"Install it with: ollama pull {config.model_name}"
            )
        
        return True, None
    except FileNotFoundError:
        return False, "Ollama command not found. Please install Ollama from https://ollama.ai"
    except subprocess.TimeoutExpired:
        return False, "Ollama is not responding. Please ensure Ollama is running."
    except Exception as e:
        logger.debug(f"Ollama check failed: {e}")
        return False, f"Error checking Ollama availability: {e}"


def validate_input_file(file_path: Path) -> tuple[bool, Optional[str]]:
    """Validate input file exists and is readable.
    
    Args:
        file_path: Path to input file
        
    Returns:
        tuple[bool, Optional[str]]: (is_valid, error_message)
    """
    if not file_path.exists():
        return False, f"Input file does not exist: {file_path}"
    
    if not file_path.is_file():
        return False, f"Input path is not a file: {file_path}"
    
    if not file_path.suffix.lower() in (".pdf", ".txt"):
        return False, f"Unsupported file type: {file_path.suffix}. Supported: .pdf, .txt"
    
    try:
        # Try to read first few bytes
        with open(file_path, "rb") as f:
            f.read(1)
    except Exception as e:
        return False, f"Cannot read file: {e}"
    
    return True, None


def run_pipeline(
    input_path: Path,
    output_dir: Optional[Path] = None,
    config: Optional[Config] = None,
    toc_only: bool = False,
    summary_only: bool = False,
    plan_only: bool = False,
    no_evaluation: bool = False,
    verbose: bool = False,
) -> int:
    """Run the clinical note parsing pipeline.
    
    Args:
        input_path: Path to input PDF or .txt file
        output_dir: Output directory (default: results/{note_id})
        config: Configuration object (default: from environment)
        toc_only: Only generate TOC (skip chunking, summarization, planning, evaluation)
        summary_only: Only generate summary (skip planning, evaluation)
        plan_only: Only generate plan (requires summary generation first, skips evaluation)
        no_evaluation: Generate TOC, summary, and plan but skip evaluation
        verbose: Enable verbose logging
        
    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    try:
        # Get configuration
        if config is None:
            config = get_config()
        
        # Validate input file
        is_valid, error_msg = validate_input_file(input_path)
        if not is_valid:
            logger.error(f"✗ {error_msg}")
            return 1
        
        # Determine execution mode
        # Note: plan_only now requires summary generation (since planner uses summary.json)
        needs_llm = summary_only or plan_only or (not toc_only and not no_evaluation)
        needs_chunks = summary_only or plan_only or (not toc_only and not no_evaluation)
        # Plan generation requires summary, so if plan_only is True, we also need summary
        needs_summary = summary_only or plan_only or (not toc_only and not no_evaluation)
        needs_plan = plan_only or (not toc_only and not summary_only and not no_evaluation)
        needs_evaluation = not toc_only and not summary_only and not plan_only and not no_evaluation
        
        # Pre-flight checks
        if needs_llm:
            logger.info("Checking Ollama availability...")
            is_available, error_msg = check_ollama_availability(config)
            if not is_available:
                error_display = (
                    f"\n{'='*70}\n"
                    f"ERROR: Ollama is not available or model '{config.model_name}' is not installed\n"
                    f"{'='*70}\n"
                    f"\n{error_msg}\n"
                    f"\nTo fix this issue:\n"
                    f"  1. Ensure Ollama is installed: https://ollama.ai\n"
                    f"  2. Start Ollama service (if not running)\n"
                    f"  3. Install the model: ollama pull {config.model_name}\n"
                    f"\nTo check available models, run: ollama list\n"
                    f"\nNote: Use --toc-only to generate only the table of contents (no LLM required)\n"
                    f"{'='*70}\n"
                )
                logger.error(error_display)
                print(error_display, file=sys.stderr)
                return 1
            logger.info("✓ Ollama is available")
        
        # Determine note_id and output directory early (before ingestion)
        # This allows us to check for existing chunks
        note_id = generate_note_id(input_path)
        if output_dir is None:
            output_dir = config.output_dir / note_id
        else:
            output_dir = output_dir / note_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up logging to file early
        setup_logging(output_dir, verbose)
        logger.info(f"Processing document: {input_path}")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"Configuration: model={config.model_name}, temperature={config.temperature}")
        logger.info(f"Execution mode: toc_only={toc_only}, summary_only={summary_only}, plan_only={plan_only}, no_evaluation={no_evaluation}")
        
        # Check if chunks already exist (for skipping ingestion/chunking)
        chunks_path = output_dir / "chunks.json"
        chunks_exist = chunks_path.exists() and needs_chunks
        
        if chunks_exist:
            try:
                logger.info("Found existing chunks.json - attempting to load...")
                chunks = load_chunks(chunks_path)
                logger.info(f"✓ Loaded {len(chunks)} existing chunks from {chunks_path}")
                logger.info("Skipping ingestion and chunking steps (using cached chunks)")
                
                # Load canonical_note and sections if needed (for downstream processing)
                canonical_text_path = output_dir / "canonical_text.txt"
                toc_path = output_dir / "toc.json"
                
                if canonical_text_path.exists():
                    try:
                        canonical_note = load_canonical_note(canonical_text_path)
                        logger.info(f"✓ Loaded canonical note from {canonical_text_path}")
                    except Exception as e:
                        logger.warning(f"Could not load canonical note: {e}. Will re-ingest.")
                        chunks_exist = False  # Force re-ingestion
                        chunks = None  # Clear chunks so we re-create them
                        canonical_note = None
                
                if toc_path.exists():
                    try:
                        sections = load_toc(toc_path)
                        logger.info(f"✓ Loaded {len(sections)} sections from {toc_path}")
                    except Exception as e:
                        logger.warning(f"Could not load ToC: {e}. Will re-detect sections.")
                        sections = None
                else:
                    sections = None
                
            except Exception as e:
                logger.warning(f"Could not load existing chunks: {e}. Will re-create chunks.")
                chunks_exist = False
                chunks = None
                canonical_note = None
                sections = None
        else:
            chunks = None
            canonical_note = None
            sections = None
        
        # Step 1: Ingest document (if chunks don't exist)
        if not chunks_exist:
            logger.info(f"[STEP 1] Ingesting document: {input_path}")
            canonical_note, note_id = ingest_document(input_path, config)
            logger.info(f"✓ Ingested: {len(canonical_note.text)} chars, {len(canonical_note.page_spans)} pages, note_id: {note_id}")
            
            # Save canonical text
            canonical_text_path = output_dir / "canonical_text.txt"
            canonical_text_path.write_text(canonical_note.text, encoding="utf-8")
            logger.info(f"Saved canonical text to: {canonical_text_path}")
        else:
            logger.info("[STEP 1] Skipped (using existing chunks)")
        
        # Step 2: Detect sections (if chunks don't exist or sections not loaded)
        total_steps = 2  # ingestion + sections
        if needs_chunks:
            total_steps += 1  # chunking
        if needs_summary:
            total_steps += 1  # summarization
        if needs_plan:
            total_steps += 1  # planning
        if needs_evaluation:
            total_steps += 1  # evaluation
        
        if not chunks_exist or sections is None:
            logger.info(f"[STEP 2/{total_steps}] Detecting sections...")
            sections = detect_sections(canonical_note, input_path, config)
            logger.info(f"✓ Detected {len(sections)} sections")
            for i, section in enumerate(sections, 1):
                logger.info(f"  {i}. {section.title} (pages {section.start_page + 1}-{section.end_page + 1}, chars {section.start_char}-{section.end_char})")
            
            # Save ToC
            toc_path = output_dir / "toc.json"
            save_toc(sections, toc_path)
            logger.info(f"✓ Saved ToC to: {toc_path}")
        else:
            logger.info(f"[STEP 2/{total_steps}] Skipped (using existing ToC)")
        
        # Break if TOC only
        if toc_only:
            logger.info("\n✓ Pipeline completed successfully (TOC only)")
            logger.info(f"Output directory: {output_dir}")
            logger.info(f"  - canonical_text.txt")
            logger.info(f"  - toc.json")
            return 0
        
        # Step 3: Create chunks (if chunks don't exist)
        step_num = 3
        if not chunks_exist:
            logger.info(f"[STEP {step_num}/{total_steps}] Creating chunks...")
            chunks = create_chunks_from_sections(sections, canonical_note, config)
            logger.info(f"✓ Created {len(chunks)} chunks")
            
            # Save chunks
            save_chunks(chunks, chunks_path)
            logger.info(f"✓ Saved chunks to: {chunks_path}")
        else:
            logger.info(f"[STEP {step_num}/{total_steps}] Skipped (using existing chunks)")
        
        # Initialize LLM client if needed
        llm_client = None
        if needs_summary or needs_plan:
            logger.info("Initializing LLM client...")
            llm_client = LLMClient(config)
            logger.info(f"✓ LLM client initialized (model: {config.model_name})")
        
        # Step 4: Generate summary (if needed)
        summary_text = None
        structured_summary = None
        if needs_summary:
            step_num += 1
            logger.info(f"[STEP {step_num}/{total_steps}] Generating summary...")
            logger.info(f"  Processing {len(chunks)} chunks at once...")
            summary_text = create_text_summary_from_chunks(chunks, llm_client)
            logger.info(f"✓ Generated summary ({len(summary_text)} characters)")
            
            # Parse text summary into structured format
            try:
                structured_summary = parse_text_summary_to_structured(summary_text)
                logger.info(f"✓ Parsed structured summary with {len(structured_summary.patient_snapshot)} patient snapshot items, "
                          f"{len(structured_summary.key_problems)} problems, {len(structured_summary.pertinent_history)} history items, "
                          f"{len(structured_summary.medicines_allergies)} medicines/allergies, "
                          f"{len(structured_summary.objective_findings)} findings, {len(structured_summary.labs_imaging)} labs/imaging, "
                          f"{len(structured_summary.concise_assessment)} assessment items")
            except Exception as e:
                logger.warning(f"Could not parse structured summary: {e}. Will save text summary only.")
            
            # Save text summary
            summary_txt_path = output_dir / "summary.txt"
            save_text_summary(summary_text, summary_txt_path)
            logger.info(f"✓ Saved text summary to: {summary_txt_path}")
            
            # Save structured summary JSON
            if structured_summary:
                summary_json_path = output_dir / "summary.json"
                save_structured_summary(structured_summary, summary_json_path)
                logger.info(f"✓ Saved structured summary to: {summary_json_path}")
        
        # Break if summary only
        if summary_only:
            logger.info("\n✓ Pipeline completed successfully (summary only)")
            logger.info(f"Output directory: {output_dir}")
            logger.info(f"  - canonical_text.txt")
            logger.info(f"  - toc.json")
            logger.info(f"  - chunks.json")
            logger.info(f"  - summary.txt")
            return 0
        
        # Step 5: Generate plan (if needed)
        # Note: Plan generation now requires summary.txt, so summary must be generated first
        plan_text = None
        if needs_plan:
            step_num += 1
            logger.info(f"[STEP {step_num}/{total_steps}] Generating treatment plan...")
            
            # Plan generation requires summary.txt - check if it exists
            summary_txt_path = output_dir / "summary.txt"
            
            # If summary_text was just created, use it
            if summary_text is None:
                # Try to load from file if it exists
                if summary_txt_path.exists():
                    try:
                        summary_text = load_text_summary(summary_txt_path)
                        logger.info(f"✓ Loaded text summary from {summary_txt_path}")
                    except Exception as e:
                        logger.error(f"Could not load text summary: {e}")
                        logger.error("Plan generation requires summary.txt. Please generate summary first.")
                        return 1
                else:
                    # Summary.txt doesn't exist - this shouldn't happen if needs_summary was True
                    # but handle it gracefully
                    logger.error(f"summary.txt not found at {summary_txt_path}")
                    logger.error("Plan generation requires summary.txt. Please generate summary first.")
                    logger.error("Hint: Run with --summary-only first, or run full pipeline without --plan-only")
                    return 1
            
            # Generate plan from text summary
            logger.info(f"  Using text summary ({len(summary_text)} characters)...")
            plan_text = create_treatment_plan_from_summary(summary_text, llm_client)
            
            logger.info(f"✓ Generated plan ({len(plan_text)} characters)")
            
            # Save plan
            plan_path = output_dir / "plan.txt"
            save_plan(plan_text, plan_path)
            logger.info(f"✓ Saved plan to: {plan_path}")
        
        # Break if plan only
        if plan_only:
            logger.info("\n✓ Pipeline completed successfully (plan only)")
            logger.info(f"Output directory: {output_dir}")
            logger.info(f"  - canonical_text.txt")
            logger.info(f"  - toc.json")
            logger.info(f"  - chunks.json")
            logger.info(f"  - summary.txt")
            logger.info(f"  - summary.json")
            logger.info(f"  - plan.txt")
            return 0
        
        # Break if no evaluation
        if no_evaluation:
            logger.info("\n✓ Pipeline completed successfully (no evaluation)")
            logger.info(f"Output directory: {output_dir}")
            logger.info(f"  - canonical_text.txt")
            logger.info(f"  - toc.json")
            logger.info(f"  - chunks.json")
            if summary_text:
                logger.info(f"  - summary.txt")
            if plan_text:
                logger.info(f"  - plan.txt")
            return 0
        
        # Step 6: Evaluation (if needed)
        if needs_evaluation:
            step_num += 1
            logger.info(f"[STEP {step_num}/{total_steps}] Evaluating results...")
            
            # Load summary and plan if not already loaded
            if summary_text is None:
                summary_path = output_dir / "summary.txt"
                if not summary_path.exists():
                    logger.error(f"✗ Summary file not found: {summary_path}")
                    return 1
                summary_text = summary_path.read_text(encoding="utf-8")
            
            if plan_text is None:
                plan_path = output_dir / "plan.txt"
                if not plan_path.exists():
                    logger.error(f"✗ Plan file not found: {plan_path}")
                    return 1
                plan_text = plan_path.read_text(encoding="utf-8")
            
            # Run evaluation
            evaluation = evaluate_summary_and_plan(summary_text, plan_text, canonical_note, chunks)
            
            # Save evaluation
            evaluation_path = output_dir / "evaluation.json"
            save_evaluation(evaluation, evaluation_path)
            logger.info(f"✓ Saved evaluation to: {evaluation_path}")
            
            # Display evaluation metrics
            logger.info("\n[EVALUATION METRICS]")
            logger.info(f"Citation Coverage:")
            logger.info(f"  Summary: {evaluation['citation_coverage']['summary_coverage_percentage']:.1f}% "
                       f"({evaluation['citation_coverage']['summary_facts_with_citations']}/{evaluation['citation_coverage']['summary_total_facts']})")
            logger.info(f"  Plan: {evaluation['citation_coverage']['plan_coverage_percentage']:.1f}% "
                       f"({evaluation['citation_coverage']['plan_recommendations_with_citations']}/{evaluation['citation_coverage']['plan_total_recommendations']})")
            logger.info(f"  Overall: {evaluation['citation_coverage']['overall_coverage_percentage']:.1f}%")
            logger.info(f"\nCitation Validity: {evaluation['citation_validity']['validity_percentage']:.1f}% "
                       f"({evaluation['citation_validity']['total_citations_checked'] - evaluation['citation_validity']['invalid_citations']}/{evaluation['citation_validity']['total_citations_checked']})")
            logger.info(f"\nHallucination Rate: {evaluation['orphan_claims']['hallucination_rate_percentage']:.1f}% "
                       f"({evaluation['orphan_claims']['total_orphans']}/{evaluation['orphan_claims']['total_claims']} orphan claims)")
            logger.info(f"\nCitation Overlap Jaccard: {evaluation['citation_overlap_jaccard']['average_jaccard_similarity']:.4f} "
                       f"(avg, {evaluation['citation_overlap_jaccard']['total_citation_pairs']} pairs, "
                       f"range: {evaluation['citation_overlap_jaccard']['min_jaccard']:.4f}-{evaluation['citation_overlap_jaccard']['max_jaccard']:.4f})")
            logger.info(f"\nSpan Consistency: {evaluation['span_consistency']['consistency_percentage']:.1f}% "
                       f"({evaluation['span_consistency']['checks_passed']}/{evaluation['span_consistency']['checks_performed']})")
            logger.info(f"\nSummary Statistics:")
            logger.info(f"  Total facts: {evaluation['summary_statistics']['total_facts_extracted']}")
            logger.info(f"  Total recommendations: {evaluation['summary_statistics']['total_recommendations_generated']}")
            if evaluation['summary_statistics']['confidence_score_distribution']['count'] > 0:
                logger.info(f"  Average confidence: {evaluation['summary_statistics']['confidence_score_distribution']['mean']:.2f}")
        
        logger.info("\n✓ Pipeline completed successfully!")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"  - canonical_text.txt")
        logger.info(f"  - toc.json")
        logger.info(f"  - chunks.json")
        if summary_text:
            logger.info(f"  - summary.txt")
        if plan_text:
            logger.info(f"  - plan.txt")
        if needs_evaluation:
            logger.info(f"  - evaluation.json")
        logger.info(f"  - pipeline.log")
        
        return 0
        
    except FileNotFoundError as e:
        logger.error(f"✗ File not found: {e}")
        return 1
    except Exception as e:
        logger.error(f"✗ Error: {e}", exc_info=True)
        return 1

