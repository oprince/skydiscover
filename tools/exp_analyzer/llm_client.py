"""Thin OpenAI-compatible LLM client. Configurable model, base URL, and API key."""

import json
import os
from typing import Optional

import openai


class LLMClient:
    def __init__(self, model: str, api_base: Optional[str] = None, api_key: Optional[str] = None):
        self.model = model
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY", "dummy")
        resolved_base = api_base or os.environ.get("OPENAI_API_BASE")
        self.client = openai.OpenAI(api_key=resolved_key, base_url=resolved_base)

    def complete(self, system: str, user: str, temperature: float = 0.0) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content

    def complete_json(self, system: str, user: str) -> object:
        """Call LLM and parse JSON from the response. Tries fenced block first, then raw."""
        text = self.complete(system, user)
        # Try ```json ... ``` block
        import re
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
