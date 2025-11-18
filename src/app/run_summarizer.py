#!/usr/bin/env python3
"""Run summarization pipeline (Part 3): extract facts from chunks and create summary.

Usage:
    python src/app/run_summarizer.py <note_id>
    python src/app/run_summarizer.py 0
    python src/app/run_summarizer.py results/0
    
    Or specify chunks file directly:
    python src/app/run_summarizer.py --chunks-file results/0/chunks.json
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
from app.config import get_config
from app.ingestion import CanonicalNote, PageSpan
from app.llm import LLMClient
from app.summarizer import extract_summary, save_summary

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
        ValueError: If chunks file is invalid
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
            # Group by page and find character ranges
            page_ranges = {}
            for section in sections:
                start_page = section.get("start_page", 0)
                end_page = section.get("end_page", 0)
                start_char = section.get("start_char", 0)
                end_char = section.get("end_char", 0)

                # Update page ranges
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

            # Create page spans
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

    # Fallback: create a single page span covering the entire document
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
    config = get_config()
    results_base = config.output_dir

    # Try as direct path first
    candidate = Path(note_id_or_path)
    if candidate.is_absolute() or candidate.exists():
        if candidate.is_dir() and (candidate / "chunks.json").exists():
            return candidate.resolve()

    # Try as note_id in results directory
    candidate = results_base / note_id_or_path
    if candidate.exists() and (candidate / "chunks.json").exists():
        return candidate.resolve()

    raise FileNotFoundError(
        f"Results directory not found for: {note_id_or_path}\n"
        f"Tried:\n"
        f"  - {Path(note_id_or_path).resolve()}\n"
        f"  - {candidate.resolve()}\n"
        f"Expected directory to contain chunks.json"
    )


def main():
    """Main entry point for summarization pipeline."""
    parser = argparse.ArgumentParser(
        description="Run summarization pipeline: extract facts from chunks and create summary"
    )
    parser.add_argument(
        "note_id",
        type=str,
        nargs="?",
        default=None,
        help="Note ID (e.g., '0') or path to results directory",
    )
    parser.add_argument(
        "--chunks-file",
        type=str,
        default=None,
        help="Path to chunks.json file (alternative to note_id)",
    )
    parser.add_argument(
        "--canonical-text-file",
        type=str,
        default=None,
        help="Path to canonical_text.txt file (default: inferred from chunks file location)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for summary.json (default: same as chunks file location)",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.note_id and not args.chunks_file:
        parser.error("Either note_id or --chunks-file must be provided")

    try:
        # Determine chunks file path
        if args.chunks_file:
            chunks_path = Path(args.chunks_file).resolve()
            results_dir = chunks_path.parent
        else:
            results_dir = find_results_directory(args.note_id)
            chunks_path = results_dir / "chunks.json"

        if not chunks_path.exists():
            raise FileNotFoundError(f"Chunks file not found: {chunks_path}")

        logger.info(f"Processing chunks from: {chunks_path}")

        # Determine canonical text file path
        if args.canonical_text_file:
            canonical_text_path = Path(args.canonical_text_file).resolve()
        else:
            canonical_text_path = results_dir / "canonical_text.txt"

        # Determine ToC path (for page span information)
        toc_path = results_dir / "toc.json"

        # Determine output directory
        if args.output_dir:
            output_dir = Path(args.output_dir)
        else:
            output_dir = results_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        # Get configuration
        config = get_config()

        # Step 1: Load chunks
        logger.info("[STEP 1] Loading chunks...")
        chunks = load_chunks_from_file(chunks_path)
        logger.info(f"✓ Loaded {len(chunks)} chunks")

        # Step 2: Load canonical note
        logger.info("[STEP 2] Loading canonical note...")
        canonical_note = load_canonical_note_from_file(canonical_text_path, toc_path)
        logger.info(f"✓ Loaded canonical note: {len(canonical_note.text)} chars")

        # Step 3: Initialize LLM client
        logger.info("[STEP 3] Initializing LLM client...")
        try:
            llm_client = LLMClient(config)
            logger.info(f"✓ LLM client initialized (model: {config.model_name})")
        except Exception as e:
            logger.error(f"✗ Failed to initialize LLM client: {e}")
            logger.error("Make sure Ollama is running and the model is installed.")
            logger.error(f"Install model with: ollama pull {config.model_name}")
            return 1

        # Step 4: Create text summary from all chunks
        logger.info("[STEP 4] Creating text summary from all chunks...")
        logger.info(f"  Processing {len(chunks)} chunks at once...")
        try:
            from app.summarizer import create_text_summary_from_chunks
            summary_text = create_text_summary_from_chunks(chunks, llm_client)
            logger.info(f"✓ Created text summary ({len(summary_text)} characters)")
        except Exception as e:
            logger.error(f"✗ Error creating summary: {e}", exc_info=True)
            return 1

        # Step 5: Save summary
        logger.info("[STEP 5] Saving summary...")
        summary_path = output_dir / "summary.txt"
        summary_path.write_text(summary_text, encoding="utf-8")
        logger.info(f"✓ Saved summary to: {summary_path}")

        logger.info(f"\n✓ Summarization pipeline completed successfully!")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"  - summary.txt")

        return 0

    except FileNotFoundError as e:
        logger.error(f"✗ File not found: {e}")
        return 1
    except Exception as e:
        logger.error(f"✗ Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

