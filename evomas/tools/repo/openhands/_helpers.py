"""Shared helpers for the OpenHands per-tool modules.

Holds the small utilities the per-tool files reuse:
- `_MAX_OUTPUT` / `_truncate` — output-length cap for tool responses.
- `_UNDO_STACK` + `_push_undo` — in-memory per-file edit history used by
  the `StrReplaceEditorTool` and `LLMBasedFileEditTool` modules.
- `_file_view` — `cat -n`-style file display shared by `ViewTool` and
  `StrReplaceEditorTool` (the latter's `view` subcommand).
- `_execute_bash_impl` — subprocess wrapper used by `CmdRunTool`.

All implementations are EvoMas-authored.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# In-memory undo stack for file-edit tools (absolute path -> snapshots).
_UNDO_STACK: dict[str, list[str]] = {}

_MAX_OUTPUT = 30_000


def _truncate(text: str, n: int = _MAX_OUTPUT) -> str:
    if len(text) <= n:
        return text
    return text[:n] + "\n<response clipped>"


def _file_view(path: Path, view_range: list[int] | None) -> str:
    if path.is_dir():
        out: list[str] = []
        base_depth = len(path.parts)
        for p in sorted(path.rglob("*")):
            if any(part.startswith(".") for part in p.relative_to(path).parts):
                continue
            depth = len(p.parts) - base_depth
            if depth > 2:
                continue
            out.append(str(p.relative_to(path)))
        return _truncate("\n".join(out) or "(empty)")
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if view_range:
        start, end = view_range[0], view_range[1]
        end = len(lines) if end == -1 else end
        sel = lines[start - 1 : end]
        offset = start
    else:
        sel = lines
        offset = 1
    width = max(3, len(str(offset + len(sel))))
    return _truncate(
        "\n".join(f"{offset + i:>{width}}\t{line}" for i, line in enumerate(sel))
    )


def _push_undo(p: Path) -> None:
    if p.is_file():
        _UNDO_STACK.setdefault(str(p.resolve()), []).append(
            p.read_text(encoding="utf-8", errors="replace")
        )


def _execute_bash_impl(command: str, cwd: str | None = None, timeout: int = 30) -> str:
    if not command.strip():
        return "(empty command)"
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            shell=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s."
    parts: list[str] = []
    if proc.stdout:
        parts.append(proc.stdout)
    if proc.stderr:
        parts.append(proc.stderr)
    parts.append(f"[exit code: {proc.returncode}]")
    return _truncate("\n".join(p.rstrip() for p in parts if p))
