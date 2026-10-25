"""Small text helpers shared across modules."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import BaseMessage


def message_text(message: BaseMessage | Any) -> str:
    """Return the plain text of a message, whatever shape its content has."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Pull the first JSON object out of an LLM reply (handles ```json fences and chatter)."""
    text = text.strip()
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for candidate in candidates:
        candidate = candidate.strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        start, end = candidate.find("{"), candidate.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError("No valid JSON object found in the model reply")


def md_cell(value: Any) -> str:
    """Make a value safe to put inside a Markdown table cell."""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    return str(value or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"
