"""Tests for the LLMToolAgent producer-slot writing introduced so hand-off
chips carry the agent's real artifact (final response text for most agents,
the workspace diff for the Patcher) instead of just the `thinking` buffer."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from evomas.agents.llm_tool_agent import LLMToolAgent
from evomas.agents.types.patcher import PatcherAgent


class _StubResponse:
    """Mimic the LangChain message shape that LLMToolAgent inspects: a
    `.content` attribute that's a plain string."""

    def __init__(self, content: Any) -> None:
        self.content = content


class _FakeLLMAgent(LLMToolAgent):
    """LLMToolAgent variant that bypasses the LLM + tool-binding layer so we
    can drive the loop deterministically. `_invoke` returns whatever response
    object the test stashed on `self._next_response` and `_extract_tool_calls`
    returns an empty list so the loop exits after one iteration."""

    name = "fake_llm"

    def __init__(self, *, response_content: Any, **kw: Any) -> None:
        super().__init__(config_block={"think": False}, **kw)
        self._next_response = _StubResponse(response_content)

    def make_llm(self) -> Any:  # type: ignore[override]
        return object()  # never actually invoked

    def _invoke(self, llm: Any, messages: list[Any]) -> Any:  # type: ignore[override]
        # Skip the real streaming path; pretend the LLM produced the stub.
        # We don't update self._thinking so the test sees the empty default.
        return self._next_response

    def _extract_tool_calls(self, response: Any) -> list[dict[str, Any]]:  # type: ignore[override]
        return []

    def _bound_tools(self) -> list[Any]:  # type: ignore[override]
        return []


def test_run_returns_thinking_and_producer_slot_for_str_content() -> None:
    """The base LLMToolAgent now writes both `thinking` (accumulator) and a
    producer-slot keyed by the agent's node name. Plain-string content goes
    straight to the slot."""
    agent = _FakeLLMAgent(response_content="hello world")
    delta = agent.run({})
    assert delta["thinking"] == ""
    assert delta["fake_llm"] == "hello world"


def test_run_handles_list_of_content_parts() -> None:
    """Some providers (Claude tool-calls, Gemini structured output) deliver
    content as a list of `{type, text}` parts; the capture helper concatenates
    the text fragments."""
    agent = _FakeLLMAgent(response_content=[
        {"type": "text", "text": "first "},
        {"type": "text", "text": "second"},
    ])
    delta = agent.run({})
    assert delta["fake_llm"] == "first second"


def test_run_empty_response_keeps_producer_slot_empty() -> None:
    """When the LLM returns no usable content, the producer slot ends up
    empty rather than carrying a stale value from a previous run."""
    agent = _FakeLLMAgent(response_content="")
    delta = agent.run({})
    assert delta["fake_llm"] == ""


def test_run_pins_workspace_path_on_instance() -> None:
    """Subclasses (PatcherAgent) read `self._last_workspace_path` to snapshot
    the diff in `_producer_value()`. The base loop must pin it from state."""
    agent = _FakeLLMAgent(response_content="ok")
    agent.run({"workspace_path": "/tmp/some/repo"})
    assert agent._last_workspace_path == "/tmp/some/repo"


# ─── PatcherAgent.diff override ──────────────────────────────────────────

def _init_git_repo(tmp_path: Path) -> Path:
    """Build a tiny git repo with one tracked file at `tmp_path`."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_patcher_producer_value_returns_workspace_diff(tmp_path: Path) -> None:
    """When the Patcher finishes and the workspace has uncommitted changes,
    `_producer_value()` should return the unified diff — that's the chip
    payload downstream agents care about."""
    repo = _init_git_repo(tmp_path)
    # Introduce a known modification post-commit so `git diff` produces a
    # patch with predictable line content.
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n")

    agent = PatcherAgent(config_block={"think": False})
    agent._last_workspace_path = str(repo)
    agent._final_response_text = "should not be used"

    out = agent._producer_value()
    assert "diff --git" in out
    assert "-    return a + b" in out
    assert "+    return a - b" in out


def test_patcher_producer_value_falls_back_to_response_when_no_diff(
    tmp_path: Path,
) -> None:
    """When the workspace path is unset or `git diff` is empty (e.g. the
    apply_description_fix tool ran in a sibling fan-out branch first), the
    Patcher's chip falls back to the LLM response text instead of writing an
    empty string."""
    repo = _init_git_repo(tmp_path)  # clean repo — no uncommitted changes
    agent = PatcherAgent(config_block={"think": False})
    agent._last_workspace_path = str(repo)
    agent._final_response_text = "ok"

    assert agent._producer_value() == "ok"


def test_patcher_producer_value_no_workspace_uses_response() -> None:
    """No workspace path pinned at all → use the response text directly,
    skipping the `git diff` shell-out."""
    agent = PatcherAgent(config_block={"think": False})
    agent._last_workspace_path = ""
    agent._final_response_text = "minimal-ack"
    assert agent._producer_value() == "minimal-ack"
