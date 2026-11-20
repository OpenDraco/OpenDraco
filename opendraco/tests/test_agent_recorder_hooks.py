"""Agents feed the ATIF recorder: prompts, every LLM call (with tool-call ids
and per-call tokens), full tool results; `_wrap` reports node start/end."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from opendraco.agents import base_agent as base_agent_mod
from opendraco.agents.llm_tool_agent import LLMToolAgent
from opendraco.core.workflow.graph_builder import _wrap
from opendraco.utils.atif import RunRecorder, validate_trajectory

USAGE = {"input": 7, "output": 2, "total": 9}


class _ScriptedAgent(LLMToolAgent):
    """LLMToolAgent whose LLM replies come from a script (no network)."""

    name = "scripted"

    def __init__(self) -> None:
        super().__init__(config_block={"think": False})
        self.tool_policy = None  # any tool allowed

    def make_llm(self, **_kw: Any) -> Any:  # type: ignore[override]
        return object()

    def _bound_tools(self) -> list[Any]:  # type: ignore[override]
        return []


class _FakeMCP:
    def __init__(self, results: dict[str, Any]) -> None:
        self.results = results

    def call(self, name: str, args: dict[str, Any]) -> Any:
        value = self.results[name]
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def recorder(tmp_path: Path):
    run = RunRecorder(
        tmp_path / "run", run_info={"run_id": "r1", "instance_ids": ["i"]},
        agent_extra={}, instances=[("i", "issue")],
    )
    inst = run.instance("i")
    return inst, inst.begin_activation("scripted", {}, model_name=None, tool_definitions=[])


def _script(monkeypatch: pytest.MonkeyPatch, replies: list[AIMessage]) -> None:
    queue = list(replies)

    def fake_llm_invoke(llm, messages, **_kw):
        return queue.pop(0), "thought", dict(USAGE)

    monkeypatch.setattr(base_agent_mod, "llm_invoke", fake_llm_invoke)


def _sub(inst) -> dict:
    return inst.to_dict()["subagent_trajectories"][0]


def test_invoke_records_llm_call_with_ids(monkeypatch, recorder):
    inst, rec = recorder
    response = AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"path": "a.py"}, "id": None}])
    _script(monkeypatch, [response])
    agent = _ScriptedAgent()
    agent.recorder = rec
    returned = agent._invoke(object(), [])  # type: ignore[arg-type]
    assert returned.tool_calls[0]["id"] == "call_0_read_file"
    step = _sub(inst)["steps"][-1]
    assert step["tool_calls"][0] == {
        "tool_call_id": "call_0_read_file", "function_name": "read_file", "arguments": {"path": "a.py"},
    }
    assert step["reasoning_content"] == "thought"
    assert step["metrics"] == {"prompt_tokens": 7, "completion_tokens": 2}


def test_loop_records_prompts_calls_and_results(monkeypatch, recorder):
    inst, rec = recorder
    _script(monkeypatch, [
        AIMessage(content="", tool_calls=[{"name": "read_file", "args": {"path": "a.py"}, "id": "c1"}]),
        AIMessage(content="final answer"),
    ])
    agent = _ScriptedAgent()
    agent.prompts = {"system": "SYS", "user": "USER {issue}"}
    agent.mcp = _FakeMCP({"read_file": "file body"})
    agent.recorder = rec
    agent.run({"issue_text": "bug"})
    sub = _sub(inst)
    assert [s["source"] for s in sub["steps"]] == ["system", "user", "agent", "agent"]
    assert sub["steps"][0]["message"] == "SYS"
    assert sub["steps"][1]["message"] == "USER bug"
    assert sub["steps"][2]["observation"]["results"] == [{"source_call_id": "c1", "content": "file body"}]
    assert sub["steps"][3]["message"] == "final answer"
    assert validate_trajectory(inst.to_dict()) == []


def test_tool_exception_recorded_as_error(monkeypatch, recorder):
    inst, rec = recorder
    _script(monkeypatch, [
        AIMessage(content="", tool_calls=[{"name": "read_file", "args": {}, "id": "c1"}]),
        AIMessage(content="gave up"),
    ])
    agent = _ScriptedAgent()
    agent.mcp = _FakeMCP({"read_file": RuntimeError("no such file")})
    agent.recorder = rec
    agent.run({})
    res = _sub(inst)["steps"][-2]["observation"]["results"][0]
    assert res["content"].startswith("Error:")
    assert res["extra"] == {"error": True}
    assert _sub(inst)["steps"][-1]["message"] == "gave up"


class _BrokenRecorder:
    """A recorder whose every call raises."""

    def __getattr__(self, name: str):
        def boom(*_a: Any, **_k: Any) -> None:
            raise TypeError("recorder broke")
        return boom


def test_a_failing_recorder_never_changes_what_the_agent_sees(monkeypatch):
    _script(monkeypatch, [
        AIMessage(content="", tool_calls=[{"name": "read_file", "args": {}, "id": "c1"}]),
        AIMessage(content="final"),
    ])
    seen: list[Any] = []
    agent = _ScriptedAgent()
    agent.mcp = _FakeMCP({"read_file": "file body"})
    agent.on_tool = lambda name, args, result: seen.append(result)
    agent.recorder = _BrokenRecorder()  # type: ignore[assignment]
    delta = agent.run({})
    assert delta["scripted"] == "final"
    assert seen == ["file body"]


def test_programmatic_tool_call_is_recorded(recorder):
    inst, rec = recorder
    agent = _ScriptedAgent()
    agent.mcp = _FakeMCP({"apply_patch": {"ok": True}})
    agent.recorder = rec
    agent._call_tool("apply_patch", {"p": 1})
    step = _sub(inst)["steps"][-1]
    assert step["llm_call_count"] == 0
    assert step["tool_calls"][0]["function_name"] == "apply_patch"


def test_no_recorder_no_change(monkeypatch):
    _script(monkeypatch, [AIMessage(content="hello")])
    agent = _ScriptedAgent()
    assert agent.recorder is None
    delta = agent.run({})
    assert delta["scripted"] == "hello"


def test_tool_definitions_default_empty():
    assert _ScriptedAgent().tool_definitions() == []


def _node_agent(run, **hooks) -> SimpleNamespace:
    return SimpleNamespace(name="n", run=run, on_run_start=hooks.get("start"), on_run_end=hooks.get("end"))


def test_wrap_calls_run_hooks():
    seen: list[tuple[str, Any]] = []
    agent = _node_agent(
        lambda state: {"n": "out"},
        start=lambda state: seen.append(("start", state.get("x"))),
        end=lambda delta: seen.append(("end", delta)),
    )
    assert _wrap(agent, [])({"x": 1}) == {"n": "out"}  # type: ignore[arg-type]
    assert seen == [("start", 1), ("end", {"n": "out"})]


def test_wrap_hook_failure_does_not_break_node():
    def bad(_arg):
        raise RuntimeError("hook broke")

    agent = _node_agent(lambda state: {"n": "out"}, start=bad, end=bad)
    assert _wrap(agent, [])({}) == {"n": "out"}  # type: ignore[arg-type]


def test_wrap_reports_end_when_agent_fails():
    ends: list[Any] = []

    def failing(_state):
        raise ValueError("agent broke")

    agent = _node_agent(failing, end=ends.append)
    delta = _wrap(agent, [])({})  # type: ignore[arg-type]
    assert ends == [delta] and "errors" in delta
