#!/usr/bin/env python3
"""Run all tests for the clinical note parser.

Usage:
    python tests/run_all_tests.py [options]
    python -m tests.run_all_tests [options]

Options:
    --verbose, -v          Show detailed test output
    --coverage, -c         Generate and display coverage report
    --unit-only            Run only unit tests
    --integration-only     Run only integration tests
    --module <name>        Run tests for specific module (e.g., --module ingestion)
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def run_tests(
    verbose: bool = False,
    coverage: bool = False,
    unit_only: bool = False,
    integration_only: bool = False,
    module: str = None,
) -> int:
    """Run tests with specified options.
    
    Args:
        verbose: Show detailed test output
        coverage: Generate coverage report
        unit_only: Run only unit tests
        integration_only: Run only integration tests
        module: Run tests for specific module only
        
    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    import pytest
    
    # Build pytest arguments
    args = []
    
    if verbose:
        args.append("-v")
    else:
        args.append("-q")  # Quiet mode by default
    
    if coverage:
        args.extend(["--cov=src/app", "--cov-report=term-missing", "--cov-report=html"])
    
    # Determine which tests to run
    if unit_only and integration_only:
        print("Error: --unit-only and --integration-only are mutually exclusive", file=sys.stderr)
        return 1
    
    if module:
        # Run tests for specific module
        test_path = f"tests/test_{module}.py"
        if not Path(test_path).exists():
            print(f"Error: Test file not found: {test_path}", file=sys.stderr)
            return 1
        args.append(test_path)
    elif unit_only:
        # Run all unit tests (exclude integration tests)
        args.append("tests/")
        args.append("--ignore=tests/test_pipeline.py")
    elif integration_only:
        # Run only integration tests
        args.append("tests/test_pipeline.py")
    else:
        # Run all tests
        args.append("tests/")
    
    # Run pytest
    exit_code = pytest.main(args)
    return exit_code


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run all tests for the clinical note parser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed test output",
    )
    parser.add_argument(
        "--coverage", "-c",
        action="store_true",
        help="Generate and display coverage report",
    )
    parser.add_argument(
        "--unit-only",
        action="store_true",
        help="Run only unit tests",
    )
    parser.add_argument(
        "--integration-only",
        action="store_true",
        help="Run only integration tests",
    )
    parser.add_argument(
        "--module",
        type=str,
        help="Run tests for specific module (e.g., 'ingestion', 'schemas')",
    )
    
    args = parser.parse_args()
    
    exit_code = run_tests(
        verbose=args.verbose,
        coverage=args.coverage,
        unit_only=args.unit_only,
        integration_only=args.integration_only,
        module=args.module,
    )
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

