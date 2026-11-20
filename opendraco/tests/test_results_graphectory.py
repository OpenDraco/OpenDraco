"""Results-page Graphectory endpoints.

`GET /api/results/graphectory` says whether `GRAPHECTORY_URL` is set;
`POST /api/results/prediction/graphectory` publishes a run's ATIF
trajectories into the local Viewer (`opendraco.utils.graphectory.publish_run`,
stubbed here; it is tested in test_graphectory.py) and answers one link per
instance; `GET /api/results/prediction/graphectory?instance_id=` returns the
saved link of one instance.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException

from api.routers import results as router
from opendraco.utils import graphectory
from opendraco.utils.atif import RunRecorder

INSTANCE = "django__django-10973"
OTHER = "astropy__astropy-12907"
STEM = "prediction-chain-4f7d9f56"
RUN_ID = "chain-4f7d9f56"
VIEWER = "http://localhost:9610"


def _link(iid: str) -> str:
    return f"{VIEWER}/api/graph?id={RUN_ID}.{iid}"


@pytest.fixture
def run_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A throwaway predictions + inference-logs tree holding one ATIF run,
    with Graphectory configured."""
    preds = tmp_path / "results" / "predictions"
    logs = tmp_path / "opendraco" / "logs" / "inference_logs"
    preds.mkdir(parents=True)
    logs.mkdir(parents=True)
    (preds / f"{STEM}.jsonl").write_text(
        json.dumps({"instance_id": INSTANCE, "model_patch": ""}) + "\n", encoding="utf-8",
    )
    RunRecorder(
        logs / STEM, run_info={"run_id": RUN_ID, "instance_ids": [INSTANCE, OTHER]},
        agent_extra={}, instances=[(INSTANCE, "a"), (OTHER, "b")],
    )
    monkeypatch.setattr(router, "PREDICTIONS_DIR", preds)
    monkeypatch.setattr(router, "INFERENCE_INTERNAL_LOGS_DIR", logs)
    monkeypatch.setenv("GRAPHECTORY_URL", VIEWER)
    return preds, logs


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Path]]:
    """`publish_run` replaced by a stand-in that records its calls, writes
    the links file like the real one, and answers one link per instance."""
    calls: list[tuple[str, Path]] = []

    def publish(viewer_url: str, run_dir: Path) -> dict[str, str]:
        calls.append((viewer_url, Path(run_dir)))
        links = {INSTANCE: _link(INSTANCE), OTHER: _link(OTHER)}
        (Path(run_dir) / "graphectory-links.json").write_text(json.dumps({"links": links}), encoding="utf-8")
        return links

    monkeypatch.setattr(graphectory, "publish_run", publish)
    return calls


def _upload(preds: Path) -> dict[str, Any]:
    return router.upload_prediction_to_graphectory({"path": str(preds / f"{STEM}.jsonl")})


def _link_file(logs: Path) -> Path:
    return logs / STEM / "graphectory-links.json"


def _saved(preds: Path, iid: str = INSTANCE) -> dict[str, Any]:
    return router.get_saved_graphectory_link(str(preds / f"{STEM}.jsonl"), iid)


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
def test_upload_publishes_the_run_folder_and_returns_links(
    run_dirs: tuple[Path, Path], published: list,
) -> None:
    preds, logs = run_dirs
    assert _upload(preds) == {"links": {INSTANCE: _link(INSTANCE), OTHER: _link(OTHER)}, "run_id": RUN_ID}
    assert published == [(VIEWER, logs / STEM)]


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
    (404, "no ATIF trajectories in prediction-chain-4f7d9f56"),
    (503, "GRAPHECTORY_URL is not an http(s) URL: 'ftp://x'"),
    (504, "Could not reach the Graphectory Viewer at http://localhost:9610"),
    (502, "The Graphectory Viewer does not list ['chain-4f7d9f56.x']"),
])
def test_upload_relays_the_publish_error(
    run_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, status: int, message: str,
) -> None:
    preds, logs = run_dirs

    def fail(*args: Any) -> dict[str, str]:
        raise graphectory.GraphectoryError(status, message)

    monkeypatch.setattr(graphectory, "publish_run", fail)
    with pytest.raises(HTTPException) as exc:
        _upload(preds)
    assert exc.value.status_code == status
    assert exc.value.detail == message
    assert not _link_file(logs).exists()


def test_upload_reports_a_missing_run_folder(run_dirs: tuple[Path, Path], published: list) -> None:
    preds, _ = run_dirs
    other = "prediction-other-00000000"
    (preds / f"{other}.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(HTTPException) as exc:
        router.upload_prediction_to_graphectory({"path": str(preds / f"{other}.jsonl")})
    assert exc.value.status_code == 404
    assert other in exc.value.detail
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
def test_saved_link_is_per_instance_after_an_upload(
    run_dirs: tuple[Path, Path], published: list,
) -> None:
    preds, _ = run_dirs
    _upload(preds)
    assert _saved(preds, INSTANCE) == {"graph": _link(INSTANCE)}
    assert _saved(preds, OTHER) == {"graph": _link(OTHER)}
    assert _saved(preds, "unknown__x-1") == {"graph": None}


@pytest.mark.parametrize("viewer", [None, "http://localhost:9611", "https://localhost:9610"])
def test_saved_link_on_another_viewer_is_ignored(
    run_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, viewer: str | None,
) -> None:
    """A link saved for another Viewer, or with Graphectory off, is not shown."""
    preds, logs = run_dirs
    if viewer is None:
        monkeypatch.delenv("GRAPHECTORY_URL", raising=False)
    else:
        monkeypatch.setenv("GRAPHECTORY_URL", viewer)
    _link_file(logs).write_text(json.dumps({"links": {INSTANCE: _link(INSTANCE)}}), encoding="utf-8")
    assert _saved(preds) == {"graph": None}


def test_saved_link_on_the_viewer_or_relative_is_kept(run_dirs: tuple[Path, Path]) -> None:
    preds, logs = run_dirs
    for link in (_link(INSTANCE), "http://LOCALHOST:9610/api/graph?id=x", "/api/graph?id=x"):
        _link_file(logs).write_text(json.dumps({"links": {INSTANCE: link}}), encoding="utf-8")
        assert _saved(preds) == {"graph": link}


def test_saved_link_is_null_before_any_upload(run_dirs: tuple[Path, Path]) -> None:
    preds, _ = run_dirs
    assert _saved(preds) == {"graph": None}


@pytest.mark.parametrize("content", [
    "not json", "[]", '{"links": 3}', '{"links": {"django__django-10973": ""}}',
    '{"links": {"django__django-10973": 3}}',
])
def test_saved_link_ignores_an_unusable_file(run_dirs: tuple[Path, Path], content: str) -> None:
    preds, logs = run_dirs
    _link_file(logs).write_text(content, encoding="utf-8")
    assert _saved(preds) == {"graph": None}


def test_saved_link_refuses_path_traversal(run_dirs: tuple[Path, Path]) -> None:
    preds, _ = run_dirs
    with pytest.raises(HTTPException) as exc:
        router.get_saved_graphectory_link(str(preds / ".." / ".." / f"{STEM}.jsonl"), INSTANCE)
    assert exc.value.status_code == 403
