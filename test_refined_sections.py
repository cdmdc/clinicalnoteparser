"""Test script to test refined section detection with empty line requirement."""

import json
import logging
from pathlib import Path

from app.ingestion import ingest_document
from app.sections import detect_sections, save_toc

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

test_file = Path("data/archive/mtsamples_pdf/mtsamples_pdf/0.pdf")
output_dir = Path("results/test_0_refined")
output_dir.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("Testing Refined Section Detection (after empty lines)")
print("=" * 60)
print(f"Input file: {test_file}")
print()

try:
    print("[STEP 1] Ingesting document...")
    canonical_note, note_id = ingest_document(test_file)
    print(f"✓ Ingested: {len(canonical_note.text)} chars, {len(canonical_note.page_spans)} pages")
    
    # Save canonical text for inspection
    canonical_text_path = output_dir / "canonical_text.txt"
    with open(canonical_text_path, "w", encoding="utf-8") as f:
        f.write(canonical_note.text)
    print(f"  Saved canonical text to: {canonical_text_path}")
    print()
    
    print("[STEP 2] Detecting sections with refined rules...")
    sections = detect_sections(canonical_note, test_file)
    print(f"✓ Detected {len(sections)} sections:")
    for i, section in enumerate(sections, 1):
        print(f"  {i}. {section.title}")
        print(f"     Pages: {section.start_page + 1}-{section.end_page + 1}")
        print(f"     Chars: {section.start_char}-{section.end_char}")
        preview = canonical_note.text[section.start_char:section.start_char+80].replace(chr(10), ' ')
        print(f"     Preview: {preview}...")
    print()
    
    print("[STEP 3] Saving ToC...")
    toc_path = output_dir / "toc.json"
    save_toc(sections, toc_path)
    print(f"✓ Saved ToC to: {toc_path}")
    print()
    
    print("[RESULT] ToC JSON:")
    print("-" * 60)
    with open(toc_path, "r", encoding="utf-8") as f:
        toc_data = json.load(f)
        print(json.dumps(toc_data, indent=2, ensure_ascii=False))
    print("-" * 60)
    
    print("\n✓ Test completed successfully!")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()

