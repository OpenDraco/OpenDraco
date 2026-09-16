"""Path utilities shared across the framework + the HTTP layer.

Functions here are FastAPI-free; `api.common.safe_under` is a thin
wrapper that translates `PermissionError` into `HTTPException(403, …)`.
"""
from __future__ import annotations

from pathlib import Path


def to_wsl(path: str) -> str:
    """Windows absolute path → WSL `/mnt/<drive>/...`."""
    p = path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        p = f"/mnt/{p[0].lower()}{p[2:]}"
    return p


def safe_under(root: Path, candidate: str) -> Path:
    """Resolve `candidate` and assert it stays under `root`. Raises
    `PermissionError` on a path-traversal attempt — the api layer
    translates that into HTTP 403."""
    p = Path(candidate).resolve()
    root_r = root.resolve()
    if root_r not in p.parents and p != root_r:
        raise PermissionError(f"path {p} is outside the allowed root {root_r}")
    return p
