"""The generated notebook's env cell must carry the *effective*
`OLLAMA_BASE_URL` — the one `opendraco/.env` set for the run — not a
hardcoded localhost that silently points a reproduction at the wrong
daemon.
"""
from __future__ import annotations

import pytest

from opendraco.utils import notebook as nb

CONFIG = {
    "id": "chain",
    "entry": "patcher",
    "end": "patcher",
    "edges": [],
    "agents": {"patcher": {"class": "Patcher", "model": "ollama/qwen3.5:9b"}},
}


def _env_cell(monkeypatch: pytest.MonkeyPatch, value: str | None) -> str:
    if value is None:
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("OLLAMA_BASE_URL", value)
    _, notebook = nb.build_notebook_for_inputs(
        instance_ids=["custom-EvoMas-evomas-instance-trivial-18757fd"],
        config_data=CONFIG,
        evaluator="apply_and_test",
    )
    cells = [
        c["source"] for c in notebook["cells"]
        if c["cell_type"] == "code" and "os.environ['OLLAMA_BASE_URL']" in c["source"]
    ]
    assert len(cells) == 1, f"expected exactly one env cell, got {len(cells)}"
    return cells[0]


def test_bakes_the_configured_remote_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    src = _env_cell(monkeypatch, "http://192.168.1.50:11434")
    assert "os.environ['OLLAMA_BASE_URL'] = 'http://192.168.1.50:11434'" in src
    assert "localhost" not in src


def test_falls_back_to_localhost_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    src = _env_cell(monkeypatch, None)
    assert "os.environ['OLLAMA_BASE_URL'] = 'http://localhost:11434'" in src


def test_strips_quotes_left_by_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    # opendraco/.env.example quotes the value; a raw pass-through would
    # emit a nested-quote syntax error in the generated cell.
    src = _env_cell(monkeypatch, '"http://gpubox:11434"')
    assert "os.environ['OLLAMA_BASE_URL'] = 'http://gpubox:11434'" in src


def test_generated_env_cell_is_valid_python(monkeypatch: pytest.MonkeyPatch) -> None:
    # A value containing a quote must not break the emitted source.
    src = _env_cell(monkeypatch, "http://host'name:11434")
    compile(src, "<env-cell>", "exec")


def test_env_cell_matches_the_shared_accessor(monkeypatch: pytest.MonkeyPatch) -> None:
    from opendraco.utils.ollama_preflight import ollama_base_url
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://gpubox:9999")
    src = _env_cell(monkeypatch, "http://gpubox:9999")
    assert f"os.environ['OLLAMA_BASE_URL'] = {ollama_base_url()!r}" in src
