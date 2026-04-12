"""Thin OpenAI-compatible LLM client using direct HTTP (no SDK dependency).

Auto-appends /v1 to the endpoint URL if not already present.
Reads OPENAI_API_KEY from the environment for auth.
Retries transient errors (timeout, connection reset, DNS) with exponential backoff.
"""

import json
import logging
import os
import re
import time
from typing import Optional
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

# Transient errors worth retrying
_RETRYABLE = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    OSError,  # covers errno 8 (DNS) and errno 54 (connection reset)
)

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds; doubles each attempt


class LLMClient:
    def __init__(self, model: str, endpoint_url: Optional[str] = None, api_key: Optional[str] = None):
        self.model = model
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.api_key = resolved_key

        base = endpoint_url or os.environ.get("OPENAI_API_BASE", "http://localhost:11434")
        base = base.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        self.base_url = base

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def complete(self, system: str, user: str, temperature: float = 0.0) -> str:
        url = urljoin(self.base_url + "/", "chat/completions")
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        last_exc: Exception = RuntimeError("No attempts made")
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = httpx.post(url, json=body, headers=self._headers(), timeout=120)
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    raise httpx.HTTPStatusError(
                        f"{e} {resp.text[:500]}", request=e.request, response=e.response
                    ) from None
                return resp.json()["choices"][0]["message"]["content"]
            except _RETRYABLE as e:
                last_exc = e
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(f"Transient error (attempt {attempt}/{MAX_RETRIES}): {e} — retrying in {delay}s")
                    time.sleep(delay)
                else:
                    logger.warning(f"Transient error (attempt {attempt}/{MAX_RETRIES}): {e} — giving up")
        raise last_exc

    def complete_json(self, system: str, user: str) -> object:
        """Call LLM and parse JSON from the response. Tries fenced block first, then raw."""
        text = self.complete(system, user)
        # Try ```json ... ``` block
        m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if m:
            return json.loads(m.group(1))
        # Try ``` ... ``` block
        m = re.search(r"```\s*([\[{].*?)\s*```", text, re.DOTALL)
        if m:
            return json.loads(m.group(1))
        # Try outermost [ ] or { }
        for start_char, end_char in [("[", "]"), ("{", "}")]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"No JSON found in LLM response:\n{text[:500]}")
