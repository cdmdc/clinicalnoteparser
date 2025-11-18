#!/usr/bin/env python3
"""Test script to run ingestion and section detection on 1.pdf to generate ToC."""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from app.ingestion import ingest_document
from app.sections import detect_sections
from app.chunks import create_chunks_from_sections, save_chunks
from app.schemas import CanonicalNote

def main():
    input_file = Path("data/archive/mtsamples_pdf/mtsamples_pdf/3.pdf")
    output_dir = Path("results/test_3_pdf")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("Testing Section Detection on 3.pdf")
    print("=" * 60)
    print(f"Input file: {input_file}")
    print()
    
    # Step 1: Ingest document
    print("[STEP 1] Ingesting document...")
    try:
        canonical_note, note_id = ingest_document(input_file)
        print(f"✓ Ingested: {len(canonical_note.text)} chars, {len(canonical_note.page_spans)} pages, note_id: {note_id}")
        
        # Save canonical text for inspection
        canonical_text_path = output_dir / "canonical_text.txt"
        canonical_text_path.write_text(canonical_note.text, encoding="utf-8")
        print(f"  Saved canonical text to: {canonical_text_path}")
        print()
    except Exception as e:
        print(f"✗ Error ingesting document: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Step 2: Detect sections
    print("[STEP 2] Detecting sections...")
    try:
        sections = detect_sections(canonical_note, input_file)
        print(f"✓ Detected {len(sections)} sections:")
        for i, section in enumerate(sections, 1):
            preview = canonical_note.text[section.start_char:section.start_char + 80].replace("\n", " ")
            print(f"  {i}. {section.title}")
            print(f"     Pages: {section.start_page + 1}-{section.end_page + 1}")
            print(f"     Chars: {section.start_char}-{section.end_char}")
            print(f"     Preview: {preview}...")
            print()
    except Exception as e:
        print(f"✗ Error detecting sections: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Step 3: Save ToC
    print("[STEP 3] Saving ToC...")
    try:
        toc_path = output_dir / "toc.json"
        toc_data = {
            "sections": [
                {
                    "title": section.title,
                    "start_char": section.start_char,
                    "end_char": section.end_char,
                    "start_page": section.start_page,
                    "end_page": section.end_page,
                }
                for section in sections
            ]
        }
        toc_path.write_text(json.dumps(toc_data, indent=2), encoding="utf-8")
        print(f"✓ Saved ToC to: {toc_path}")
        print()
    except Exception as e:
        print(f"✗ Error saving ToC: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Step 4: Create chunks
    print("[STEP 4] Creating chunks...")
    try:
        chunks = create_chunks_from_sections(sections, canonical_note)
        print(f"✓ Created {len(chunks)} chunks")
        for i, chunk in enumerate(chunks[:5], 1):  # Show first 5 chunks
            preview = chunk.text[:60].replace("\n", " ")
            print(f"  {i}. {chunk.chunk_id} ({chunk.section_title}): {preview}...")
        if len(chunks) > 5:
            print(f"  ... and {len(chunks) - 5} more chunks")
        print()
    except Exception as e:
        print(f"✗ Error creating chunks: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Step 5: Save chunks
    print("[STEP 5] Saving chunks...")
    try:
        chunks_path = output_dir / "chunks.json"
        save_chunks(chunks, chunks_path)
        print(f"✓ Saved chunks to: {chunks_path}")
        print()
    except Exception as e:
        print(f"✗ Error saving chunks: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Display result
    print("[RESULT] ToC JSON:")
    print("-" * 60)
    print(json.dumps(toc_data, indent=2))
    print("-" * 60)
    print()
    print("✓ Test completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())

