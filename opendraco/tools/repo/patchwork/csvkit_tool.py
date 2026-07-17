"""patchwork `csvkit_tool` tool.

Upstream reference: https://github.com/patched-codes/patchwork/blob/main/patchwork/common/tools/csvkit_tool.py
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


import csv
from pathlib import Path


@tool
def csvkit_tool(path: str, head: int = 10) -> str:
    """Print the first `head` rows of a CSV file. Mirrors the read-only
    bits of upstream `csvkit_tool` without pulling in the full csvkit
    dependency."""
    p = Path(path)
    if not p.is_file():
        return f"error: {path} is not a file."
    rows = []
    with p.open("r", encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.reader(f)):
            if i >= head:
                break
            rows.append(",".join(row))
    return "\n".join(rows) or "(empty)"
