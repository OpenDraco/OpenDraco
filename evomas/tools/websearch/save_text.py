"""`save_text` — write a string to a user-specified path on disk.

Distinct from the translate bundle's `write_file`, which sandboxes
writes to `EVOMAS_WORKSPACE_PATH`. This tool accepts the path verbatim
from the LLM so a CLI user can say "write the answer to ./answer.md"
in the problem statement and the researcher agent honours it. Relative
paths resolve against the process CWD; absolute paths land where the
user named. No sandboxing — the user is the one running the CLI.
Parent directories are created on demand.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from langchain_core.tools import tool


@tool
def save_text(path: str, content: str) -> dict[str, Any]:
    """Write `content` to the file at `path` (UTF-8). Creates parent
    directories if missing. Use this when the user explicitly asks
    for the answer to be saved to a file."""
    raw = (path or "").strip()
    if not raw:
        return {"ok": False, "error": "empty path"}
    p = Path(raw).expanduser()
    # Windows-only rebase: small LLMs sometimes drop the leading `.`
    # in `./foo.md`, leaving `/foo.md`. Without a drive letter that
    # resolves to `C:\foo.md` (drive root, rarely writable). Rewrite
    # to CWD-relative so the user's "save next to me" intent wins
    # over the typo. POSIX `/foo.md` is unambiguous → don't touch.
    if os.name == "nt" and not p.drive and (raw.startswith("/") or raw.startswith("\\")):
        p = Path.cwd() / raw.lstrip("/").lstrip("\\")
    elif not p.is_absolute():
        p = Path.cwd() / p
    target = p.resolve()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content or "", encoding="utf-8", newline="\n")
    except OSError as exc:
        return {"ok": False, "error": f"write failed: {exc}", "path": str(target)}
    return {"ok": True, "path": str(target), "bytes": len((content or "").encode("utf-8"))}
