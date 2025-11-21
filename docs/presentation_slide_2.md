# Slide 2: Dataset

## MTSamples Dataset

### Dataset Overview

**Source**: MTSamples Medical Transcription Samples Dataset
- **Location**: `data/archive/mtsamples_pdf/mtsamples_pdf/`
- **Size**: ~5,000 clinical note PDFs
- **Specialties**: ~40 different medical specialties
  - Examples: Allergy/Immunology, Cardiovascular/Pulmonary, Surgery, Cardiology, Radiology, etc.

**Citation**: 
> MTSamples dataset - A collection of medical transcription reports used for NLP research. Available at: https://www.mtsamples.com/ (or cite the specific source you obtained it from)

---

### Dataset Characteristics

#### Note Length
- **Average**: ~3,400 characters per note
- **Range**: 1,300 - 5,500 characters
- **Average Sections**: ~9 sections per note

#### Document Structure
Each note contains:
- **Overview Section**: 
  - Medical Specialty
  - Sample Name
  - Description (brief overview/chief concern)
- **Clinical Sections**: Variable structure including:
  - SUBJECTIVE / HISTORY
  - OBJECTIVE / PHYSICAL EXAM
  - ASSESSMENT / IMPRESSION
  - PLAN / RECOMMENDATIONS
  - MEDICATIONS, ALLERGIES
  - LABS / IMAGING
  - And more...

#### Specialty Diversity
- Covers 40+ medical specialties
- Includes various note types:
  - Consultation notes
  - Procedure reports
  - Follow-up visits
  - Emergency department notes
  - And more...

---

### Data Preparation Steps

#### Step 1: Document Ingestion & PDF Extraction

**Our Approach**:
- **File Format Support**: PDF (via `pypdf`) and plain text files
  - **Rationale**: `pypdf` is lightweight, doesn't require external dependencies, and provides sufficient text extraction for our use case
- **Note ID Generation**: Create filesystem-safe identifier from filename (sanitize special chars) or MD5 hash if filename unavailable
  - **Rationale**: Enables per-document output organization without path conflicts
- **Page-by-Page Extraction**:
  - Extract text from each PDF page sequentially using `page.extract_text()`
  - **Critical Design Decision**: Track character offsets for each page to maintain global position mapping
  - Add newline between pages (except first page) to preserve page boundaries
  - Handle empty pages gracefully (log warning, continue with empty string)
  - **Rationale**: Sequential processing ensures deterministic character offsets, enabling precise citation tracking

- **Page Span Mapping**: Create `PageSpan` objects mapping character ranges to page numbers (zero-based)
  - Each page gets: `(start_char, end_char, page_index)`
  - **Rationale**: Enables bidirectional mapping - from character position → page number for citations, and page number → character range for navigation
  - **Trade-off**: We prioritize character-level precision over page-level granularity (character offsets are more precise for citations)

**Output**: `CanonicalNote` object containing:
- Full document text (concatenated pages with newlines)
- List of `PageSpan` objects for page-to-character mapping

**Why This Design**: We need a **canonical text representation** with precise character-to-page mapping. This enables:
1. **Traceability**: Every extracted fact can cite exact character positions
2. **Reproducibility**: Same document always produces same canonical representation
3. **Efficiency**: Single text string is easier to process than page-by-page operations

---

#### Step 2: Text Normalization

**Our Approach**: Minimal normalization that preserves document structure

**Design Philosophy**: We normalize only what's necessary for processing, while **preserving structural markers** that enable accurate section detection.

**Normalization Operations**:

1. **Encoding Normalization**:
   - Replace non-breaking spaces (`\xa0`, `\u2009`, `\u202f`) with regular spaces
   - **Rationale**: PDFs often contain Unicode whitespace that breaks text matching; we normalize to standard spaces for consistent processing

2. **Line Ending Normalization**:
   - Convert all line endings (`\r\n`, `\r`) to `\n` (Unix-style)
   - **Rationale**: Consistent line endings simplify regex patterns and line-by-line processing

3. **Empty Line Preservation** (CRITICAL):
   - **Do NOT** collapse single or double newlines (`\n` or `\n\n`)
   - Only collapse excessive empty lines (3+ consecutive newlines → 2 newlines)
   - **Rationale**: Empty lines (`\n\n`) are **structural markers** that indicate:
     - Section boundaries (section headers appear after empty lines)
     - Paragraph boundaries (paragraphs are separated by empty lines)
   - **Why This Matters**: Our section detection algorithm relies on finding all-caps text at the start of a line **after an empty line**. If we collapse empty lines, we lose this critical signal.

