# Slide 4: Prompt & Retrieval Strategy

## Overview

Our system uses a **single-pass, full-context retrieval strategy** where all chunks are processed together in one LLM call, rather than traditional RAG-style retrieval. This approach prioritizes comprehensive context over selective retrieval.

---

## Retrieval Strategy: Full-Context Processing

### Approach: Process All Chunks, Not Selective Retrieval

**Key Design Decision**: We process **all chunks** in a single LLM call rather than using retrieval-augmented generation (RAG) with similarity search.

**Why This Approach**:
1. **Complete Context**: LLM sees entire document, can make connections across sections
2. **No Information Loss**: No risk of missing relevant chunks due to retrieval failures
3. **Efficiency**: Single LLM call vs. multiple calls (chunk retrieval + generation)
4. **Deterministic**: Same document always processes same chunks (no retrieval variability)

**Trade-offs**:
- **Context Window Limits**: Requires LLM with sufficient context window (our chunks fit in ~2K-4K token windows)
- **Cost**: Processes all text even if some chunks less relevant (but single call is more efficient overall)
- **Scalability**: Works well for clinical notes (typically 3-10 chunks), may need adjustment for very long documents

**When We Use This**:
- Clinical notes are typically manageable size (average ~3,400 chars = ~3-10 chunks)
- Full context is valuable for medical reasoning (connections across sections matter)
- Traceability requires processing all chunks anyway (for citation coverage)

---

## Chunking Strategy

### Hierarchical Chunking with Semantic Boundaries

**Three-Level Hierarchy**:

1. **Section Level** (Top)
   - Document split into sections (Overview, HISTORY, ASSESSMENT, etc.)
   - Sections provide semantic context (type of information)

2. **Paragraph Level** (Middle)
   - Sections split into paragraphs (double newlines `\n\n`)
   - Paragraphs are semantic units (complete thoughts)

3. **Sentence Level** (Bottom, if needed)
   - Long paragraphs (>3000 chars) split at sentence boundaries
   - Preserves sentence structure

### Chunk Assembly Rules

**Process**:
1. Extract section text
2. Split into paragraphs (preserve boundaries)
3. For paragraphs > `max_paragraph_size`: Split at sentences
4. Merge paragraphs into chunks approaching `chunk_size`
5. Add `chunk_overlap` between consecutive chunks

**Key Principle**: **Never split mid-sentence or mid-paragraph** unless paragraph exceeds maximum size.

---

## Window Sizes & Configuration

### Configuration Parameters

| Parameter | Default | Purpose | Rationale |
|-----------|---------|---------|-----------|
| `chunk_size` | 1500 chars | Target chunk size | ~300-400 tokens, fits comfortably in 2K-4K token context windows |
| `chunk_overlap` | 200 chars | Overlap between chunks | ~50 tokens, ensures context continuity at boundaries |
| `max_paragraph_size` | 3000 chars | Max paragraph before sentence splitting | Allows paragraphs up to 2x chunk size before forcing split |

### Token Estimation

**Character-to-Token Ratio**: ~4 characters per token (English text)

**Chunk Size Calculation**:
- 1500 characters ≈ 375 tokens
- With prompt overhead (~500-1000 tokens), total per chunk: ~875-1375 tokens
- Multiple chunks (3-10) + prompt: ~2,625-13,750 tokens total
- **Fits in**: 4K-8K token context windows (most modern LLMs)

### Overlap Strategy

**Implementation**:
- Take last `chunk_overlap` characters from current chunk
- Find first word boundary (space) in overlap region
- Start new chunk from word boundary
- **Rationale**: Overlap at word boundaries is more readable and maintains context

**Example**:
```
Chunk 1: "...patient presents with chest pain. The pain started..."
         [---200 chars overlap---]
Chunk 2: "The pain started yesterday and is radiating..."
```

**Why Overlap Matters**:
- **Context Continuity**: Information at chunk boundaries isn't lost
- **Citation Accuracy**: Facts spanning boundaries can be properly cited
- **LLM Performance**: LLMs perform better with surrounding context

---

## Prompt Schema

### Summary Generation Prompt Schema

**Input Format**:
```
## {section_title} ({chunk_id}, chars {start_char}-{end_char})
{chunk_text}

## {section_title} ({chunk_id}, chars {start_char}-{end_char})
{chunk_text}
...
```

