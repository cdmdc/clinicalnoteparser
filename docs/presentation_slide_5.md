# Slide 5: Models & Tools

## Overview

Our system uses a **minimal, local-first technology stack** optimized for privacy, simplicity, and offline operation. All AI models run locally via Ollama, with no external API dependencies.

---

## LLM Models

### Primary LLM: `qwen2.5:7b` (Default)

**Model Details**:
- **Name**: Qwen2.5 7B
- **Parameters**: 7 billion
- **Provider**: Ollama (local execution)
- **Use Cases**: 
  - Summary generation (structured extraction)
  - Plan generation (treatment recommendations)
  - JSON-structured output parsing

**Why This Model**:
1. **Quality vs. Speed Balance**: 7B parameters provide good quality for structured extraction tasks while remaining fast enough for local execution
2. **Context Window**: Sufficient context window (typically 8K-32K tokens) for processing full clinical notes
3. **JSON Output**: Good at following structured output formats (JSON schemas)
4. **Local Execution**: Runs entirely on local machine via Ollama (privacy, no API costs)
5. **Open Source**: Fully open-source, no vendor lock-in

**Configuration**:
- **Temperature**: 0.1 (default) - Low temperature for deterministic, structured outputs
- **Configurable**: Can be changed via `CLINICAL_NOTE_MODEL` environment variable
- **GPU Acceleration**: Automatically uses GPU/MPS (Apple Silicon) if available via Ollama

**Alternative Models**:
- Any Ollama-compatible model can be used
- Tested with: `llama3`, `mistral`, `qwen2.5:14b` (larger, slower)
- Model selection depends on quality requirements vs. speed constraints

---

## Embedding Models

### Embedding Model: `nomic-embed-text` (Optional)

**Model Details**:
- **Name**: Nomic Embed Text
- **Provider**: Ollama (local execution)
- **Use Case**: Semantic accuracy evaluation (plan recommendations)
- **Embedding Dimension**: 768 dimensions (typical)

**Why This Model**:
1. **Lightweight**: Fast embedding generation for evaluation tasks
2. **Local Execution**: No external API calls (privacy-preserving)
3. **Medical Text**: Works reasonably well for medical/clinical text
4. **Ollama Integration**: Seamless integration with existing Ollama setup

**Usage**:
- **Purpose**: Compute cosine similarity between plan recommendations and cited source text
- **When Used**: Only during evaluation phase (semantic accuracy metrics)
- **Optional**: Pipeline works without embeddings (evaluation just skips semantic accuracy)

**Implementation**:
- Direct HTTP calls to Ollama embeddings API (`/api/embeddings`)
- No vector store needed (embeddings computed on-demand)
- Cosine similarity computed using `numpy`

**Alternative Embedding Models**:
- Any Ollama-compatible embedding model can be used
- Configurable via `embedding_model` parameter in evaluation functions
- Other options: `all-minilm`, `mxbai-embed-large` (if available in Ollama)

---

## Vector Store

### No Vector Store Used

**Design Decision**: We do **not** use a vector store (e.g., Chroma, Pinecone, FAISS).

