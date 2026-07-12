import logging
import os
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from evomas.exceptions.errors import RepoCloneError

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ROOT: Path = Path(tempfile.gettempdir()) / "evomas_workspace"


@dataclass
class Workspace:
    instance_id: str
    repo: str
    base_commit: str
    path: Path


def _force_rmtree(path: Path) -> None:
    """Remove a directory tree, handling Windows read-only/locked files."""
    def _on_error(func, p, _exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    shutil.rmtree(path, onerror=_on_error)
    if path.exists():
        # Last resort on Windows: shell rmdir bypasses Python file-handle locks.
        subprocess.run(
            ["cmd", "/c", "rmdir", "/S", "/Q", str(path)],
            capture_output=True,
        )
    if path.exists():
        logger.error("_force_rmtree: could not remove %s", path)


def get_workspace_root() -> Path:
    DEFAULT_WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    return DEFAULT_WORKSPACE_ROOT


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 600) -> str:
    logger.debug("running %s (cwd=%s)", cmd, cwd)
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RepoCloneError(
            f"command {cmd} failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def clone_workspace(instance_id: str, repo: str, base_commit: str) -> Workspace:
    root = get_workspace_root()
    path: Path = root / instance_id
    url: str = f"https://github.com/{repo}.git"

    if path.exists():
        # Prefer in-place reset over rmtree-then-reclone: on Windows a
        # locked .git subdir can leave the dir partially intact and break
        # the subsequent `git clone` with "File exists" (rc=128).
        try:
            _run(["git", "reset", "--hard", "HEAD"], cwd=path)
            _run(["git", "clean", "-fdx"], cwd=path)
            try:
                _run(["git", "checkout", base_commit], cwd=path)
            except RepoCloneError:
                _run(["git", "fetch", "--all"], cwd=path)
                _run(["git", "checkout", base_commit], cwd=path)
            head = _run(["git", "rev-parse", "HEAD"], cwd=path).strip()
            logger.info("reusing workspace at %s (HEAD=%s)", path, head)
            return Workspace(instance_id, repo, base_commit, path)
        except Exception as exc:
            logger.warning(
                "workspace exists but in-place checkout failed (%s); recloning", exc,
            )
        # Retry loop: on Windows the first pass often hits Defender /
        # OneDrive scan locks leaving stale `.git/hooks/*.sample` behind.
        for _ in range(3):
            _force_rmtree(path)
            if not path.exists():
                break
            time.sleep(0.5)

        # AV can rehydrate template files faster than git writes them
        # (`cannot copy ... applypatch-msg.sample: File exists`). Fall
        # back to a unique sibling path so the clone lands somewhere fresh.
        if path.exists():
            new_path = path.parent / f"{path.name}-{uuid.uuid4().hex[:8]}"
            logger.warning(
                "could not fully remove stale workspace at %s; using fresh path %s",
                path, new_path,
            )
            path = new_path

    # Belt-and-braces wipe before clone — guards the recurring Windows
    # destination-not-empty failure (rc=3 / "File exists").
    logger.info("cloning %s @ %s into %s", url, base_commit, path)
    _force_rmtree(path)
    try:
        _run(["git", "clone", url, str(path)], timeout=900)
    except RepoCloneError as exc:
        # Retry on fresh uuid path when git hits the AV-rehydrates-templates race.
        if "File exists" in str(exc):
            fallback = path.parent / f"{path.name}-{uuid.uuid4().hex[:8]}"
            logger.warning(
                "git clone hit a stale-file conflict (%s); retrying at %s",
                exc, fallback,
            )
            _force_rmtree(fallback)
            _run(["git", "clone", url, str(fallback)], timeout=900)
            path = fallback
        else:
            raise
    try:
        _run(["git", "checkout", base_commit], cwd=path)
    except RepoCloneError:
        _run(["git", "fetch", "--all"], cwd=path)
        _run(["git", "checkout", base_commit], cwd=path)
    return Workspace(instance_id, repo, base_commit, path)


def cleanup_workspace(workspace: Workspace) -> None:
    if workspace.path.exists():
        shutil.rmtree(workspace.path, ignore_errors=True)