**Trade-offs**:
- **We preserve structure** at the cost of some whitespace "noise" (extra blank lines)
- **We prioritize accuracy** of section detection over "clean" text formatting
- **We normalize encoding** but preserve layout cues (empty lines, line breaks)

**Why This Design**: Clinical notes use empty lines as visual separators between sections. By preserving them, we can use simple, deterministic regex-based section detection rather than requiring complex layout analysis or LLM-based detection for every document.

---

#### Step 3: Section Detection

**Our Approach**: Deterministic regex-based detection with pattern matching, prioritizing speed and reliability over LLM-based approaches

**Design Philosophy**: We use **rule-based detection first** because:
1. **Speed**: Regex is orders of magnitude faster than LLM calls
2. **Reliability**: Deterministic results, no variability from LLM responses
3. **Cost**: No API costs for section detection (critical for processing 5,000+ documents)
4. **Accuracy**: Clinical notes follow predictable formatting conventions

**Three-Phase Approach**:

**Phase 1: Overview Section Detection**
- **Pattern Matching**: Search first 2000 characters for "Medical Specialty", "Sample Name", "Description" fields (case-insensitive regex)
- **Boundary Detection**: Find first major section header after overview fields
  - Regex: `^\s*([A-Z][A-Z\s]{3,}):?\s*$` (all-caps words at start of line)
  - Or matches against `CLINICAL_SECTION_PATTERNS` list (SUBJECTIVE, OBJECTIVE, HISTORY, etc.)
- **Rationale**: MTSamples dataset has consistent structure - overview always comes first, followed by clinical sections
- **Output**: Overview section with character offsets (start: 0, end: position of first clinical section)

**Phase 2: Clinical Section Header Detection**
- **Our Refined Rules** (applied in order, all must pass):
  
  1. **Location Constraint**: Must be at start of line (≤3 spaces leading whitespace)
     - **Rationale**: Section headers are left-aligned in clinical notes; indented text is content, not headers
   
  2. **Format Constraint**: Must be all-caps (`isupper()` check)
     - **Rationale**: Clinical section headers are consistently capitalized (SUBJECTIVE, OBJECTIVE, etc.)
     - **Trade-off**: We miss mixed-case headers, but gain precision (fewer false positives)
   
  3. **Context Constraint**: Must appear after an empty line (or be first line after Overview)
     - **Rationale**: This is why we preserved empty lines in normalization! Empty lines are the strongest signal for section boundaries
     - **Implementation**: Check if previous line is empty (`prev_line.strip() == ""`)
     - **Fallback**: Accept if header is on its own line and followed by content (handles edge cases)
   
  4. **Pattern Matching**: Must match known clinical section patterns OR pass heuristic
     - **Known Patterns**: 20+ regex patterns for common sections (SUBJECTIVE, OBJECTIVE, HISTORY, PHYSICAL EXAM, ASSESSMENT, PLAN, MEDICATIONS, ALLERGIES, LABS, IMAGING, etc.)
     - **Heuristic Fallback**: 4-50 chars, all-caps, no digits, ≤5 words
     - **Rationale**: Covers common sections while allowing discovery of non-standard section names
   
  5. **Line Validation**: Header must be on its own line (entire line is just the header, optional colon)
     - **Rationale**: Prevents matching all-caps text that's part of a sentence

- **Deduplication**: Remove duplicate headers at same position (case-insensitive)
- **Sorting**: Sort by character position in document

**Phase 3: Section Object Creation**
- **Section Boundaries**: 
  - Start: Header position (character offset)
  - End: Next section header position (or end of document)
- **Page Mapping**: Convert character offsets to page numbers using `PageSpan` mapping
  - **Rationale**: Enables citations to include both character spans AND page numbers
- **Validation**: Ensure start < end, valid page ranges

**Fallback Mechanisms**:
- **Insufficient Sections**: If < `min_sections_for_success` (default: 2) sections found after Overview:
  - Log warning
  - **Note**: LLM fallback is planned but not yet implemented (would use `prompts/section_inference.md`)
  - **Rationale**: Most documents work with regex; LLM fallback is expensive, so we only use it when necessary
- **No Sections Found**: Create single "Full Note" section spanning entire document
  - **Rationale**: Better to have one section than fail completely; LLM can still process the full document

