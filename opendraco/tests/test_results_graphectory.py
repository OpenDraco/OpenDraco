"""Results-page Graphectory endpoints.

`GET /api/results/graphectory` says whether `GRAPHECTORY_URL` is set;
`POST /api/results/prediction/graphectory` publishes a run into the local
Viewer (`opendraco.utils.graphectory.publish_run`, stubbed here; it is
tested in test_graphectory.py) and saves the link beside the log;
`GET /api/results/prediction/graphectory` returns that saved link.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

from api.routers import results as router
from opendraco.utils import graphectory

INSTANCE = "django__django-10973"
STEM = "prediction-chain-4f7d9f56"
RUN_ID = "chain-4f7d9f56"
VIEWER = "http://localhost:9610"
GRAPH = f"{VIEWER}/api/graph?id={RUN_ID}"
NDJSON = (
    json.dumps({"type": "run_meta", "run_id": RUN_ID, "config_name": "chain",
                "instance_ids": [INSTANCE, "astropy__astropy-12907"]}) + "\n"
    + json.dumps({"type": "agent_input", "agent": "locator", "note": "héllo"}) + "\n"
)


@pytest.fixture
def run_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Point the router at a throwaway predictions + inference-logs tree
    holding one run, with Graphectory configured."""
    preds = tmp_path / "results" / "predictions"
    logs = tmp_path / "opendraco" / "logs" / "inference_logs"
    preds.mkdir(parents=True)
    logs.mkdir(parents=True)
    (preds / f"{STEM}.jsonl").write_text(
        json.dumps({"instance_id": INSTANCE, "model_patch": ""}) + "\n", encoding="utf-8",
    )
    # Bytes: text mode would turn "\n" into "\r\n" on Windows.
    (logs / f"{STEM}.ndjson").write_bytes(NDJSON.encode("utf-8"))
    monkeypatch.setattr(router, "PREDICTIONS_DIR", preds)
    monkeypatch.setattr(router, "INFERENCE_INTERNAL_LOGS_DIR", logs)
    monkeypatch.setenv("GRAPHECTORY_URL", VIEWER)
    return preds, logs


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str, str]]:
    """`publish_run` replaced by a stand-in that records its calls and
    answers the run's link."""
    calls: list[tuple[str, str, str, str]] = []

    def publish(viewer_url: str, run_id: str, title: str, log_text: str) -> str:
        calls.append((viewer_url, run_id, title, log_text))
        return graphectory.graph_link(viewer_url, graphectory.safe_run_id(run_id))

    monkeypatch.setattr(graphectory, "publish_run", publish)
    return calls


def _upload(preds: Path) -> dict[str, Any]:
    return router.upload_prediction_to_graphectory({"path": str(preds / f"{STEM}.jsonl")})


def _link_file(logs: Path) -> Path:
    return logs / f"{STEM}.graphectory-link.json"


