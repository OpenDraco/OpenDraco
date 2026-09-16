"""lingma_swe_gpt `search_code_in_file` — keyword search inside one file."""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import tool


@tool
def search_code_in_file(code_str: str, file_name: str, workspace: str) -> str:
    """Search for a substring inside a specific file.

    Args:
        code_str: substring to find.
        file_name: relative path of the file to scan (interpreted
            relative to `workspace`).
        workspace: absolute path to the repo root.

    Returns a JSON `{"result", "summary", "ok"}` payload where `result`
    is a newline-joined list of `file:line  <line text>` for each
    occurrence of `code_str`.
    """
    base = Path(workspace)
    target = base / file_name
    if not target.is_file():
        return json.dumps({
            "result": "", "summary": f"search_code_in_file: {file_name!r} not found", "ok": False,
        })
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return json.dumps({
            "result": "", "summary": f"search_code_in_file: read failed ({exc})", "ok": False,
        })
    hits: list[str] = []
    for i, line in enumerate(text.split("\n"), start=1):
        if code_str in line:
            rendered = line.strip()
            if len(rendered) > 200:
                rendered = rendered[:200] + " ..."
            hits.append(f"{file_name}:{i}  {rendered}")
    if not hits:
        return json.dumps({
            "result": "",
            "summary": f"search_code_in_file({code_str!r} in {file_name!r}) (no matches)",
            "ok": False,
        })
    return json.dumps({
        "result": "\n".join(hits),
        "summary": f"search_code_in_file({code_str!r} in {file_name!r}) ({len(hits)} match{'es' if len(hits) != 1 else ''})",
        "ok": True,
    })
