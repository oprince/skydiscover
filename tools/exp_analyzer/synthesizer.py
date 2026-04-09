"""Stage 3: Discover all recurring patterns and map them to records."""

import logging
from dataclasses import dataclass, field
from typing import Dict, List

from .extractor import Record
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Pattern discovery
# ──────────────────────────────────────────────────────────────────────────────

DISCOVERY_SYSTEM = """\
You are an expert experiment analyst performing post-mortem analysis.

You will receive summaries of all records from an experiment. Your task is to \
identify EVERY recurring pattern, failure mode, or strategic insight that appears \
across multiple records — no matter how many patterns that is.

For each pattern:
- "name": a concise snake_case label (e.g. "session_affinity_regression")
- "description": one sentence explaining what this pattern means
- "occurrences": list of record IDs where this pattern appears

Return ONLY a JSON array of pattern objects. Include all patterns that appear in \
at least 2 records. Do not cap the number of patterns."""

DISCOVERY_USER_TEMPLATE = """\
Below are summaries of {n} records from an experiment.

{summaries}

Identify ALL recurring patterns (≥2 occurrences). Return a JSON array where each \
entry has: "name", "description", "occurrences" (list of record IDs)."""


@dataclass
class Pattern:
    name: str
    description: str
    occurrences: List[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.occurrences)


def discover_patterns(records: List[Record], llm: LLMClient) -> List[Pattern]:
    """Send all record summaries to the LLM and return discovered patterns with counts."""
    if not records:
        return []

    summaries = "\n".join(
        f"[{r.id}] {r.summary}"
        + (f" | outcome: {r.outcome}" if r.outcome else "")
        + (f" | decisions: {'; '.join(r.key_decisions[:3])}" if r.key_decisions else "")
        for r in records
    )

    user_msg = DISCOVERY_USER_TEMPLATE.format(n=len(records), summaries=summaries)

    logger.info(f"Discovering patterns across {len(records)} records...")
    try:
        raw_list = llm.complete_json(DISCOVERY_SYSTEM, user_msg)
    except Exception as e:
        logger.error(f"Pattern discovery failed: {e}")
        return []

    if not isinstance(raw_list, list):
        logger.error(f"Expected list from pattern discovery, got {type(raw_list)}")
        return []

    patterns = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "unnamed_pattern")).strip()
        desc = str(item.get("description", "")).strip()
        occ = item.get("occurrences", [])
        if not isinstance(occ, list):
            occ = [str(occ)]
        occ = [str(o) for o in occ]
        if name and len(occ) >= 2:
            patterns.append(Pattern(name=name, description=desc, occurrences=occ))

    # Sort by occurrence count descending
    patterns.sort(key=lambda p: p.count, reverse=True)
    logger.info(f"Discovered {len(patterns)} patterns")
    return patterns


# ──────────────────────────────────────────────────────────────────────────────
# Mapping: record → patterns
# ──────────────────────────────────────────────────────────────────────────────

def build_mapping(records: List[Record], patterns: List[Pattern]) -> Dict[str, List[str]]:
    """
    Return a dict mapping record_id → list of pattern names that apply to it.
    Built from the occurrences lists returned by the LLM (no extra LLM call needed).
    """
    mapping: Dict[str, List[str]] = {r.id: [] for r in records}
    for pattern in patterns:
        for record_id in pattern.occurrences:
            if record_id in mapping:
                mapping[record_id].append(pattern.name)
    return mapping
