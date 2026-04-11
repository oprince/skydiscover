"""Write all output files: JSON taxonomy, CSV tables, Markdown report."""

import csv
import json
import os
from typing import Dict, List, Optional

from .extractor import Record
from .synthesizer import Pattern
from .verdict import Verdict


def write_all(
    records: List[Record],
    patterns: List[Pattern],
    mapping: Dict[str, List[str]],
    output_dir: str,
    verdict: Optional[Verdict] = None,
    model: Optional[str] = None,
    elapsed_seconds: Optional[float] = None,
) -> None:
    os.makedirs(output_dir, exist_ok=True)

    _write_records_json(records, output_dir)
    _write_shortcoming_list(patterns, output_dir)
    _write_per_record_csv(records, mapping, output_dir)
    _write_mapping_csv(records, patterns, mapping, output_dir)
    if verdict is not None:
        _write_verdict_json(verdict, output_dir)
    _write_markdown_report(records, patterns, mapping, output_dir, verdict, model, elapsed_seconds)

    print(f"\nAnalysis complete. Output written to: {output_dir}")
    print(f"  {len(records)} records extracted")
    print(f"  {len(patterns)} recurring patterns discovered")
    if verdict is not None:
        print(f"  {len(verdict.what_works)} 'what works' finding(s)")
        print(f"  {len(verdict.what_doesnt_work)} 'what doesn't work' finding(s)")


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


def _write_verdict_json(verdict: Verdict, output_dir: str) -> None:
    path = os.path.join(output_dir, "verdict.json")
    data = {
        "overall_assessment": verdict.overall_assessment,
        "what_works": [
            {"finding": v.finding, "evidence": v.evidence, "confidence": v.confidence}
            for v in verdict.what_works
        ],
        "what_doesnt_work": [
            {"finding": v.finding, "evidence": v.evidence, "confidence": v.confidence}
            for v in verdict.what_doesnt_work
        ],
    }
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


CONFIDENCE_BADGE = {"high": "🟢", "medium": "🟡", "low": "🔴"}


def _format_elapsed(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"


def _write_markdown_report(
    records: List[Record],
    patterns: List[Pattern],
    mapping: Dict[str, List[str]],
    output_dir: str,
    verdict: Optional[Verdict] = None,
    model: Optional[str] = None,
    elapsed_seconds: Optional[float] = None,
) -> None:
    path = os.path.join(output_dir, "report.md")
    lines = []

    lines.append("# Experiment Analysis Report\n")
    lines.append(f"**{len(records)} records** extracted — **{len(patterns)} recurring patterns** discovered\n")
    meta_parts = []
    if model:
        meta_parts.append(f"Model: `{model}`")
    if elapsed_seconds is not None:
        meta_parts.append(f"Analysis time: {_format_elapsed(elapsed_seconds)}")
    if meta_parts:
        lines.append(f"*{' · '.join(meta_parts)}*\n")

    # ── Verdict ──────────────────────────────────────────────────────────────
    if verdict is not None:
        lines.append("---\n")
        lines.append("## Verdict\n")

        if verdict.overall_assessment:
            lines.append(f"{verdict.overall_assessment}\n")

        lines.append("### What Works\n")
        if verdict.what_works:
            for item in verdict.what_works:
                badge = CONFIDENCE_BADGE.get(item.confidence, "")
                lines.append(f"- {badge} **{item.finding}**\n")
                if item.evidence:
                    lines.append(f"  - *Evidence:* {', '.join(f'`{e}`' for e in item.evidence)}\n")
        else:
            lines.append("*(no clear successes identified)*\n")

        lines.append("### What Doesn't Work\n")
        if verdict.what_doesnt_work:
            for item in verdict.what_doesnt_work:
                badge = CONFIDENCE_BADGE.get(item.confidence, "")
                lines.append(f"- {badge} **{item.finding}**\n")
                if item.evidence:
                    lines.append(f"  - *Evidence:* {', '.join(f'`{e}`' for e in item.evidence)}\n")
        else:
            lines.append("*(no clear failures identified)*\n")

    # ── Pattern taxonomy ──────────────────────────────────────────────────────
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
