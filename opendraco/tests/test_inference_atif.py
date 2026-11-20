"""The inference worker records every run as ATIF (and only ATIF).

A real two-node graph (`locator` → `patcher`, built by `build_graph`) runs
scripted LLM agents; everything else the worker touches (config, clone,
diff, preflight) is stubbed so a run is a few instant steps."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage

from api.routers import inference
from opendraco.agents import base_agent as base_agent_mod
from opendraco.agents.llm_tool_agent import LLMToolAgent
from opendraco.exceptions.errors import OpendracoError
from opendraco.utils import atif
from opendraco.utils.atif import validate_trajectory

IID1, IID2 = "django__django-10973", "astropy__astropy-12907"
PATCH = "diff --" + "git a/x b/x"
CFG = {
    "id": "chain", "entry": "locator", "end": "patcher",
    "edges": [{"from": "locator", "to": "patcher"}],
}


class _Scripted(LLMToolAgent):
    def __init__(self, node: str) -> None:
        super().__init__(config_block={"think": False}, node_name=node)
        self.tool_policy = None
        self.fallback_enabled = False
        self.prompts = {"system": f"you are {node}", "user": "fix {issue}"}

    def make_llm(self, **_kw: Any) -> Any:  # type: ignore[override]
        return object()

    def _bound_tools(self) -> list[Any]:  # type: ignore[override]
        return []


class _MCP:
    def call(self, name: str, args: dict[str, Any]) -> Any:
        return f"{name} result"


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    import opendraco.config.history as history
    import opendraco.config.loader as loader
    import opendraco.core.workflow.runner as runner
    import opendraco.utils.ollama_preflight as preflight
    import opendraco.utils.patch as patch_utils
    import opendraco.utils.workspace as workspace

    instances = tmp_path / "instances.jsonl"
    instances.write_text("".join(
        json.dumps({"instance_id": iid, "repo": "r/r", "base_commit": "abc",
                    "problem_statement": f"bug in {iid}", "hints_text": "look at x"}) + "\n"
        for iid in (IID1, IID2)
    ), encoding="utf-8")
    logs = tmp_path / "inference_logs"
    for name in ("PREDICTIONS_DIR", "PREDICTION_TEXT_LOGS_DIR", "PREDICTION_CONFIGS_DIR"):
        monkeypatch.setattr(inference, name, tmp_path / name)
    monkeypatch.setattr(inference, "INFERENCE_INTERNAL_LOGS_DIR", logs)
    monkeypatch.setattr(inference, "INSTANCES_PATH", instances)
    monkeypatch.delenv("GRAPHECTORY_URL", raising=False)

    state = SimpleNamespace(preflight=lambda cfg, event_sink: None, on_llm=None, logs=logs, active=[])
    monkeypatch.setattr(loader, "load_config", lambda name: dict(CFG))
    monkeypatch.setattr(history, "current_sha", lambda name: "abc1234")
    monkeypatch.setattr(preflight, "preflight_models",
                        lambda cfg, event_sink: state.preflight(cfg, event_sink))

    def build(cfg: dict) -> dict:
        agents = {n: _Scripted(n) for n in ("locator", "patcher")}
        for a in agents.values():
            a.mcp = _MCP()
        return agents

    monkeypatch.setattr(runner, "_build_agents", build)
    monkeypatch.setattr(patch_utils, "generate_diff_impl", lambda path: PATCH)
    monkeypatch.setattr(workspace, "clone_workspace",
                        lambda iid, repo, commit: SimpleNamespace(path=tmp_path))

    def fake_llm_invoke(llm, messages, agent_name: str = "", **_kw):
        state.active.append(inference.inference_active())
        if state.on_llm:
            state.on_llm(agent_name)
        tool_turn = agent_name == "locator" and not any(isinstance(m, AIMessage) for m in messages)
        if tool_turn:
            reply = AIMessage(content="", tool_calls=[{"name": "search_code", "args": {"q": "bug"}, "id": "c1"}])
        else:
            reply = AIMessage(content=f"{agent_name} done")
        return reply, f"{agent_name} thinks", {"input": 10, "output": 2, "total": 12}

    monkeypatch.setattr(base_agent_mod, "llm_invoke", fake_llm_invoke)
    return state


def _run(ids=(IID1, IID2)) -> list[dict[str, Any]]:
    async def drain() -> list[str]:
        resp = await inference.run_inference(
            inference.InferenceRequest(instance_ids=list(ids), config="chain"),
        )
        return [chunk async for chunk in resp.body_iterator]

    return [json.loads(c.removeprefix("data: ")) for c in asyncio.run(drain())]


def _doc(env: SimpleNamespace, run_id: str, iid: str) -> dict:
    path = env.logs / f"prediction-{run_id}" / iid / "trajectory.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _run_id(events: list[dict]) -> str:
    return next(e["run_id"] for e in events if e["type"] == "run_id")


def test_run_writes_valid_atif_per_instance(env: SimpleNamespace) -> None:
    events = _run()
    assert events[-1]["type"] == "done"
    run_id = _run_id(events)
    for iid in (IID1, IID2):
        doc = _doc(env, run_id, iid)
        assert validate_trajectory(doc) == []
        assert doc["extra"]["status"] == "done"
        assert doc["extra"]["model_patch"] == PATCH
        assert doc["extra"]["run"]["config_sha"] == "abc1234"
        assert doc["agent"]["extra"]["edges"] == CFG["edges"]
        assert doc["steps"][0]["message"] == f"bug in {iid}\n\n## Hints\nlook at x"
        dispatch = [s for s in doc["steps"] if s["source"] == "agent"]
        assert [s["tool_calls"][0]["arguments"]["agent"] for s in dispatch] == ["locator", "patcher"]
        handoffs = dispatch[0]["observation"]["results"][0]["extra"]["handoffs"]
        assert [h["to"] for h in handoffs] == ["patcher"]
        assert "locator" in dispatch[1]["tool_calls"][0]["arguments"]["inputs"]
        loc = doc["subagent_trajectories"][0]
        assert loc["trajectory_id"] == "locator#1"
        assert [s["source"] for s in loc["steps"]] == ["system", "user", "agent", "agent"]
        assert loc["steps"][2]["observation"]["results"][0]["content"] == "search_code result"
        assert doc["final_metrics"]["extra"]["per_agent"]["locator"]["total"] == 24
    assert not list(env.logs.glob("*.ndjson"))


def test_sse_keeps_its_live_events(env: SimpleNamespace) -> None:
    types = {e["type"] for e in _run()}
    assert {"run_meta", "instance_start", "agent_input", "agent_event", "handoff",
            "tool_call", "response", "instance_done", "done"} <= types


def test_preflight_error_marks_all_instances_error(env: SimpleNamespace) -> None:
    def fail(cfg: Any, event_sink: Any) -> None:
        raise OpendracoError("no model")

    env.preflight = fail
    events = _run()
    assert events[-1]["type"] == "error"
    run_id = _run_id(events)
    for iid in (IID1, IID2):
        doc = _doc(env, run_id, iid)
        assert doc["extra"]["status"] == "error"
        assert doc["steps"][-1]["source"] == "system"
        assert "no model" in doc["steps"][-1]["message"]
        assert validate_trajectory(doc) == []


def test_cancel_marks_remaining_cancelled(env: SimpleNamespace) -> None:
    def cancel(agent_name: str) -> None:
        inference._cancel_flags[IID1] = True

    env.on_llm = cancel
    events = _run()
    assert events[-1]["type"] == "cancelled"
    run_id = _run_id(events)
    for iid in (IID1, IID2):
        assert _doc(env, run_id, iid)["extra"]["status"] == "cancelled"


def test_unexpected_error_marks_unfinished_error(env: SimpleNamespace, monkeypatch) -> None:
    import opendraco.core.workflow.state_factory as state_factory

    def boom(*_a: Any) -> Any:
        raise RuntimeError("state broke")

    monkeypatch.setattr(state_factory, "build_initial_state", boom)
    events = _run()
    assert events[-1]["type"] == "error"
    doc = _doc(env, _run_id(events), IID1)
    assert doc["extra"]["status"] == "error"
    assert "state broke" in doc["extra"]["error"]["message"]
    assert "traceback" in doc["extra"]["error"]


def test_active_run_exposes_run_dir(env: SimpleNamespace) -> None:
    events = _run(ids=(IID1,))
    snap = env.active[0]
    assert snap["active"] is True
    assert snap["run_dir"] == f"prediction-{_run_id(events)}"
    assert "log_path" not in snap
    assert inference.inference_active() == {"active": False}


def test_trajectory_endpoint(env: SimpleNamespace) -> None:
    run_dir = f"prediction-{_run_id(_run(ids=(IID1,)))}"
    first = inference.inference_trajectory(run_dir=run_dir, instance_id=IID1)
    assert first["trajectory"]["extra"]["status"] == "done"
    assert first["is_running"] is False and first["unchanged"] is False
    again = inference.inference_trajectory(run_dir=run_dir, instance_id=IID1, since_mtime=first["mtime"])
    assert again == {"trajectory": None, "mtime": first["mtime"], "unchanged": True, "is_running": False}
    with pytest.raises(HTTPException) as exc:
        inference.inference_trajectory(run_dir=run_dir, instance_id="nope__nope-1")
    assert exc.value.status_code == 404
    for bad_dir, bad_iid in (("../..", IID1), (run_dir, "../../etc")):
        with pytest.raises(HTTPException) as exc:
            inference.inference_trajectory(run_dir=bad_dir, instance_id=bad_iid)
        assert exc.value.status_code in (400, 403, 404)


def test_trajectory_endpoint_reads_running_before_mtime(env: SimpleNamespace, monkeypatch) -> None:
    """If the run's last write lands while the endpoint reads the file, the
    answer must still say "running" so the page polls once more instead of
    stopping on a stale view."""
    import pathlib

    run_dir = f"prediction-{_run_id(_run(ids=(IID1,)))}"
    real_stat = pathlib.Path.stat
    seen = {"n": 0, "finish_at": None}

    def stat_spy(self, *a, **k):
        if self.name == "trajectory.json":
            seen["n"] += 1
            if seen["n"] == seen["finish_at"]:
                inference._active_run = None  # the run's last write lands now
        return real_stat(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "stat", stat_spy)
    inference.inference_trajectory(run_dir=run_dir, instance_id=IID1)  # count the endpoint's stats
    seen.update(finish_at=seen["n"], n=0)  # finish on its last one: when it reads the mtime
    monkeypatch.setattr(inference, "_active_run", {"run_dir": run_dir})
    assert inference.inference_trajectory(run_dir=run_dir, instance_id=IID1)["is_running"] is True


def test_log_tail_is_gone() -> None:
    assert not hasattr(inference, "inference_log_tail")


def test_recorder_write_failure_does_not_fail_run(env: SimpleNamespace, monkeypatch) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(atif, "write_json_atomic", boom)
    events = _run()
    assert events[-1]["type"] == "done"
    preds = Path(events[-1]["output_path"]).read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["instance_id"] for line in preds] == [IID1, IID2]
