"""claude_coder `ExploreRepoFolderTool` — depth-N recursive folder summary.

Behavior-faithful re-implementation: walks a folder up to `depth`
levels deep, returns a flat list of relative paths with a `/` suffix on
directories. Skips the usual noise dirs. Fresh EvoMas implementation
built on `pathlib.Path.rglob`.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_SKIP = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".angular", ".pytest_cache"}


@tool
def ExploreRepoFolderTool(path: str = ".", depth: int = 3, limit: int = 200) -> str:
    """Return a JSON list of relative entries under `path` up to `depth`
    levels deep, capped at `limit` entries. Directory entries carry a
    trailing `/`."""
    root = Path(path).resolve()
    if not root.is_dir():
        return json.dumps({"error": f"not a directory: {path}"})
    out: list[str] = []
    for p in sorted(root.rglob("*")):
        parts = p.relative_to(root).parts
        if any(part in _SKIP for part in parts):
            continue
        if len(parts) > depth:
            continue
        rel = "/".join(parts)
        out.append(rel + "/" if p.is_dir() else rel)
        if len(out) >= limit:
            break
    logger.info("[claude_coder.ExploreRepoFolderTool] %s -> %d entries", root, len(out))
    return json.dumps({"root": str(root), "entries": out, "count": len(out)})
