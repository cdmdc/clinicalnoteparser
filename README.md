# Clinical Note Parser

A pipeline that extracts structured information from clinical notes (PDF or .txt files) and generates a table of contents, summary, and treatment plan recommendations. The system uses local LLMs via Ollama for privacy and offline operation.

## Project Overview

This tool processes unstructured clinical notes and extracts:
- **Table of Contents (TOC)**: Inferred sections with character offsets and page indices
- **Summary**: Patient snapshot, problem list, medications/allergies, history, exam findings, labs/imaging, and assessment
- **Treatment Plan**: Problem-oriented recommendations with rationale, confidence scores, and source citations

All outputs include explicit citations linking back to the source text, enabling traceability and verification.

## Prerequisites

- **Python 3.11+**: Required for modern Python features
- **uv**: Modern Python package manager ([installation guide](https://github.com/astral-sh/uv))
- **Ollama**: Local LLM runtime ([installation guide](https://ollama.ai))
- **Ollama Model**: The default model is `qwen2.5:7b`. Install it with:
  ```bash
  ollama pull qwen2.5:7b
  ```

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <repository-url>
cd clinicalnoteparser
```

### 2. Activate the Virtual Environment

The project uses `uv` for dependency management. Activate the virtual environment:

```bash
source .venv/bin/activate
```

**Note**: Always activate the virtual environment before running any commands. All commands should be run from the project root directory (`clinicalnoteparser`).

### 3. Install Dependencies

Dependencies are already defined in `pyproject.toml`. If you need to reinstall:

```bash
uv sync
```

Or install from `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 4. Verify Ollama Installation

Ensure Ollama is running and the model is available:

```bash
# Check if Ollama is running
ollama list

# If qwen2.5:7b is not listed, install it
ollama pull qwen2.5:7b
```

### 5. Verify Installation

Run the test suite to verify everything is set up correctly:

```bash
PYTHONPATH=src python tests/run_all_tests.py
```

## Data Download Instructions

### MTSamples Dataset

The pipeline is designed to work with clinical notes from the MTSamples dataset:

1. **Download from Kaggle**: 
   - Visit [MTSamples Dataset on Kaggle](https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions)
   - Download the dataset

2. **Expected Data Structure**:
   ```
   data/
   └── archive/
       └── mtsamples_pdf/
           └── mtsamples_pdf/
               ├── 0.pdf
               ├── 1.pdf
               ├── 570.pdf
               └── ...
   ```

3. **Prepare Sample PDFs**:
   - Place PDF files in `data/archive/mtsamples_pdf/mtsamples_pdf/`
   - The CLI can search for files by name in this location automatically

### Using Your Own Files

You can process any PDF or .txt file:
- Place files in any location
- Provide the full path or relative path to the CLI
- The CLI will also search common locations if you provide just a filename

## How to Run

### Basic Usage

The CLI accepts a PDF or .txt filename or path:

```bash
# From project root with virtual environment activated
PYTHONPATH=src python -m app.cli process <input_path>
```

### Examples

#### Process a PDF by filename (searches common locations):

```bash
PYTHONPATH=src python -m app.cli process 570.pdf
```

#### Process a PDF with full path:

```bash
PYTHONPATH=src python -m app.cli process data/archive/mtsamples_pdf/mtsamples_pdf/570.pdf
```

#### Process a .txt file:

```bash
PYTHONPATH=src python -m app.cli process note.txt
```

#### Process with custom output directory:

```bash
PYTHONPATH=src python -m app.cli process 570.pdf --output-dir my_results
```

#### Process with different Ollama model:

```bash
PYTHONPATH=src python -m app.cli process 570.pdf --model llama3.2
```

#### Enable verbose logging:

```bash
PYTHONPATH=src python -m app.cli process 570.pdf --verbose
```

### Conditional Execution Modes

The pipeline supports running only specific parts:

#### Generate only TOC (fast, no LLM needed):

```bash
PYTHONPATH=src python -m app.cli process 570.pdf --toc-only
```

#### Generate only summary:

```bash
PYTHONPATH=src python -m app.cli process 570.pdf --summary-only
```

#### Generate only treatment plan:

```bash
PYTHONPATH=src python -m app.cli process 570.pdf --plan-only
```

#### Generate TOC, summary, and plan (skip evaluation):

```bash
PYTHONPATH=src python -m app.cli process 570.pdf --no-evaluation
```

### Batch Processing (Parallel Execution)

Process multiple documents in parallel for faster throughput:

#### Process multiple files with glob pattern:

```bash
# Process all PDFs in current directory with 4 workers (default)
PYTHONPATH=src python -m app.cli process-batch "*.pdf" --workers 4

# Process all PDFs in a specific directory
PYTHONPATH=src python -m app.cli process-batch "data/archive/mtsamples_pdf/*.pdf" --workers 4
```

#### Process specific files (comma-separated):

```bash
# Process specific files with 2 workers
PYTHONPATH=src python -m app.cli process-batch "0.pdf,1.pdf,2.pdf" --workers 2

# Process with summary-only mode
PYTHONPATH=src python -m app.cli process-batch "0.pdf,1.pdf,2.pdf" --workers 2 --summary-only
```

#### Advanced batch processing:

```bash
# Process with custom model and verbose logging
PYTHONPATH=src python -m app.cli process-batch "*.pdf" --workers 8 --model llama3.2 --verbose

# Process with custom output directory
PYTHONPATH=src python -m app.cli process-batch "*.pdf" --workers 4 --output-dir my_results
```

#### Batch Processing Features:

- **Parallel Execution**: Uses `ThreadPoolExecutor` for efficient I/O-bound LLM calls
- **Progress Tracking**: Real-time progress updates showing `[X/Total] ✓ filename` as tasks complete
- **Error Isolation**: Each document's failure doesn't affect others
- **Summary Report**: Final summary showing succeeded/failed counts with error details
- **Configurable Workers**: Adjust `--workers` based on system capacity (default: 4)
- **All Flags Supported**: Works with all existing flags (`--toc-only`, `--summary-only`, `--plan-only`, `--no-evaluation`, `--verbose`, `--model`)

**Why Threading?** LLM calls are I/O-bound (network requests to Ollama), making threading optimal for parallelization. The default of 4 workers prevents overwhelming Ollama while providing significant speedup.

**Example Output:**
```
Processing 10 file(s) with 4 worker(s)...

[1/10] ✓ 0.pdf
[2/10] ✓ 1.pdf
[3/10] ✓ 2.pdf
[4/10] ✓ 3.pdf
...

======================================================================
Batch processing complete: ✓ 10 succeeded, ✗ 0 failed
======================================================================
```

### CLI Options

#### Single Document Processing (`process` command)

| Option | Short | Description |
|--------|-------|-------------|
| `--output-dir` | `-o` | Output directory (default: `results/`) |
| `--model` | `-m` | Ollama model name (default: `qwen2.5:7b`) |
| `--verbose` | `-v` | Enable DEBUG logging |
| `--toc-only` | | Only generate TOC |
| `--summary-only` | | Only generate summary |
| `--plan-only` | | Only generate treatment plan |
| `--no-evaluation` | | Skip evaluation metrics |

#### Batch Processing (`process-batch` command)

All options from `process` command, plus:

| Option | Short | Description |
|--------|-------|-------------|
| `--workers` | `-w` | Number of parallel workers (default: `4`) |

**Input Pattern**: The first argument can be:
- A glob pattern: `"*.pdf"`, `"data/archive/mtsamples_pdf/*.pdf"`
- Comma-separated filenames: `"0.pdf,1.pdf,2.pdf"` (searches common locations automatically)

## Output Structure

All outputs are saved to per-document folders in the output directory (default: `results/`):

```
results/
└── {note_id}/
    ├── canonical_text.txt      # Normalized text with page mapping
    ├── toc.json                # Table of contents with sections
    ├── chunks.json             # Text chunks for LLM processing
    ├── summary.txt             # Structured summary with citations
    ├── plan.txt                # Treatment plan with recommendations
    ├── evaluation.json         # Evaluation metrics
    └── pipeline.log            # Detailed execution log
```

### Output File Descriptions

#### `canonical_text.txt`
- Normalized text representation of the document
- All text in a single string with consistent formatting
- Used for section detection and chunking

#### `toc.json`
- Table of contents with detected sections
- Each section includes:
  - `title`: Section name (e.g., "Overview", "HISTORY")
  - `start_char`: Starting character position
  - `end_char`: Ending character position
  - `start_page`: Starting page number (0-indexed)
  - `end_page`: Ending page number (0-indexed)

#### `chunks.json`
- Text chunks prepared for LLM processing
- Each chunk includes:
  - `chunk_id`: Unique identifier (e.g., "chunk_0")
  - `section_title`: Section the chunk belongs to
  - `text`: Chunk text content
  - `start_char`: Global starting character position
  - `end_char`: Global ending character position
  - `page_start`: Starting page number
  - `page_end`: Ending page number

#### `summary.txt`
- Structured summary in plain text format
- Sections include:
  - **Patient Snapshot**: Age, sex, brief overview
  - **Key Problems**: List of identified problems
  - **Pertinent History**: Relevant medical history
  - **Medicines/Allergies**: Current medications and allergies
  - **Objective Findings**: Physical exam findings
  - **Labs/Imaging**: Laboratory and imaging results
  - **Concise Assessment**: Diagnosis and treatment plans
- Each item includes source citations with character spans

#### `plan.txt`
- Problem-oriented treatment plan
- Organized by:
  - **Diagnostics**: Recommended diagnostic tests
  - **Therapeutics**: Treatment recommendations
  - **Follow-ups**: Follow-up appointments and monitoring
- Each recommendation includes:
  - Rationale grounded in source text
  - Confidence score (0-1)
  - Source citations with character spans
  - Hallucination guard notes (if evidence is weak)

#### `evaluation.json`
- Evaluation metrics for quality assessment
- Includes:
  - Citation coverage and validity
  - Hallucination rate (orphan claims)
  - Span consistency
  - Confidence score distribution
  - Citation overlap (Jaccard similarity)

#### `pipeline.log`
- Detailed execution log
- Includes:
  - All pipeline steps with timestamps
  - LLM call inputs and outputs
  - Errors and warnings
  - Performance metrics

## Configuration

### Environment Variables

Configuration can be customized via environment variables or a `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `CLINICAL_NOTE_MODEL` | `qwen2.5:7b` | Ollama model name |
| `CLINICAL_NOTE_TEMPERATURE` | `0.1` | LLM temperature (0.0-2.0) |
| `CLINICAL_NOTE_CHUNK_SIZE` | `1500` | Target chunk size in characters |
| `CLINICAL_NOTE_CHUNK_OVERLAP` | `200` | Overlap between chunks |
| `CLINICAL_NOTE_MAX_PARAGRAPH_SIZE` | `3000` | Max paragraph size before splitting |
| `CLINICAL_NOTE_MIN_SECTIONS` | `2` | Minimum sections for successful detection |
| `CLINICAL_NOTE_ENABLE_LLM_FALLBACK` | `true` | Enable LLM fallback for section detection |
| `CLINICAL_NOTE_MAX_RETRIES` | `3` | Max retries for LLM calls |
| `CLINICAL_NOTE_MAX_CHUNK_FAILURE_RATE` | `0.3` | Max chunk processing failure rate (0.0-1.0) |
| `CLINICAL_NOTE_MAX_PAGES_WARNING` | `30` | Page count warning threshold |
| `CLINICAL_NOTE_OUTPUT_DIR` | `results` | Output directory path |

### Example `.env` File

Create a `.env` file in the project root:

```env
CLINICAL_NOTE_MODEL=llama3.2
CLINICAL_NOTE_TEMPERATURE=0.2
CLINICAL_NOTE_CHUNK_SIZE=2000
CLINICAL_NOTE_OUTPUT_DIR=my_results
```

### Configuration Validation

The system validates configuration:
- `chunk_overlap` must be less than `chunk_size`
- `temperature` must be between 0.0 and 2.0
- `max_chunk_failure_rate` must be between 0.0 and 1.0

## Troubleshooting

### Common Issues

#### 1. "Ollama is not available" Error

**Problem**: Ollama is not running or not installed.

**Solution**:
```bash
# Check if Ollama is installed
which ollama

# Start Ollama (if installed but not running)
ollama serve

# Install Ollama from https://ollama.ai
```

#### 2. "Model 'qwen2.5:7b' not found" Error

**Problem**: The specified Ollama model is not installed.

**Solution**:
```bash
# List available models
ollama list

# Install the model
ollama pull qwen2.5:7b

# Or use a different model with --model flag
python -m app.cli process 570.pdf --model llama3.2
```

#### 3. "ModuleNotFoundError: No module named 'app'"

**Problem**: Python path is not set correctly.

**Solution**: Always run commands with `PYTHONPATH=src`:
```bash
PYTHONPATH=src python -m app.cli process 570.pdf
```

Or ensure you're in the project root and the virtual environment is activated.

#### 4. PDF Processing Fails

**Problem**: PDF cannot be read or processed.

**Solution**:
- Verify the PDF is not corrupted
- Check if the PDF is password-protected (not supported)
- Try converting to .txt format and processing that instead
- Check `pipeline.log` for detailed error messages

#### 5. Few Sections Detected

**Problem**: Section detection finds fewer sections than expected.

**Solution**:
- Check `pipeline.log` for section detection details
- The system will automatically use LLM fallback if enabled
- Verify the PDF has clear section headers (bold, all-caps, at start of line)
- For .txt files, ensure section headers are clearly formatted

#### 6. LLM Calls Timeout or Fail

**Problem**: LLM calls are slow or failing.

**Solution**:
- Check if Ollama is running: `ollama list`
- Verify model is installed: `ollama pull qwen2.5:7b`
- Try a smaller model or reduce `chunk_size` in configuration
- Check system resources (CPU, RAM, GPU if using MPS)
- Review `pipeline.log` for specific error messages

#### 7. High Memory Usage

**Problem**: Processing large PDFs uses too much memory.

**Solution**:
- Reduce `chunk_size` in configuration
- Process documents one at a time (use `process` instead of `process-batch`)
- Reduce `--workers` count in batch processing
- Use `--toc-only` or `--summary-only` to process in stages
- For PDFs >30 pages, the system will log a warning

#### 8. Batch Processing Issues

**Problem**: Batch processing fails or is slow.

**Solution**:
- Reduce `--workers` count if Ollama is overwhelmed (try 2 instead of 4)
- Check system resources (CPU, RAM, network)
- Process smaller batches if memory is limited
- Use `--toc-only` for faster batch processing without LLM calls
- Check individual `pipeline.log` files in each document's output directory

### Getting Help

1. **Check Logs**: Review `results/{note_id}/pipeline.log` for detailed error messages
2. **Run Tests**: Verify installation with `PYTHONPATH=src python tests/run_all_tests.py`
3. **Verbose Mode**: Use `--verbose` flag for detailed debugging output
4. **Review Documentation**: Check `prompts/README.md` for prompt engineering details

## PHI Protection

**Important**: This system is designed to protect Protected Health Information (PHI):

- **No PHI Addition**: The system does not add, infer, or fabricate PHI
- **Source-Only Extraction**: Only information explicitly present in the source text is extracted
- **No Inference**: Patient names, dates of birth, addresses, or identifiers are not inferred
- **Explicit Citations**: All extracted information includes source citations for verification

The prompts include explicit instructions to prevent PHI hallucination. See `prompts/README.md` for details on PHI protection measures.

## Logging

### Log File Location

Logs are saved per document in:
```
results/{note_id}/pipeline.log
```

### Log Format

Logs include:
- **Timestamps**: All entries include timestamps
- **Log Levels**: DEBUG, INFO, WARNING, ERROR
- **LLM Calls**: Input prompts and output responses
- **Pipeline Steps**: Each step of the pipeline with status
- **Errors**: Full error traces and context

### Using Logs for Debugging

1. **Check for Errors**: Search for "ERROR" in the log file
2. **Review LLM Calls**: Check prompt inputs and outputs for unexpected behavior
3. **Trace Execution**: Follow the step-by-step execution to identify where issues occur
4. **Performance Analysis**: Review timestamps to identify slow steps

### Log Levels

- **DEBUG**: Detailed information (enabled with `--verbose`)
- **INFO**: General information about pipeline execution
- **WARNING**: Non-fatal issues (e.g., few sections detected)
- **ERROR**: Fatal errors that stop execution

## Testing

### Run All Tests

```bash
PYTHONPATH=src python tests/run_all_tests.py
```

### Run with Coverage

```bash
PYTHONPATH=src python tests/run_all_tests.py --coverage
```

### Run Specific Test Module

```bash
PYTHONPATH=src python tests/run_all_tests.py --module ingestion
```

### Run Only Unit Tests

```bash
PYTHONPATH=src python tests/run_all_tests.py --unit-only
```

### Run Only Integration Tests

```bash
PYTHONPATH=src python tests/run_all_tests.py --integration-only
```

## Project Structure

```
clinicalnoteparser/
├── src/
│   └── app/
│       ├── ingestion.py      # PDF/txt loading and text extraction
│       ├── sections.py       # Section detection
│       ├── chunks.py         # Text chunking
│       ├── llm.py            # LLM client wrapper
│       ├── summarizer.py     # Summary generation
│       ├── planner.py        # Treatment plan generation
│       ├── evaluation.py     # Evaluation metrics
│       ├── pipeline.py       # Main pipeline orchestration
│       ├── cli.py            # Command-line interface
│       ├── config.py         # Configuration management
│       └── schemas.py        # Pydantic data models
├── prompts/
│   ├── README.md             # Prompt engineering documentation
│   ├── section_inference.md  # Section detection prompt
│   ├── summary_extraction.md # Fact extraction prompt
│   ├── text_summary.md       # Summary generation prompt
│   └── plan_generation.md    # Plan generation prompt
├── tests/
│   ├── conftest.py           # Shared test fixtures
│   ├── run_all_tests.py      # Test runner
│   └── test_*.py             # Unit and integration tests
├── data/
│   └── archive/
│       └── mtsamples_pdf/    # Sample PDF files
├── results/                  # Output directory (generated)
├── pyproject.toml            # Project dependencies
├── requirements.txt          # Exported dependencies
└── README.md                 # This file
```

## License

[Add your license information here]

## Contributing

[Add contributing guidelines here]
