"""scripts/ndjson_to_atif.py: legacy inference `.ndjson` logs → ATIF folders."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from opendraco.utils.atif import validate_trajectory
from scripts import ndjson_to_atif as mig

FIXTURE = Path(__file__).parent / "fixtures" / "legacy_run.ndjson"
STEM = "prediction-chain-0000abcd"
IIDS = ("demo__demo-1", "demo__demo-2")


@pytest.fixture
def logs(tmp_path: Path) -> Path:
    folder = tmp_path / "inference_logs"
    folder.mkdir()
    shutil.copy(FIXTURE, folder / f"{STEM}.ndjson")
    return folder


def _doc(run_dir: Path, iid: str) -> dict:
    return json.loads((run_dir / iid / "trajectory.json").read_text(encoding="utf-8"))


def test_converts_fixture(logs: Path) -> None:
    run_dir = mig.convert_ndjson(
        logs / f"{STEM}.ndjson", logs,
        instances={IIDS[0]: {"problem_statement": "it breaks"}},
    )
    assert run_dir == logs / STEM
    for iid in IIDS:
        doc = _doc(run_dir, iid)
        assert validate_trajectory(doc) == [], validate_trajectory(doc)
        assert doc["extra"]["status"] == "done"
        assert doc["extra"]["model_patch"].startswith("diff --")
        assert doc["extra"]["run"]["config_sha"] == "abc1234"
        assert "legacy" in doc["notes"]
        dispatch = [s for s in doc["steps"] if s["source"] == "agent"]
        assert [s["tool_calls"][0]["arguments"]["agent"] for s in dispatch] == ["locator", "patcher"]
        assert dispatch[1]["tool_calls"][0]["arguments"]["inputs"] == {"locator": "foo.py"}
        assert dispatch[0]["observation"]["results"][0]["extra"]["handoffs"][0]["to"] == "patcher"
        loc = doc["subagent_trajectories"][0]
        assert loc["steps"][0]["reasoning_content"] == "let me search"
        assert loc["steps"][0]["message"] == "Searching"
        tool = loc["steps"][1]
        assert tool["llm_call_count"] == 0
        assert tool["tool_calls"][0]["function_name"] == "search_code"
        assert tool["tool_calls"][0]["arguments"] == {"preview": "query=foo"}
        assert tool["observation"]["results"][0]["content"] == "2 items"
        assert doc["final_metrics"]["extra"]["per_agent"]["locator"] == {"input": 100, "output": 20, "total": 120}
    assert _doc(run_dir, IIDS[0])["steps"][0]["message"] == "it breaks"
    assert (logs / f"{STEM}.ndjson").is_file()


def test_converted_steps_carry_no_made_up_timestamps(logs: Path) -> None:
    """Legacy logs have no per-step times; stamping the conversion time would
    show fake durations, so converted steps have no timestamp at all."""
    run_dir = mig.convert_ndjson(logs / f"{STEM}.ndjson", logs)
    doc = _doc(run_dir, IIDS[0])
    steps = doc["steps"] + [s for sub in doc["subagent_trajectories"] for s in sub["steps"]]
    assert all("timestamp" not in s for s in steps)
    assert validate_trajectory(doc) == []


def test_cli_converts_then_skips(logs: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(mig, "LOGS_DIR", logs)
    monkeypatch.setattr(mig, "load_instances", lambda: {})
    assert mig.main([]) == 0
    assert (logs / STEM / IIDS[0] / "trajectory.json").is_file()
    assert "converted" in capsys.readouterr().out
    assert mig.main([]) == 0
    assert "nothing to convert" in capsys.readouterr().out


def test_error_log_becomes_error_status(logs: Path) -> None:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    cut = next(i for i, l in enumerate(lines) if json.loads(l)["type"] == "agent_event")
    broken = lines[:cut] + [json.dumps({"type": "error", "message": "boom", "traceback": "tb"})]
    path = logs / "prediction-broken-1.ndjson"
    path.write_text("\n".join(broken) + "\n", encoding="utf-8")
    run_dir = mig.convert_ndjson(path, logs)
    for iid in IIDS:
        doc = _doc(run_dir, iid)
        assert doc["extra"]["status"] == "error"
        assert validate_trajectory(doc) == []


def test_cancelled_log(logs: Path) -> None:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()[:5] + [json.dumps({"type": "cancelled"})]
    path = logs / "prediction-cancel-1.ndjson"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run_dir = mig.convert_ndjson(path, logs)
    assert {_doc(run_dir, iid)["extra"]["status"] for iid in IIDS} == {"cancelled"}


def test_a_log_without_run_meta_is_refused(logs: Path) -> None:
    path = logs / "prediction-bad.ndjson"
    path.write_text('{"type": "status", "message": "hi"}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        mig.convert_ndjson(path, logs)


def test_cli_exit_code_on_a_bad_file(logs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mig, "LOGS_DIR", logs)
    monkeypatch.setattr(mig, "load_instances", lambda: {})
    bad = logs / "prediction-bad.ndjson"
    bad.write_text("not json\n", encoding="utf-8")
    assert mig.main([str(bad)]) == 1
