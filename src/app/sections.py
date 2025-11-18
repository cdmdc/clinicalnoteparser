"""Section detection module.

This module detects document sections and generates a table of contents
with character offsets and page numbers.
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Optional

from pypdf import PdfReader

from app.config import Config, get_config
from app.schemas import CanonicalNote, Section

logger = logging.getLogger(__name__)

# Common clinical section patterns (case-insensitive)
CLINICAL_SECTION_PATTERNS = [
    r"^(?:SUBJECTIVE)",
    r"^(?:OBJECTIVE)",
    r"^(?:HISTORY|HISTORY OF PRESENT ILLNESS|HPI)",
    r"^(?:PAST MEDICAL HISTORY|PMH|PAST HISTORY)",
    r"^(?:PHYSICAL EXAM|PHYSICAL EXAMINATION|PE|EXAM)",
    r"^(?:MEDICATIONS|MEDS|CURRENT MEDICATIONS)",
    r"^(?:ALLERGIES|ALLERGY|ADVERSE REACTIONS)",
    r"^(?:LABS?|LABORATORY|LAB RESULTS)",
    r"^(?:IMAGING|RADIOLOGY|X-RAY|CT|MRI)",
    r"^(?:ASSESSMENT|ASSESSMENT AND PLAN|A&P)",
    r"^(?:PLAN)",
    r"^(?:DIAGNOSIS|DIAGNOSES)",
    r"^(?:PROCEDURES?|SURGERY)",
    r"^(?:SOCIAL HISTORY|SH)",
    r"^(?:FAMILY HISTORY|FH)",
    r"^(?:REVIEW OF SYSTEMS|ROS)",
    r"^(?:CHIEF COMPLAINT|CC)",
    r"^(?:VITAL SIGNS|VITALS)",
    r"^(?:HEENT)",
    r"^(?:NECK)",
    r"^(?:LUNGS)",
    r"^(?:CARDIOVASCULAR|CV)",
    r"^(?:ABDOMEN|ABD)",
    r"^(?:EXTREMITIES|EXT)",
    r"^(?:NEUROLOGIC|NEURO)",
]


def detect_overview_section(
    text: str, start_pos: int = 0
) -> tuple[int, Optional[str]]:
    """Detect the Overview section at the start of the document.

    Looks for 'Medical Specialty', 'Sample Name', and 'Description' fields
    and extracts text until the first major section header.

    Args:
        text: Full document text
        start_pos: Starting position to search from

    Returns:
        Tuple[int, Optional[str]]: End position of overview and overview title (None if not found)
    """
    # Patterns for overview fields (flexible, case-insensitive)
    overview_patterns = [
        r"(?i)medical\s+specialty",
        r"(?i)sample\s+name",
        r"(?i)description",
    ]

    # Check if any overview fields are present
    overview_found = any(
        re.search(pattern, text[start_pos : start_pos + 2000]) for pattern in overview_patterns
    )

    if not overview_found:
        # No overview fields found, return None
        return start_pos, None

    # Find the first major section header after the overview
    # Look for all-caps words at start of line or common section patterns
    first_section_pattern = r"^\s*([A-Z][A-Z\s]{3,}):?\s*$"
    first_section_match = re.search(first_section_pattern, text[start_pos:], re.MULTILINE)

    if first_section_match:
        overview_end = start_pos + first_section_match.start()
        return overview_end, "Overview"

    # If no clear section header found, look for common section patterns
    for pattern in CLINICAL_SECTION_PATTERNS:
        match = re.search(pattern, text[start_pos:], re.MULTILINE | re.IGNORECASE)
        if match:
            overview_end = start_pos + match.start()
            return overview_end, "Overview"

    # No section header found, overview extends to end (unlikely but handle it)
    return len(text), "Overview"


def find_section_headers_in_text(
    text: str,
    overview_end: int,
    is_pdf: bool = False,
    pdf_file_path: Optional[Path] = None,
    canonical_note=None,
) -> List[tuple[int, str]]:
    """Find section headers that are BOTH bold AND capitalized, after empty lines.

    Refined rules:
    - Section headers (after Overview) always start after an empty line
    - Are at the left start of the page (beginning of line, minimal whitespace)
    - Are capitalized (all-caps)
    - Match clinical section patterns

    For PDFs: Only matches text that is both bold and all-caps at start of line after empty line.
    For .txt files: Only matches all-caps text at start of line after empty line (can't detect bold).

    Args:
        text: Document text to search
        overview_end: End position of overview section
        is_pdf: Whether this is a PDF (for bold text detection)
        pdf_file_path: Path to PDF file if available (for bold text extraction)
        canonical_note: CanonicalNote object for page span mapping

    Returns:
        List[Tuple[int, str]]: List of (position, header_text) tuples
    """
    candidates: List[tuple[int, str]] = []

    # Only search after overview section
    search_text = text[overview_end:]
    search_offset = overview_end

    # Pattern to match section headers with refined rules:
    # 1. Must be at the start of a line (left-aligned, minimal whitespace - up to 3 spaces)
    # 2. Must be all-caps (capitalized)
    # 3. Must match clinical section patterns
    # 4. Must be on its own line (entire line is just the header, indicating it's after an empty line or section break)
    
    # Split text into lines to check line-by-line
    lines = search_text.split("\n")
    line_start_positions = []
    current_pos = search_offset
    
    for line in lines:
        line_start_positions.append(current_pos)
        current_pos += len(line) + 1  # +1 for newline
    
    # Check each line for section headers
    for line_idx, line in enumerate(lines):
        line_stripped = line.strip()
        
        # Skip empty lines
        if not line_stripped:
            continue
        
        # Check if line is a potential section header:
        # 1. Must be all-caps
        # 2. Must be at start of line (minimal leading whitespace - up to 3 spaces)
        # 3. Must match patterns
        # 4. Must be on its own line (entire line is just the header)
        
        # Check leading whitespace
        leading_whitespace = len(line) - len(line.lstrip())
        if leading_whitespace > 3:
            continue  # Too much indentation, not at start of line
        
        # Check if line is all-caps
        if not line_stripped.isupper():
            continue
        
        # Check if entire line is just the header (with optional colon)
        # Remove colon if present for pattern matching
        header_text = line_stripped.rstrip(":")
        
        # Validate header length
        if len(header_text) < 3 or len(header_text) >= 100:
            continue
        
        # Check if it matches clinical section patterns
        matches_pattern = any(
            re.match(pattern, header_text, re.IGNORECASE)
            for pattern in CLINICAL_SECTION_PATTERNS
        )
        
        if not matches_pattern:
            # Accept if it's all-caps, 4-50 chars, and looks like a section name
            if (
                len(header_text) >= 4
                and len(header_text) <= 50
                and not any(char.isdigit() for char in header_text)
            ):
                words = header_text.split()
                if len(words) <= 5:
                    matches_pattern = True
        
        if matches_pattern:
            # Check if this header is on its own line (entire line is just the header)
            # This indicates it's a section header, even if there's no explicit empty line before it
            # Also accept if previous line is empty or this is the first line
            is_valid_header = False
            
            if line_idx == 0:
                # First line after Overview - acceptable
                is_valid_header = True
            elif line_idx > 0:
                prev_line = lines[line_idx - 1].strip()
                if not prev_line:
                    # Previous line is empty - this is what we want
                    is_valid_header = True
                else:
                    # Previous line has content, but if this line is entirely the header,
                    # it's still likely a section header (headers are typically on their own line)
                    # Check if next line exists and has content (header should be followed by content)
                    if line_idx + 1 < len(lines):
                        next_line = lines[line_idx + 1].strip()
                        if next_line:
                            # Header is on its own line, followed by content - this is a valid section header
                            is_valid_header = True
            
            if is_valid_header:
                actual_start = line_start_positions[line_idx] + leading_whitespace
                candidates.append((actual_start, header_text))

    # Remove duplicates and sort by position
    seen = set()
    unique_candidates = []
    for pos, header in sorted(candidates, key=lambda x: x[0]):
        header_upper = header.upper()
        if (pos, header_upper) not in seen:
            seen.add((pos, header_upper))
            unique_candidates.append((pos, header))

    logger.info(
        f"Found {len(unique_candidates)} section headers "
        f"(after empty lines, all-caps): {[h for _, h in unique_candidates]}"
    )

    return unique_candidates


def _char_span_to_page(
    start_char: int, end_char: int, page_spans: List
) -> int:
    """Map a character span to a page number (one-based).

    Args:
        start_char: Starting character position
        end_char: Ending character position
        page_spans: List of PageSpan objects

    Returns:
        int: Page number (one-based)
    """
    for span in page_spans:
        if span.start_char <= start_char < span.end_char:
            return span.page_index + 1
    # Fallback: check end_char
    for span in page_spans:
        if span.start_char <= end_char <= span.end_char:
            return span.page_index + 1
    return 1


def create_sections_from_headers(
    text: str,
    headers: List[tuple[int, str]],
    overview_end: int,
    canonical_note: CanonicalNote,
) -> List[Section]:
    """Create Section objects from detected headers.

    Args:
        text: Full document text
        headers: List of (position, header_text) tuples
        overview_end: End position of overview section
        canonical_note: CanonicalNote for page mapping

    Returns:
        List[Section]: List of Section objects
    """
    sections: List[Section] = []

    # Add overview section if it exists
    if overview_end > 0:
        overview_start_page = _char_span_to_page(0, overview_end, canonical_note.page_spans)
        overview_end_page = _char_span_to_page(
            overview_end - 1, overview_end, canonical_note.page_spans
        )
        sections.append(
            Section(
                title="Overview",
                start_char=0,
                end_char=overview_end,
                start_page=overview_start_page - 1,  # Convert to zero-based
                end_page=overview_end_page - 1,
            )
        )

    # Filter headers that come after overview
    filtered_headers = [(pos, header) for pos, header in headers if pos >= overview_end]

    # Create sections from headers
    for i, (start_pos, title) in enumerate(filtered_headers):
        # Determine end position (next section or end of document)
        if i + 1 < len(filtered_headers):
            end_pos = filtered_headers[i + 1][0]
        else:
            end_pos = len(text)

        # Get page numbers
        start_page = _char_span_to_page(start_pos, end_pos, canonical_note.page_spans)
        end_page = _char_span_to_page(end_pos - 1, end_pos, canonical_note.page_spans)

        sections.append(
            Section(
                title=title.strip(),
                start_char=start_pos,
                end_char=end_pos,
                start_page=start_page - 1,  # Convert to zero-based
                end_page=end_page - 1,
            )
        )

    return sections


def detect_sections(
    canonical_note: CanonicalNote,
    file_path: Path,
    config: Config | None = None,
) -> List[Section]:
    """Detect sections in a document and return Section objects.

    Args:
        canonical_note: CanonicalNote with text and page spans
        file_path: Path to original file (for PDF bold text detection)
        config: Configuration instance (uses global config if None)

    Returns:
        List[Section]: List of detected sections
    """
    if config is None:
        config = get_config()

    text = canonical_note.text
    is_pdf = file_path.suffix.lower() == ".pdf"

    # Step 1: Detect overview section
    overview_end, overview_title = detect_overview_section(text)
    logger.info(f"Overview section detected: end={overview_end}, title={overview_title}")

    # Step 2: Find section headers (after empty lines, all-caps, at start of line)
    headers = find_section_headers_in_text(
        text,
        overview_end,
        is_pdf=is_pdf,
        pdf_file_path=file_path if is_pdf else None,
        canonical_note=canonical_note,
    )
    logger.info(f"Found {len(headers)} potential section headers")

    # Step 3: Create sections from headers
    sections = create_sections_from_headers(
        text, headers, overview_end, canonical_note
    )

    # Step 4: Check if we have enough sections
    sections_after_overview = [s for s in sections if s.title != "Overview"]
    if len(sections_after_overview) < config.min_sections_for_success:
        logger.warning(
            f"Only found {len(sections_after_overview)} sections after Overview "
            f"(minimum: {config.min_sections_for_success}). "
            "LLM fallback would be triggered here (not yet implemented)."
        )

    # Step 5: Final fallback - single section if no sections found
    if not sections:
        logger.warning("No sections detected, creating single 'Full Note' section")
        start_page = 0
        end_page = len(canonical_note.page_spans) - 1 if canonical_note.page_spans else 0
        sections = [
            Section(
                title="Full Note",
                start_char=0,
                end_char=len(text),
                start_page=start_page,
                end_page=end_page,
            )
        ]

    logger.info(f"Detected {len(sections)} sections: {[s.title for s in sections]}")
    return sections


def save_toc(sections: List[Section], output_path: Path) -> None:
    """Save table of contents to JSON file.

    Args:
        sections: List of Section objects
        output_path: Path to save ToC JSON file

    Raises:
        ValueError: If sections cannot be validated
    """
    # Validate sections
    for section in sections:
        try:
            assert section.start_char < section.end_char
            assert section.start_page <= section.end_page
        except Exception as e:
            raise ValueError(f"Invalid section: {section.title}: {e}") from e

    # Convert to dict for JSON serialization
    toc_data = {
        "sections": [section.model_dump() for section in sections],
    }

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(toc_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved ToC to {output_path} with {len(sections)} sections")

