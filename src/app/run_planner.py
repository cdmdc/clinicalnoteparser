#!/usr/bin/env python3
"""Run plan generation pipeline: create prioritized treatment plan from chunks.

Usage:
    python src/app/run_planner.py <note_id>
    python src/app/run_planner.py 0
    python src/app/run_planner.py results/0
    
    Or specify chunks file directly:
    python src/app/run_planner.py --chunks-file results/0/chunks.json
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
from app.llm import LLMClient
from app.planner import create_treatment_plan_from_chunks, save_plan

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
    """Main entry point for plan generation pipeline."""
    parser = argparse.ArgumentParser(
        description="Run plan generation pipeline: create prioritized treatment plan from chunks"
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
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for plan.txt (default: same as chunks file location)",
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

        # Step 2: Initialize LLM client
        logger.info("[STEP 2] Initializing LLM client...")
        try:
            llm_client = LLMClient(config)
            logger.info(f"✓ LLM client initialized (model: {config.model_name})")
        except Exception as e:
            logger.error(f"✗ Failed to initialize LLM client: {e}")
            logger.error("Make sure Ollama is running and the model is installed.")
            logger.error(f"Install model with: ollama pull {config.model_name}")
            return 1

        # Step 3: Generate treatment plan
        logger.info("[STEP 3] Generating prioritized treatment plan...")
        logger.info(f"  Processing {len(chunks)} chunks at once...")
        try:
            plan_text = create_treatment_plan_from_chunks(chunks, llm_client)
            logger.info(f"✓ Generated treatment plan ({len(plan_text)} characters)")
        except Exception as e:
            logger.error(f"✗ Error generating plan: {e}", exc_info=True)
            return 1

        # Step 4: Save plan
        logger.info("[STEP 4] Saving plan...")
        plan_path = output_dir / "plan.txt"
        save_plan(plan_text, plan_path)
        logger.info(f"✓ Saved plan to: {plan_path}")

        logger.info(f"\n✓ Plan generation pipeline completed successfully!")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"  - plan.txt")

        return 0

    except FileNotFoundError as e:
        logger.error(f"✗ File not found: {e}")
        return 1
    except Exception as e:
        logger.error(f"✗ Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