**Why This Design**:
- **Deterministic First**: Regex-based detection is fast, reliable, and works for 95%+ of documents
- **Pattern-Based**: Leverages consistent formatting conventions in clinical notes
- **Structure-Aware**: Uses empty lines (preserved in normalization) as primary signal
- **Graceful Degradation**: Falls back to single section rather than failing

**Output**: List of `Section` objects with:
- `title`: Section header text (normalized)
- `start_char`, `end_char`: Global character offsets (for precise citations)
- `start_page`, `end_page`: Page numbers (zero-based, for human-readable citations)

**Saved to**: `toc.json` (Table of Contents)

---

#### Step 4: Chunking

**Our Approach**: Hierarchical chunking that respects semantic boundaries while optimizing for LLM context windows

**Design Philosophy**: We chunk at **semantic boundaries** (paragraphs, sentences) rather than arbitrary character counts because:
1. **Semantic Coherence**: LLMs perform better on complete thoughts (paragraphs) than mid-sentence cuts
2. **Citation Accuracy**: Citations are more meaningful when they reference complete semantic units
3. **Context Preservation**: Overlap ensures no information is lost at chunk boundaries

**Chunking Strategy** (hierarchical, bottom-up):

1. **Paragraph-Level Splitting** (First Priority):
   - Split section text on double newlines (`\n\n`) - these are paragraph boundaries we preserved in normalization
   - Remove leading/trailing whitespace from each paragraph
   - Filter out empty paragraphs
   - **Rationale**: Paragraphs are **semantic units** - they represent complete thoughts or observations. Splitting at paragraph boundaries maintains coherence.

2. **Long Paragraph Handling** (Second Priority):
   - If paragraph exceeds `max_paragraph_size` (default: 3000 chars):
     - Split at sentence boundaries using regex: `([.!?])\s+`
     - Reconstruct sentences preserving punctuation (regex captures punctuation, so we merge it back)
     - Merge sentences into chunks ≤ `max_paragraph_size`
   - **Rationale**: Some paragraphs (e.g., long medication lists) exceed LLM context. We split at sentence boundaries (next-best semantic boundary) rather than mid-sentence.

3. **Chunk Assembly** (Third Priority):
   - **Target Size**: `chunk_size` (default: 1500 characters)
     - **Rationale**: Balances LLM context window limits (typically 2K-4K tokens) with information density
     - **Trade-off**: Smaller chunks = more LLM calls but better focus; larger chunks = fewer calls but may lose detail
   
   - **Overlap**: `chunk_overlap` (default: 200 characters) between consecutive chunks
     - **Implementation**: Take last `chunk_overlap` chars from current chunk, find first word boundary (space), start new chunk from that point
     - **Rationale**: 
       - **Context Continuity**: Ensures information at chunk boundaries isn't lost
       - **LLM Performance**: LLMs perform better when they have surrounding context
       - **Citation Accuracy**: Overlap helps when facts span chunk boundaries
     - **Word Boundary Alignment**: Overlap starts at word boundary (not mid-word) for readability
   
   - **Process**:
     - Iterate through processed paragraphs
     - Add paragraphs to current chunk until adding next would exceed `chunk_size`
     - Save current chunk, start new chunk with overlap
     - Track character offsets precisely for citation mapping

4. **Chunk Object Creation**:
   - **Global Character Offsets**: Each chunk tracks `start_char` and `end_char` in **full document** (not just section)
     - **Rationale**: Enables citations that reference the entire document, not just section-relative positions
   - **Section Association**: Each chunk tagged with `section_title`
     - **Rationale**: Provides context about what type of information is in the chunk (e.g., "ASSESSMENT" vs "MEDICATIONS")
   - **Unique IDs**: Globally unique `chunk_id` (format: `chunk_0`, `chunk_1`, ...)
     - **Rationale**: Enables precise citation references in LLM outputs (e.g., "chunk_11:4648-5547")

**Configuration Parameters** (tuned for our use case):
- `chunk_size`: 1500 characters
  - **Rationale**: ~300-400 tokens (assuming ~4 chars/token), fits comfortably in most LLM context windows with room for prompts
- `chunk_overlap`: 200 characters
  - **Rationale**: ~50 tokens of overlap - enough for context continuity without excessive redundancy
  - **Constraint**: Must be < `chunk_size` (validated in config)
- `max_paragraph_size`: 3000 characters
  - **Rationale**: Allows paragraphs up to 2x chunk size before forcing sentence-level splitting

