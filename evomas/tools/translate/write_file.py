"""`write_file` — overwrite (or create) a workspace file with given content.

EvoMas's existing repo-tools cover read / list / patch but never expose
a primitive write. For tasks where the LLM produces a whole new file
body inline (translation, re-formatting, doc rewrites, …), a literal
write tool is the cleanest primitive — building a context-perfect diff
for "replace every line" is fragile and burns prompt tokens.

The tool takes only `path` + `content` so small models can call it
reliably. The active workspace root is read from the
`EVOMAS_WORKSPACE_PATH` env var the runner sets before agents run;
`path` can be absolute or relative-to-workspace, either way it must
resolve to a location under the active workspace. `.gold` sidecars
are refused so translation evals can keep their reference files
alongside inputs without the agent clobbering them.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from langchain_core.tools import tool


def _active_workspace() -> Path | None:
    """The runner exports `EVOMAS_WORKSPACE_PATH` before invoking the
    graph; the tool sandboxes writes against that value. Returns None
    when the env var is unset so callers can fail loud."""
    raw = (os.environ.get("EVOMAS_WORKSPACE_PATH") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def _safe_resolve(workspace: Path, path: str) -> Path:
    """Resolve `path` under `workspace`; reject `..` escapes + absolute
    paths that fall outside the workspace tree."""
    candidate = (workspace / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    workspace_resolved = workspace.resolve()
    try:
        candidate.relative_to(workspace_resolved)
    except ValueError as exc:
        raise ValueError(
            f"refusing to write outside workspace: {candidate} is not under {workspace_resolved}"
        ) from exc
    return candidate


@tool
def write_file(path: str, content: str) -> dict[str, Any]:
    """Overwrite (or create) a file inside the active workspace.

    Args:
        path: Path to the file. Can be just the filename (`intro.md`),
            a workspace-relative path (`docs/intro.md`), or an absolute
            path that resolves to a location under the active workspace.
        content: Full file body. Replaces any existing content verbatim.

    Returns:
        `{"ok": True, "path": "<absolute path>", "bytes": <int>}` on
        success, or `{"ok": False, "error": "..."}` on a validation
        failure (workspace not set, sandbox violation, .gold file).
    """
    workspace = _active_workspace()
    if workspace is None:
        return {"ok": False, "error": "EVOMAS_WORKSPACE_PATH is unset or not a directory"}

    if path.endswith(".gold") or "/.gold" in path.replace("\\", "/"):
        return {"ok": False, "error": f"refusing to overwrite a gold-standard file: {path}"}

    try:
        target = _safe_resolve(workspace, path)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    return {"ok": True, "path": str(target), "bytes": len(content.encode("utf-8"))}
