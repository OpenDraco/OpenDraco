"""Readers of the stored run log read ATIF: the config History panel's
"runs that used this version" and the Results page's trajectory endpoint."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from api.routers import results, topology
from opendraco.utils.atif import RunRecorder

RUN_ID = "cfg-ab12cd34"
STEM = f"prediction-{RUN_ID}"
IIDS = ["django__django-10973", "astropy__astropy-12907"]


def _record(logs: Path, run_id: str = RUN_ID, name: str = "cfg", sha: str | None = "abc1234",
            ts: str = "2026-11-20T10:00:00") -> Path:
    folder = logs / f"prediction-{run_id}"
    RunRecorder(
        folder,
        run_info={"run_id": run_id, "config_name": name, "config_sha": sha,
                  "instance_ids": IIDS, "ts": ts},
        agent_extra={}, instances=[(iid, "issue") for iid in IIDS],
    )
    return folder


@pytest.fixture
def logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "inference_logs"
    folder.mkdir()
    monkeypatch.setattr(topology, "INFERENCE_INTERNAL_LOGS_DIR", folder)
    monkeypatch.setattr(results, "INFERENCE_INTERNAL_LOGS_DIR", folder)
    return folder


# ─── History panel ───────────────────────────────────────────────────────────
def test_history_lists_runs_from_atif(logs: Path) -> None:
    _record(logs)
    _record(logs, run_id="cfg-00000002", ts="2026-11-21T10:00:00")
    _record(logs, run_id="other-1", name="other")
    _record(logs, run_id="cfg-nosha", sha=None)
    body = topology.list_runs_for_config_sha("cfg", "abc1234")
    assert body == {"matches": [
        {"runId": "cfg-00000002", "instanceIds": IIDS, "ts": "2026-11-21T10:00:00"},
        {"runId": RUN_ID, "instanceIds": IIDS, "ts": "2026-11-20T10:00:00"},
    ]}


def test_history_matches_sha_prefixes(logs: Path) -> None:
    _record(logs)
    assert len(topology.list_runs_for_config_sha("cfg", "abc1")["matches"]) == 1


def test_history_skips_unreadable_files(logs: Path) -> None:
    bad = logs / "prediction-broken" / IIDS[0]
    bad.mkdir(parents=True)
    (bad / "trajectory.json").write_text("not json", encoding="utf-8")
    (logs / "stray.txt").write_text("x", encoding="utf-8")
    _record(logs)
    assert [m["runId"] for m in topology.list_runs_for_config_sha("cfg", "abc1234")["matches"]] == [RUN_ID]


# ─── Results trajectory endpoint ─────────────────────────────────────────────
@pytest.fixture
def preds(tmp_path: Path, logs: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "predictions"
    folder.mkdir()
    (folder / f"{STEM}.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(results, "PREDICTIONS_DIR", folder)
    _record(logs)
    return folder


def test_results_trajectory_for_an_instance(preds: Path) -> None:
    body = results.get_prediction_trajectory(str(preds / f"{STEM}.jsonl"), IIDS[1])
    assert body["exists"] is True and body["name"] == "trajectory.json"
    assert body["trajectory"]["extra"]["instance_id"] == IIDS[1]


def test_results_trajectory_defaults_to_the_first_instance(preds: Path) -> None:
    body = results.get_prediction_trajectory(str(preds / f"{STEM}.jsonl"))
    assert body["trajectory"]["extra"]["instance_id"] == IIDS[0]


def test_results_trajectory_unknown_instance(preds: Path) -> None:
    body = results.get_prediction_trajectory(str(preds / f"{STEM}.jsonl"), "nope__nope-1")
    assert body["exists"] is False and body["trajectory"] is None


def test_results_trajectory_without_a_run_folder(preds: Path) -> None:
    (preds / "prediction-old-1.jsonl").write_text("{}\n", encoding="utf-8")
    body = results.get_prediction_trajectory(str(preds / "prediction-old-1.jsonl"))
    assert body["exists"] is False


@pytest.mark.parametrize("instance_id", ["../../x", "..", "a/b"])
def test_results_trajectory_refuses_odd_instance_ids(preds: Path, instance_id: str) -> None:
    with pytest.raises(HTTPException) as exc:
        results.get_prediction_trajectory(str(preds / f"{STEM}.jsonl"), instance_id)
    assert exc.value.status_code in (400, 403)


def test_results_trajectory_refuses_path_traversal(preds: Path) -> None:
    with pytest.raises(HTTPException) as exc:
        results.get_prediction_trajectory(str(preds / ".." / ".." / f"{STEM}.jsonl"))
    assert exc.value.status_code in (403, 404)


def test_ndjson_endpoint_is_gone() -> None:
    assert not hasattr(results, "get_prediction_ndjson")
