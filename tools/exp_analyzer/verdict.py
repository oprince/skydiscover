"""Stage 4: Generate a verdict — what works well and what doesn't."""

import logging
from dataclasses import dataclass, field
from typing import List

from .extractor import Record
from .llm_client import LLMClient
from .synthesizer import Pattern

logger = logging.getLogger(__name__)

VERDICT_SYSTEM = """\
You are an expert experiment analyst. You have been given a set of experiment records \
and the recurring patterns found across them.

Your task: produce a clear, evidence-based verdict that directly answers:
  "What works well, and what doesn't?"

Return ONLY a JSON object with these keys:
- "what_works": list of objects, each with:
    - "finding": one concise sentence stating what works
    - "evidence": list of record IDs and/or pattern names that support this
    - "confidence": "high", "medium", or "low"
- "what_doesnt_work": list of objects, each with:
    - "finding": one concise sentence stating what doesn't work or is a limitation
    - "evidence": list of record IDs and/or pattern names that support this
    - "confidence": "high", "medium", or "low"
- "overall_assessment": 2-4 sentences summarising the experiment's net result and \
the most important takeaway

Be specific — reference concrete outcomes, metrics, and decisions from the records. \
Do not hedge or use generic language. If the evidence is thin for a finding, say so \
via a "low" confidence rating."""

VERDICT_USER_TEMPLATE = """\
=== RECORDS ({n_records} total) ===
{record_lines}

=== RECURRING PATTERNS ({n_patterns} total) ===
{pattern_lines}

Based on everything above, produce a JSON verdict with "what_works", \
"what_doesnt_work", and "overall_assessment"."""


@dataclass
class VerdictItem:
    finding: str
    evidence: List[str] = field(default_factory=list)
    confidence: str = "medium"


@dataclass
class Verdict:
    what_works: List[VerdictItem] = field(default_factory=list)
    what_doesnt_work: List[VerdictItem] = field(default_factory=list)
    overall_assessment: str = ""


def generate_verdict(records: List[Record], patterns: List[Pattern], llm: LLMClient) -> Verdict:
    """Call the LLM to produce a direct verdict: what works / what doesn't."""
    if not records:
        return Verdict()

    record_lines = "\n".join(
        f"[{r.id}] {r.summary}"
        + (f" | outcome: {r.outcome}" if r.outcome else "")
        + (f" | decisions: {'; '.join(r.key_decisions[:3])}" if r.key_decisions else "")
        + (f" | observations: {'; '.join(r.notable_observations[:2])}" if r.notable_observations else "")
        for r in records
    )

    pattern_lines = "\n".join(
        f"[{p.name}] ({p.count} occurrences) {p.description}"
        for p in patterns
    ) or "(no recurring patterns found)"

    user_msg = VERDICT_USER_TEMPLATE.format(
        n_records=len(records),
        record_lines=record_lines,
        n_patterns=len(patterns),
        pattern_lines=pattern_lines,
    )

    logger.info("Generating verdict (what works / what doesn't)...")
    try:
        raw = llm.complete_json(VERDICT_SYSTEM, user_msg)
    except Exception as e:
        logger.error(f"Verdict generation failed: {e}")
        return Verdict()

    if not isinstance(raw, dict):
        logger.error(f"Expected dict from verdict, got {type(raw)}")
        return Verdict()

    def _parse_items(lst) -> List[VerdictItem]:
        if not isinstance(lst, list):
            return []
        items = []
        for item in lst:
            if not isinstance(item, dict):
                continue
            finding = str(item.get("finding", "")).strip()
            if not finding:
                continue
            evidence = item.get("evidence", [])
            if not isinstance(evidence, list):
                evidence = [str(evidence)] if evidence else []
            evidence = [str(e) for e in evidence]
            confidence = str(item.get("confidence", "medium")).strip().lower()
            if confidence not in ("high", "medium", "low"):
                confidence = "medium"
            items.append(VerdictItem(finding=finding, evidence=evidence, confidence=confidence))
        return items

    return Verdict(
        what_works=_parse_items(raw.get("what_works", [])),
        what_doesnt_work=_parse_items(raw.get("what_doesnt_work", [])),
        overall_assessment=str(raw.get("overall_assessment", "")).strip(),
    )
