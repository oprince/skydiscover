"""Stage 3: Discover all recurring patterns and map them to records."""

import logging
from dataclasses import dataclass, field
from typing import Dict, List

from .extractor import Record
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

BATCH_SIZE = 150  # records per batch — keeps each prompt under ~15k tokens

# ──────────────────────────────────────────────────────────────────────────────
# Pattern discovery
# ──────────────────────────────────────────────────────────────────────────────

DISCOVERY_SYSTEM = """\
You are an expert experiment analyst performing post-mortem analysis.

You will receive summaries of a batch of records from an experiment. Your task is to \
identify EVERY recurring pattern, failure mode, or strategic insight that appears \
across multiple records in this batch — no matter how many patterns that is.

For each pattern:
- "name": a concise snake_case label (e.g. "session_affinity_regression")
- "description": one sentence explaining what this pattern means
- "occurrences": list of record IDs where this pattern appears

Return ONLY a JSON array of pattern objects. Include all patterns that appear in \
at least 2 records. Do not cap the number of patterns."""

DISCOVERY_USER_TEMPLATE = """\
Below are summaries of {n} records (batch {batch_num}/{batch_total}) from an experiment.

{summaries}

Identify ALL recurring patterns (≥2 occurrences). Return a JSON array where each \
entry has: "name", "description", "occurrences" (list of record IDs)."""

CONSOLIDATION_SYSTEM = """\
You are an expert experiment analyst. You have discovered patterns from multiple \
batches of records and must now consolidate them into a final deduplicated list.

Merge patterns that describe the same underlying phenomenon (even if named slightly \
differently). For merged patterns, combine their occurrence lists (union).

Return ONLY a JSON array where each entry has:
- "name": canonical snake_case label
- "description": one sentence
- "occurrences": combined list of all record IDs (no duplicates)"""

CONSOLIDATION_USER_TEMPLATE = """\
Below are patterns discovered across {n_batches} batches. Consolidate duplicates \
and near-synonyms into a single canonical list.

{patterns_json}

Return the merged JSON array."""


@dataclass
class Pattern:
    name: str
    description: str
    occurrences: List[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.occurrences)


def _parse_patterns(raw_list: list) -> List[Pattern]:
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
    return patterns


def _merge_by_name(batches: List[List[Pattern]]) -> List[Pattern]:
    """First-pass merge: union occurrences for patterns sharing the same name."""
    merged: Dict[str, Pattern] = {}
    for batch in batches:
        for p in batch:
            if p.name in merged:
                existing = merged[p.name]
                existing.occurrences = list(dict.fromkeys(existing.occurrences + p.occurrences))
            else:
                merged[p.name] = Pattern(
                    name=p.name,
                    description=p.description,
                    occurrences=list(p.occurrences),
                )
    return list(merged.values())


def _summaries_for_batch(batch: List[Record]) -> str:
    return "\n".join(
        f"[{r.id}] {r.summary}"
        + (f" | outcome: {r.outcome}" if r.outcome else "")
        + (f" | decisions: {'; '.join(r.key_decisions[:3])}" if r.key_decisions else "")
        for r in batch
    )


def discover_patterns(records: List[Record], llm: LLMClient) -> List[Pattern]:
    """Discover patterns in batches then consolidate into a final deduplicated list."""
    if not records:
        return []

    # Split into batches
    batches = [records[i:i + BATCH_SIZE] for i in range(0, len(records), BATCH_SIZE)]
    n_batches = len(batches)
    logger.info(f"Discovering patterns in {n_batches} batch(es) of up to {BATCH_SIZE} records...")

    batch_results: List[List[Pattern]] = []
    for idx, batch in enumerate(batches):
        summaries = _summaries_for_batch(batch)
        user_msg = DISCOVERY_USER_TEMPLATE.format(
            n=len(batch),
            batch_num=idx + 1,
            batch_total=n_batches,
            summaries=summaries,
        )
        logger.info(f"  Batch {idx + 1}/{n_batches}: {len(batch)} records, "
                    f"~{(len(DISCOVERY_SYSTEM) + len(user_msg)) // 4} tokens")
        try:
            raw_list = llm.complete_json(DISCOVERY_SYSTEM, user_msg)
        except Exception as e:
            logger.error(f"  Batch {idx + 1} pattern discovery failed: {e}")
            batch_results.append([])
            continue

        if not isinstance(raw_list, list):
            logger.error(f"  Batch {idx + 1}: expected list, got {type(raw_list)}")
            batch_results.append([])
            continue

        parsed = _parse_patterns(raw_list)
        logger.info(f"  Batch {idx + 1}: {len(parsed)} patterns found")
        batch_results.append(parsed)

    # First-pass merge by exact name
    merged = _merge_by_name(batch_results)
    logger.info(f"After name-merge: {len(merged)} patterns")

    if n_batches == 1 or len(merged) == 0:
        merged.sort(key=lambda p: p.count, reverse=True)
        return merged

    # Consolidation pass: ask LLM to deduplicate near-synonyms
    import json
    patterns_payload = [
        {"name": p.name, "description": p.description, "occurrences": p.occurrences}
        for p in merged
    ]
    user_msg = CONSOLIDATION_USER_TEMPLATE.format(
        n_batches=n_batches,
        patterns_json=json.dumps(patterns_payload, indent=2),
    )
    logger.info(f"Consolidation pass: {len(merged)} patterns, "
                f"~{(len(CONSOLIDATION_SYSTEM) + len(user_msg)) // 4} tokens")
    try:
        raw_list = llm.complete_json(CONSOLIDATION_SYSTEM, user_msg)
        if isinstance(raw_list, list):
            consolidated = _parse_patterns(raw_list)
            if consolidated:
                merged = consolidated
                logger.info(f"After consolidation: {len(merged)} patterns")
    except Exception as e:
        logger.warning(f"Consolidation pass failed ({e}), using name-merged results")

    merged.sort(key=lambda p: p.count, reverse=True)
    logger.info(f"Discovered {len(merged)} patterns total")
    return merged


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
