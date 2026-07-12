"""Tests for `evomas.utils.ollama_preflight.preflight_models`.

The preflight helper is the gate that decides whether a run can start:
it pulls any missing Ollama model the config references, and raises
`EvomasError` when a pull can't succeed (no `ollama` binary, registry
404, etc.). These tests stub `subprocess.Popen` so no real network
fires.
"""
from __future__ import annotations

import subprocess
from typing import Any

import pytest

from evomas.exceptions.errors import EvomasError
from evomas.utils import ollama_preflight


def _stub_popen(returncode: int, lines: list[str]) -> type:
    """Build a `subprocess.Popen`-like stand-in. The real Popen iterator
    yields lines from stdout; we return a list of pre-canned strings."""
    class _Proc:
        def __init__(self, *a: Any, **kw: Any) -> None:
            self.returncode = returncode
            self.stdout = iter(lines + [""] if lines else [])

        def wait(self) -> None:
            pass

    return _Proc


def test_skips_when_no_ollama_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """A config that doesn't reference any Ollama model never invokes
    Popen and returns without error."""
    cfg = {"agents": {"a": {"model": "gemini/gemini-pro"}}}
    # Verify Popen is NEVER constructed. Replace it with a sentinel
    # that explodes if called.
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **kw: pytest.fail("should not invoke Popen for non-Ollama configs"))
    ollama_preflight.preflight_models(cfg)


