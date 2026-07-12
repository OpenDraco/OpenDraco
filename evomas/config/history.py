"""Git-backed version history for user-loaded configs. Lives in a
dedicated repo under `evomas/config/loaded/` (gitignored at the project
root). Each Save commits the file with a structural-diff summary.

Public API: `commit_save`, `commit_delete`, `current_sha`,
`list_history`, `read_at`, `delete_commit`, `clear_history_for`."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LOADED_DIR = Path(__file__).resolve().parent / "loaded"


def _ensure_repo() -> Any:
    """Get-or-create the loaded-configs repo. GitPython is imported lazily."""
    from git import Repo, InvalidGitRepositoryError  # type: ignore

    LOADED_DIR.mkdir(parents=True, exist_ok=True)
    try:
        return Repo(LOADED_DIR)
    except InvalidGitRepositoryError:
        repo = Repo.init(LOADED_DIR)
        # Local-only identity — don't touch the user's global git config.
        with repo.config_writer() as cw:
            cw.set_value("user", "name", "EvoMas")
            cw.set_value("user", "email", "evomas@local")
        # Seed HEAD so iter_commits() doesn't choke on an empty repo.
        repo.index.commit("init", parent_commits=[])
        return repo


def _read_at_head_bytes(repo: Any, rel: str) -> bytes | None:
    """Raw blob bytes at HEAD, or None when HEAD lacks the file.
    Bytes-not-strings so CRLF/LF normalisation doesn't break dedupe."""
    try:
        blob = repo.head.commit.tree / rel
        return blob.data_stream.read()
    except Exception:  # noqa: BLE001
        return None


def _read_at_head(repo: Any, rel: str) -> str | None:
    raw = _read_at_head_bytes(repo, rel)
    return raw.decode("utf-8") if raw is not None else None


def _diff_summary(prev: dict[str, Any] | None, curr: dict[str, Any]) -> str:
    """One-line structural diff: agent +/-/edits and edge-count delta."""
    n_agents = len(curr.get("agents") or {})
    n_edges = len(curr.get("edges") or [])
    if prev is None:
        return f"create: {n_agents} agents, {n_edges} edges"
    prev_a = (prev.get("agents") or {})
    curr_a = (curr.get("agents") or {})
    prev_keys = set(prev_a.keys())
    curr_keys = set(curr_a.keys())
    added = curr_keys - prev_keys
    removed = prev_keys - curr_keys
    same = curr_keys & prev_keys
    edited = sum(1 for n in same if prev_a.get(n) != curr_a.get(n))
    delta_e = len(curr.get("edges") or []) - len(prev.get("edges") or [])
    parts: list[str] = []
    if added:   parts.append(f"+{len(added)} agents")
    if removed: parts.append(f"-{len(removed)} agents")
    if edited:  parts.append(f"~{edited} agents")
    if delta_e: parts.append(f"{delta_e:+d} edges")
    # Metadata-only edits (description/entry/end) still hit here.
    if not parts:
        parts.append("metadata only")
    return "edit: " + ", ".join(parts)


