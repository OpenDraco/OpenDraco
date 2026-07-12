"""Locator agent — scripted-LLM tests that drive `run()` end-to-end without
Ollama, MCP, or a real workspace. The fake mocks two surfaces:

  * `_invoke` — returns the next response from a scripted iterator, so the
    LLM loop sees deterministic per-iteration content + tool-call shapes.
  * `_call_tool` — returns canned tool results, bypassing MCP dispatch.

Everything else (prompt rendering, message history, `_capture_response_text`,
stop-condition handling, max_iters cap, summary fallback) runs the real
production code. The tests pin the Locator's loop exit paths and the prompt
discipline added after the qwen3.5:9b runaway-narration logs.
"""
from __future__ import annotations

from typing import Any

import pytest

from evomas.agents.types.locator import LocatorAgent


# ─── Scripted fake-LLM helper ────────────────────────────────────────────────
class _StubResponse:
    """Mimics the LangChain `AIMessage` shape the loop reads:
      * `.content` — string or list-of-parts; consumed by `_capture_response_text`
      * `.tool_calls` — list of `{name, args, id}` dicts; consumed by
        `_extract_tool_calls`. Empty list means "no tool calls — exit loop".
    """

    def __init__(
        self,
        content: Any = "",
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class _ScriptedLocator(LocatorAgent):
    """Real `LocatorAgent` so DEFAULT_SYSTEM/USER/CONFIG/TOOLS exercise the
    production code paths; only `_invoke`, `_extract_tool_calls`,
    `_bound_tools`, and `_call_tool` are replaced so the loop runs without
    Ollama, MCP, or a workspace."""

    def __init__(
        self,
        responses: list[_StubResponse],
        tool_outputs: dict[str, Any] | None = None,
        config_block: dict[str, Any] | None = None,
    ) -> None:
        # `think: False` keeps the streaming thinking-buffer path quiet —
        # `_capture_response_text` still runs normally.
        block = {"think": False, **(config_block or {})}
        super().__init__(config_block=block)
        self._scripted = iter(responses)
        self._tool_outputs = tool_outputs or {}
        self.tool_calls_made: list[tuple[str, dict[str, Any]]] = []
        self.iter_count = 0

    def make_llm(self) -> Any:  # type: ignore[override]
        return object()  # never invoked

    def _invoke(self, llm: Any, messages: list[Any]) -> Any:  # type: ignore[override]
        self.iter_count += 1
        try:
            return next(self._scripted)
        except StopIteration:
            # The test under-scripted the iterator. Bubble a clear failure
            # instead of the opaque StopIteration the loop would otherwise
            # surface.
            raise AssertionError(
                f"_invoke called more times than scripted (iter {self.iter_count})"
            )

    def _extract_tool_calls(self, response: Any) -> list[dict[str, Any]]:  # type: ignore[override]
        return list(getattr(response, "tool_calls", []) or [])

    def _bound_tools(self) -> list[Any]:  # type: ignore[override]
        return []

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:  # type: ignore[override]
        self.tool_calls_made.append((name, arguments))
        return self._tool_outputs.get(name, f"<no canned result for {name}>")


def _state() -> dict[str, Any]:
    """Minimum state the LLM loop reads — empty workspace + issue is fine
    since no real tool actually touches the filesystem."""
    return {
        "issue_text": "L031 rule fires when no JOIN is present.",
        "workspace_path": "/tmp/fake-workspace",
        "instance": {"instance_id": "sqlfluff__sqlfluff-1625"},
    }


# ─── Tests ───────────────────────────────────────────────────────────────────
def test_locator_stops_when_files_block_emitted_without_tool_call() -> None:
    """Cleanest exit: the model returns the `<files>` block on iter 1 with no
    tool calls. The loop hits the `no tool calls — stopping loop` branch and
    `delta["locator"]` carries the response verbatim."""
    agent = _ScriptedLocator(
        responses=[_StubResponse(content="<files>src/sqlfluff/rules/L031.py</files>")],
    )
    delta = agent.run(_state())

    assert agent.iter_count == 1
    assert agent.tool_calls_made == []
    assert delta["locator"] == "<files>src/sqlfluff/rules/L031.py</files>"


def test_locator_runs_search_then_read_then_answers() -> None:
    """Happy multi-iteration path: search → read → answer. Three iterations,
    two tool calls in order, final delta is the `<files>` block."""
    responses = [
        _StubResponse(tool_calls=[{
            "name": "search_code",
            "args": {"query": "L031", "directory": "/tmp/fake-workspace"},
            "id": "c1",
        }]),
        _StubResponse(tool_calls=[{
            "name": "read_file",
            "args": {"path": "/tmp/fake-workspace/src/sqlfluff/rules/L031.py"},
            "id": "c2",
        }]),
        _StubResponse(content="<files>src/sqlfluff/rules/L031.py</files>"),
    ]
    tool_outputs = {
        "search_code": [{"path": "src/sqlfluff/rules/L031.py", "score": 4.2, "snippet": "..."}],
        "read_file":   "1: class Rule_L031(BaseRule):\n2:     ...\n",
    }
    agent = _ScriptedLocator(responses=responses, tool_outputs=tool_outputs)
    delta = agent.run(_state())

    assert agent.iter_count == 3
    assert [name for name, _ in agent.tool_calls_made] == ["search_code", "read_file"]
    assert delta["locator"] == "<files>src/sqlfluff/rules/L031.py</files>"


def test_locator_respects_max_iters_cap() -> None:
    """When every iteration emits a tool call (model never gives up),
    `max_iters` caps the loop. The fallback summary path fires because
    `_final_response_text` is still empty at the cap — one extra `_invoke`
    runs with no tools bound. Production `max_iters` is 6 (see
    `LocatorAgent.DEFAULT_CONFIG`); we use 3 here for speed."""
    looping = [
        _StubResponse(tool_calls=[{"name": "search_code", "args": {}, "id": f"c{i}"}])
        for i in range(3)
    ]
    fallback_answer = _StubResponse(content="<files>fallback.py</files>")
    agent = _ScriptedLocator(
        responses=[*looping, fallback_answer],
        tool_outputs={"search_code": []},
        config_block={"max_iters": 3},
    )
    delta = agent.run(_state())

    # 3 loop iterations + 1 fallback _invoke = 4 scripted responses consumed.
    assert agent.iter_count == 4
    assert len(agent.tool_calls_made) == 3
    assert delta["locator"] == "<files>fallback.py</files>"


def test_locator_max_iters_cap_does_not_hang_when_fallback_also_empties() -> None:
    """Belt-and-braces: if the fallback also returns empty content, the loop
    finishes cleanly without raising. Producer slot ends up empty."""
    looping = [
        _StubResponse(tool_calls=[{"name": "list_files", "args": {}, "id": f"c{i}"}])
        for i in range(2)
    ]
    empty_fallback = _StubResponse(content="")
    agent = _ScriptedLocator(
        responses=[*looping, empty_fallback],
        tool_outputs={"list_files": []},
        config_block={"max_iters": 2},
    )
    delta = agent.run(_state())

    assert agent.iter_count == 3  # 2 loop + 1 fallback
    assert delta["locator"] == ""


def test_locator_prompt_carries_stop_discipline() -> None:
    """Regression: the prompt tightening landed alongside this test is what
    keeps qwen3.5:9b from running until max_iters. If a future edit drifts
    away from the discipline phrasing the locator's runaway-narration
    behaviour comes back. Cheap string-presence assertions over
    DEFAULT_SYSTEM / DEFAULT_USER / DEFAULT_CONFIG."""
    system = LocatorAgent.DEFAULT_SYSTEM
    user = LocatorAgent.DEFAULT_USER
    cfg = LocatorAgent.DEFAULT_CONFIG

    # Stop rule + budget present in the system prompt.
    assert "Stop rule" in system
    assert "STOP calling tools" in system
    assert "≤ 4 tool calls" in system
    # Anti-patterns block calls out the specific failure modes seen in the
    # 7cef53fe.log run.
    assert "let me verify" in system
    assert "one more file" in system
    # Inline stop reminder in the user template (system prompts get buried
    # at long context lengths).
    assert "STOP" in user
    # Hyperparameter floor — chain.json can still override.
    assert cfg["max_iters"] == 6
    assert cfg["temperature"] == 0.2
    assert cfg["num_predict"] == 512
