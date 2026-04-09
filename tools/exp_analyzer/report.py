"""Write all output files: JSON taxonomy, CSV tables, Markdown report."""

import csv
import json
import os
from typing import Dict, List

from .extractor import Record
from .synthesizer import Pattern


def write_all(
    records: List[Record],
    patterns: List[Pattern],
    mapping: Dict[str, List[str]],
    output_dir: str,
) -> None:
    os.makedirs(output_dir, exist_ok=True)

    _write_records_json(records, output_dir)
    _write_shortcoming_list(patterns, output_dir)
    _write_per_record_csv(records, mapping, output_dir)
    _write_mapping_csv(records, patterns, mapping, output_dir)
    _write_markdown_report(records, patterns, mapping, output_dir)

    print(f"\nAnalysis complete. Output written to: {output_dir}")
    print(f"  {len(records)} records extracted")
    print(f"  {len(patterns)} recurring patterns discovered")


# ──────────────────────────────────────────────────────────────────────────────

def _write_records_json(records: List[Record], output_dir: str) -> None:
    path = os.path.join(output_dir, "records.json")
    data = [
        {
            "id": r.id,
            "source": r.source,
            "summary": r.summary,
            "outcome": r.outcome,
            "key_decisions": r.key_decisions,
            "notable_observations": r.notable_observations,
        }
        for r in records
    ]
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  [wrote] {path}")


def _write_shortcoming_list(patterns: List[Pattern], output_dir: str) -> None:
    path = os.path.join(output_dir, "shortcoming_list.json")
    data = [
        {
            "name": p.name,
            "description": p.description,
            "occurrence_count": p.count,
            "occurrences": p.occurrences,
        }
        for p in patterns
    ]
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  [wrote] {path}")


def _write_per_record_csv(
    records: List[Record], mapping: Dict[str, List[str]], output_dir: str
) -> None:
    path = os.path.join(output_dir, "per_record_analysis.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "source", "summary", "outcome", "matched_patterns"])
        for r in records:
            matched = "; ".join(mapping.get(r.id, []))
            writer.writerow([r.id, r.source, r.summary, r.outcome, matched])
    print(f"  [wrote] {path}")


def _write_mapping_csv(
    records: List[Record],
    patterns: List[Pattern],
    mapping: Dict[str, List[str]],
    output_dir: str,
) -> None:
    path = os.path.join(output_dir, "mapping_results.csv")
    pattern_names = [p.name for p in patterns]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id"] + pattern_names)
        for r in records:
            matched_set = set(mapping.get(r.id, []))
            row = [r.id] + [1 if pn in matched_set else 0 for pn in pattern_names]
            writer.writerow(row)
    print(f"  [wrote] {path}")


def _write_markdown_report(
    records: List[Record],
    patterns: List[Pattern],
    mapping: Dict[str, List[str]],
    output_dir: str,
) -> None:
    path = os.path.join(output_dir, "report.md")
    lines = []

    lines.append("# Experiment Analysis Report\n")
    lines.append(f"**{len(records)} records** extracted — **{len(patterns)} recurring patterns** discovered\n")

    # Pattern taxonomy
    lines.append("---\n")
    lines.append("## Recurring Patterns\n")
    lines.append("Sorted by occurrence count (descending).\n")
    for p in patterns:
        lines.append(f"### `{p.name}` — {p.count} occurrence{'s' if p.count != 1 else ''}\n")
        lines.append(f"{p.description}\n")
        lines.append(f"**Seen in:** {', '.join(f'`{o}`' for o in p.occurrences)}\n")

    # Per-record summary
    lines.append("---\n")
    lines.append("## Per-Record Summary\n")
    lines.append("| ID | Outcome | Matched Patterns |\n")
    lines.append("|---|---|---|\n")
    for r in records:
        matched = ", ".join(f"`{pn}`" for pn in mapping.get(r.id, [])) or "—"
        outcome = r.outcome.replace("|", "/") if r.outcome else "—"
        lines.append(f"| `{r.id}` | {outcome} | {matched} |\n")

    with open(path, "w") as f:
        f.writelines(lines)
    print(f"  [wrote] {path}")
