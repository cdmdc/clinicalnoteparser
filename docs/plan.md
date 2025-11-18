# Clinical Note Parser Implementation Plan

## Plan Overview

This plan implements a minimal, production-ready pipeline for parsing clinical PDF notes into structured JSON outputs using local LLMs via Ollama. The architecture follows a clear separation of concerns with testable modules.

## Implementation Principles

**Code Quality & Best Practices:**

When implementing this plan, adhere to expert software engineering principles:

- **Object-Oriented Design**: 
  - Use classes for cohesive functionality (e.g., `PDFIngester`, `SectionDetector`, `ChunkProcessor`)
  - Encapsulate data and behavior appropriately
  - Prefer composition over inheritance
  - Use dependency injection for testability (e.g., pass LLM client to functions rather than creating it internally)

- **Modularity**:
  - Each module should have a single, well-defined responsibility
  - Minimize coupling between modules; use clear interfaces
  - Functions should be small, focused, and do one thing well
  - Avoid deep nesting; prefer early returns and guard clauses

- **Simplicity**:
  - Write code that is easy to understand at a glance
  - Avoid premature optimization; prefer clear, straightforward implementations
  - Use Python's built-in features and standard library when appropriate
  - Don't over-abstract; keep abstractions at the right level

- **Readability**:
  - Use descriptive variable and function names (e.g., `extract_sections_from_text()` not `process()`)
  - Add docstrings to all public functions and classes (Google or NumPy style)
  - Use type hints for function parameters and return values
  - Write self-documenting code; comments should explain "why", not "what"

- **Documentation**:
  - Module-level docstrings explaining purpose and usage
  - Function docstrings with Args, Returns, Raises sections
  - Inline comments for complex logic or non-obvious decisions
  - Document design decisions and trade-offs in code comments where relevant

- **Error Handling**:
  - Use specific exception types (e.g., `FileNotFoundError`, `ValueError`)
  - Provide clear, actionable error messages
  - Fail fast with helpful diagnostics
  - Use context managers for resource management (files, connections)

- **Testing**:
  - Write testable code (pure functions where possible, dependency injection)
  - Test edge cases and error conditions
  - Use descriptive test names that explain what is being tested
  - Mock external dependencies (LLM calls, file I/O) for unit tests

- **Code Organization**:
  - Group related functions and classes logically
  - Use private methods/attributes (leading underscore) for internal implementation
  - Keep imports organized (stdlib, third-party, local)
  - Follow PEP 8 style guidelines (use `black` for formatting)

## Architecture Evaluation

**Strengths of Proposed Design:**
- ✅ Single canonical text representation simplifies downstream processing
- ✅ Clear module boundaries enable testing and maintenance
- ✅ Citation tracking with character offsets and page numbers
- ✅ Local-first approach (Ollama) ensures privacy and offline capability
- ✅ Minimal dependencies reduce complexity

**Improvements & Considerations:**
- ✅ Error handling and retry logic for LLM calls (with failure rate thresholds)
- ✅ Structured output parsing with fallbacks
- ✅ Configuration management with validation
- ✅ Citation span validation before conversion
- ✅ Progress tracking with CLI indicators
- ✅ PDF formatting detection using pypdf font analysis
- ✅ Robust section detection with multiple fallback strategies
- ✅ Edge case handling for chunking and deduplication

## Output Structure

All outputs saved to `results/{note_id}/` per document:
- **Intermediate**: `canonical_text.txt`, `chunks.json`
- **Final**: `toc.json`, `summary.json`, `plan.json`
- **Evaluation**: `evaluation.json`
- **Logs**: `pipeline.log` (comprehensive logging of all steps, including LLM call inputs/outputs)

## Implementation Steps

### 1. Project Setup & Core Infrastructure

**Environment Setup:**
- **Important**: All commands should be run from the project directory (`clinicalnoteparser`)
- Activate the virtual environment before building or running: `source .venv/bin/activate`
- This ensures all dependencies and Python paths are correctly configured

