#!/usr/bin/env python3
"""Run ingestion pipeline (Part 2): ingestion, section detection, and chunking.

Usage:
    python src/app/run_ingest.py <pdf_filename>
    python src/app/run_ingest.py 0.pdf
    python src/app/run_ingest.py data/archive/mtsamples_pdf/mtsamples_pdf/1.pdf
    
    Or from project root:
    python -m app.run_ingest <pdf_filename>  (requires PYTHONPATH=src)
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src directory to Python path so imports work without PYTHONPATH=src
# This works whether the script is run directly or as a module
_script_dir = Path(__file__).parent
_project_root = _script_dir.parent.parent
_src_dir = _project_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
# Also add project root in case we need it
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from app.chunks import create_chunks_from_sections, save_chunks
from app.config import get_config
from app.ingestion import ingest_document
from app.sections import detect_sections, save_toc

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def find_pdf_file(pdf_input: str) -> Path:
    """Find PDF file from input (filename or full path).

    Args:
        pdf_input: PDF filename (e.g., "0.pdf") or full path

    Returns:
        Path: Path to PDF file

    Raises:
        FileNotFoundError: If PDF file is not found
    """
    pdf_path = Path(pdf_input)

    # If it's already a full path and exists, return it
    if pdf_path.exists():
        return pdf_path.resolve()

    # Otherwise, try to find it in data/archive/mtsamples_pdf/mtsamples_pdf/
    project_root = Path(__file__).parent.parent.parent
    default_dir = project_root / "data" / "archive" / "mtsamples_pdf" / "mtsamples_pdf"
    candidate_path = default_dir / pdf_input

    if candidate_path.exists():
        return candidate_path.resolve()

    raise FileNotFoundError(
        f"PDF file not found: {pdf_input}\n"
        f"Tried:\n"
        f"  - {pdf_path.resolve()}\n"
        f"  - {candidate_path.resolve()}"
    )


def main():
    """Main entry point for ingestion pipeline."""
    parser = argparse.ArgumentParser(
        description="Run ingestion pipeline: extract text, detect sections, create chunks"
    )
    parser.add_argument(
        "pdf",
        type=str,
        help="PDF filename (e.g., '0.pdf') or full path to PDF file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: results/{note_id})",
    )

    args = parser.parse_args()

    try:
        # Find PDF file
        pdf_path = find_pdf_file(args.pdf)
        logger.info(f"Processing PDF: {pdf_path}")

        # Get configuration
        config = get_config()

        # Step 1: Ingest document
        logger.info("[STEP 1] Ingesting document...")
        canonical_note, note_id = ingest_document(pdf_path)
        logger.info(
            f"✓ Ingested: {len(canonical_note.text)} chars, "
            f"{len(canonical_note.page_spans)} pages, note_id: {note_id}"
        )

        # Determine output directory
        if args.output_dir:
            output_dir = Path(args.output_dir)
        else:
            output_dir = config.output_dir / note_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save canonical text for inspection
        canonical_text_path = output_dir / "canonical_text.txt"
        canonical_text_path.write_text(canonical_note.text, encoding="utf-8")
        logger.info(f"  Saved canonical text to: {canonical_text_path}")

        # Step 2: Detect sections
        logger.info("[STEP 2] Detecting sections...")
        sections = detect_sections(canonical_note, pdf_path, config)
        logger.info(f"✓ Detected {len(sections)} sections:")
        for i, section in enumerate(sections, 1):
            logger.info(
                f"  {i}. {section.title} "
                f"(pages {section.start_page + 1}-{section.end_page + 1}, "
                f"chars {section.start_char}-{section.end_char})"
            )

        # Save ToC
        toc_path = output_dir / "toc.json"
        save_toc(sections, toc_path)
        logger.info(f"✓ Saved ToC to: {toc_path}")

        # Step 3: Create chunks
        logger.info("[STEP 3] Creating chunks...")
        chunks = create_chunks_from_sections(sections, canonical_note, config)
        logger.info(f"✓ Created {len(chunks)} chunks")

        # Show chunk summary
        for i, chunk in enumerate(chunks[:5], 1):
            preview = chunk.text[:60].replace("\n", " ")
            logger.info(f"  {i}. {chunk.chunk_id} ({chunk.section_title}): {preview}...")
        if len(chunks) > 5:
            logger.info(f"  ... and {len(chunks) - 5} more chunks")

        # Save chunks
        chunks_path = output_dir / "chunks.json"
        save_chunks(chunks, chunks_path)
        logger.info(f"✓ Saved chunks to: {chunks_path}")

        logger.info(f"\n✓ Pipeline completed successfully!")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"  - canonical_text.txt")
        logger.info(f"  - toc.json")
        logger.info(f"  - chunks.json")

        return 0

    except FileNotFoundError as e:
        logger.error(f"✗ File not found: {e}")
        return 1
    except Exception as e:
        logger.error(f"✗ Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

