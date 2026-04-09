"""
Experiment Analyzer — generic post-mortem analysis tool.

Usage:
  python -m tools.exp_analyzer <path> [<path> ...] [options]

Examples:
  python -m tools.exp_analyzer ./experiment_dir/
  python -m tools.exp_analyzer run.log metrics.csv notes.md
  python -m tools.exp_analyzer EXP22.md --model qwen2.5:7b --api-base http://localhost:11434/v1
  python -m tools.exp_analyzer EXP22.md --model claude-sonnet-4-6 --api-key $ANTHROPIC_API_KEY
"""

import argparse
import logging
import sys

from .extractor import extract_records
from .ingester import ingest
from .llm_client import LLMClient
from .report import write_all
from .synthesizer import build_mapping, discover_patterns


def main():
    parser = argparse.ArgumentParser(
        description="Generic experiment log analyzer — extracts records and discovers recurring patterns.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="Files or directories to analyze (.md, .txt, .log, .json, .csv)",
    )
    parser.add_argument(
        "--model", "-m",
        default="qwen2.5:7b",
        help="LLM model name (default: qwen2.5:7b)",
    )
    parser.add_argument(
        "--api-base",
        default="http://localhost:11434/v1",
        help="LLM API base URL (default: http://localhost:11434/v1)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="LLM API key (default: $OPENAI_API_KEY or 'dummy' for local)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./exp_analysis_output",
        help="Directory to write output files (default: ./exp_analysis_output)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=12000,
        help="Max characters per chunk when splitting large files (default: 12000)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s [%(name)s] %(message)s",
    )

    llm = LLMClient(model=args.model, api_base=args.api_base, api_key=args.api_key)

    # Stage 1: Ingest
    print(f"\nStage 1: Ingesting files from {args.paths}")
    chunks = ingest(args.paths, chunk_size=args.chunk_size)
    if not chunks:
        print("No files found or all files were empty. Exiting.")
        sys.exit(1)
    print(f"  {len(chunks)} chunk(s) from {len({c.source for c in chunks})} file(s)")

    # Stage 2: Extract records
    print(f"\nStage 2: Extracting records (model={args.model})")
    records = extract_records(chunks, llm)
    if not records:
        print("No records extracted. Check your input files and model.")
        sys.exit(1)
    print(f"  {len(records)} records extracted")

    # Stage 3: Synthesize patterns
    print(f"\nStage 3: Discovering patterns across {len(records)} records")
    patterns = discover_patterns(records, llm)
    mapping = build_mapping(records, patterns)

    # Output
    print(f"\nWriting output to {args.output_dir}")
    write_all(records, patterns, mapping, args.output_dir)


if __name__ == "__main__":
    main()