**Environment & Dependencies:**
- Install packages inside the environment using `uv add <package>`:
  - Production: `uv add langchain-community pypdf pydantic typer python-dotenv`
  - Development: `uv add --dev pytest pytest-cov black mypy ruff`
- Generate requirements.txt file: `uv export -o requirements.txt --format requirements-txt`
- Create configuration system with environment variable support
- Validate configuration on startup (chunk_size > chunk_overlap, temperature in [0, 2], etc.)

**Project Structure:**
```
src/
  app/
    __init__.py
    ingestion.py      # PDF → CanonicalNote
    sections.py       # Section detection → ToC
    chunks.py         # Chunking strategy
    summarizer.py     # Fact extraction with citations
    planner.py        # Plan generation
    schemas.py        # Pydantic models
    llm.py            # Ollama wrapper + prompts
    evaluation.py     # Quality checks
    cli.py            # CLI entrypoint
    config.py         # Configuration management
    pipeline.py       # Main orchestration
prompts/
  README.md              # Prompt reasoning and design notes
  section_inference.md
  summary_extraction.md
  plan_generation.md
tests/
  test_ingestion.py
  test_sections.py
  test_citations.py
  test_no_evidence.py
```

**Data Models (`app/schemas.py`):**
- `CanonicalNote`: text + page_spans mapping
- `Section`, `Chunk`, `SpanFact`, `ChunkExtraction`
- `Summary`, `PlanCitation`, `Recommendation`, `ProblemPlan`, `Plan`
- All with Pydantic validation

**Configuration (`app/config.py`):**
- Model name (default: "llama3"), temperature (default: 0.1, validated in [0, 2])
- Chunk size (default: 1500 chars), chunk overlap (default: 200 chars, validated: chunk_size > chunk_overlap)
- Max retries for LLM calls (default: 3), output directory
- Section detection: min_sections_for_success (default: 2), enable_llm_fallback (default: True)
- Chunking: max_paragraph_size (default: 3000 chars)
- Error handling: max_chunk_failure_rate (default: 0.3 = 30%)
- Large PDF threshold: max_pages_warning (default: 30 pages)
- Load from environment variables with sensible defaults
- Validate all configuration values on startup

**Note ID Generation:**
- Generate `note_id` from PDF filename: use `Path(pdf_path).stem` (filename without extension)
- If filename is not suitable, use hash of first 1000 chars of PDF content as fallback
- Ensure note_id is filesystem-safe (replace invalid chars with underscores)

### 2. PDF Processing & Section Detection

**PDF Ingestion (`app/ingestion.py`):**
- **File Format Support**: Accept both PDF and .txt files
  - If input is `.txt`: Read directly, treat as single "page" (page_index: 0)
  - If input is `.pdf`: Use `pypdf` directly (not just langchain wrapper) to access font information for bold detection
  - Auto-detect file type from extension
- **PDF Processing**:
  - Validate PDF has extractable text; return clear error if empty/malformed
  - **Large PDF Handling**: If PDF has >30 pages (configurable via max_pages_warning):
    - Alert user via console warning: "Warning: PDF has {N} pages. Processing may take longer."
    - Log warning to pipeline.log with page count
    - Continue processing (no abort, just informational)
- **Text Processing** (both PDF and .txt):
  - Handle encoding errors gracefully: try UTF-8, fallback to latin-1, log warnings
  - Normalize text (non-breaking spaces, line endings)
  - Build `page_spans` array mapping character positions to pages
    - For PDFs: one span per page
    - For .txt: single span covering entire document (page_index: 0)
- Utility: `char_span_to_page()` for citation mapping
- Save canonical text to `results/{note_id}/canonical_text.txt`
- Insert newline between pages (PDF only), track exact character offsets
- Check Ollama availability before starting pipeline (fail fast with helpful message)

**Section Detection (`app/sections.py`):**
- **Overview Section**: Use flexible regex patterns to find 'Medical Specialty', 'Sample Name', and 'Description' fields (optional matching, any order)
  - Extract text from start of document until first major section header
  - If fields missing, use text before first section header as Overview
