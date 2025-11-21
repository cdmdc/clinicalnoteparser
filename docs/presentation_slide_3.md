# Slide 3: System Design

## Pipeline Architecture

### Overview

Our system transforms unstructured clinical notes into structured, actionable outputs through a multi-stage pipeline that combines deterministic processing with LLM-based reasoning.

```
PDF/Text Input
    ↓
[1. Ingestion] → Canonical Text Representation
    ↓
[2. Segmentation/ToC] → Table of Contents (Sections)
    ↓
[3. Chunking] → LLM-Ready Chunks
    ↓
[4. LLM Reasoning] → Structured Outputs
    ├─ Summary Generation
    └─ Plan Generation
    ↓
[5. Evaluation] → Quality Metrics
    ↓
Final Outputs (JSON + Text)
```

---

## Stage 1: Ingestion

**Input**: PDF or plain text file  
**Output**: `CanonicalNote` (text + page_spans)

**Process**:
- Extract text page-by-page using `pypdf`
- Normalize encoding and line endings
- **Critical**: Preserve empty lines for section detection
- Create character-to-page mapping (`PageSpan` objects)

**Output Files**:
- `canonical_text.txt`: Full document text with preserved structure

**Design Rationale**:
- Single canonical representation enables consistent processing
- Character offsets enable precise citations
- Page mapping provides human-readable references

---

## Stage 2: Segmentation / Table of Contents (ToC)

**Input**: Canonical text  
**Output**: `toc.json` (List of `Section` objects)

**Process**:
1. **Overview Detection**: Identify "Overview" section (Medical Specialty, Sample Name, Description)
2. **Section Header Detection**: 
   - Regex-based pattern matching
   - Rules: All-caps, at start of line, after empty line
   - Matches 20+ clinical section patterns (SUBJECTIVE, OBJECTIVE, ASSESSMENT, PLAN, etc.)
3. **Section Creation**: 
   - Define boundaries (start_char, end_char)
   - Map to page numbers
   - Create `Section` objects

**Output Files**:
- `toc.json`: Table of contents with section titles, character offsets, and page numbers

**Design Rationale**:
- **Deterministic First**: Regex-based detection is fast, reliable, and works for 95%+ of documents
- **Structure-Aware**: Uses empty lines (preserved in ingestion) as primary signal
- **Fallback**: Single "Full Note" section if detection fails (graceful degradation)

**Example ToC Structure**:
```json
{
  "sections": [
    {
      "title": "Overview",
      "start_char": 0,
      "end_char": 245,
      "start_page": 0,
      "end_page": 0
    },
    {
      "title": "HISTORY",
      "start_char": 246,
      "end_char": 892,
      "start_page": 0,
      "end_page": 0
    },
    ...
  ]
}
```

---

## Stage 3: Chunking

**Input**: Sections from ToC  
**Output**: `chunks.json` (List of `Chunk` objects)

**Process**:
1. **Paragraph Splitting**: Split sections on double newlines (`\n\n`)
2. **Long Paragraph Handling**: Split at sentence boundaries if paragraph > 3000 chars
3. **Chunk Assembly**:
   - Merge paragraphs into ~1500 character chunks
   - Add 200 character overlap between chunks (at word boundaries)
   - Track global character offsets

**Output Files**:
- `chunks.json`: Chunks with text, character offsets, and section associations

**Design Rationale**:
- **Semantic Boundaries**: Respect paragraphs and sentences (complete thoughts)
- **LLM Optimization**: Chunk size (1500 chars ≈ 300-400 tokens) fits context windows
- **Context Continuity**: Overlap ensures no information loss at boundaries
- **Citation Precision**: Global offsets enable exact citations

**Example Chunk Structure**:
```json
{
  "chunks": [
    {
      "chunk_id": "chunk_0",
      "text": "Section content...",
      "start_char": 246,
      "end_char": 1746,
      "section_title": "HISTORY"
    },
    ...
  ]
}
```

---

## Stage 4: LLM Reasoning

