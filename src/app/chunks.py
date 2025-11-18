"""Chunking logic for splitting sections into LLM-processable chunks."""

import json
import logging
import re
from pathlib import Path
from typing import List

from app.config import Config, get_config
from app.schemas import CanonicalNote, Chunk, Section

logger = logging.getLogger(__name__)


def split_into_paragraphs(text: str) -> List[str]:
    """Split text into paragraphs (preserve paragraph boundaries).
    
    Paragraphs are separated by double newlines (\n\n).
    
    Args:
        text: Text to split into paragraphs
        
    Returns:
        List[str]: List of paragraph texts (may be empty strings)
    """
    # Split on double newlines (empty lines)
    paragraphs = text.split("\n\n")
    # Remove leading/trailing whitespace from each paragraph
    paragraphs = [p.strip() for p in paragraphs]
    # Filter out empty paragraphs
    paragraphs = [p for p in paragraphs if p]
    return paragraphs


def split_long_paragraph(paragraph: str, max_size: int) -> List[str]:
    """Split a long paragraph at sentence boundaries.
    
    If a paragraph exceeds max_size, split it at sentence boundaries
    (period, exclamation, question mark followed by space or newline).
    
    Args:
        paragraph: Paragraph text to split
        max_size: Maximum size for each split piece
        
    Returns:
        List[str]: List of paragraph pieces (may be single item if paragraph is short)
    """
    if len(paragraph) <= max_size:
        return [paragraph]
    
    # Split at sentence boundaries: . ! ? followed by space or newline
    sentence_pattern = r'([.!?])\s+'
    sentences = re.split(sentence_pattern, paragraph)
    
    # Reconstruct sentences (pattern captures punctuation, so we need to merge)
    reconstructed = []
    for i in range(0, len(sentences) - 1, 2):
        if i + 1 < len(sentences):
            sentence = sentences[i] + sentences[i + 1]
            reconstructed.append(sentence)
        else:
            reconstructed.append(sentences[i])
    if len(sentences) % 2 == 1:
        reconstructed.append(sentences[-1])
    
    # Merge sentences into chunks that don't exceed max_size
    chunks = []
    current_chunk = ""
    
    for sentence in reconstructed:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        # If adding this sentence would exceed max_size, save current chunk
        if current_chunk and len(current_chunk) + len(sentence) + 1 > max_size:
            chunks.append(current_chunk.strip())
            current_chunk = sentence
        else:
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence
    
    # Add remaining chunk
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks if chunks else [paragraph]


def create_chunks_from_section(
    section: Section,
    canonical_note: CanonicalNote,
    chunk_size: int,
    chunk_overlap: int,
    max_paragraph_size: int,
) -> List[Chunk]:
    """Create chunks from a section's text.
    
    Process:
    1. Extract section text
    2. Split into paragraphs (preserve boundaries)
    3. Handle long paragraphs (split at sentence boundaries)
    4. Merge paragraphs into ~chunk_size chunks with chunk_overlap
    5. Create Chunk objects with global character offsets
    
    Args:
        section: Section to chunk
        canonical_note: CanonicalNote for text access
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks in characters
        max_paragraph_size: Maximum paragraph size before splitting
        
    Returns:
        List[Chunk]: List of Chunk objects
    """
    # Extract section text
    section_text = canonical_note.text[section.start_char:section.end_char]
    
    # Split into paragraphs
    paragraphs = split_into_paragraphs(section_text)
    
    # Handle long paragraphs
    processed_paragraphs = []
    for para in paragraphs:
        if len(para) > max_paragraph_size:
            processed_paragraphs.extend(split_long_paragraph(para, max_paragraph_size))
        else:
            processed_paragraphs.append(para)
    
    # Merge paragraphs into chunks with overlap
    chunks = []
    current_chunk = ""
    current_start_char = section.start_char
    chunk_idx = 0
    
    for para in processed_paragraphs:
        para_with_newline = para + "\n\n"
        
        # If adding this paragraph would exceed chunk_size, save current chunk
        if current_chunk and len(current_chunk) + len(para_with_newline) > chunk_size:
            # Save current chunk
            chunk_end_char = section.start_char + len(section_text[:len(current_chunk)])
            chunks.append(
                Chunk(
                    chunk_id=f"{section.title.lower().replace(' ', '_')}_{chunk_idx}",
                    text=current_chunk.strip(),
                    start_char=current_start_char,
                    end_char=chunk_end_char,
                    section_title=section.title,
                )
            )
            chunk_idx += 1
            
            # Start new chunk with overlap
            # Calculate overlap: take last chunk_overlap chars from current chunk
            if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                overlap_text = current_chunk[-chunk_overlap:]
                # Try to start overlap at word boundary
                overlap_start = overlap_text.find(" ")
                if overlap_start > 0:
                    overlap_text = overlap_text[overlap_start + 1:]
                current_chunk = overlap_text + "\n\n" + para
                current_start_char = chunk_end_char - len(overlap_text)
            else:
                current_chunk = para
                current_start_char = chunk_end_char
        else:
            if current_chunk:
                current_chunk += para_with_newline
            else:
                current_chunk = para
                # Find the actual start position of this paragraph in the section
                para_start_in_section = section_text.find(para)
                if para_start_in_section >= 0:
                    current_start_char = section.start_char + para_start_in_section
    
    # Add final chunk
    if current_chunk:
        chunk_end_char = section.end_char
        chunks.append(
            Chunk(
                chunk_id=f"{section.title.lower().replace(' ', '_')}_{chunk_idx}",
                text=current_chunk.strip(),
                start_char=current_start_char,
                end_char=chunk_end_char,
                section_title=section.title,
            )
        )
    
    return chunks


def create_chunks_from_sections(
    sections: List[Section],
    canonical_note: CanonicalNote,
    config: Config | None = None,
) -> List[Chunk]:
    """Create chunks from all sections.
    
    Args:
        sections: List of Section objects
        canonical_note: CanonicalNote for text access
        config: Configuration instance (uses global config if None)
        
    Returns:
        List[Chunk]: List of all Chunk objects with unique chunk_ids
    """
    if config is None:
        config = get_config()
    
    all_chunks = []
    global_chunk_idx = 0
    
    for section in sections:
        section_chunks = create_chunks_from_section(
            section,
            canonical_note,
            config.chunk_size,
            config.chunk_overlap,
            config.max_paragraph_size,
        )
        
        # Update chunk_ids to be globally unique
        for chunk in section_chunks:
            chunk.chunk_id = f"chunk_{global_chunk_idx}"
            global_chunk_idx += 1
            all_chunks.append(chunk)
    
    logger.info(f"Created {len(all_chunks)} chunks from {len(sections)} sections")
    return all_chunks


def save_chunks(chunks: List[Chunk], output_path: Path) -> None:
    """Save chunks to JSON file.
    
    Args:
        chunks: List of Chunk objects
        output_path: Path to save chunks JSON file
        
    Raises:
        ValueError: If chunks cannot be validated
    """
    # Validate chunks
    for chunk in chunks:
        try:
            assert chunk.start_char < chunk.end_char
            assert len(chunk.text) > 0
        except Exception as e:
            raise ValueError(f"Invalid chunk: {chunk.chunk_id}: {e}") from e
    
    # Convert to dict for JSON serialization
    chunks_data = {
        "chunks": [chunk.model_dump() for chunk in chunks],
    }
    
    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved {len(chunks)} chunks to {output_path}")