- **Primary Method**: 
  - **For PDFs**: Use `pypdf` to extract text with font information, detect bold text
    - Identify bolded all-caps words at the start of a line (e.g., "HISTORY", "PAST MEDICAL HISTORY", etc.)
  - **For .txt files**: Use pattern matching (no font information available)
    - Identify all-caps words at the start of a line (e.g., "HISTORY", "PAST MEDICAL HISTORY", etc.)
  - **Common to both**: Check for common clinical section patterns (case-insensitive): History, Physical Examination, Medications, Allergies, etc.
- Sort candidates by position, create non-overlapping sections
- **LLM Fallback Trigger**: Use LLM-based section detection if:
  - Regex finds < min_sections_for_success (default: 2) sections after Overview, OR
  - No section headers found after Overview, OR
  - User explicitly enables via config
- **Final Fallback**: Single "Full Note" section if both regex and LLM fail
- Generate ToC with page numbers, save to `results/{note_id}/toc.json`
- **Output Validation**: Validate ToC JSON structure using Pydantic models before saving
- Ensure all required fields are present and types are correct

**Chunking (`app/chunks.py`):**
- Extract text slices per section
- Split into paragraphs (preserve paragraph boundaries)
- **Edge Case Handling**: If a single paragraph exceeds max_paragraph_size (default: 3000 chars), split at sentence boundaries
- Merge paragraphs into ~1500 char chunks with 200 char overlap
- Maintain global character offsets, assign unique chunk_ids
- Track section_title for context in prompts
- Save chunks metadata to `results/{note_id}/chunks.json`
- **Output Validation**: Validate chunks JSON structure using Pydantic models before saving
- **Note**: Process chunks sequentially for now (parallelization can be added later if needed)

### 3. LLM Integration & Summarization

**LLM Wrapper (`app/llm.py`):**
- Initialize `ChatOllama` with configurable model (default: "llama3")
- Check Ollama availability and model existence before first call (fail fast)
- Implement retry logic with exponential backoff (max_retries from config)
- Parse JSON responses with error handling and fallbacks
  - Try structured JSON parsing first
  - Fallback to text extraction if JSON parsing fails
  - Log parsing errors for debugging
- Load prompts from `prompts/` directory
- Return structured responses with error information
- **Logging Integration**: Accept logger parameter, log all LLM calls:
  - Log before call: model name, prompt summary, parameters
  - Log after call: response summary, processing time, success/failure
  - Log retries with attempt numbers
  - Log full inputs/outputs at DEBUG level (or to separate detailed log if needed)

**Prompt Templates:**
- `section_inference.md`: Optional LLM-based section detection
- `summary_extraction.md`: Extract structured facts from chunks
- `plan_generation.md`: Generate problem-oriented recommendations
- **Prompt Hardening Requirements** (all prompts must include):
  - **PHI Protection**: "Do not add, infer, or fabricate any Protected Health Information (PHI). Only extract information explicitly present in the source text. Do not infer patient names, dates of birth, addresses, or other identifiers."
  - **Anti-Fabrication**: "Do not invent facts, diagnoses, or recommendations. Only extract information that is clearly stated in the provided text."
  - **Citation Requirements**: "Every fact or recommendation must be tied to specific source text spans. If you cannot find evidence for a claim, do not include it."
  - **Uncertainty Handling**: "If evidence is weak or ambiguous, use low confidence scores and include a note explaining the uncertainty."
- All prompts emphasize citation requirements and evidence grounding
- **Prompt Reasoning Documentation**: Create `prompts/README.md` explaining:
  - Design decisions for each prompt
  - Why certain instructions are included
  - How prompts work together in the pipeline
  - Examples of effective vs. ineffective prompt patterns

**Chunk-Level Extraction (`app/summarizer.py`):**
- For each chunk, call LLM with summary extraction prompt
- Parse `ChunkExtraction` response (JSON schema)
- **Citation Span Validation**: Validate all spans before conversion:
  - Check: `0 <= start_char_local < end_char_local <= len(chunk.text)`
  - Skip invalid spans with warning log
