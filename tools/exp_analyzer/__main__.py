"""
Experiment Analyzer — generic post-mortem analysis tool.

Subcommands:
  analyze   Run the full pipeline (ingest → extract → patterns → verdict → report)
  report    Regenerate report.md from a previous run's saved output (no LLM calls)

Usage:
  python -m tools.exp_analyzer analyze <path> [<path> ...] [options]
  python -m tools.exp_analyzer report  --input-dir ./exp_analysis_output [options]

Examples:
  python -m tools.exp_analyzer analyze ./experiment_dir/
  python -m tools.exp_analyzer analyze EXP22.md --model gemini-2.5-flash
  python -m tools.exp_analyzer report --input-dir ./exp_analysis_output
  python -m tools.exp_analyzer report --input-dir ./exp_analysis_output --output-dir ./report_only/
"""

import argparse
import json
import logging
import os
import sys
import time

from .extractor import Record, extract_records
from .ingester import ingest
from .llm_client import LLMClient
from .report import write_all, _write_markdown_report
from .synthesizer import Pattern, build_mapping, discover_patterns
from .verdict import Verdict, VerdictItem, generate_verdict


# ──────────────────────────────────────────────────────────────────────────────
# Subcommand: analyze
# ──────────────────────────────────────────────────────────────────────────────

def _add_analyze_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="Files or directories to analyze (.md, .txt, .log, .json, .csv)",
    )
    p.add_argument("--model", "-m", default="gemini-2.5-flash",
                   help="LLM model name (default: gemini-2.5-flash)")
    p.add_argument("--endpoint-url",
                   default="https://ete-litellm.ai-models.vpc-int.res.ibm.com",
                   help="LLM endpoint base URL (default: https://ete-litellm.ai-models.vpc-int.res.ibm.com)")
    p.add_argument("--api-key", default=None,
                   help="LLM API key (default: $OPENAI_API_KEY)")
    p.add_argument("--output-dir", "-o", default="./exp_analysis_output",
                   help="Directory to write output files (default: ./exp_analysis_output)")
    p.add_argument("--chunk-size", type=int, default=12000,
                   help="Max characters per chunk when splitting large files (default: 12000)")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Enable verbose logging")


def cmd_analyze(args: argparse.Namespace) -> None:
    llm = LLMClient(model=args.model, endpoint_url=args.endpoint_url, api_key=args.api_key)
    start_time = time.monotonic()

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

    # Stage 4: Generate verdict
    print(f"\nStage 4: Generating verdict (what works / what doesn't)")
    verdict = generate_verdict(records, patterns, llm)
    if verdict.overall_assessment:
        print(f"\n  Overall: {verdict.overall_assessment}")
    print(f"  {len(verdict.what_works)} 'what works' finding(s), "
          f"{len(verdict.what_doesnt_work)} 'what doesn't work' finding(s)")

    elapsed = time.monotonic() - start_time
    print(f"\nWriting output to {args.output_dir}")
    write_all(records, patterns, mapping, args.output_dir, verdict,
              model=args.model, elapsed_seconds=elapsed)


# ──────────────────────────────────────────────────────────────────────────────
# Subcommand: report
# ──────────────────────────────────────────────────────────────────────────────

def _add_report_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--input-dir", "-i", default="./exp_analysis_output",
                   help="Directory containing a previous run's output (default: ./exp_analysis_output)")
    p.add_argument("--output-dir", "-o", default=None,
                   help="Where to write the new report.md (default: same as --input-dir)")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Enable verbose logging")


def _load_records(input_dir: str) -> list[Record]:
    path = os.path.join(input_dir, "records.json")
    with open(path) as f:
        data = json.load(f)
    return [
        Record(
            id=r["id"],
            source=r.get("source", ""),
            summary=r.get("summary", ""),
            outcome=r.get("outcome", ""),
            key_decisions=r.get("key_decisions", []),
            notable_observations=r.get("notable_observations", []),
        )
        for r in data
    ]


def _load_patterns(input_dir: str) -> list[Pattern]:
    path = os.path.join(input_dir, "shortcoming_list.json")
    with open(path) as f:
        data = json.load(f)
    return [
        Pattern(
            name=p["name"],
            description=p.get("description", ""),
            occurrences=p.get("occurrences", []),
        )
        for p in data
    ]


def _load_verdict(input_dir: str) -> Verdict | None:
    path = os.path.join(input_dir, "verdict.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)

    def _items(raw: list) -> list[VerdictItem]:
        return [
            VerdictItem(
                finding=v.get("finding", ""),
                evidence=v.get("evidence", []),
                confidence=v.get("confidence", "medium"),
            )
            for v in raw
        ]

    return Verdict(
        overall_assessment=data.get("overall_assessment", ""),
        what_works=_items(data.get("what_works", [])),
        what_doesnt_work=_items(data.get("what_doesnt_work", [])),
    )


def _build_mapping_from_patterns(records: list[Record], patterns: list[Pattern]) -> dict:
    mapping = {r.id: [] for r in records}
    for p in patterns:
        for rid in p.occurrences:
            if rid in mapping:
                mapping[rid].append(p.name)
    return mapping


def _load_meta(input_dir: str) -> dict:
    path = os.path.join(input_dir, "meta.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def cmd_report(args: argparse.Namespace) -> None:
    input_dir = args.input_dir
    output_dir = args.output_dir or input_dir

    # Validate required files exist
    for fname in ("records.json", "shortcoming_list.json"):
        fpath = os.path.join(input_dir, fname)
        if not os.path.exists(fpath):
            print(f"Error: required file not found: {fpath}")
            sys.exit(1)

    print(f"\nLoading results from {input_dir}")
    records = _load_records(input_dir)
    patterns = _load_patterns(input_dir)
    mapping = _build_mapping_from_patterns(records, patterns)
    verdict = _load_verdict(input_dir)
    meta = _load_meta(input_dir)

    print(f"  {len(records)} records, {len(patterns)} patterns"
          + (f", verdict loaded" if verdict else ", no verdict found")
          + (f", model: {meta['model']}" if meta.get("model") else ""))

    os.makedirs(output_dir, exist_ok=True)
    _write_markdown_report(
        records, patterns, mapping, output_dir, verdict,
        model=meta.get("model"),
        elapsed_seconds=meta.get("elapsed_seconds"),
    )
    print(f"\nReport written to {os.path.join(output_dir, 'report.md')}")


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Experiment Analyzer — extracts records and discovers patterns from experiment logs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Run the full pipeline (ingest → extract → patterns → verdict → report)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_analyze_args(analyze_parser)

    report_parser = subparsers.add_parser(
        "report",
        help="Regenerate report.md from a previous run's saved output (no LLM calls)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_report_args(report_parser)

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(levelname)s [%(name)s] %(message)s",
    )

    if args.subcommand == "analyze":
        cmd_analyze(args)
    elif args.subcommand == "report":
        cmd_report(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
