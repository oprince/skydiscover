"""Stage 2: Extract structured records from raw log chunks using the LLM."""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .ingester import Chunk
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an experiment analyst. Your job is to extract structured records from \
raw experiment logs, regardless of their format or domain.

A "record" is any discrete unit of work: an iteration, a run, a trial, a step, \
a decision, or any event with a measurable outcome.

For each record you find, extract:
- "id": a short identifier (e.g. "iter_3", "run_2", "step_5", or invent one if absent)
- "summary": one sentence describing what happened
- "outcome": the measured result or metric, if any (string)
- "key_decisions": list of decisions, actions, or changes made (strings)
- "notable_observations": list of important observations or findings (strings)

Return ONLY a JSON array of records. If no discrete records are found, return [].
Do not include commentary outside the JSON."""

USER_TEMPLATE = """\
File: {source} (chunk {index_plus_one}/{total})

---
{text}
---

Extract all discrete records from the excerpt above. Return a JSON array."""


@dataclass
class Record:
    id: str
    source: str
    summary: str = ""
    outcome: str = ""
    key_decisions: List[str] = field(default_factory=list)
    notable_observations: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


def extract_records(chunks: List[Chunk], llm: LLMClient) -> List[Record]:
    """Call the LLM on each chunk and return a flat list of Records."""
    all_records: List[Record] = []
    seen_ids: Dict[str, int] = {}

    for chunk in chunks:
        logger.info(f"Extracting records from {chunk.source} chunk {chunk.index + 1}/{chunk.total}")
        user_msg = USER_TEMPLATE.format(
            source=chunk.source,
            index_plus_one=chunk.index + 1,
            total=chunk.total,
            text=chunk.text,
        )
        try:
            raw_list = llm.complete_json(SYSTEM_PROMPT, user_msg)
        except Exception as e:
            logger.warning(f"Extraction failed for {chunk.source} chunk {chunk.index}: {e}")
            continue

        if not isinstance(raw_list, list):
            logger.warning(f"Expected list, got {type(raw_list)} for {chunk.source} chunk {chunk.index}")
            continue

        for item in raw_list:
            if not isinstance(item, dict):
                continue
            raw_id = str(item.get("id", "record"))
            # Deduplicate IDs across chunks
            if raw_id in seen_ids:
                seen_ids[raw_id] += 1
                unique_id = f"{raw_id}_{seen_ids[raw_id]}"
            else:
                seen_ids[raw_id] = 0
                unique_id = raw_id

            all_records.append(
                Record(
                    id=unique_id,
                    source=chunk.source,
                    summary=str(item.get("summary", "")),
                    outcome=str(item.get("outcome", "")),
                    key_decisions=_to_str_list(item.get("key_decisions", [])),
                    notable_observations=_to_str_list(item.get("notable_observations", [])),
                    raw=item,
                )
            )

    return all_records


def _to_str_list(val) -> List[str]:
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        return [val]
    return []
