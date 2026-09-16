"""Payload shape descriptions for inter-agent hand-offs.

Sizes use `len(str(value))` not JSON length because state slots routinely
hold non-JSON values (Path, exceptions, dataclasses) and the user sees the
same stringified representation in the preview modal."""
from __future__ import annotations

from typing import Any


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def summarize_payload(value: Any) -> str:
    """Return a short, log-safe shape description for a state-slot value."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        # bool before int: bools are ints in Python, the int branch would print `int(True)`.
        return f"bool({value})"
    if isinstance(value, int):
        return f"int({value})"
    if isinstance(value, float):
        return f"float({value})"
    if isinstance(value, str):
        return f"str({_format_bytes(len(value))})"
    if isinstance(value, bytes):
        return f"bytes({_format_bytes(len(value))})"
    if isinstance(value, (list, tuple)):
        kind = "list" if isinstance(value, list) else "tuple"
        approx = len(str(value))
        return f"{kind}({len(value)} items, ~{_format_bytes(approx)})"
    if isinstance(value, dict):
        approx = len(str(value))
        return f"dict({len(value)} keys, ~{_format_bytes(approx)})"
    if isinstance(value, set):
        approx = len(str(value))
        return f"set({len(value)} items, ~{_format_bytes(approx)})"
    type_name = type(value).__name__
    try:
        size = len(str(value))
    except Exception:
        return f"{type_name}(?)"
    return f"{type_name}(~{_format_bytes(size)})"


def preview_payload(value: Any, max_chars: int = 16384) -> str:
    """Stringify `value` and truncate to `max_chars`, suffixing with
    `... (N more chars)` when truncated."""
    try:
        text = str(value)
    except Exception as exc:
        return f"<unrenderable: {type(value).__name__}: {exc}>"
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}... ({len(text) - max_chars} more chars)"
