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
    flags: Optional[dict] = None,
    elapsed_seconds: Optional[float] = None,
) -> None:
    os.makedirs(output_dir, exist_ok=True)

    _write_records_json(records, output_dir)
    _write_shortcoming_list(patterns, output_dir)
    _write_per_record_csv(records, mapping, output_dir)
    _write_mapping_csv(records, patterns, mapping, output_dir)
    if verdict is not None:
        _write_verdict_json(verdict, output_dir)
    _write_meta_json(output_dir, flags=flags, elapsed_seconds=elapsed_seconds)
    _write_markdown_report(records, patterns, mapping, output_dir, verdict, flags, elapsed_seconds)

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


def _write_meta_json(
    output_dir: str,
    flags: Optional[dict] = None,
    elapsed_seconds: Optional[float] = None,
) -> None:
    path = os.path.join(output_dir, "meta.json")
    # Load existing to accumulate elapsed time across partial runs
    existing: dict = {}
    if os.path.exists(path):
        with open(path) as f:
            existing = json.load(f)
    data: dict = {}
    if flags is not None:
        data["flags"] = flags
    elif existing.get("flags"):
        data["flags"] = existing["flags"]
    if elapsed_seconds is not None:
        previous = existing.get("elapsed_seconds") or 0
        data["elapsed_seconds"] = round(previous + elapsed_seconds, 1)
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
    flags: Optional[dict] = None,
    elapsed_seconds: Optional[float] = None,
) -> None:
    path = os.path.join(output_dir, "report.md")
    lines = []

    lines.append("# Experiment Analysis Report\n")
    lines.append(f"- **Records extracted:** {len(records)}\n")
    lines.append(f"- **Recurring patterns:** {len(patterns)}\n")
    if elapsed_seconds is not None:
        lines.append(f"- **Analysis time:** {_format_elapsed(elapsed_seconds)}\n")
    if flags:
        for key, value in flags.items():
            lines.append(f"- **{key}:** `{value}`\n")
    lines.append("\n")

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
                    lines.append(f"  - *Evidence:* {len(item.evidence)} record(s) — "
                                 f"filter `per_record_analysis.csv` by id: "
                                 f"{', '.join(f'`{e}`' for e in item.evidence[:3])}"
                                 f"{'…' if len(item.evidence) > 3 else ''}\n")
        else:
            lines.append("*(no clear successes identified)*\n")

        lines.append("### What Doesn't Work\n")
        if verdict.what_doesnt_work:
            for item in verdict.what_doesnt_work:
                badge = CONFIDENCE_BADGE.get(item.confidence, "")
                lines.append(f"- {badge} **{item.finding}**\n")
                if item.evidence:
                    lines.append(f"  - *Evidence:* {len(item.evidence)} record(s) — "
                                 f"filter `per_record_analysis.csv` by id: "
                                 f"{', '.join(f'`{e}`' for e in item.evidence[:3])}"
                                 f"{'…' if len(item.evidence) > 3 else ''}\n")
        else:
            lines.append("*(no clear failures identified)*\n")

    # ── Pattern taxonomy ──────────────────────────────────────────────────────
    lines.append("---\n")
    lines.append("## Recurring Patterns\n")
    lines.append("Sorted by occurrence count (descending).\n")
    for p in patterns:
        preview = ", ".join(f"`{o}`" for o in p.occurrences[:3])
        ellipsis = "…" if p.count > 3 else ""
        lines.append(f"### `{p.name}`\n")
        lines.append(f"{p.description}\n")
        lines.append(f"**Occurrences:** {p.count} record(s) — "
                     f"filter `per_record_analysis.csv` by `matched_patterns` containing `{p.name}` "
                     f"(e.g. {preview}{ellipsis})\n")

    lines.append("\n---\n")
    lines.append("*Full per-record breakdown (id, outcome, matched patterns) is available in `per_record_analysis.csv`.*\n")

    with open(path, "w") as f:
        f.writelines(lines)
    print(f"  [wrote] {path}")
