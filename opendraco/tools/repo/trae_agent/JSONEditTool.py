"""trae_agent `JSONEditTool` — set a top-level key in a JSON file.

Parses `value` as JSON when possible (numbers, booleans, nested
objects, arrays); falls back to storing it as a literal string when
the parse fails. Top-level value must be a JSON object — array /
scalar roots are rejected with an error.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def JSONEditTool(path: str, key: str, value: str) -> str:
    """Read a JSON file, set top-level `key` to `value` (parsed as JSON
    if possible, else stored as a string), write it back, return "ok"."""
    p = Path(path)
    if not p.is_file():
        return f"error: {path} is not a file."
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return f"error: {path} is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return "error: top-level JSON value must be an object to set a key."
    try:
        data[key] = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        data[key] = value
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "ok"
