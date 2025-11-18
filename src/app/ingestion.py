"""PDF and text file ingestion module."""

import hashlib
import logging
import re
from pathlib import Path
from typing import Tuple

from pypdf import PdfReader

from app.config import Config, get_config
from app.schemas import CanonicalNote, PageSpan

logger = logging.getLogger(__name__)


def generate_note_id(file_path: Path) -> str:
    """Generate a filesystem-safe note ID from file path."""
    note_id = file_path.stem
    if not note_id or len(note_id) < 1:
        try:
            with open(file_path, "rb") as f:
                content = f.read(1000)
                note_id = hashlib.md5(content).hexdigest()[:16]
        except Exception as e:
            logger.warning(f"Could not generate hash-based note_id: {e}")
            note_id = "unknown_note"
    note_id = re.sub(r'[<>:"/\\|?*]', "_", note_id)
    note_id = re.sub(r'\s+', "_", note_id)
    note_id = note_id.strip("._")
    return note_id if note_id else "unknown_note"


def normalize_text(text: str) -> str:
    """Normalize text by handling encoding issues and line endings.
    
    IMPORTANT: Preserves empty lines (double newlines) from the original PDF/text.
    Empty lines are critical for section header detection, so they must be preserved.
    Only collapses excessive empty lines (3+ consecutive newlines) to 2.
    """
    # Replace non-breaking spaces with regular spaces
    text = text.replace("\xa0", " ")
    text = text.replace("\u2009", " ")  # Thin space
    text = text.replace("\u202f", " ")  # Narrow no-break space
    
    # Normalize line endings to \n
    # CRITICAL: Preserve empty lines - don't collapse single newlines
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    
    # Preserve empty lines (double newlines) from original document
    # Only collapse excessive empty lines (3+ consecutive newlines) to 2
    # This preserves the document structure while preventing too many blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    # Note: We do NOT collapse single newlines or double newlines
    # Empty lines (double newlines) are preserved as-is to enable section detection
    
    return text


def char_span_to_page(start_char: int, end_char: int, page_spans: list[PageSpan]) -> int:
    """Map a character span to a page number (one-based)."""
    for span in page_spans:
        if span.start_char <= start_char < span.end_char:
            return span.page_index + 1
    for span in page_spans:
        if span.start_char <= end_char <= span.end_char:
            return span.page_index + 1
    return 1


def load_pdf(file_path: Path, config: Config) -> Tuple[str, list[PageSpan]]:
    """Load and extract text from a PDF file."""
    if not file_path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    try:
        reader = PdfReader(str(file_path))
        num_pages = len(reader.pages)

        if num_pages > config.max_pages_warning:
            warning_msg = f"Warning: PDF has {num_pages} pages. Processing may take longer."
            logger.warning(warning_msg)
            print(warning_msg)

        if num_pages == 0:
            raise ValueError(f"PDF file is empty: {file_path}")

        page_texts = []
        page_spans = []
        current_char = 0

        for page_idx, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if not page_text:
                    logger.warning(f"Page {page_idx + 1} has no extractable text")
                    page_text = ""

                page_text = normalize_text(page_text)

                if page_idx > 0:
                    page_text = "\n" + page_text

                start_char = current_char
                end_char = current_char + len(page_text)
                page_spans.append(
                    PageSpan(start_char=start_char, end_char=end_char, page_index=page_idx)
                )

                page_texts.append(page_text)
                current_char = end_char

            except Exception as e:
                logger.error(f"Error extracting text from page {page_idx + 1}: {e}")
                if page_idx > 0:
                    page_texts.append("\n")
                else:
                    page_texts.append("")
                start_char = current_char
                end_char = current_char + len(page_texts[-1])
                page_spans.append(
                    PageSpan(start_char=start_char, end_char=end_char, page_index=page_idx)
                )
                current_char = end_char

        full_text = "".join(page_texts)

        if not full_text.strip():
            raise ValueError(f"PDF file contains no extractable text: {file_path}")

        return full_text, page_spans

    except Exception as e:
        if isinstance(e, (ValueError, FileNotFoundError)):
            raise
        raise ValueError(f"Error reading PDF file {file_path}: {e}") from e


def load_text_file(file_path: Path) -> Tuple[str, list[PageSpan]]:
    """Load and extract text from a .txt file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Text file not found: {file_path}")

    encodings = ["utf-8", "latin-1"]
    text = None
    last_error = None

    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                text = f.read()
            break
        except UnicodeDecodeError as e:
            last_error = e
            logger.warning(f"Failed to read {file_path} with {encoding} encoding")
            continue
        except Exception as e:
            raise ValueError(f"Error reading text file {file_path}: {e}") from e

    if text is None:
        raise ValueError(f"Could not decode text file {file_path} with any encoding: {last_error}")

    if not text.strip():
        raise ValueError(f"Text file is empty: {file_path}")

    text = normalize_text(text)

    page_spans = [PageSpan(start_char=0, end_char=len(text), page_index=0)]

    return text, page_spans


def ingest_document(file_path: Path, config: Config | None = None) -> Tuple[CanonicalNote, str]:
    """Ingest a document (PDF or .txt) and create canonical representation."""
    if config is None:
        config = get_config()

    file_path = Path(file_path).resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    note_id = generate_note_id(file_path)
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        logger.info(f"Loading PDF: {file_path}")
        text, page_spans = load_pdf(file_path, config)
    elif suffix == ".txt":
        logger.info(f"Loading text file: {file_path}")
        text, page_spans = load_text_file(file_path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Supported formats: .pdf, .txt")

    canonical_note = CanonicalNote(text=text, page_spans=page_spans)

    logger.info(f"Ingested document: {len(text)} characters, {len(page_spans)} pages, note_id: {note_id}")

    return canonical_note, note_id