**Architecture**: Single LLM client (Ollama) with retry logic and JSON parsing

**Components**:
- **LLMClient**: Wrapper around `ChatOllama` (LangChain)
- **Prompt Templates**: Stored in `prompts/` directory
- **Retry Logic**: Exponential backoff (default: 3 retries)
- **JSON Parsing**: Automatic extraction from markdown code blocks or raw JSON

### 4.1 Summary Generation

**Input**: All chunks (with section headers and character spans)  
**Output**: `summary.json` (StructuredSummary)

**Process**:
1. **Chunk Formatting**: Combine all chunks with section headers and citation metadata
   - Format: `## {section_title} ({chunk_id}, chars {start_char}-{end_char})`
   - Include chunk text
2. **Prompt Construction**: Load `prompts/text_summary.md` template
   - Inject formatted chunks
   - Request structured JSON output with 7 sections
3. **LLM Call**: Single call with all chunks
   - **Rationale**: LLM sees full document context, can make connections across sections
   - **Trade-off**: Larger context but single call (faster than chunk-by-chunk)
4. **Response Parsing**: Extract JSON, validate against `StructuredSummary` schema
5. **Validation**: Pydantic validation ensures schema compliance

**Output Structure**:
```json
{
  "patient_snapshot": [{"text": "...", "source": "..."}],
  "key_problems": [{"text": "...", "source": "..."}],
  "pertinent_history": [{"text": "...", "source": "..."}],
  "medicines_allergies": [{"text": "...", "source": "..."}],
  "objective_findings": [{"text": "...", "source": "..."}],
  "labs_imaging": [{"text": "...", "source": "..."}],
  "assessment": [{"text": "...", "source": "..."}]
}
```

**Citation Format**: `"[section_title] section, chunk_X:start_char-end_char"`

**Design Rationale**:
- **Single Call**: More efficient than chunk-by-chunk processing
- **Full Context**: LLM can connect information across sections
- **Structured Output**: JSON schema ensures consistency and enables downstream processing
- **Source Citations**: Every fact is traceable to original document

### 4.2 Plan Generation

**Input**: `summary.json` (StructuredSummary)  
**Output**: `plan.json` (StructuredPlan)

**Process**:
1. **Summary Formatting**: 
   - Load structured summary JSON
   - Format as text with section headers
   - Extract section titles for prompt context
2. **Prompt Construction**: Load `prompts/plan_generation.md` template
   - Inject formatted summary (text + JSON)
   - Include section titles list for citation guidance
   - Emphasize extracting from `assessment` field
3. **LLM Call**: Single call with summary
   - **Rationale**: Plan generation requires synthesized information, not raw chunks
   - **Dependency**: Requires summary to be generated first
4. **Response Parsing**: Extract JSON, validate against `StructuredPlan` schema

**Output Structure**:
```json
{
  "recommendations": [
    {
      "number": 1,
      "recommendation": "Comprehensive recommendation text...",
      "source": "ASSESSMENT section, chunk_11:4648-5547",
      "confidence": 0.9,
      "hallucination_guard_note": null
    },
    ...
  ]
}
```

**Design Rationale**:
- **Summary-First**: Plans are derived from synthesized summary, not raw chunks
- **Assessment Focus**: Primary source is `assessment` field (contains diagnoses, treatments, follow-ups)
- **Prioritization**: Recommendations ordered by urgency/importance
- **Confidence Scoring**: Each recommendation includes confidence and hallucination guard

**Key Design Decision**: We generate plan from summary (not chunks) because:
- Summary already synthesizes information across sections
- Plan requires high-level reasoning, not raw extraction
- Reduces LLM calls (summary → plan, not chunks → plan)

---

## Stage 5: Evaluation

**Input**: Summary, Plan, Chunks, Canonical Note  
**Output**: `evaluation.json` (Quality Metrics)

**Metrics Computed**:

1. **Citation Coverage**:
   - Percentage of summary/plan items with valid citations
   - Tracks orphan claims (no source)