- Convert local spans to global spans using chunk offsets
- Add page numbers using `char_span_to_page()`
- **Error Handling Strategy**:
  - Track failed chunks (parsing errors, validation failures)
  - If < max_chunk_failure_rate (default: 30%) fail: continue with partial results, flag in evaluation
  - If >= max_chunk_failure_rate fail: abort with clear error message
  - Log all failures for debugging

**Aggregation & Deduplication:**
- Collect facts across all chunks
- **Deduplication Algorithm**:
  - Normalize text: lowercase, strip punctuation, collapse whitespace
  - Check span overlaps: if two facts have >80% character span overlap, merge them
  - Use simple text similarity: if normalized texts are >90% similar (simple character-based comparison), merge
  - Keep the fact with more citations when merging
  - **Threshold Justification**: >80% span overlap and >90% text similarity thresholds are tuned for clinical notes where slight variations (e.g., "patient has diabetes" vs "patient has diabetes mellitus") should be merged. These thresholds may need adjustment based on actual data characteristics.
- Group by category: problems, history, medications, allergies, etc.
- **Patient Snapshot Generation**:
  - Primary: Final LLM call on aggregated facts
  - Fallback: If LLM fails, extract from structured facts using regex patterns (age, sex patterns)
  - Final fallback: Mark as "Unable to extract" rather than failing
- Save to `results/{note_id}/summary.json` with all facts and citations
- **Output Validation**: Validate summary JSON structure using Pydantic `Summary` model before saving
- Ensure all required fields are present, citations are valid, and types are correct

### 4. Plan Generation & Evaluation

**Plan Generation (`app/planner.py`):**
- For each problem in summary, gather relevant facts
- **Citation Linking Strategy**: 
  - Assign unique fact IDs to all facts in the prompt using format: `fact_001`, `fact_002`, `fact_003`, etc. (zero-padded, sequential)
  - Include fact IDs in the prompt alongside fact text
  - Have LLM reference fact IDs when generating recommendations
  - Match LLM-selected fact IDs back to source facts
  - Alternative: Use text matching with fuzzy similarity if fact IDs not provided or LLM doesn't use them
- Call LLM with plan generation prompt (include fact IDs)
- Parse `ProblemPlan` response, link recommendations to source facts by ID or text matching
- Copy citation spans from matched source facts
- Generate global_followup recommendations
- Save to `results/{note_id}/plan.json` with all recommendations and citations
- **Output Validation**: Validate plan JSON structure using Pydantic `Plan` model before saving
- Ensure all required fields are present, citations are valid, confidence scores are in [0, 1], and types are correct
- **Constraint**: No evidence → no recommendation (empty list or low confidence with hallucination_note)

**Evaluation (`app/evaluation.py`):**
- **Citation Coverage**: 
  - Calculate % of facts in summary with at least one citation
  - Calculate % of plan recommendations with at least one citation
  - Report overall citation coverage percentage
- **Citation Validity**: 
  - Verify all citation spans are within [0, len(note.text)]
  - Check that start_char < end_char for all citations
  - Count and report invalid citations
- **Orphan Claims (Hallucination Rate)**:
  - Count facts in summary with empty citations list
  - Count plan recommendations with empty citations list
  - Calculate hallucination rate: (orphan claims / total claims) × 100
- **Citation Overlap Jaccard**:
  - For facts with multiple citations, calculate Jaccard similarity between citation spans
  - Measure how well citations align across similar facts
  - Report average Jaccard score
- **Span Consistency**: 
  - Verify text slices match expected content: for each citation, extract note.text[start:end] and verify it's not empty
  - Check that extracted text matches the fact text (fuzzy match allowed)
- **Summary Statistics**:
  - Total facts extracted
  - Total recommendations generated
  - Average citations per fact/recommendation
  - Distribution of confidence scores
- Save comprehensive evaluation report to `results/{note_id}/evaluation.json` with all metrics

### 5. CLI & Pipeline Integration