# ─── Status ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("value", [None, "", '""'])
def test_status_names_the_missing_setting(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("GRAPHECTORY_URL", raising=False)
    else:
        monkeypatch.setenv("GRAPHECTORY_URL", value)
    assert router.get_graphectory_status() == {
        "configured": False, "url": "", "missing": ["GRAPHECTORY_URL"],
    }


def test_status_reports_the_viewer_url_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPHECTORY_URL", '"http://localhost:9610/"')
    assert router.get_graphectory_status() == {
        "configured": True, "url": VIEWER, "missing": [],
    }


# ─── Publish ─────────────────────────────────────────────────────────────────
def test_upload_publishes_the_whole_log_and_returns_the_link(
    run_dirs: tuple[Path, Path], published: list,
) -> None:
    preds, _ = run_dirs
    assert _upload(preds) == {"graph": GRAPH, "run_id": RUN_ID, "log_name": f"{STEM}.ndjson"}
    [(viewer_url, run_id, title, log_text)] = published
    assert (viewer_url, run_id, title) == (VIEWER, RUN_ID, RUN_ID)
    assert log_text == NDJSON


def test_upload_sanitises_the_run_id_from_an_odd_stem(
    run_dirs: tuple[Path, Path], published: list,
) -> None:
    preds, logs = run_dirs
    odd = "prediction-my config!run"
    (preds / f"{odd}.jsonl").write_text("{}\n", encoding="utf-8")
    (logs / f"{odd}.ndjson").write_bytes(NDJSON.encode("utf-8"))
    body = router.upload_prediction_to_graphectory({"path": str(preds / f"{odd}.jsonl")})
    assert body["run_id"] == "my-config-run"
    assert published[0][1] == "my-config-run"


def test_upload_saves_the_link_beside_the_log(
    run_dirs: tuple[Path, Path], published: list,
) -> None:
    preds, logs = run_dirs
    _upload(preds)
    assert json.loads(_link_file(logs).read_text(encoding="utf-8")) == {
        "graph": GRAPH, "run_id": RUN_ID,
    }


def test_upload_still_answers_when_the_link_cannot_be_saved(
    run_dirs: tuple[Path, Path], published: list,
) -> None:
    preds, logs = run_dirs
    _link_file(logs).mkdir()  # a directory where the file should go
    assert _upload(preds)["graph"] == GRAPH


@pytest.mark.parametrize("value", [None, ""])
def test_upload_refuses_when_graphectory_is_not_configured(
    run_dirs: tuple[Path, Path], published: list, monkeypatch: pytest.MonkeyPatch,
    value: str | None,
) -> None:
    preds, _ = run_dirs
    if value is None:
        monkeypatch.delenv("GRAPHECTORY_URL", raising=False)
    else:
        monkeypatch.setenv("GRAPHECTORY_URL", value)
    with pytest.raises(HTTPException) as exc:
        _upload(preds)
    assert exc.value.status_code == 503
    assert "GRAPHECTORY_URL" in exc.value.detail
    assert published == []


@pytest.mark.parametrize(("status", "message"), [
    (400, "Graphectory could not convert the run: no agent activity"),
    (503, "GRAPHECTORY_URL is not an http(s) URL: 'ftp://x'"),
    (504, "Could not reach the Graphectory Viewer at http://localhost:9610"),
    (502, "The Graphectory Viewer does not list run 'chain-4f7d9f56'"),
])
def test_upload_relays_the_publish_error(
    run_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, status: int, message: str,
) -> None:
    preds, logs = run_dirs

    def fail(*args: Any) -> str:
        raise graphectory.GraphectoryError(status, message)

    monkeypatch.setattr(graphectory, "publish_run", fail)
    with pytest.raises(HTTPException) as exc:
        _upload(preds)
    assert exc.value.status_code == status
    assert exc.value.detail == message
    assert not _link_file(logs).exists()


def test_upload_reports_a_missing_log(run_dirs: tuple[Path, Path], published: list) -> None:
    preds, logs = run_dirs
    (logs / f"{STEM}.ndjson").unlink()
    with pytest.raises(HTTPException) as exc:
        _upload(preds)
    assert exc.value.status_code == 404
    assert f"{STEM}.ndjson" in exc.value.detail
    assert published == []


def test_upload_refuses_an_empty_log(run_dirs: tuple[Path, Path], published: list) -> None:
    preds, logs = run_dirs
    (logs / f"{STEM}.ndjson").write_bytes(b"\n")
    with pytest.raises(HTTPException) as exc:
        _upload(preds)
    assert exc.value.status_code == 400
    assert "empty" in exc.value.detail
    assert published == []


def test_upload_requires_a_path(run_dirs: tuple[Path, Path], published: list) -> None:
    with pytest.raises(HTTPException) as exc:
        router.upload_prediction_to_graphectory({})
    assert exc.value.status_code == 400


def test_upload_refuses_path_traversal(run_dirs: tuple[Path, Path], published: list) -> None:
    preds, _ = run_dirs
    outside = preds.parent / f"{STEM}.jsonl"
    outside.write_text("{}\n", encoding="utf-8")
    with pytest.raises(HTTPException) as exc:
        router.upload_prediction_to_graphectory({"path": str(preds / ".." / f"{STEM}.jsonl")})
    assert exc.value.status_code == 403
    assert published == []


# ─── Saved link ──────────────────────────────────────────────────────────────
def test_saved_link_is_returned_after_an_upload(
    run_dirs: tuple[Path, Path], published: list,
) -> None:
    preds, _ = run_dirs
    _upload(preds)
    assert router.get_saved_graphectory_link(str(preds / f"{STEM}.jsonl")) == {"graph": GRAPH}


@pytest.mark.parametrize("viewer", [None, "http://localhost:9611", "https://localhost:9610"])
def test_saved_link_on_another_viewer_is_ignored(
    run_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, viewer: str | None,
) -> None:
    """A link saved for another Viewer (e.g. a remote server, before
    GRAPHECTORY_URL changed), or with Graphectory off, is not shown."""
    preds, logs = run_dirs
    if viewer is None:
        monkeypatch.delenv("GRAPHECTORY_URL", raising=False)
    else:
        monkeypatch.setenv("GRAPHECTORY_URL", viewer)
    _link_file(logs).write_text(json.dumps({"graph": GRAPH}), encoding="utf-8")
    assert router.get_saved_graphectory_link(str(preds / f"{STEM}.jsonl")) == {"graph": None}


def test_saved_link_on_the_viewer_or_relative_is_kept(run_dirs: tuple[Path, Path]) -> None:
    preds, logs = run_dirs
    for link in (GRAPH, "http://LOCALHOST:9610/api/graph?id=x", "/api/graph?id=x"):
        _link_file(logs).write_text(json.dumps({"graph": link}), encoding="utf-8")
        assert router.get_saved_graphectory_link(str(preds / f"{STEM}.jsonl")) == {"graph": link}


def test_saved_link_is_null_before_any_upload(run_dirs: tuple[Path, Path]) -> None:
    preds, _ = run_dirs
    assert router.get_saved_graphectory_link(str(preds / f"{STEM}.jsonl")) == {"graph": None}


@pytest.mark.parametrize("content", ["not json", "[]", '{"graph": 3}', '{"graph": ""}'])
def test_saved_link_ignores_an_unusable_file(run_dirs: tuple[Path, Path], content: str) -> None:
    preds, logs = run_dirs
    _link_file(logs).write_text(content, encoding="utf-8")
    assert router.get_saved_graphectory_link(str(preds / f"{STEM}.jsonl")) == {"graph": None}


def test_saved_link_refuses_path_traversal(run_dirs: tuple[Path, Path]) -> None:
    preds, _ = run_dirs
    with pytest.raises(HTTPException) as exc:
        router.get_saved_graphectory_link(str(preds / ".." / ".." / f"{STEM}.jsonl"))
    assert exc.value.status_code == 403