2. **Citation Validity**:
   - Section name validation (cited section matches chunk section_title)
   - Span validation (character spans within chunk bounds)
   - Tracks mismatches and out-of-bounds citations

3. **Hallucination Rate**:
   - Percentage of items with confidence < 0.8
   - Tracks low-confidence recommendations

4. **Span Consistency**:
   - Overlap between citations for similar facts
   - Jaccard similarity for citation overlap

5. **Semantic Accuracy** (Plan only):
   - Cosine similarity between recommendation text and cited source text
   - Uses Ollama embeddings (`nomic-embed-text`)
   - Validates recommendations are supported by source

6. **Summary Statistics**:
   - Counts per section
   - Confidence score distribution (mean, median, min, max)

**Design Rationale**:
- **Comprehensive Metrics**: Covers multiple quality dimensions
- **Automated Validation**: Catches common errors (invalid citations, hallucinations)
- **Semantic Validation**: Embeddings verify recommendation-source alignment
- **Actionable Feedback**: Metrics guide prompt refinement and system improvement

---

## Output Files

**Per-Document Outputs** (in `results/{note_id}/`):

1. **`canonical_text.txt`**: Full document text (normalized)
2. **`toc.json`**: Table of contents (sections with offsets)
3. **`chunks.json`**: Chunks ready for LLM processing
4. **`summary.json`**: Structured summary (7 sections, with citations)
5. **`plan.json`**: Prioritized treatment plan (with citations)
6. **`evaluation.json`**: Quality metrics and statistics
7. **`pipeline.log`**: Detailed execution log

**Text Outputs** (for human readability):
- Summary and plan can be formatted as text (via `format_structured_summary_as_text()`, `format_plan_as_text()`)

---

## Key Design Principles

### 1. **Traceability First**
- Every extracted fact cites exact character positions
- Citations include section, chunk ID, and character spans
- Enables verification and accountability

### 2. **Deterministic Where Possible**
- Section detection: Regex-based (fast, reliable)
- Chunking: Rule-based (reproducible)
- LLM: Only for content extraction/reasoning (where needed)

### 3. **Single-Pass LLM Processing**
- Summary: All chunks in one call (full context)
- Plan: Summary in one call (synthesized information)
- **Rationale**: More efficient than iterative chunk processing

### 4. **Schema-Driven Outputs**
- Pydantic models ensure type safety and validation
- JSON schemas enable downstream processing
- Consistent structure across documents

### 5. **Graceful Degradation**
- Fallback to single section if detection fails
- Continue with partial results if some chunks fail
- Log warnings but don't fail completely

### 6. **Local Processing**
- All LLM calls via Ollama (local)
- No external API dependencies
- Privacy-preserving (no data leaves local machine)

---

## Pipeline Execution Modes

**Conditional Execution** (via CLI flags):
- `--toc-only`: Stop after ToC generation (no LLM required)
- `--summary-only`: Generate summary, skip plan and evaluation
- `--plan-only`: Generate plan from existing summary
- `--no-evaluation`: Skip evaluation metrics

**Caching**:
- Pipeline checks for existing `chunks.json` and skips ingestion/chunking if found
- Enables re-running summary/plan generation without re-processing document

**Parallel Processing**:
- `process_batch` command processes multiple documents concurrently
- Uses `ThreadPoolExecutor` for parallel execution
- Each document processed independently

---

## Technology Stack

- **PDF Processing**: `pypdf` (lightweight, no external dependencies)
- **LLM Integration**: `langchain-ollama` (Ollama wrapper)
- **Schema Validation**: `pydantic` (type safety, JSON validation)
- **CLI**: `typer` (modern Python CLI framework)
- **Logging**: Python `logging` module (structured, per-document logs)
- **Embeddings**: Ollama API (`nomic-embed-text`) for semantic accuracy

**LLM Model**: `qwen2.5:7b` (default, configurable)
- 7B parameter model
- Good balance of quality and speed
- Runs locally via Ollama

