"""ATIF (Agent Trajectory Interchange Format) validator, writer and recorders."""
from __future__ import annotations

import copy
import json
import os
import stat
from pathlib import Path

import pytest

from opendraco.utils.atif import (
    SCHEMA_VERSION,
    now_iso,
    validate_trajectory,
    write_json_atomic,
)


def _minimal() -> dict:
    return {
        "schema_version": "ATIF-v1.8",
        "agent": {"name": "a", "version": "1"},
        "steps": [{"step_id": 1, "source": "user", "message": "hi"}],
    }


def _agent_step(step_id: int = 2, **kw) -> dict:
    step = {"step_id": step_id, "source": "agent", "message": ""}
    step.update(kw)
    return step


# ─── Validator ───────────────────────────────────────────────────────────────

def test_schema_version_constant():
    assert SCHEMA_VERSION == "ATIF-v1.8"


def test_now_iso_is_utc_z():
    ts = now_iso()
    assert ts.endswith("Z")
    doc = _minimal()
    doc["steps"][0]["timestamp"] = ts
    assert validate_trajectory(doc) == []


def test_valid_minimal_trajectory():
    assert validate_trajectory(_minimal()) == []


@pytest.mark.parametrize("mutate, field", [
    (lambda d: d["agent"].pop("version"), "version"),
    (lambda d: d.pop("steps"), "steps"),
    (lambda d: d["steps"][0].pop("message"), "message"),
    (lambda d: d.pop("schema_version"), "schema_version"),
    (lambda d: d.pop("agent"), "agent"),
])
def test_rejects_missing_required(mutate, field):
    doc = _minimal()
    mutate(doc)
    errors = validate_trajectory(doc)
    assert errors and any(field in e for e in errors)


def test_rejects_non_sequential_step_ids():
    doc = _minimal()
    doc["steps"].append({"step_id": 3, "source": "user", "message": "again"})
    errors = validate_trajectory(doc)
    assert errors and any("step_id" in e for e in errors)


def test_rejects_bad_source():
    doc = _minimal()
    doc["steps"][0]["source"] = "tool"
    assert validate_trajectory(doc)


def test_rejects_unknown_source_call_id():
    doc = _minimal()
    doc["steps"].append(_agent_step(
        tool_calls=[{"tool_call_id": "a", "function_name": "f", "arguments": {}}],
        observation={"results": [{"source_call_id": "x", "content": "?"}]},
    ))
    errors = validate_trajectory(doc)
    assert errors and any("source_call_id" in e for e in errors)


def test_accepts_matching_source_call_id():
    doc = _minimal()
    doc["steps"].append(_agent_step(
        tool_calls=[{"tool_call_id": "a", "function_name": "f", "arguments": {}}],
        observation={"results": [{"source_call_id": "a", "content": "ok"}]},
    ))
    assert validate_trajectory(doc) == []


@pytest.mark.parametrize("field, value", [
    ("tool_calls", [{"tool_call_id": "a", "function_name": "f", "arguments": {}}]),
    ("metrics", {"prompt_tokens": 1}),
    ("reasoning_content", "hmm"),
    ("model_name", "m"),
])
def test_rejects_agent_fields_on_user_step(field, value):
    doc = _minimal()
    doc["steps"][0][field] = value
    errors = validate_trajectory(doc)
    assert errors and any(field in e for e in errors)


@pytest.mark.parametrize("field, value", [
    ("metrics", {"prompt_tokens": 1}),
    ("reasoning_content", "hmm"),
])
def test_rejects_metrics_on_zero_llm_call_step(field, value):
    doc = _minimal()
    doc["steps"].append(_agent_step(llm_call_count=0, **{field: value}))
    errors = validate_trajectory(doc)
    assert errors and any(field in e for e in errors)


def _with_sub(sub: dict | None = None, ref: dict | None = None) -> dict:
    doc = _minimal()
    sub = sub if sub is not None else {**_minimal(), "trajectory_id": "s#1"}
    ref = ref if ref is not None else {"trajectory_id": "s#1"}
    doc["steps"].append(_agent_step(
        llm_call_count=0,
        tool_calls=[{"tool_call_id": "d1", "function_name": "run_agent", "arguments": {}}],
        observation={"results": [{"source_call_id": "d1", "subagent_trajectory_ref": [ref]}]},
    ))
    doc["subagent_trajectories"] = [sub]
    return doc