def commit_save(name: str) -> str | None:
    """Commit `<name>.json`. Returns the new SHA, or None when bytes
    match HEAD (no-op skip)."""
    target = LOADED_DIR / f"{name}.json"
    if not target.is_file():
        return None
    repo = _ensure_repo()
    rel = f"{name}.json"
    new_bytes = target.read_bytes()
    head_bytes = _read_at_head_bytes(repo, rel)
    if head_bytes == new_bytes:
        return None
    try:
        curr = json.loads(new_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        curr = {}
    try:
        prev = json.loads(head_bytes.decode("utf-8")) if head_bytes else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        prev = None
    msg = f"{name}: {_diff_summary(prev, curr)}"
    repo.index.add([rel])
    commit = repo.index.commit(msg)
    return commit.hexsha


def commit_delete(name: str) -> str | None:
    """Record a `<name>: delete` commit. Returns None if untracked."""
    repo = _ensure_repo()
    rel = f"{name}.json"
    if _read_at_head(repo, rel) is None:
        return None
    repo.index.remove([rel], working_tree=False)
    commit = repo.index.commit(f"{name}: delete")
    return commit.hexsha


def current_sha(name: str) -> str | None:
    """Most recent SHA touching `<name>.json`. Captured by the inference
    worker at run start to pin each run to a config version."""
    try:
        repo = _ensure_repo()
        rel = f"{name}.json"
        commits = list(repo.iter_commits(paths=rel, max_count=1))
        return commits[0].hexsha if commits else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("current_sha(%s) failed: %s", name, exc)
        return None


def list_history(name: str) -> list[dict[str, Any]]:
    """Newest-first commits touching `<name>.json`."""
    repo = _ensure_repo()
    rel = f"{name}.json"
    out: list[dict[str, Any]] = []
    for c in repo.iter_commits(paths=rel):
        out.append({
            "sha": c.hexsha,
            "ts": datetime.fromtimestamp(c.committed_date, tz=timezone.utc).isoformat(),
            "message": (c.message or "").strip(),
            "parent_sha": c.parents[0].hexsha if c.parents else None,
        })
    return out


def read_at(name: str, sha: str) -> str:
    """File contents at `sha`. Raises if the SHA doesn't carry the file."""
    repo = _ensure_repo()
    return repo.git.show(f"{sha}:{name}.json")


def delete_commit(sha: str) -> str | None:
    """Drop one commit via `git rebase --onto <parent> <sha>`. Descendants
    get rewritten SHAs. Returns the new HEAD, or None when the target
    is unknown or is a root commit.

    `-X theirs` keeps each descendant's own snapshot when its patch
    conflicts with the new base — semantically "skip this version,
    keep what came after exactly as it was"."""
    repo = _ensure_repo()
    try:
        target = repo.commit(sha)
    except Exception:  # noqa: BLE001
        return None
    if not target.parents:
        return None
    parent = target.parents[0]
    # Belt-and-braces: clean up any stray rebase state before starting.
    try:
        repo.git.rebase("--abort")
    except Exception:  # noqa: BLE001
        pass
    if repo.head.commit.hexsha == target.hexsha:
        repo.git.reset("--hard", parent.hexsha)
    else:
        try:
            repo.git.rebase("--onto", parent.hexsha, target.hexsha, "-X", "theirs")
        except Exception:
            try:
                repo.git.rebase("--abort")
            except Exception:  # noqa: BLE001
                pass
            return None
    return repo.head.commit.hexsha


def clear_history_for(name: str) -> None:
    """Drop every commit touching `<name>.json` from the timeline.

    Each commit in this repo is single-file (see `commit_save` /
    `commit_delete`) so dropping one only deletes that config's
    history; descendants get re-applied via `rebase -X theirs`, which
    rewrites their SHAs but preserves their per-file snapshots. Other
    configs' visible history therefore survives intact.

    Working-tree `<name>.json` is read up-front and re-written after
    the loop so the loader still finds it — the next save will commit
    it as the new starting point.
    """
    if "/" in name or "\\" in name or not name:
        raise ValueError(f"invalid config name: {name!r}")
    target = LOADED_DIR / f"{name}.json"
    saved_bytes = target.read_bytes() if target.is_file() else None

    # Loop until `list_history` returns empty — that's the only honest
    # termination signal since each rebase rewrites every SHA after the
    # drop point, and the next pass needs the fresh values.
    while True:
        entries = list_history(name)
        if not entries:
            break
        progress = False
        # Drop the oldest commit first so its descendants get
        # re-applied in one pass; otherwise we'd churn the same
        # commits through multiple rebases. `list_history` returns
        # newest-first, hence the reversed iteration.
        for entry in reversed(entries):
            new_head = delete_commit(entry["sha"])
            if new_head is not None:
                progress = True
                break
        if not progress:
            # Every remaining entry is unreachable or a root commit —
            # `_ensure_repo` only seeds an empty "init" root that
            # never touches any config file, so we shouldn't hit this
            # in practice. Bail out rather than spin.
            logger.warning(
                "clear_history_for(%r): could not drop %d remaining entries",
                name, len(entries),
            )
            break

    # Restore working-tree content so the loader still finds the file.
    # The rebase loop overwrites it with whatever HEAD's tree had at
    # the new base (which doesn't include this config anymore).
    if saved_bytes is not None:
        LOADED_DIR.mkdir(parents=True, exist_ok=True)
        target.write_bytes(saved_bytes)
