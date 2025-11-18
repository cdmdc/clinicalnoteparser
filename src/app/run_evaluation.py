#!/usr/bin/env python3
"""Run evaluation pipeline: evaluate summary and plan quality metrics.

Usage:
    python src/app/run_evaluation.py <note_id>
    python src/app/run_evaluation.py 0
    python src/app/run_evaluation.py results/0
"""

import argparse
import json
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

from app.chunks import Chunk
from app.evaluation import evaluate_summary_and_plan, save_evaluation
from app.ingestion import CanonicalNote, PageSpan

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_chunks_from_file(chunks_path: Path) -> list[Chunk]:
    """Load chunks from JSON file.

    Args:
        chunks_path: Path to chunks.json file

    Returns:
        list[Chunk]: List of Chunk objects

    Raises:
        FileNotFoundError: If chunks file doesn't exist
    """
    if not chunks_path.exists():
        raise FileNotFoundError(f"Chunks file not found: {chunks_path}")

    with open(chunks_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks_data = data.get("chunks", [])
    chunks = [Chunk(**chunk_data) for chunk_data in chunks_data]

    logger.info(f"Loaded {len(chunks)} chunks from {chunks_path}")
    return chunks


def load_canonical_note_from_file(
    canonical_text_path: Path, toc_path: Optional[Path] = None
) -> CanonicalNote:
    """Load canonical note from text file, optionally using ToC for page spans.

    Args:
        canonical_text_path: Path to canonical_text.txt file
        toc_path: Optional path to toc.json file for page span information

    Returns:
        CanonicalNote: CanonicalNote object

    Raises:
        FileNotFoundError: If canonical text file doesn't exist
    """
    if not canonical_text_path.exists():
        raise FileNotFoundError(f"Canonical text file not found: {canonical_text_path}")

    text = canonical_text_path.read_text(encoding="utf-8")

    # Try to load page spans from ToC if available
    page_spans = []
    if toc_path and toc_path.exists():
        try:
            with open(toc_path, "r", encoding="utf-8") as f:
                toc_data = json.load(f)
            sections = toc_data.get("sections", [])

            # Reconstruct page spans from sections
            page_ranges = {}
            for section in sections:
                start_page = section.get("start_page", 0)
                end_page = section.get("end_page", 0)
                start_char = section.get("start_char", 0)
                end_char = section.get("end_char", 0)

                for page_idx in range(start_page, end_page + 1):
                    if page_idx not in page_ranges:
                        page_ranges[page_idx] = {"start": start_char, "end": end_char}
                    else:
                        page_ranges[page_idx]["start"] = min(
                            page_ranges[page_idx]["start"], start_char
                        )
                        page_ranges[page_idx]["end"] = max(
                            page_ranges[page_idx]["end"], end_char
                        )

            for page_idx in sorted(page_ranges.keys()):
                page_range = page_ranges[page_idx]
                page_spans.append(
                    PageSpan(
                        start_char=page_range["start"],
                        end_char=page_range["end"],
                        page_index=page_idx,
                    )
                )

            logger.info(f"Loaded page spans from ToC: {len(page_spans)} pages")
        except Exception as e:
            logger.warning(f"Failed to load page spans from ToC: {e}, using single page")

    # Fallback: create a single page span
    if not page_spans:
        page_spans = [PageSpan(start_char=0, end_char=len(text), page_index=0)]
        logger.info("Using single page span (no ToC or ToC parsing failed)")

    canonical_note = CanonicalNote(text=text, page_spans=page_spans)
    logger.info(f"Loaded canonical note: {len(text)} characters, {len(page_spans)} pages")
    return canonical_note


def find_results_directory(note_id_or_path: str) -> Path:
    """Find results directory from note_id or path.

    Args:
        note_id_or_path: Note ID (e.g., "0") or path to results directory

    Returns:
        Path: Path to results directory

    Raises:
        FileNotFoundError: If results directory doesn't exist
    """
    from app.config import get_config

    config = get_config()
    results_base = config.output_dir

    # Try as direct path first
    candidate = Path(note_id_or_path)
    if candidate.is_absolute() or candidate.exists():
        if candidate.is_dir() and (candidate / "summary.txt").exists() and (candidate / "plan.txt").exists():
            return candidate.resolve()

    # Try as note_id in results directory
    candidate = results_base / note_id_or_path
    if candidate.exists() and (candidate / "summary.txt").exists() and (candidate / "plan.txt").exists():
        return candidate.resolve()

    raise FileNotFoundError(
        f"Results directory not found for: {note_id_or_path}\n"
        f"Tried:\n"
        f"  - {Path(note_id_or_path).resolve()}\n"
        f"  - {candidate.resolve()}\n"
        f"Expected directory to contain summary.txt and plan.txt"
    )


def main():
    """Main entry point for evaluation pipeline."""
    parser = argparse.ArgumentParser(
        description="Run evaluation pipeline: evaluate summary and plan quality metrics"
    )
    parser.add_argument(
        "note_id",
        type=str,
        help="Note ID (e.g., '0') or path to results directory",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for evaluation.json (default: same as results directory)",
    )

    args = parser.parse_args()

    try:
        # Find results directory
        results_dir = find_results_directory(args.note_id)
        logger.info(f"Processing results from: {results_dir}")

        # Determine file paths
        summary_path = results_dir / "summary.txt"
        plan_path = results_dir / "plan.txt"
        canonical_text_path = results_dir / "canonical_text.txt"
        chunks_path = results_dir / "chunks.json"
        toc_path = results_dir / "toc.json"

        # Check required files exist
        if not summary_path.exists():
            raise FileNotFoundError(f"Summary file not found: {summary_path}")
        if not plan_path.exists():
            raise FileNotFoundError(f"Plan file not found: {plan_path}")
        if not canonical_text_path.exists():
            raise FileNotFoundError(f"Canonical text file not found: {canonical_text_path}")
        if not chunks_path.exists():
            raise FileNotFoundError(f"Chunks file not found: {chunks_path}")

        # Determine output directory
        if args.output_dir:
            output_dir = Path(args.output_dir)
        else:
            output_dir = results_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Load files
        logger.info("[STEP 1] Loading files...")
        summary_text = summary_path.read_text(encoding="utf-8")
        plan_text = plan_path.read_text(encoding="utf-8")
        canonical_note = load_canonical_note_from_file(canonical_text_path, toc_path)
        chunks = load_chunks_from_file(chunks_path)
        logger.info("✓ Loaded all required files")

        # Step 2: Evaluate
        logger.info("[STEP 2] Evaluating summary and plan...")
        evaluation = evaluate_summary_and_plan(
            summary_text, plan_text, canonical_note, chunks
        )
        logger.info("✓ Evaluation completed")

        # Step 3: Display metrics
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

        # Step 4: Save evaluation
        logger.info("\n[STEP 3] Saving evaluation...")
        evaluation_path = output_dir / "evaluation.json"
        save_evaluation(evaluation, evaluation_path)
        logger.info(f"✓ Saved evaluation to: {evaluation_path}")

        logger.info(f"\n✓ Evaluation pipeline completed successfully!")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"  - evaluation.json")

        return 0

    except FileNotFoundError as e:
        logger.error(f"✗ File not found: {e}")
        return 1
    except Exception as e:
        logger.error(f"✗ Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