def test_skips_when_already_pulled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every required model already on disk → no pull fires."""
    cfg = {"agents": {"a": {"model": "ollama/qwen3:8b"}}}
    monkeypatch.setattr(ollama_preflight, "_list_pulled", lambda: {"ollama/qwen3:8b"})
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **kw: pytest.fail("Popen invoked for an already-pulled model"))
    ollama_preflight.preflight_models(cfg)


def test_raises_when_ollama_binary_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """`ollama` not on PATH → FileNotFoundError on Popen → wrap in
    `EvomasError` with a clear message pointing the user at the
    install URL."""
    cfg = {"agents": {"a": {"model": "ollama/qwen3:8b"}}}
    monkeypatch.setattr(ollama_preflight, "_list_pulled", lambda: set())

    def fake_popen(*a: Any, **kw: Any) -> Any:
        raise FileNotFoundError("ollama not on PATH")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    with pytest.raises(EvomasError, match="ollama"):
        ollama_preflight.preflight_models(cfg)


def test_raises_on_pull_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """`ollama pull` returns a non-zero exit code (registry 404,
    network failure, etc.) → fail-fast with `EvomasError` BEFORE the
    agent loop tries the missing model."""
    cfg = {"agents": {"a": {"model": "ollama/does-not-exist:7b"}}}
    monkeypatch.setattr(ollama_preflight, "_list_pulled", lambda: set())
    monkeypatch.setattr(
        subprocess, "Popen",
        _stub_popen(returncode=1, lines=["pulling manifest", "Error: model not found"]),
    )

    with pytest.raises(EvomasError, match="exit code 1"):
        ollama_preflight.preflight_models(cfg)


def test_pull_forwards_ollama_host_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """When OLLAMA_BASE_URL points at a remote daemon (LAN GPU box,
    cloud Ollama, etc.), the preflight MUST pull to that same host —
    otherwise the local CLI daemon gets the model while the agents
    try to reach the remote one and 404 anyway. The fix is to forward
    `OLLAMA_HOST` to the subprocess from `_ollama_base_url()`."""
    cfg = {"agents": {"a": {"model": "ollama/qwen3:8b"}}}
    monkeypatch.setattr(ollama_preflight, "_list_pulled", lambda: set())
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.50:11434")

    captured: dict[str, Any] = {}

    class _CaptureProc:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["env"] = kwargs.get("env") or {}
            self.returncode = 0
            self.stdout = iter(["success"])
        def wait(self) -> None: pass
    monkeypatch.setattr(subprocess, "Popen", _CaptureProc)

    ollama_preflight.preflight_models(cfg)

    # The forwarded env must carry OLLAMA_HOST set to the same base URL
    # we'd probe with `/api/tags`, so the pull lands on the right daemon.
    assert captured["env"].get("OLLAMA_HOST") == "http://192.168.1.50:11434"


def test_event_sink_receives_progress_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """When `event_sink` is provided (the API-worker case), the helper
    streams `preflight_pull_start` / `preflight_log` / `preflight_pull_done`
    events for each missing model."""
    cfg = {"agents": {"a": {"model": "ollama/qwen3:8b"}}}
    monkeypatch.setattr(ollama_preflight, "_list_pulled", lambda: set())
    monkeypatch.setattr(
        subprocess, "Popen",
        _stub_popen(returncode=0, lines=["pulling manifest", "downloading abc...", "success"]),
    )

    events: list[dict[str, Any]] = []
    ollama_preflight.preflight_models(cfg, event_sink=events.append)

    kinds = [e["type"] for e in events]
    assert "preflight_pull_start" in kinds
    assert "preflight_log" in kinds
    assert kinds[-1] == "preflight_pull_done"
    assert events[-1]["code"] == 0


def test_pulls_every_missing_model_in_multi_model_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """A config whose agents use DIFFERENT models (e.g. a small router
    on qwen3:8b paired with a beefier patcher on qwen3.5:9b) must pull
    BOTH if neither is on disk. Pull happens sequentially in the order
    the models first appear in `cfg.agents`; each gets its own
    `preflight_pull_*` SSE event triple. Duplicate model references
    across agents collapse to one pull (deduplication)."""
    cfg = {
        "agents": {
            "router":  {"model": "ollama/qwen3:8b"},
            "patcher": {"model": "ollama/qwen3.5:9b"},
            # Duplicate of `router`'s model — must NOT trigger a second pull.
            "ensembler": {"model": "ollama/qwen3:8b"},
            # Non-Ollama provider — skipped entirely.
            "remote": {"model": "gemini/gemini-pro"},
        }
    }
    monkeypatch.setattr(ollama_preflight, "_list_pulled", lambda: set())
    pulled_calls: list[list[str]] = []

    class _CaptureProc:
        def __init__(self, cmd: list[str], *a: Any, **kw: Any) -> None:
            pulled_calls.append(cmd)
            self.returncode = 0
            self.stdout = iter(["success"])
        def wait(self) -> None: pass
    monkeypatch.setattr(subprocess, "Popen", _CaptureProc)

    events: list[dict[str, Any]] = []
    ollama_preflight.preflight_models(cfg, event_sink=events.append)

    # Exactly two `ollama pull` invocations — one per UNIQUE Ollama model.
    # The Gemini agent's model is skipped (different provider); the
    # duplicate `qwen3:8b` reference collapses.
    pull_cmds = [c for c in pulled_calls if c[:2] == ["ollama", "pull"]]
    pulled_names = [c[2] for c in pull_cmds]
    assert pulled_names == ["qwen3:8b", "qwen3.5:9b"], (
        f"expected sequential pulls of both unique models, got {pulled_names}"
    )

    # SSE event stream covers both models: one `pull_start` + at least
    # one `log` + one `pull_done` per model.
    starts  = [e for e in events if e["type"] == "preflight_pull_start"]
    dones   = [e for e in events if e["type"] == "preflight_pull_done"]
    assert {e["model"] for e in starts} == {"ollama/qwen3:8b", "ollama/qwen3.5:9b"}
    assert {e["model"] for e in dones}  == {"ollama/qwen3:8b", "ollama/qwen3.5:9b"}
    assert all(e["code"] == 0 for e in dones)


def test_multi_model_pull_fail_fast_aborts_remaining(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the FIRST pull in a multi-model config fails, the helper
    raises `EvomasError` and never starts pulling subsequent models.
    Prevents a partially-broken pull queue from silently downloading
    half the configured models before bailing."""
    cfg = {
        "agents": {
            "a": {"model": "ollama/does-not-exist:0b"},   # this one will fail
            "b": {"model": "ollama/qwen3.5:9b"},          # should NEVER be attempted
        }
    }
    monkeypatch.setattr(ollama_preflight, "_list_pulled", lambda: set())
    captured: list[list[str]] = []

    class _FailFirstProc:
        def __init__(self, cmd: list[str], *a: Any, **kw: Any) -> None:
            captured.append(cmd)
            # First pull (does-not-exist) fails with exit 1.
            self.returncode = 1 if "does-not-exist:0b" in cmd else 0
            self.stdout = iter(["pulling manifest", "Error: model not found"])
        def wait(self) -> None: pass
    monkeypatch.setattr(subprocess, "Popen", _FailFirstProc)

    with pytest.raises(EvomasError, match="does-not-exist:0b"):
        ollama_preflight.preflight_models(cfg)

    # Only ONE pull was attempted — the second model was never reached.
    pull_targets = [c[2] for c in captured if c[:2] == ["ollama", "pull"]]
    assert pull_targets == ["does-not-exist:0b"]


def test_bare_model_names_normalized_to_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    """`model: "qwen3:8b"` (no prefix) is treated as `ollama/qwen3:8b`
    — the provider router defaults to Ollama for unprefixed names, so
    the preflight has to match that behavior or it would skip exactly
    the models that need pulling most."""
    cfg = {"agents": {"a": {"model": "qwen3:8b"}}}
    pulled_set: set[str] = set()  # pretend none pulled
    monkeypatch.setattr(ollama_preflight, "_list_pulled", lambda: pulled_set)
    monkeypatch.setattr(
        subprocess, "Popen",
        _stub_popen(returncode=0, lines=["success"]),
    )

    events: list[dict[str, Any]] = []
    ollama_preflight.preflight_models(cfg, event_sink=events.append)
    # The bare name was promoted to `ollama/qwen3:8b` and a pull fired.
    assert any(e.get("model") == "ollama/qwen3:8b" for e in events)