**Main Pipeline (`app/pipeline.py`):**
- **Pre-flight Checks**: 
  - Verify Ollama is running and model is available
  - Validate configuration values
  - Check input file exists and is readable (supports both PDF and .txt)
  - Detect file type from extension (.pdf or .txt)
- Orchestrate all steps: ingestion → sections → chunks → summarization → planning → evaluation
- Create output directory structure: `results/{note_id}/`
- **Comprehensive Logging**: Set up file logger to `results/{note_id}/pipeline.log`
  - Use Python `logging` module with clear formatting
  - Include timestamps, log levels, and module names
  - Log all major steps with clear labels:
    - `[STEP 1/6] PDF Ingestion`
    - `[STEP 2/6] Section Detection`
    - `[STEP 3/6] Chunking`
    - `[STEP 4/6] Fact Extraction`
    - `[STEP 5/6] Plan Generation`
    - `[STEP 6/6] Evaluation`
  - **LLM Call Logging**: For every LLM call, log:
    - Input prompt (full text or summary if very long)
    - Model name and parameters (temperature, etc.)
    - Response (full JSON or summary if very long)
    - Processing time
    - Any errors or retries
  - Log configuration values at startup
  - Log intermediate results (section counts, chunk counts, fact counts)
  - Log validation results and warnings
  - Log errors with full stack traces
- **Progress Tracking**: Also log major steps at INFO level for console output
- Pass data between modules
- Handle errors and logging (INFO for major steps, DEBUG for details)
- **Output Validation**: Validate all JSON outputs using Pydantic models before saving:
  - `toc.json` → Validate against ToC schema
  - `summary.json` → Validate against `Summary` model
  - `plan.json` → Validate against `Plan` model
  - `chunks.json` → Validate against chunks schema
  - `evaluation.json` → Validate against evaluation schema
- Save all intermediate and final outputs only after successful validation

**CLI (`app/cli.py`):**
- Use Typer for CLI interface
- Command: `process <input_path> [--output-dir] [--model] [--verbose]`
  - `input_path`: Path to PDF or .txt file
  - `--output-dir`: Output directory (default: `results/`)
  - `--model`: Ollama model name (default: `llama3`)
  - `--verbose`: Enable DEBUG logging
- **Progress Indicators**: Print simple progress to stdout:
  - `[1/6] Loading document...` (PDF or .txt)
  - `[2/6] Detecting sections...` (with section count)
  - `[3/6] Chunking text...` (with chunk count)
  - `[4/6] Extracting facts...` (with progress: chunk X/Y)
  - `[5/6] Generating plan...`
  - `[6/6] Evaluating results...`
- Run full pipeline, create per-document output folder
- Print evaluation metrics summary at end (citation coverage, hallucination rate, etc.)
- Handle errors gracefully with informative messages
- Use verbose flag to control logging level (INFO vs DEBUG)

### 6. Testing & Documentation

**Logging Setup:**
- Configure Python `logging` module in `app/pipeline.py`
- Create file handler for `results/{note_id}/pipeline.log`
- Use structured log format: `[TIMESTAMP] [LEVEL] [MODULE] MESSAGE`
- Log levels: DEBUG (detailed), INFO (major steps), WARNING (issues), ERROR (failures)
- **LLM Call Logging**: Create helper function to log LLM interactions:
  - Log prompt template name and variables
  - Log full prompt text (or truncate if > 5000 chars, show first/last 1000)
  - Log model response (or truncate if > 5000 chars)
  - Log processing time and token counts if available
  - Log retry attempts and final status
- Ensure logs are flushed after each major step
- Handle log file creation errors gracefully

**Testing:**
- `test_ingestion.py`: Synthetic PDF with known page structure
- `test_sections.py`: Text with clear section headings
- `test_citations.py`: Known phrases and positions
- `test_no_evidence.py`: Edge case handling
- Mock LLM responses for deterministic testing
- Integration test with sample PDF from data/archive
- Test logging: Verify logs are created and contain expected information

