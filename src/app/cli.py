"""Command-line interface module.

This module provides the CLI entrypoint using Typer.
"""

import sys
from pathlib import Path

# Add src directory to Python path so imports work without PYTHONPATH=src
_script_dir = Path(__file__).parent
_project_root = _script_dir.parent.parent
_src_dir = _project_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    import typer
except ImportError:
    print("Error: typer is not installed. Install it with: uv add typer")
    sys.exit(1)

from app.config import Config, get_config
from app.pipeline import run_pipeline

app = typer.Typer(help="Clinical Note Parser - Extract structured information from clinical notes")


@app.command()
def process(
    input_path: str = typer.Argument(..., help="PDF or .txt filename (e.g., '570.pdf') or path to file"),
    output_dir: str = typer.Option(None, "--output-dir", "-o", help="Output directory (default: results/)"),
    model: str = typer.Option(None, "--model", "-m", help="Ollama model name (default: llama3)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable DEBUG logging"),
    toc_only: bool = typer.Option(False, "--toc-only", help="Only generate TOC (skip chunking, summarization, planning, evaluation)"),
    summary_only: bool = typer.Option(False, "--summary-only", help="Only generate summary (skip planning, evaluation)"),
    plan_only: bool = typer.Option(False, "--plan-only", help="Only generate plan (skip summarization, evaluation)"),
    no_evaluation: bool = typer.Option(False, "--no-evaluation", help="Generate TOC, summary, and plan but skip evaluation"),
):
    """Process a clinical note (PDF or .txt) and extract structured information.
    
    The input_path can be:
    - Just a filename (e.g., "570.pdf") - will search in common locations
    - A relative path (e.g., "data/archive/570.pdf")
    - An absolute path (e.g., "/path/to/570.pdf")
    
    Examples:
        # Full pipeline (all outputs including evaluation) - just use filename
        python cli.py 570.pdf
        
        # Only generate TOC
        python cli.py 570.pdf --toc-only
        
        # Only generate summary
        python cli.py 570.pdf --summary-only
        
        # Only generate plan
        python cli.py 570.pdf --plan-only
        
        # Generate everything except evaluation
        python cli.py 570.pdf --no-evaluation
        
        # Use custom model and output directory
        python cli.py 570.pdf --model llama3.2 --output-dir my_results
    """
    # Validate mutually exclusive flags
    flags_set = [toc_only, summary_only, plan_only]
    if sum(flags_set) > 1:
        typer.echo("Error: --toc-only, --summary-only, and --plan-only are mutually exclusive.", err=True)
        typer.echo("Please specify only one of these flags.", err=True)
        raise typer.Exit(1)
    
    if no_evaluation and any(flags_set):
        typer.echo("Error: --no-evaluation cannot be used with --toc-only, --summary-only, or --plan-only.", err=True)
        raise typer.Exit(1)
    
    # Convert input path to Path object
    # If it's just a filename, search in common locations
    input_file = Path(input_path)
    
    # If it's just a filename (no directory separators), search for it
    if "/" not in input_path and "\\" not in input_path:
        # Search in common locations
        search_paths = [
            Path(input_path),  # Current directory
            Path("data/archive/mitsamples_pdf") / input_path,
            Path("data/archive/mtsamples_pdf") / input_path,
            Path("data/archive/mtsamples_pdf/mtsamples_pdf") / input_path,
        ]
        
        for candidate in search_paths:
            if candidate.exists() and candidate.is_file():
                input_file = candidate.resolve()
                break
        else:
            # File not found in any location
            typer.echo(f"Error: File '{input_path}' not found in current directory or common locations.", err=True)
            typer.echo(f"Searched in:", err=True)
            for search_path in search_paths:
                typer.echo(f"  - {search_path}", err=True)
            raise typer.Exit(1)
    elif not input_file.is_absolute():
        # Relative path - try to resolve it
        if not input_file.exists():
            # Try relative to current directory
            candidate = Path.cwd() / input_file
            if candidate.exists():
                input_file = candidate
            else:
                # Try in data directories
                for base_dir in ["data/archive/mitsamples_pdf", "data/archive/mtsamples_pdf", "data/archive/mtsamples_pdf/mtsamples_pdf"]:
                    candidate = Path(base_dir) / input_file
                    if candidate.exists():
                        input_file = candidate
                        break
    
    # Convert output_dir to Path if provided
    output_path = Path(output_dir) if output_dir else None
    
    # Get or create config
    config = get_config()
    if model:
        config.model_name = model
    
    # Check if LLM is needed and if Ollama is available
    needs_llm = not toc_only  # TOC-only doesn't need LLM
    if needs_llm:
        typer.echo("Checking Ollama availability...", err=False)
        from app.pipeline import check_ollama_availability
        is_available, error_msg = check_ollama_availability(config)
        if not is_available:
            typer.echo("\n" + "="*70, err=True)
            typer.echo("ERROR: Ollama is not available or model is not installed", err=True)
            typer.echo("="*70, err=True)
            typer.echo(f"\n{error_msg}", err=True)
            typer.echo("\nTo fix this issue:", err=True)
            typer.echo("  1. Ensure Ollama is installed: https://ollama.ai", err=True)
            typer.echo("  2. Start Ollama service (if not running)", err=True)
            typer.echo(f"  3. Install the model: ollama pull {config.model_name}", err=True)
            typer.echo("\nTo check available models, run: ollama list", err=True)
            typer.echo("\nNote: Use --toc-only to generate only the table of contents (no LLM required)", err=True)
            typer.echo("="*70 + "\n", err=True)
            raise typer.Exit(1)
        typer.echo("✓ Ollama is available\n", err=False)
    
    # Run pipeline
    exit_code = run_pipeline(
        input_path=input_file,
        output_dir=output_path,
        config=config,
        toc_only=toc_only,
        summary_only=summary_only,
        plan_only=plan_only,
        no_evaluation=no_evaluation,
        verbose=verbose,
    )
    
    if exit_code != 0:
        raise typer.Exit(exit_code)


def main():
    """Main entry point for CLI."""
    # Use typer.run() to make 'process' the default command
    # This allows users to run: python cli.py 570.pdf instead of python cli.py process 570.pdf
    typer.run(process)


if __name__ == "__main__":
    main()
