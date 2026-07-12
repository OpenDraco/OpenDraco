"""OpenHands `LLMBasedFileEditTool` — overwrite a slice of a file (or
the whole file) with new content.

Minimal implementation: a 1-indexed inclusive `[start, end]` slice is
replaced with `content`. `start=end=-1` appends. Missing files are
created. Every successful edit pushes the previous contents onto the
shared undo stack so a later `StrReplaceEditorTool` `undo_edit` can
restore them.
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from evomas.tools.repo.openhands._helpers import _push_undo


@tool
def LLMBasedFileEditTool(path: str, content: str, start: int = 1, end: int = -1) -> str:
    """Edit `path` by replacing the 1-indexed inclusive line range
    `[start, end]` with `content`. `end=-1` means "to end of file";
    `start=end=-1` appends `content`. Creates the file if it does not
    already exist. Returns a short status string."""
    p = Path(path)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"File created at {path}."
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if start == -1 and end == -1:
        new_text = text.rstrip("\n") + "\n" + content + ("\n" if not content.endswith("\n") else "")
    else:
        end_eff = len(lines) if end == -1 else end
        start_eff = max(1, start)
        replacement = content.splitlines()
        new_lines = lines[: start_eff - 1] + replacement + lines[end_eff:]
        new_text = "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")
    _push_undo(p)
    p.write_text(new_text, encoding="utf-8")
    return f"File edited at {path}."