def test_subagent_valid():
    assert validate_trajectory(_with_sub()) == []


def test_subagent_without_trajectory_id():
    sub = _minimal()
    errors = validate_trajectory(_with_sub(sub=sub))
    assert errors and any("trajectory_id" in e for e in errors)


def test_subagent_duplicate_ids():
    doc = _with_sub()
    doc["subagent_trajectories"].append(copy.deepcopy(doc["subagent_trajectories"][0]))
    errors = validate_trajectory(doc)
    assert errors and any("unique" in e for e in errors)


def test_ref_without_id_or_path():
    errors = validate_trajectory(_with_sub(ref={"session_id": "x"}))
    assert errors and any("subagent_trajectory_ref" in e for e in errors)


def test_ref_to_missing_subagent():
    errors = validate_trajectory(_with_sub(ref={"trajectory_id": "nope"}))
    assert errors and any("nope" in e for e in errors)


def test_ref_with_path_needs_no_embedded():
    assert validate_trajectory(_with_sub(ref={"trajectory_path": "x.json"})) == []


def test_bad_step_inside_subagent_is_prefixed():
    sub = {**_minimal(), "trajectory_id": "s#1"}
    sub["steps"][0]["source"] = "robot"
    errors = validate_trajectory(_with_sub(sub=sub))
    assert errors and all(e.startswith("subagent_trajectories[0].") for e in errors)


def test_rejects_bad_timestamp():
    doc = _minimal()
    doc["steps"][0]["timestamp"] = "yesterday"
    errors = validate_trajectory(doc)
    assert errors and any("timestamp" in e for e in errors)


def test_rejects_non_object_arguments():
    doc = _minimal()
    doc["steps"].append(_agent_step(
        tool_calls=[{"tool_call_id": "a", "function_name": "f", "arguments": "x=1"}],
    ))
    errors = validate_trajectory(doc)
    assert errors and any("arguments" in e for e in errors)


# ─── Atomic writer ───────────────────────────────────────────────────────────