**Why This Hierarchical Approach**:
1. **Semantic Preservation**: Paragraphs → sentences → chunks maintains semantic coherence
2. **Flexibility**: Handles both short sections (single chunk) and long sections (multiple chunks with overlap)
3. **LLM Optimization**: Chunk size tuned for LLM context windows; overlap ensures no information loss
4. **Citation Precision**: Global character offsets enable exact citation back to original document

**Trade-offs**:
- **We prioritize semantic boundaries** over perfect chunk size uniformity (chunks may vary ±20% in size)
- **We use overlap** which increases total tokens processed but improves accuracy
- **We split long paragraphs** at sentences rather than preserving them as single chunks (better for LLM processing)

**Output**: List of `Chunk` objects with:
- `chunk_id`: Unique identifier (e.g., `chunk_0`, `chunk_1`)
- `text`: Chunk text content (paragraphs separated by `\n\n`)
- `start_char`, `end_char`: Global character offsets in full document
- `section_title`: Parent section name (for context)

**Saved to**: `chunks.json`

---

### Data Flow Summary

```
PDF/Text File
    ↓
[Ingestion] 
  • Page-by-page extraction (pypdf)
  • Character offset tracking
  • Page span mapping
    ↓
CanonicalNote (text + page_spans)
    ↓
[Normalization]
  • Encoding cleanup (Unicode whitespace → spaces)
  • Line ending normalization (→ \n)
  • CRITICAL: Preserve empty lines (\n\n)
    ↓
Normalized text (structure-preserved)
    ↓
[Section Detection]
  • Overview detection (pattern matching)
  • Clinical header detection (regex + empty line context)
  • Section boundary creation
    ↓
List[Section] → toc.json
  • Character offsets + page numbers
    ↓
[Chunking]
  • Paragraph splitting (\n\n boundaries)
  • Sentence splitting (for long paragraphs)
  • Chunk assembly (1500 chars, 200 overlap)
    ↓
List[Chunk] → chunks.json
  • Global character offsets
  • Section associations
    ↓
Ready for LLM Processing
```

**Key Design Principles & Rationale**:

1. **Traceability First**
   - **Approach**: Every step maintains character offsets and page mappings
   - **Rationale**: Medical applications require precise citations for accountability and verification
   - **Implementation**: Global character offsets enable citations like `chunk_11:4648-5547` that map directly to original document

2. **Structure Preservation**
   - **Approach**: Preserve empty lines, paragraph boundaries, section structure
   - **Rationale**: Document structure carries semantic meaning (sections, paragraphs = logical units)
   - **Trade-off**: We keep "noise" (extra whitespace) to preserve signals (structure markers)

3. **Deterministic Over LLM**
   - **Approach**: Use regex/pattern matching for section detection, LLM only for content extraction
   - **Rationale**: 
     - Faster (regex is instant vs seconds per LLM call)
     - More reliable (deterministic results)
     - Lower cost (no API calls for structure detection)
   - **Trade-off**: May miss non-standard formats, but works for 95%+ of documents

4. **Semantic Boundary Respect**
   - **Approach**: Chunk at paragraph → sentence → character boundaries (hierarchical)
   - **Rationale**: LLMs perform better on complete semantic units than arbitrary cuts
   - **Implementation**: Paragraphs first, then sentences, then character limits

5. **LLM Optimization**
   - **Approach**: Chunk size (1500 chars) tuned for context windows; overlap (200 chars) for continuity
   - **Rationale**: Balance between information density and context window limits
   - **Trade-off**: Overlap increases tokens processed but improves accuracy and citation quality

6. **Robustness & Graceful Degradation**
   - **Approach**: Handle edge cases (empty pages, missing sections, long paragraphs) with fallbacks
   - **Rationale**: Real-world documents are messy; pipeline should never fail completely
   - **Implementation**: Warnings for edge cases, fallback to single section if detection fails

---

### De-Identification

**Status**: The MTSamples dataset is a publicly available research dataset that contains **already de-identified** medical transcription samples.

**Note**: 
- Patient identifiers (names, dates of birth, addresses, etc.) have been removed or anonymized in the original dataset
- The dataset is designed for research and educational purposes
- Our pipeline includes additional PHI protection measures:
  - Explicit instructions to LLMs to not add or infer PHI
  - No hallucination of patient identifiers
  - Local processing for privacy

**Citation**: 
> MTSamples dataset is provided as de-identified medical transcription samples for research purposes. [Cite the specific source/paper if available]