**Why No Vector Store**:
1. **Full-Context Processing**: We process all chunks in a single LLM call, not selective retrieval
2. **No Retrieval Needed**: No similarity search required (we don't retrieve top-K chunks)
3. **Small Document Size**: Clinical notes are small enough to fit in LLM context window
4. **Simplicity**: Fewer dependencies, simpler architecture
5. **Deterministic**: Same document always processes same chunks (no retrieval variability)

**When We Would Use Vector Store**:
- If documents were too large for single LLM call
- If we needed selective retrieval (RAG-style)
- If we needed to search across multiple documents
- If we needed persistent document indexing

**Current Approach**:
- All chunks processed directly in LLM prompt
- Embeddings only used for evaluation (semantic similarity), not retrieval
- No persistent storage of embeddings or vectors

---

## Core Libraries

### 1. LangChain (`langchain-ollama`, `langchain-community`, `langchain-core`)

**Purpose**: LLM integration and abstraction

**Why LangChain**:
- **Ollama Integration**: Provides `ChatOllama` wrapper for Ollama models
- **Message Formatting**: Handles `SystemMessage` and `HumanMessage` formatting
- **Abstraction**: Clean interface for LLM calls (model-agnostic)
- **Mature Library**: Well-tested, widely used

**Usage**:
- `ChatOllama`: Main LLM client wrapper
- `HumanMessage`, `SystemMessage`: Message formatting
- Fallback to `langchain-community` for backward compatibility

**Alternatives Considered**:
- Direct Ollama API calls (more control, but more code)
- OpenAI SDK (requires external API, not local)
- **Chosen**: LangChain for simplicity and Ollama support

---

### 2. PyPDF (`pypdf`)

**Purpose**: PDF text extraction

**Why PyPDF**:
- **Lightweight**: No external dependencies (pure Python)
- **Simple API**: Easy to use for basic text extraction
- **Font Information**: Can extract font information (for bold text detection)
- **No OCR**: Text-based PDFs only (sufficient for our use case)

**Usage**:
- Extract text from PDF pages
- Extract font information (for section header detection)
- Page-by-page processing with character offset tracking

**Limitations**:
- No OCR support (scanned PDFs not supported)
- Limited layout analysis (but sufficient for our needs)

**Alternatives Considered**:
- `pdfplumber` (more features, but heavier)
- `PyMuPDF` (faster, but more complex)
- **Chosen**: PyPDF for simplicity and no external dependencies

---

### 3. Pydantic (`pydantic`)

**Purpose**: Schema validation and data modeling

**Why Pydantic**:
- **Type Safety**: Runtime type validation for all data structures
- **JSON Schema**: Automatic JSON schema generation
- **Validation**: Catches errors early (invalid citations, missing fields)
- **Documentation**: Self-documenting models with field descriptions
- **Modern Python**: Uses Python 3.11+ features (type hints, dataclasses)

**Usage**:
- Define all data models (`CanonicalNote`, `Section`, `Chunk`, `StructuredSummary`, `StructuredPlan`)
- Validate LLM outputs against schemas
- Serialize/deserialize JSON with validation

**Benefits**:
- Prevents invalid data from propagating through pipeline
- Clear error messages when LLM outputs don't match schema
- Type hints enable better IDE support and static analysis

**Alternatives Considered**:
- `dataclasses` (no validation)
- `marshmallow` (older, more verbose)
- **Chosen**: Pydantic for modern Python features and validation

---

### 4. Typer (`typer`)

**Purpose**: Command-line interface (CLI)

**Why Typer**:
- **Modern**: Built on Python type hints (no decorator magic)
- **Clean API**: Simple, intuitive interface
- **Auto-Documentation**: Automatic help text generation
- **Type Validation**: CLI argument type checking

**Usage**:
- `process`: Single document processing
- `process_batch`: Batch processing with parallel execution
- `eval_summary`: Evaluation summary generation
- All commands with proper argument parsing and help text

**Benefits**:
- Professional CLI with automatic help and validation
- Easy to extend with new commands
- Better than `argparse` (less boilerplate)

**Alternatives Considered**:
- `argparse` (standard library, but verbose)
- `click` (popular, but decorator-based)
- **Chosen**: Typer for modern Python and type hints

---

### 5. Requests (`requests`)

**Purpose**: HTTP client for Ollama embeddings API

**Why Requests**:
- **Simple**: Straightforward HTTP client
- **Standard Library Alternative**: Could use `urllib`, but `requests` is more readable
- **Error Handling**: Better error handling than `urllib`

**Usage**:
- Direct HTTP calls to Ollama embeddings API (`/api/embeddings`)
- Only used for semantic accuracy evaluation (not core pipeline)

**Note**: Could be replaced with `httpx` (async) if needed, but `requests` is sufficient for our use case.

---

### 6. NumPy (`numpy`)

**Purpose**: Numerical computations for semantic accuracy

**Why NumPy**:
- **Efficient**: Fast array operations for cosine similarity
- **Standard**: Widely used, well-tested
- **Lightweight**: Small dependency for vector operations

**Usage**:
- Convert embeddings to numpy arrays
- Compute cosine similarity: `np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))`
- Only used in evaluation phase

**Alternatives Considered**:
- Manual cosine similarity (more code, less efficient)
- `scipy` (overkill for simple cosine similarity)
- **Chosen**: NumPy for efficiency and simplicity

---

### 7. Matplotlib (`matplotlib`)

**Purpose**: Visualization for evaluation summaries

**Why Matplotlib**:
- **Standard**: Most common Python plotting library
- **Flexible**: Can create various plot types (bar charts, histograms, box plots)
- **File Output**: Easy to save plots as PNG files

**Usage**:
- Generate evaluation summary plots (bar charts, histograms, box plots)
- Multi-panel overview plots
- Saved to `results/eval_summary/plots/` directory

**When Used**: Only for `eval_summary` command (aggregate evaluation visualization)

---

### 8. Python-dotenv (`python-dotenv`)

**Purpose**: Environment variable management

**Why Python-dotenv**:
- **Configuration**: Load configuration from `.env` files
- **Flexibility**: Easy to override defaults without code changes
- **Standard**: Common pattern for Python applications

**Usage**:
- Load `CLINICAL_NOTE_MODEL`, `CLINICAL_NOTE_TEMPERATURE`, etc. from `.env`
- Fallback to defaults if not set
- Enables easy configuration without modifying code

---

### 9. Pytest (`pytest`, `pytest-cov`, `pytest-mock`)

**Purpose**: Testing framework

**Why Pytest**:
- **Modern**: Better than `unittest` (less boilerplate)
- **Fixtures**: Powerful fixture system for test setup
- **Plugins**: Coverage (`pytest-cov`) and mocking (`pytest-mock`) support
- **Standard**: Most common Python testing framework

**Usage**:
- Unit tests for each module
- Integration tests for pipeline
- Coverage reporting
- Real LLM tests (not mocked, uses actual Ollama)

---

## Technology Stack Summary

### Core Dependencies

| Library | Purpose | Why Chosen |
|---------|---------|------------|
| `langchain-ollama` | LLM integration | Ollama wrapper, clean API |
| `pypdf` | PDF processing | Lightweight, no external deps |
| `pydantic` | Schema validation | Type safety, validation |
| `typer` | CLI framework | Modern, type-hint based |
| `requests` | HTTP client | Ollama embeddings API |
| `numpy` | Numerical ops | Cosine similarity |
| `matplotlib` | Plotting | Evaluation visualization |
| `python-dotenv` | Config management | Environment variables |
| `pytest` | Testing | Modern testing framework |

### Runtime Requirements

- **Python 3.11+**: Modern type hints, performance improvements
- **Ollama**: Local LLM runtime (external dependency)
- **uv**: Package manager (optional, can use pip)

---

## Design Philosophy: Minimal Dependencies

### Why We Chose This Stack

1. **Local-First**: All AI models run locally (Ollama), no external APIs
2. **Privacy**: No data leaves local machine
3. **Simplicity**: Minimal dependencies, easy to understand and maintain
4. **No Vendor Lock-in**: Open-source models and libraries
5. **Offline Operation**: Works without internet (after initial setup)

### What We Avoided

- **Cloud APIs**: No OpenAI, Anthropic, or other cloud LLM APIs
- **Vector Databases**: No Chroma, Pinecone, FAISS (not needed for our approach)
- **Heavy ML Frameworks**: No PyTorch, TensorFlow (Ollama handles model execution)
- **Complex Dependencies**: Prefer simple, focused libraries

### Trade-offs

**Benefits**:
- Privacy-preserving (all processing local)
- No API costs
- Works offline
- Simple architecture

**Limitations**:
- Requires local GPU/CPU resources
- Model quality limited by local model size
- Setup requires Ollama installation
- Slower than cloud APIs (but acceptable for our use case)

---

## Model Configuration

### Default Configuration

```python
model_name: "qwen2.5:7b"          # Main LLM
temperature: 0.1                   # Low for deterministic outputs
embedding_model: "nomic-embed-text" # For semantic accuracy
ollama_base_url: "http://127.0.0.1:11434"  # Local Ollama
```

### Environment Variables

All configuration can be overridden via environment variables:
- `CLINICAL_NOTE_MODEL`: LLM model name
- `CLINICAL_NOTE_TEMPERATURE`: LLM temperature
- `OLLAMA_BASE_URL`: Ollama API URL (if not local)
- `CLINICAL_NOTE_CHUNK_SIZE`: Chunk size
- `CLINICAL_NOTE_CHUNK_OVERLAP`: Chunk overlap
- And more...

### Model Selection Guidelines

**For Better Quality** (slower):
- Use larger models: `qwen2.5:14b`, `llama3:70b`
- Trade-off: Slower inference, more memory required

**For Faster Processing** (lower quality):
- Use smaller models: `qwen2.5:1.5b`, `tinyllama`
- Trade-off: May have lower quality structured outputs

**For Our Use Case**:
- `qwen2.5:7b` provides good balance
- Fast enough for local execution
- Good quality for structured extraction
- Fits in reasonable memory footprint

---

## Summary: Technology Choices

**Core Principle**: **Minimal, local-first, privacy-preserving**

1. **LLM**: Ollama with `qwen2.5:7b` (local, open-source)
2. **Embeddings**: Ollama with `nomic-embed-text` (local, on-demand)
3. **Vector Store**: None (full-context processing, no retrieval)
4. **Libraries**: Minimal, focused dependencies
   - LangChain for LLM abstraction
   - PyPDF for PDF processing
   - Pydantic for validation
   - Typer for CLI
   - Standard libraries for everything else

**Result**: A simple, maintainable system that processes clinical notes entirely locally with no external dependencies or API costs.