**Output Schema** (JSON):
```json
{
  "patient_snapshot": [
    {"text": "...", "source": "SECTION_NAME section, chunk_X:Y-Z"}
  ],
  "key_problems": [
    {"text": "...", "source": "SECTION_NAME section, chunk_X:Y-Z"}
  ],
  "pertinent_history": [
    {"text": "...", "source": "SECTION_NAME section, chunk_X:Y-Z"}
  ],
  "medicines_allergies": [
    {"text": "...", "source": "SECTION_NAME section, chunk_X:Y-Z"}
  ],
  "objective_findings": [
    {"text": "...", "source": "SECTION_NAME section, chunk_X:Y-Z"}
  ],
  "labs_imaging": [
    {"text": "...", "source": "SECTION_NAME section, chunk_X:Y-Z"}
  ],
  "assessment": [
    {"text": "...", "source": "SECTION_NAME section, chunk_X:Y-Z"}
  ]
}
```

**Schema Rules**:
- Each section is an **array** of items (allows multiple facts per section)
- Each item has exactly **two fields**: `text` and `source`
- `text`: Summarized information (not verbatim copy)
- `source`: Citation in specific format (see Citation Rules below)
- Empty sections use empty array `[]` (not `null` or placeholder text)

### Plan Generation Prompt Schema

**Input Format**:
- Summary text (formatted with section headers)
- Summary JSON (for reference)
- Valid section titles list

**Output Schema** (JSON):
```json
{
  "recommendations": [
    {
      "number": 1,
      "recommendation": "Comprehensive recommendation text...",
      "source": "SECTION_NAME section, chunk_X:Y-Z",
      "confidence": 0.9,
      "hallucination_guard_note": null
    }
  ]
}
```

**Schema Rules**:
- `recommendations`: Array of recommendation objects
- Each recommendation has: `number`, `recommendation`, `source`, `confidence`, `hallucination_guard_note`
- `number`: Integer, ordered by urgency (1 = most urgent)
- `recommendation`: Comprehensive text including diagnosis, diagnostics, therapeutics, follow-ups, risks/benefits
- `source`: Citation from summary (copied from assessment item)
- `confidence`: Float [0, 1]
- `hallucination_guard_note`: String or null (required if confidence < 0.8)

---

## Citation Rules

### Citation Format

**Standard Format**:
```
"[SECTION_NAME] section, [chunk_id]:[start_char]-[end_char]"
```

**Example**:
```
"MEDICAL DECISION MAKING section, chunk_11:2192-2922"
```

### Citation Components

1. **Section Name**:
   - Must match **exact** `section_title` from chunk header
   - Case-sensitive (e.g., "MEDICAL DECISION MAKING" not "Medical Decision Making")
   - Must appear in chunk headers provided to LLM

2. **Chunk ID**:
   - Format: `chunk_X` where X is integer (e.g., `chunk_0`, `chunk_11`)
   - Must match **exact** `chunk_id` from chunk header
   - Globally unique across document

3. **Character Range**:
   - Format: `start_char-end_char` (e.g., `2192-2922`)
   - **Global** character offsets (relative to full document, not chunk)
   - Must be within chunk bounds: `chunk.start_char ≤ start_char < end_char ≤ chunk.end_char`

### Citation Rules & Validation

**Rule 1: Exact Match Requirement**
- Section name, chunk ID, and character range must **exactly match** chunk headers provided to LLM
- **No fabrication**: LLM cannot invent section names, chunk IDs, or character ranges
- **Validation**: Evaluation system checks citations against actual chunks

**Rule 2: One Source Per Item**
- Each summary item has **one** `source` field
- Each plan recommendation has **one** `source` field
- If information spans multiple chunks, LLM should choose most relevant chunk

**Rule 3: Empty Sections**
- If section has no information: Use empty array `[]`
- **Do NOT** create entries with:
  - `{"text": "None documented", "source": "..."}`
  - `{"text": "No information available", "source": "..."}`
  - Fake citations to non-existent sections

**Rule 4: Source Inheritance (Plan Generation)**
- Plan recommendations copy `source` from corresponding summary `assessment` item
- Plan LLM receives "Valid Section Titles" list to prevent fabrication
- Plan citations must reference sections that exist in summary

### Citation Validation in Evaluation

**Validation Checks**:
1. **Section Name Validation**: Cited section name matches chunk's `section_title`
2. **Span Validation**: Character spans are within chunk's global bounds
3. **Chunk ID Validation**: Chunk ID exists in document
4. **Format Validation**: Citation matches expected format (regex parsing)

**Metrics Tracked**:
- Citation coverage (percentage of items with valid citations)
- Section name mismatches
- Span out-of-bounds errors
- Orphan claims (items without citations)

