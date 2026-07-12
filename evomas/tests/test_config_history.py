"""Tests for `evomas.config.history` — the GitPython-backed version log
that powers the topology page's History panel.

Each test runs against a temporary `LOADED_DIR` so the user's real
loaded-configs history isn't touched. `monkeypatch.setattr` swaps the
module-level path constant before each call so `_ensure_repo()` initses
inside the tmp dir."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def history_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the history module at an isolated tmp dir."""
    from evomas.config import history
    monkeypatch.setattr(history, "LOADED_DIR", tmp_path)
    return tmp_path


def _write(loaded: Path, name: str, data: dict) -> None:
    (loaded / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_commit_save_records_first_commit(history_tmp: Path) -> None:
    from evomas.config.history import commit_save, list_history
    _write(history_tmp, "demo", {"id": "demo", "agents": {"a": {}}, "edges": []})
    sha = commit_save("demo")
    assert sha and len(sha) == 40
    entries = list_history("demo")
    assert len(entries) == 1
    assert entries[0]["sha"] == sha
    # The summary names the file and reports the agent / edge counts.
    assert "demo:" in entries[0]["message"]
    assert "1 agents" in entries[0]["message"]


def test_commit_save_skips_when_unchanged(history_tmp: Path) -> None:
    """Saving the same bytes twice must produce ONE commit, not two —
    otherwise the history sidebar fills with no-op entries every time
    the user reopens-and-saves without editing."""
    from evomas.config.history import commit_save, list_history
    _write(history_tmp, "demo", {"id": "demo", "agents": {"a": {}}, "edges": []})
    first = commit_save("demo")
    second = commit_save("demo")
    assert first is not None
    assert second is None
    assert len(list_history("demo")) == 1


def test_commit_save_records_subsequent_edit(history_tmp: Path) -> None:
    from evomas.config.history import commit_save, list_history, read_at
    _write(history_tmp, "demo", {"id": "demo", "agents": {"a": {}}, "edges": []})
    sha1 = commit_save("demo")
    _write(history_tmp, "demo", {
        "id": "demo",
        "agents": {"a": {}, "b": {}},
        "edges": [{"from": "a", "to": "b"}],
    })
    sha2 = commit_save("demo")
    assert sha1 and sha2 and sha1 != sha2
    entries = list_history("demo")
    assert len(entries) == 2
    # Newest first.
    assert entries[0]["sha"] == sha2
    assert "+1 agents" in entries[0]["message"]
    # Older content is recoverable.
    raw_old = read_at("demo", sha1)
    parsed_old = json.loads(raw_old)
    assert list(parsed_old["agents"].keys()) == ["a"]


def test_current_sha_tracks_head(history_tmp: Path) -> None:
    from evomas.config.history import commit_save, current_sha
    assert current_sha("demo") is None
    _write(history_tmp, "demo", {"id": "demo", "agents": {}, "edges": []})
    sha = commit_save("demo")
    assert current_sha("demo") == sha


def test_commit_delete_records_deletion(history_tmp: Path) -> None:
    from evomas.config.history import commit_delete, commit_save, list_history
    _write(history_tmp, "demo", {"id": "demo", "agents": {}, "edges": []})
    commit_save("demo")
    (history_tmp / "demo.json").unlink()
    sha = commit_delete("demo")
    assert sha is not None
    entries = list_history("demo")
    assert "delete" in entries[0]["message"]


def test_read_at_invalid_sha_raises(history_tmp: Path) -> None:
    """A made-up SHA must raise so the API endpoint can surface a 404."""
    from evomas.config.history import commit_save, read_at
    _write(history_tmp, "demo", {"id": "demo", "agents": {}, "edges": []})
    commit_save("demo")
    with pytest.raises(Exception):
        read_at("demo", "deadbeef" * 5)


def test_delete_commit_tip_resets_head(history_tmp: Path) -> None:
    """Deleting HEAD = `git reset --hard HEAD~1`. The previous commit
    becomes the new HEAD and is the last entry in the history."""
    from evomas.config.history import commit_save, delete_commit, list_history
    _write(history_tmp, "demo", {"id": "demo", "agents": {}, "edges": []})
    sha1 = commit_save("demo")
    _write(history_tmp, "demo", {"id": "demo", "agents": {"a": {}}, "edges": []})
    sha2 = commit_save("demo")
    assert sha1 and sha2
    assert delete_commit(sha2) == sha1
    entries = list_history("demo")
    # Only the first save survives. Note `list_history` filters to
    # commits touching demo.json, so the seed `init` commit isn't in
    # the list.
    assert [e["sha"] for e in entries] == [sha1]


def test_delete_commit_middle_rewrites_descendants(history_tmp: Path) -> None:
    """Dropping a middle commit rebases descendants onto its parent —
    their SHAs change. The middle commit is gone from the timeline;
    later edits remain (with new SHAs) and the working tree ends at
    a state equivalent to HEAD's content."""
    from evomas.config.history import commit_save, delete_commit, list_history
    _write(history_tmp, "demo", {"id": "demo", "agents": {}, "edges": []})
    sha1 = commit_save("demo")
    _write(history_tmp, "demo", {"id": "demo", "agents": {"a": {}}, "edges": []})
    sha2 = commit_save("demo")
    _write(history_tmp, "demo", {
        "id": "demo", "agents": {"a": {}, "b": {}}, "edges": [],
    })
    sha3 = commit_save("demo")
    assert sha1 and sha2 and sha3
    new_head = delete_commit(sha2)
    assert new_head is not None and new_head != sha3
    entries = list_history("demo")
    shas = [e["sha"] for e in entries]
    # sha2 is gone. sha3 was rewritten so it shouldn't be in the new
    # list verbatim. sha1 (the root touch of this file) is preserved.
    assert sha2 not in shas
    assert sha3 not in shas
    assert sha1 in shas


def test_delete_commit_unknown_sha_returns_none(history_tmp: Path) -> None:
    """A SHA the repo doesn't carry returns None rather than raising —
    the API endpoint then surfaces a 409 / 404 to the caller."""
    from evomas.config.history import commit_save, delete_commit
    _write(history_tmp, "demo", {"id": "demo", "agents": {}, "edges": []})
    commit_save("demo")
    assert delete_commit("deadbeef" * 5) is None
