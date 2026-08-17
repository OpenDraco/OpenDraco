"""The local harness wrapper must only forward flags the vendored
SWE-bench actually defines.

`run_evaluation.py` ends in `main(**vars(args))`, so its parser and
`main()` are in lockstep — a flag missing from `--help` is missing from
the harness entirely, and passing it kills the run with argparse's
exit code 2 before a single container starts.
"""
from __future__ import annotations

import subprocess

import pytest

import scripts.evaluation.run_swebench_evaluation as ev


# Trimmed from the vendored fork's real `--help`; it defines no caching knobs.
HELP_WITHOUT_CACHE = """\
usage: run_evaluation.py [-h] [-d DATASET_NAME] [-s SPLIT]
                         [-i INSTANCE_IDS [INSTANCE_IDS ...]] -p
                         PREDICTIONS_PATH [--max_workers MAX_WORKERS]
                         [--open_file_limit OPEN_FILE_LIMIT] [-t TIMEOUT] -id
                         RUN_ID [--rewrite_reports REWRITE_REPORTS]
                         [--report_dir REPORT_DIR] [--modal MODAL]

options:
  -h, --help            show this help message and exit
  --max_workers MAX_WORKERS
                        Maximum number of workers (default: 4)
  --report_dir REPORT_DIR
                        Directory to write reports to (default: .)
"""

HELP_WITH_CACHE = HELP_WITHOUT_CACHE + """\
  --cache_level {none,base,env,instance}
                        Cache level (default: env)
  --force_rebuild FORCE_REBUILD
                        Force rebuild of all images (default: False)
"""

WITH_CACHE = frozenset({"--cache_level", "--force_rebuild", "--report_dir"})
WITHOUT_CACHE = frozenset({"--report_dir", "--max_workers"})


@pytest.fixture(autouse=True)
def _clear_probe_cache() -> None:
    ev._SUPPORTED_FLAGS_CACHE.clear()


# ─── probing the harness ──────────────────────────────────────────────────────

def test_probe_reads_flags_out_of_help(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ev.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, HELP_WITH_CACHE, ""),
    )
    flags = ev._harness_supported_flags("python")
    assert {"--cache_level", "--force_rebuild", "--max_workers"} <= flags
    assert "--report_dir" in flags


def test_probe_returns_none_when_harness_cannot_be_run(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*a, **k):
        raise OSError("Exec format error")
    monkeypatch.setattr(ev.subprocess, "run", _boom)
    assert ev._harness_supported_flags("python") is None


def test_probe_is_cached_per_interpreter(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def _fake(cmd, *a, **k):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, HELP_WITHOUT_CACHE, "")

    monkeypatch.setattr(ev.subprocess, "run", _fake)
    ev._harness_supported_flags("python")
    ev._harness_supported_flags("python")
    assert len(calls) == 1


# ─── choosing which flags to forward ──────────────────────────────────────────

def test_defaults_are_dropped_when_harness_lacks_them() -> None:
    assert ev._cache_flags(WITHOUT_CACHE, ev.DEFAULT_CACHE_LEVEL, False) == []


def test_supported_flags_are_forwarded() -> None:
    assert ev._cache_flags(WITH_CACHE, "env", False) == ["--cache_level", "env"]
    assert ev._cache_flags(WITH_CACHE, "none", True) == [
        "--cache_level", "none", "--force_rebuild", "True",
    ]


def test_explicit_cache_level_on_unsupporting_harness_is_refused() -> None:
    with pytest.raises(ev.UnsupportedHarnessFlag) as exc:
        ev._cache_flags(WITHOUT_CACHE, "none", False)
    assert "--cache_level" in str(exc.value)


def test_explicit_force_rebuild_on_unsupporting_harness_is_refused() -> None:
    with pytest.raises(ev.UnsupportedHarnessFlag) as exc:
        ev._cache_flags(WITHOUT_CACHE, ev.DEFAULT_CACHE_LEVEL, True)
    assert "--force_rebuild" in str(exc.value)


def test_unprobeable_harness_drops_defaults_but_honours_explicit_asks() -> None:
    assert ev._cache_flags(None, ev.DEFAULT_CACHE_LEVEL, False) == []
    assert ev._cache_flags(None, "none", True) == [
        "--cache_level", "none", "--force_rebuild", "True",
    ]


# ─── end to end through run_evaluation ────────────────────────────────────────

@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch, tmp_path) -> list[list[str]]:
    """Capture the harness argv; stub out docker and the interpreter probe."""
    cmds: list[list[str]] = []

    def _fake_run(cmd, *a, **k):
        if cmd[-1] == "--help":
            return subprocess.CompletedProcess(cmd, 0, HELP_WITHOUT_CACHE, "")
        cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(ev.subprocess, "run", _fake_run)
    monkeypatch.setattr(ev, "_swebench_python", lambda: "python")
    monkeypatch.setattr(ev, "_remove_stale_containers", lambda run_id: None)
    monkeypatch.setattr(ev, "_purge_stale_reports", lambda run_id, report_dir: None)
    return cmds


def test_run_evaluation_omits_the_flag_the_fork_rejects(spawned: list, tmp_path) -> None:
    preds = tmp_path / "p.jsonl"
    preds.write_text("{}\n", encoding="utf-8")
    rc = ev.run_evaluation(str(preds), "run-1", "dev", report_dir=str(tmp_path))
    assert rc == 0
    assert len(spawned) == 1
    assert "--cache_level" not in spawned[0]
    assert "--force_rebuild" not in spawned[0]
    # The flags the fork does define still go through.
    assert "--predictions_path" in spawned[0] and "--run_id" in spawned[0]


def test_run_evaluation_refuses_rather_than_silently_ignoring(spawned: list, tmp_path) -> None:
    preds = tmp_path / "p.jsonl"
    preds.write_text("{}\n", encoding="utf-8")
    rc = ev.run_evaluation(
        str(preds), "run-1", "dev", report_dir=str(tmp_path), force_rebuild=True,
    )
    assert rc == 2
    # Nothing was launched — a corrupt image must not be quietly reused.
    assert spawned == []