---

## Prompt Engineering Principles

### 1. Explicit Schema Definition

**Approach**: Prompts include detailed JSON schema with examples

**Rationale**:
- Reduces LLM errors (clear structure expectations)
- Enables automatic parsing and validation
- Consistent output format across documents

**Implementation**:
- JSON schema in markdown code blocks
- Escaped curly braces (`{{` and `}}`) for Python string formatting
- Examples showing exact format expected

### 2. Anti-Hallucination Instructions

**Key Instructions**:
- "Do NOT fabricate section names"
- "Do NOT create fake citations"
- "Use ONLY section titles that appear in chunk headers"
- "If information doesn't exist, use empty array []"

**Rationale**:
- Medical applications require high accuracy
- Fabricated citations break traceability
- Empty arrays are better than fake data

### 3. Comprehensive Extraction

**Instructions**:
- "Extract **ALL** items" (emphasized with bold)
- "Create separate items for each distinct [thing]"
- "Do not omit any [information type]"

**Rationale**:
- Clinical notes require comprehensive extraction
- Missing information can impact patient care
- Separate items enable better downstream processing

### 4. Citation Requirements

**Explicit Requirements**:
- "Every item MUST include a source citation"
- "Use EXACT section_title, chunk_id, and character range"
- "Verify each citation matches a chunk header above"

**Rationale**:
- Traceability is non-negotiable in medical applications
- Exact matching enables automated validation
- Verification instruction reduces errors

### 5. PHI Protection

**Instructions**:
- "Do not add, infer, or fabricate Protected Health Information (PHI)"
- "Only extract information explicitly present in source text"

**Rationale**:
- HIPAA compliance requires PHI protection
- Prevents hallucination of patient identifiers
- Legal and ethical requirement

---

## Prompt Template Structure

### Template Loading

**Location**: `prompts/` directory
- `text_summary.md`: Summary generation prompt
- `plan_generation.md`: Plan generation prompt
- `section_inference.md`: Optional section detection fallback

**Loading Process**:
1. `LLMClient.load_prompt(prompt_name)` reads template file
2. Template uses Python `.format()` for variable substitution
3. Variables: `{chunks_with_headers}`, `{summary_sections}`, `{section_titles_list}`

### Template Variables

**Summary Prompt**:
- `{chunks_with_headers}`: Formatted chunks with section headers and citation metadata

**Plan Prompt**:
- `{summary_sections}`: Formatted summary (text + JSON)
- `{section_titles_list}`: List of valid section titles (prevents fabrication)

### Prompt Construction Flow

```
1. Load template from prompts/{name}.md
2. Format chunks/summary with citation metadata
3. Inject formatted content into template
4. Add system instructions (PHI protection, citation rules)
5. Send to LLM with JSON parsing enabled
```

---

## Retrieval vs. Full-Context: Design Rationale

### Why Not Traditional RAG?

**Traditional RAG Approach**:
1. Query → Embedding
2. Similarity search → Top-K chunks
3. LLM generation with retrieved chunks

**Why We Don't Use This**:
- **Clinical notes are small**: Average 3-10 chunks, all fit in context window
- **Full context matters**: Medical reasoning requires seeing all information
- **No query needed**: We're extracting everything, not answering specific questions
- **Deterministic processing**: Same document always processes same chunks

### When Full-Context Works Best

**Ideal For**:
- Documents that fit in LLM context window
- Tasks requiring comprehensive extraction (not selective retrieval)
- Applications where traceability requires processing all chunks
- Scenarios where connections across sections matter

**Our Use Case**:
- Clinical notes: 1,300-5,500 characters (3-10 chunks)
- Task: Extract all information comprehensively
- Requirement: Every fact must be traceable (process all chunks)
- Reasoning: Medical decisions benefit from full context

---

## Summary: Key Design Decisions

1. **Full-Context Processing**: Process all chunks in single LLM call (not selective retrieval)
2. **Semantic Chunking**: Respect paragraphs and sentences (not arbitrary character cuts)
3. **Overlap Strategy**: 200-char overlap at word boundaries for context continuity
4. **Explicit Citations**: Every item must cite exact chunk with character spans
5. **Schema-Driven**: JSON schemas in prompts ensure consistent output
6. **Anti-Hallucination**: Explicit instructions prevent fabrication
7. **Comprehensive Extraction**: "Extract ALL" instructions ensure nothing is missed

**Result**: A system that processes clinical notes comprehensively with full traceability, optimized for medical information extraction rather than question-answering.