**Documentation:**
- **README.md** (comprehensive setup and usage guide):
  - **Project Overview**: Brief description of the clinical note parser
  - **Setup Instructions**:
    - Prerequisites (Python 3.9+, uv, Ollama)
    - Installation steps: `uv add` commands for dependencies
    - Environment setup: `source .venv/bin/activate`
    - Verify Ollama installation and model availability
  - **Data Download Instructions**:
    - MTSamples dataset: Link to Kaggle, download instructions
    - Expected data structure: `data/archive/mtsamples_pdf/`
    - How to prepare sample PDFs for testing
  - **How to Run**:
    - Basic usage: `python -m app.cli process <input_path>`
    - Examples with PDF: `python -m app.cli process data/archive/mtsamples_pdf/mtsamples_pdf/570.pdf`
    - Examples with .txt: `python -m app.cli process note.txt`
    - CLI options and flags explained
  - **Output Structure**: 
    - Per-document folder structure in `results/{note_id}/`
    - Description of each output file (toc.json, summary.json, plan.json, etc.)
    - Example outputs with sample structure
  - **Configuration**: 
    - Environment variables
    - Configuration options and defaults
    - How to customize model, chunk size, etc.
  - **Troubleshooting**: Common issues and solutions
  - **PHI Protection**: Document that the system does not add or infer PHI, only extracts what's explicitly in source text
- **Prompt Documentation**:
  - Create `prompts/README.md` with prompt reasoning notes (see Phase 3)
  - Document prompt engineering approach and design decisions
  - Explain PHI protection measures in prompts
- **Logging Documentation**: 
  - Explain log file format, what's logged, and how to use logs for debugging
  - Log file location and structure
- Add comprehensive error handling and logging throughout

## Technical Decisions

**Why This Approach:**
1. **Single Canonical Text**: Simplifies all downstream processing; PDF complexity handled once
2. **Dual Format Support**: PDF and .txt support ensures flexibility; .txt is simpler for testing and debugging
3. **pypdf Font Analysis**: Direct access to font information enables reliable bold text detection for section headers (PDFs)
4. **Multi-Tier Section Detection**: pypdf bold detection → pattern matching → LLM fallback → single section ensures robustness
5. **Chunk-Level Processing**: Fits LLM context limits; sequential processing for now (parallelization can be added later)
6. **Local Spans → Global**: More reliable than asking LLM for global positions; validation ensures correctness
7. **Pydantic Schemas**: Type safety, validation, JSON serialization
8. **Ollama + LangChain**: Standard interface, local execution, easy model switching
9. **Fail-Fast Pre-flight Checks**: Verify Ollama/model availability before processing saves time
10. **Configurable Error Thresholds**: Allows graceful degradation with partial results
11. **Comprehensive Logging**: Per-document log files enable debugging, audit trails, and prompt engineering iteration
12. **PHI Protection**: Explicit prompt instructions prevent adding or inferring PHI, ensuring safety

**Trade-offs:**
- pypdf font analysis may not work for all PDF formats (mitigated by pattern matching and LLM fallback)
- .txt files lack font information, so section detection relies on pattern matching only (mitigated by LLM fallback)
- Sequential chunk processing is slower but simpler (can parallelize later if needed)
- Local LLMs may be slower than cloud APIs (acceptable for privacy/offline needs)
- Simple text similarity for deduplication (sufficient for most cases, avoids heavy dependencies)

## Success Criteria

- ✅ Processes PDFs and .txt files from `data/archive/mtsamples_pdf` successfully
- ✅ Generates valid JSON outputs with proper structure
- ✅ All facts and recommendations have citations
- ✅ Citations map correctly to source text
- ✅ Handles edge cases (empty sections, no evidence, parsing errors)
- ✅ Test coverage >80% for core modules
- ✅ CLI is intuitive and provides helpful feedback
- ✅ All outputs saved to per-document folders in `results/`

## Future Extensions (Out of Scope)

- OCR for scanned PDFs
- HTML viewer with citation highlighting
- Multi-note RAG for cohort analysis
- Web interface
- Database storage