def test_write_json_atomic(tmp_path: Path):
    target = tmp_path / "a" / "b" / "trajectory.json"
    write_json_atomic(target, {"p": Path("/x"), "n": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"p": "/x", "n": 1}
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o644
    assert stat.S_IMODE(os.stat(target.parent).st_mode) == 0o755
    assert [p.name for p in target.parent.iterdir()] == ["trajectory.json"]


# ─── Recorders ───────────────────────────────────────────────────────────────
import logging  # noqa: E402
import threading  # noqa: E402

from opendraco.utils.atif import RunRecorder  # noqa: E402

RUN_INFO = {
    "run_id": "cfg-ab12cd34", "config_name": "cfg", "config_sha": "abc1234",
    "instance_ids": ["i-1", "i-2"], "ts": "2026-11-20T10:00:00",
}
AGENT_EXTRA = {
    "config_name": "cfg", "config_sha": "abc1234",
    "edges": [{"from": "locator", "to": "patcher"}], "start": "locator", "end": "patcher",
}
PATCH = "diff --" + "git a b"


def _run(tmp_path: Path, ids=("i-1", "i-2")) -> RunRecorder:
    info = {**RUN_INFO, "instance_ids": list(ids)}
    return RunRecorder(
        tmp_path / "prediction-cfg-ab12cd34", run_info=info, agent_extra=AGENT_EXTRA,
        instances=[(iid, f"issue {iid}") for iid in ids],
    )


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_run_recorder_creates_queued_files(tmp_path: Path):
    run = _run(tmp_path)
    for iid in ("i-1", "i-2"):
        path = tmp_path / "prediction-cfg-ab12cd34" / iid / "trajectory.json"
        doc = _read(path)
        assert validate_trajectory(doc) == []
        assert doc["schema_version"] == "ATIF-v1.8"
        assert doc["session_id"] == "cfg-ab12cd34"
        assert doc["trajectory_id"] == f"cfg-ab12cd34.{iid}"
        assert doc["agent"]["name"] == "opendraco"
        assert doc["agent"]["extra"]["edges"] == AGENT_EXTRA["edges"]
        assert doc["extra"]["status"] == "queued"
        assert doc["extra"]["run"]["run_id"] == "cfg-ab12cd34"
        assert doc["extra"]["instance_id"] == iid
        assert doc["steps"][0]["source"] == "user"
        assert doc["steps"][0]["message"] == f"issue {iid}"
        assert run.instance(iid).path == path


def _full_activation(inst):
    rec = inst.begin_activation("locator", {"issue": "x"}, model_name="ollama/q", tool_definitions=[])
    rec.prompt("system", "S")
    rec.prompt("user", "U")
    rec.llm_call(message="", reasoning="think",
                 tool_calls=[{"id": "c1", "name": "read_file", "args": {"path": "a.py"}}],
                 usage={"input": 10, "output": 5, "total": 15}, model_name="ollama/q")
    rec.tool_result("c1", "contents")
    rec.llm_call(message="done", reasoning="", tool_calls=[],
                 usage={"input": 20, "output": 3, "total": 23}, model_name=None)
    inst.end_activation(rec, summary="s", delta={"locator": "done"},
                        handoffs=[{"to": "patcher", "summary": "s", "preview": "p", "timestamp": now_iso()}])
    return rec


def test_full_activation_roundtrip(tmp_path: Path):
    inst = _run(tmp_path).instance("i-1")
    inst.start()
    _full_activation(inst)
    inst.finish("done", model_patch=PATCH)
    doc = _read(inst.path)
    assert validate_trajectory(doc) == []
    assert [s["source"] for s in doc["steps"]] == ["user", "agent"]
    dispatch = doc["steps"][1]
    assert dispatch["llm_call_count"] == 0
    assert dispatch["tool_calls"][0]["function_name"] == "run_agent"
    assert dispatch["tool_calls"][0]["arguments"] == {"agent": "locator", "inputs": {"issue": "x"}}
    result = dispatch["observation"]["results"][0]
    assert result["content"] == "s"
    assert result["subagent_trajectory_ref"] == [{"trajectory_id": "locator#1"}]
    assert result["extra"]["handoffs"][0]["to"] == "patcher"
    assert result["extra"]["delta_keys"] == ["locator"]
    sub = doc["subagent_trajectories"][0]
    assert sub["trajectory_id"] == "locator#1"
    assert sub["agent"]["name"] == "locator"
    assert sub["agent"]["model_name"] == "ollama/q"
    assert [s["source"] for s in sub["steps"]] == ["system", "user", "agent", "agent"]
    first = sub["steps"][2]
    assert first["llm_call_count"] == 1
    assert first["reasoning_content"] == "think"
    assert first["metrics"] == {"prompt_tokens": 10, "completion_tokens": 5}
    assert first["observation"]["results"][0] == {"source_call_id": "c1", "content": "contents"}
    assert "reasoning_content" not in sub["steps"][3]
    assert doc["final_metrics"]["total_prompt_tokens"] == 30
    assert doc["final_metrics"]["total_completion_tokens"] == 8
    assert doc["final_metrics"]["extra"]["per_agent"]["locator"]["total"] == 38
    assert doc["extra"]["status"] == "done"
    assert doc["extra"]["model_patch"] == PATCH


def test_partial_file_is_valid_mid_activation(tmp_path: Path):
    inst = _run(tmp_path).instance("i-1")
    inst.start()
    rec = inst.begin_activation("locator", {}, model_name=None, tool_definitions=[])
    rec.llm_call(message="m", reasoning="", tool_calls=[{"id": "c1", "name": "f", "args": {}}],
                 usage={"input": 1, "output": 1, "total": 2}, model_name=None)
    doc = _read(inst.path)
    assert validate_trajectory(doc) == []
    assert doc["extra"]["status"] == "running"
    assert doc["subagent_trajectories"][0]["trajectory_id"] == "locator#1"


def test_second_activation_gets_new_id(tmp_path: Path):
    inst = _run(tmp_path).instance("i-1")
    inst.start()
    for _ in range(2):
        rec = inst.begin_activation("locator", {}, model_name=None, tool_definitions=[])
        inst.end_activation(rec, summary="", delta={}, handoffs=[])
    doc = _read(inst.path)
    assert [s["trajectory_id"] for s in doc["subagent_trajectories"]] == ["locator#1", "locator#2"]
    assert [s["tool_calls"][0]["tool_call_id"] for s in doc["steps"][1:]] == ["dispatch-1", "dispatch-2"]
    assert validate_trajectory(doc) == []


def test_programmatic_tool_result(tmp_path: Path):
    inst = _run(tmp_path).instance("i-1")
    rec = inst.begin_activation("patcher", {}, model_name=None, tool_definitions=[])
    rec.tool_result(None, {"ok": True}, name="apply_patch", args={"p": 1})
    doc = _read(inst.path)
    step = doc["subagent_trajectories"][0]["steps"][-1]
    assert step["source"] == "agent" and step["llm_call_count"] == 0
    assert "metrics" not in step
    assert step["tool_calls"][0]["function_name"] == "apply_patch"
    assert step["tool_calls"][0]["arguments"] == {"p": 1}
    assert step["observation"]["results"][0]["source_call_id"] == step["tool_calls"][0]["tool_call_id"]
    assert validate_trajectory(doc) == []


def test_tool_error_marked(tmp_path: Path):
    inst = _run(tmp_path).instance("i-1")
    rec = inst.begin_activation("locator", {}, model_name=None, tool_definitions=[])
    rec.llm_call(message="", reasoning="", tool_calls=[{"id": "c1", "name": "f", "args": {}}],
                 usage={}, model_name=None)
    rec.tool_result("c1", "Error: boom", error=True)
    res = _read(inst.path)["subagent_trajectories"][0]["steps"][-1]["observation"]["results"][0]
    assert res == {"source_call_id": "c1", "content": "Error: boom", "extra": {"error": True}}


def test_fail_unfinished(tmp_path: Path):
    run = _run(tmp_path, ids=("i-1", "i-2", "i-3"))
    run.instance("i-1").start()
    run.instance("i-1").finish("done")
    run.instance("i-2").start()
    run.fail_unfinished("cancelled", "Cancelled by user")
    assert _read(run.instance("i-1").path)["extra"]["status"] == "done"
    for iid in ("i-2", "i-3"):
        doc = _read(run.instance(iid).path)
        assert doc["extra"]["status"] == "cancelled"
        assert doc["steps"][-1]["source"] == "system"
        assert doc["steps"][-1]["extra"]["event"] == "cancelled"
        assert validate_trajectory(doc) == []


def test_fail_unfinished_error_keeps_details(tmp_path: Path):
    run = _run(tmp_path, ids=("i-1",))
    run.fail_unfinished("error", "boom", {"message": "boom", "traceback": "tb"})
    doc = _read(run.instance("i-1").path)
    assert doc["extra"]["status"] == "error"
    assert doc["extra"]["error"] == {"message": "boom", "traceback": "tb"}


def test_concurrent_activations_keep_all_steps(tmp_path: Path):
    inst = _run(tmp_path).instance("i-1")
    inst.start()

    def work(n: int) -> None:
        rec = inst.begin_activation(f"agent{n}", {}, model_name=None, tool_definitions=[])
        for k in range(5):
            rec.llm_call(message=str(k), reasoning="", tool_calls=[{"id": f"c{k}", "name": "f", "args": {}}],
                         usage={"input": 1, "output": 1, "total": 2}, model_name=None)
            rec.tool_result(f"c{k}", "r")
        inst.end_activation(rec, summary="", delta={}, handoffs=[])

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    doc = _read(inst.path)
    assert validate_trajectory(doc) == []
    assert len(doc["steps"]) == 1 + 8
    assert len(doc["subagent_trajectories"]) == 8
    assert all(len(s["steps"]) == 5 for s in doc["subagent_trajectories"])


def test_unserializable_values_are_stringified(tmp_path: Path):
    inst = _run(tmp_path).instance("i-1")
    rec = inst.begin_activation("locator", {"p": Path("/in")}, model_name=None, tool_definitions=[])
    rec.llm_call(message="", reasoning="",
                 tool_calls=[{"id": "c1", "name": "f", "args": {"p": Path("/x"), "s": {1}}}],
                 usage={}, model_name=None)
    rec.tool_result("c1", b"bytes")
    doc = _read(inst.path)
    assert validate_trajectory(doc) == []
    step = doc["subagent_trajectories"][0]["steps"][-1]
    assert step["tool_calls"][0]["arguments"]["p"] == "/x"
    assert isinstance(step["tool_calls"][0]["arguments"]["s"], str)
    assert step["observation"]["results"][0]["content"] == "b'bytes'"


def _strict_load(path: Path) -> dict:
    def no_constants(name: str):
        raise ValueError(f"non-JSON constant {name}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=no_constants)


def test_odd_keys_and_nan_are_recorded_as_strings(tmp_path: Path):
    """Tuple/Path dict keys and NaN/inf must neither raise nor produce a
    file a strict JSON reader (FastAPI's encoder) rejects."""
    inst = _run(tmp_path).instance("i-1")
    rec = inst.begin_activation("locator", {("a", "b"): 1}, model_name=None, tool_definitions=[])
    rec.llm_call(message="", reasoning="", tool_calls=[{"id": "c1", "name": "f", "args": {"n": float("nan")}}],
                 usage={}, model_name=None)
    rec.tool_result("c1", {("a", "b"): 1, Path("x"): float("inf")})
    rec.tool_result(None, "r", name="g", args={Path("k"): 1})
    inst.end_activation(rec, summary="", delta={Path("p"): float("-inf")}, handoffs=[])
    doc = _strict_load(inst.path)
    assert validate_trajectory(doc) == []
    sub = doc["subagent_trajectories"][0]
    assert sub["steps"][0]["tool_calls"][0]["arguments"] == {"n": "nan"}
    assert sub["steps"][1]["tool_calls"][0]["arguments"] == {"k": 1}
    result = doc["steps"][1]["observation"]["results"][0]
    assert result["extra"]["delta"] == {"p": "-inf"}
    assert doc["steps"][1]["tool_calls"][0]["arguments"]["inputs"] == {"('a', 'b')": 1}


def test_read_run_info_reads_only_the_head(tmp_path: Path):
    """History lookups must not parse a whole (possibly huge) trajectory."""
    from opendraco.utils.atif import read_run_info

    inst = _run(tmp_path).instance("i-1")
    rec = inst.begin_activation("locator", {}, model_name=None, tool_definitions=[])
    rec.llm_call(message="x" * 300_000, reasoning="", tool_calls=[], usage={}, model_name=None)
    raw = inst.path.read_bytes()
    inst.path.write_bytes(raw[:70_000])  # the tail is gone: not parseable as a whole
    assert read_run_info(inst.path) == RUN_INFO | {"instance_ids": ["i-1", "i-2"]}


def test_read_run_info_falls_back_to_a_full_parse(tmp_path: Path):
    from opendraco.utils.atif import read_run_info

    doc = {"agent": {"name": "a", "version": "1"}, "steps": [], "extra": {"run": {"run_id": "r"}}}
    path = tmp_path / "trajectory.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert read_run_info(path) == {"run_id": "r"}
    path.write_text("not json", encoding="utf-8")
    assert read_run_info(path) is None


def test_flush_failure_is_swallowed(tmp_path: Path, monkeypatch, caplog):
    inst = _run(tmp_path).instance("i-1")
    from opendraco.utils import atif

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(atif, "write_json_atomic", boom)
    with caplog.at_level(logging.WARNING):
        rec = inst.begin_activation("locator", {}, model_name=None, tool_definitions=[])
        rec.llm_call(message="", reasoning="", tool_calls=[], usage={}, model_name=None)
        inst.finish("done")
    assert "disk full" in caplog.text
