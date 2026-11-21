"""Local Graphectory: publish a run into the Viewer.

`publish_run` copies a run's ATIF trajectories into
`<RESULTS_DIR>/graphectory` and reloads the Viewer until it lists every
instance; a finished run is published in the background. The
`graphectory-viewer` container is only ever inspected, never changed. These
tests use a scripted stand-in ATIF Viewer on a loopback port (stdlib
`http.server`) and a stubbed `docker`, so no network or Docker is needed.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import stat
import logging
import socket
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from api.routers import inference
from opendraco.exceptions.errors import OpendracoError
from opendraco.utils import graphectory
from opendraco.utils.atif import RunRecorder

LOGGER_NAME = graphectory.logger.name
# Captured before any test patches it.
REAL_DATA_DIR = graphectory.DATA_DIR
RUN_ID = "chain-4f7d9f56"
IIDS = ("django__django-10973", "astropy__astropy-12907")


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """No test may write into the real `<RESULTS_DIR>/graphectory`."""
    data_dir = tmp_path / "isolated-results" / "graphectory"
    monkeypatch.setattr(graphectory, "DATA_DIR", data_dir)
    return data_dir


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """A finished two-instance run, recorded as ATIF."""
    folder = tmp_path / "inference_logs" / f"prediction-{RUN_ID}"
    run = RunRecorder(
        folder, run_info={"run_id": RUN_ID, "config_name": "chain", "instance_ids": list(IIDS)},
        agent_extra={}, instances=[(iid, "issue") for iid in IIDS],
    )
    for iid in IIDS:
        run.instance(iid).start()
        run.instance(iid).finish("done", model_patch="")
    return folder


def _graph_id(iid: str) -> str:
    return f"{RUN_ID}.{iid}"


# ─── Stand-ins ───────────────────────────────────────────────────────────────
@dataclass
class FakeViewer:
    """Loopback stand-in for the ATIF Graphectory Viewer (the fork's
    feat/atif-mas branch): `POST /api/config` (re)loads `data_dir`,
    `GET /api/graphs` lists every ATIF file by its `trajectory_id`,
    `POST /api/upload` stores one trajectory under `data_dir` and loads it
    (`upload_status` other than 200 makes it answer that error instead)."""
    url: str
    data_dir: Path
    requests: list[tuple[str, str, Any]] = field(default_factory=list)
    config_ok: bool = True
    list_runs: bool = True
    loaded: bool = False
    upload_status: int = 200


@pytest.fixture
def fake_viewer(tmp_path: Path) -> Iterator[FakeViewer]:
    state = FakeViewer(url="", data_dir=tmp_path / "data")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: Any, ctype: str = "application/json") -> None:
            raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            state.requests.append(("GET", self.path, None))
            if self.path == "/":
                self._send(200, b"<html>viewer</html>", "text/html")
            elif self.path == "/api/graphs":
                ids = sorted(
                    json.loads(p.read_text(encoding="utf-8"))["trajectory_id"]
                    for p in state.data_dir.rglob("trajectory.json")
                ) if state.loaded and state.list_runs else []
                self._send(200, {"status": "complete", "graphs": [{"instance_id": i} for i in ids]})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            state.requests.append(("POST", self.path, body))
            if self.path == "/api/config" and state.config_ok:
                state.loaded = True
                self._send(200, {"ok": True, "trajs": body["trajs"], "agent_type": "atif"})
            elif self.path == "/api/upload":
                if state.upload_status != 200:
                    self._send(state.upload_status, {"error": "Uploads are disabled."})
                    return
                target = state.data_dir / body["run_id"] / body["instance_id"] / "trajectory.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(body["trajectory"]), encoding="utf-8")
                state.loaded = True
                self._send(200, {"ok": True, "trajs": str(state.data_dir), "agent_type": "atif"})
            else:
                self._send(400, {"error": "bad data source"})

        def log_message(self, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state.url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()


def _closed_port() -> int:
    """A loopback port nothing listens on."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ─── Settings ────────────────────────────────────────────────────────────────
def test_the_viewer_url_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPHECTORY_URL", ' "http://localhost:9610/" ')
    assert graphectory.graphectory_base_url() == "http://localhost:9610"


@pytest.mark.parametrize("value", [None, "", "  ", '""'])
def test_unset_or_empty_means_disabled(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    """No default: Graphectory is off until GRAPHECTORY_URL is set."""
    if value is None:
        monkeypatch.delenv("GRAPHECTORY_URL", raising=False)
    else:
        monkeypatch.setenv("GRAPHECTORY_URL", value)
    assert graphectory.graphectory_base_url() == ""


@pytest.mark.parametrize(("raw", "expected"), [
    ("chain-4f7d9f56", "chain-4f7d9f56"),
    ("my config/run 1", "my-config-run-1"),
    ("..hidden", "hidden"),
    ("///", "run"),
    ("x" * 200, "x" * 128),
])
def test_run_id_is_sanitised(raw: str, expected: str) -> None:
    assert graphectory.safe_run_id(raw) == expected
    assert graphectory.is_valid_run_id(graphectory.safe_run_id(raw))


def test_the_data_folder_is_under_results_dir() -> None:
    from opendraco.paths import RESULTS_DIR
    assert REAL_DATA_DIR == RESULTS_DIR / "graphectory"


def test_the_converter_is_gone() -> None:
    """Graphectory reads ATIF itself: OpenDraco ships no converter."""
    assert importlib.util.find_spec("opendraco.utils.graphectory_converter") is None
    assert not hasattr(graphectory, "convert_run")


def test_the_viewer_is_built_from_the_atif_fork() -> None:
    assert "https://github.com/xiangfengyepan/Graphectory.git" in graphectory.BUILD_COMMAND
    assert "-b feat/atif-mas" in graphectory.BUILD_COMMAND


def test_graph_links_quote_the_id() -> None:
    assert graphectory.graph_link("http://v", "r.a/b") == "http://v/api/graph?id=r.a%2Fb"


# ─── publish_run ─────────────────────────────────────────────────────────────
def test_publish_copies_atif_and_returns_links(fake_viewer: FakeViewer, run_dir: Path) -> None:
    links = graphectory.publish_run(fake_viewer.url, run_dir, fake_viewer.data_dir)
    assert links == {iid: f"{fake_viewer.url}/api/graph?id={_graph_id(iid)}" for iid in IIDS}
    for iid in IIDS:
        copied = fake_viewer.data_dir / RUN_ID / iid / "trajectory.json"
        assert copied.read_bytes() == (run_dir / iid / "trajectory.json").read_bytes()
        assert stat.S_IMODE(copied.stat().st_mode) == 0o644
        assert stat.S_IMODE(copied.parent.stat().st_mode) == 0o755
    assert json.loads((run_dir / "graphectory-links.json").read_text(encoding="utf-8")) == {"links": links}
    assert ("POST", "/api/config", {"trajs": "/data", "eval_report": ""}) in fake_viewer.requests
    assert fake_viewer.requests[-1][:2] == ("GET", "/api/graphs")


def test_publish_clears_legacy_sessions(fake_viewer: FakeViewer, run_dir: Path) -> None:
    """Converter-made Claude Code sessions would hide every ATIF run in the
    Viewer (it picks one format per folder)."""
    old = fake_viewer.data_dir / "old-run"
    (old / "agents" / "main").mkdir(parents=True)
    (old / "state.json").write_text("{}", encoding="utf-8")
    (old / "agents" / "main" / "wire.jsonl").write_text("", encoding="utf-8")
    notes = fake_viewer.data_dir / "notes"
    notes.mkdir()
    graphectory.publish_run(fake_viewer.url, run_dir, fake_viewer.data_dir)
    assert not old.exists()
    assert notes.is_dir()


def test_clear_legacy_sessions_counts(tmp_path: Path) -> None:
    for name in ("a", "b"):
        (tmp_path / name / "agents").mkdir(parents=True)
        (tmp_path / name / "state.json").write_text("{}", encoding="utf-8")
    (tmp_path / "c").mkdir()
    assert graphectory.clear_legacy_sessions(tmp_path) == 2
    assert graphectory.clear_legacy_sessions(tmp_path / "missing") == 0


def test_a_run_without_trajectories_is_a_404(fake_viewer: FakeViewer, tmp_path: Path) -> None:
    empty = tmp_path / "empty-run"
    empty.mkdir()
    with pytest.raises(graphectory.GraphectoryError) as exc:
        graphectory.publish_run(fake_viewer.url, empty, fake_viewer.data_dir)
    assert exc.value.status == 404
    assert fake_viewer.requests == []


def test_an_unreachable_viewer_is_a_504_naming_the_container(tmp_path: Path, run_dir: Path) -> None:
    with pytest.raises(graphectory.GraphectoryError) as exc:
        graphectory.publish_run(f"http://127.0.0.1:{_closed_port()}", run_dir, tmp_path / "d")
    assert exc.value.status == 504
    assert "graphectory-viewer" in str(exc.value) and "opendraco status" in str(exc.value)


def test_a_viewer_that_refuses_its_data_folder_is_a_502(fake_viewer: FakeViewer, run_dir: Path) -> None:
    fake_viewer.config_ok = False
    with pytest.raises(graphectory.GraphectoryError) as exc:
        graphectory.publish_run(fake_viewer.url, run_dir, fake_viewer.data_dir)
    assert exc.value.status == 502
    assert "bad data source" in str(exc.value)


def test_a_viewer_that_never_lists_the_run_names_the_atif_fork(
    fake_viewer: FakeViewer, run_dir: Path,
) -> None:
    """E.g. a stock Graphectory, which can't read ATIF, or another /data."""
    fake_viewer.list_runs = False
    with pytest.raises(graphectory.GraphectoryError) as exc:
        graphectory.publish_run(fake_viewer.url, run_dir, fake_viewer.data_dir)
    assert exc.value.status == 502
    assert _graph_id(IIDS[0]) in str(exc.value)
    assert "feat/atif-mas" in str(exc.value) and "ATIF" in str(exc.value)


# ─── A Viewer on another machine: upload ─────────────────────────────────────
@pytest.mark.parametrize(("url", "local"), [
    ("http://localhost:9610", True), ("http://127.0.0.1:9610/", True),
    ("http://LOCALHOST", True), ("http://[::1]:9610", True),
    ("https://server.example.ts.net:9610", False), ("http://100.117.74.33:9610", False),
    ("http://192.168.1.20:9610", False),
])
def test_only_localhost_is_a_local_viewer(url: str, local: bool) -> None:
    assert graphectory.is_local_viewer(url) is local


@pytest.fixture
def remote_viewer(fake_viewer: FakeViewer, monkeypatch: pytest.MonkeyPatch) -> FakeViewer:
    """The stand-in Viewer, treated as being on another machine: its
    `data_dir` plays the server's upload folder, which OpenDraco cannot see."""
    monkeypatch.setattr(graphectory, "is_local_viewer", lambda url: False)
    return fake_viewer


def test_publish_uploads_to_a_viewer_on_another_machine(
    remote_viewer: FakeViewer, run_dir: Path, _isolated_data_dir: Path,
) -> None:
    links = graphectory.publish_run(remote_viewer.url, run_dir)
    assert links == {iid: f"{remote_viewer.url}/api/graph?id={_graph_id(iid)}" for iid in IIDS}
    uploads = [body for method, path, body in remote_viewer.requests if path == "/api/upload"]
    assert [(u["run_id"], u["instance_id"]) for u in uploads] == [(RUN_ID, iid) for iid in sorted(IIDS)]
    for upload in uploads:
        local = json.loads((run_dir / upload["instance_id"] / "trajectory.json").read_text(encoding="utf-8"))
        assert upload["trajectory"] == local
    # The Viewer switches to its upload folder itself: no /api/config, and
    # nothing is written to this machine's data folder.
    assert not any(path == "/api/config" for _m, path, _b in remote_viewer.requests)
    assert not _isolated_data_dir.exists()
    assert remote_viewer.requests[-1][:2] == ("GET", "/api/graphs")
    assert json.loads((run_dir / "graphectory-links.json").read_text(encoding="utf-8")) == {"links": links}


def test_a_local_viewer_gets_no_upload(fake_viewer: FakeViewer, run_dir: Path) -> None:
    graphectory.publish_run(fake_viewer.url, run_dir, fake_viewer.data_dir)
    assert not any(path == "/api/upload" for _m, path, _b in fake_viewer.requests)


@pytest.mark.parametrize(("status", "expected"), [
    (404, "has no upload endpoint"),
    (403, "refuses uploads"),
])
def test_a_viewer_that_cannot_take_uploads_says_how_to_enable_them(
    remote_viewer: FakeViewer, run_dir: Path, status: int, expected: str,
) -> None:
    """404: a Viewer older than the upload endpoint. 403: started without
    `--upload_dir`."""
    remote_viewer.upload_status = status
    with pytest.raises(graphectory.GraphectoryError) as exc:
        graphectory.publish_run(remote_viewer.url, run_dir)
    assert exc.value.status == 502 and exc.value.viewer_status == status
    assert expected in str(exc.value) and "--upload_dir" in str(exc.value)
    assert not (run_dir / "graphectory-links.json").exists()


def test_another_upload_error_keeps_the_viewers_message(
    remote_viewer: FakeViewer, run_dir: Path,
) -> None:
    remote_viewer.upload_status = 500
    with pytest.raises(graphectory.GraphectoryError) as exc:
        graphectory.publish_run(remote_viewer.url, run_dir)
    assert exc.value.status == 502
    assert "POST /api/upload with HTTP 500: Uploads are disabled." in str(exc.value)


def test_an_upload_the_viewer_cannot_read_names_the_atif_fork(
    remote_viewer: FakeViewer, run_dir: Path,
) -> None:
    remote_viewer.list_runs = False
    with pytest.raises(graphectory.GraphectoryError) as exc:
        graphectory.publish_run(remote_viewer.url, run_dir)
    assert exc.value.status == 502
    assert "stored the upload" in str(exc.value) and "feat/atif-mas" in str(exc.value)


@pytest.mark.parametrize("url", ["", "ftp://x", "http://"])
def test_a_bad_viewer_url_is_a_503(tmp_path: Path, run_dir: Path, url: str) -> None:
    with pytest.raises(graphectory.GraphectoryError) as exc:
        graphectory.publish_run(url, run_dir, tmp_path / "d")
    assert exc.value.status == 503


def test_publish_run_dir_never_raises_and_warns(
    run_dir: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    assert graphectory.publish_run_dir(f"http://127.0.0.1:{_closed_port()}", run_dir) is None
    assert any(r.levelno == logging.WARNING and RUN_ID in r.getMessage() for r in caplog.records)


def test_publish_run_dir_logs_the_links_at_info(
    fake_viewer: FakeViewer, run_dir: Path, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(graphectory, "DATA_DIR", fake_viewer.data_dir)
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    links = graphectory.publish_run_dir(fake_viewer.url, run_dir)
    assert links and set(links) == set(IIDS)
    assert any(r.levelno == logging.INFO and links[IIDS[0]] in r.getMessage() for r in caplog.records)


def test_the_viewer_is_reachable_only_when_it_answers(fake_viewer: FakeViewer) -> None:
    assert graphectory.graphectory_reachable(fake_viewer.url) is True
    assert graphectory.graphectory_reachable(f"http://127.0.0.1:{_closed_port()}") is False
    assert graphectory.graphectory_reachable("ftp://example.org") is False


# ─── The end-of-run publish ──────────────────────────────────────────────────
def test_the_end_of_run_publish_is_off_without_graphectory_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GRAPHECTORY_URL", raising=False)
    started: list[Any] = []
    monkeypatch.setattr(
        inference, "threading", SimpleNamespace(Thread=lambda *a, **k: started.append(k)),
    )
    inference._start_graphectory_publish("unused-run-dir")
    assert started == []


def test_the_end_of_run_publish_writes_the_links(
    run_dir: Path, fake_viewer: FakeViewer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPHECTORY_URL", fake_viewer.url)
    monkeypatch.setattr(graphectory, "DATA_DIR", fake_viewer.data_dir)
    threads: list[threading.Thread] = []
    real_thread = threading.Thread

    def spy(*args: Any, **kwargs: Any) -> threading.Thread:
        threads.append(real_thread(*args, **kwargs))
        return threads[-1]

    monkeypatch.setattr(inference, "threading", SimpleNamespace(Thread=spy))
    inference._start_graphectory_publish(str(run_dir))
    [thread] = threads
    assert thread.daemon is True
    thread.join(10)
    saved = json.loads((run_dir / "graphectory-links.json").read_text(encoding="utf-8"))
    assert set(saved["links"]) == set(IIDS)


def test_an_unusable_run_dir_warns_and_does_not_raise(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    inference._publish_run_folder("http://127.0.0.1:9", str(tmp_path / "missing"))
    assert any(r.levelno == logging.WARNING for r in caplog.records)


# ─── The Viewer's container ──────────────────────────────────────────────────
@dataclass
class FakeDocker:
    """Records `docker` calls and answers them from its state."""
    container: dict[str, Any] | None = None
    image: bool = True
    installed: bool = True
    calls: list[list[str]] = field(default_factory=list)

    def __call__(self, *args: str) -> subprocess.CompletedProcess[str]:
        if not self.installed:
            raise FileNotFoundError("docker")
        self.calls.append(list(args))
        ok = subprocess.CompletedProcess(list(args), 0, "", "")
        fail = subprocess.CompletedProcess(list(args), 1, "", "No such object")
        if args[:2] == ("container", "inspect"):
            return subprocess.CompletedProcess(list(args), 0, json.dumps([self.container]), "") \
                if self.container else fail
        if args[:2] == ("image", "inspect"):
            return ok if self.image else fail
        if args[0] == "rm":
            self.container = None
        return ok


def _container(data_dir: Path, port: int) -> dict[str, Any]:
    return {
        "Mounts": [{"Source": str(data_dir), "Destination": "/data"}],
        "HostConfig": {"PortBindings": {"9610/tcp": [{"HostIp": "", "HostPort": str(port)}]}},
    }


@pytest.fixture
def docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeDocker:
    fake = FakeDocker()
    monkeypatch.setattr(graphectory, "_docker", fake)
    monkeypatch.setattr(graphectory, "DATA_DIR", tmp_path / "results" / "graphectory")
    return fake


@pytest.mark.parametrize(("url", "port"), [
    ("http://localhost:9610", 9610), ("http://127.0.0.1:9611/", 9611),
    ("http://localhost", 80), ("https://localhost", 443), ("http://localhost:bad", None),
])
def test_the_viewer_port_comes_from_the_url(url: str, port: int | None) -> None:
    assert graphectory.viewer_port(url) == port


def test_the_run_command_mounts_the_data_folder(docker: FakeDocker) -> None:
    cmd = graphectory.run_command(9611)
    assert cmd.startswith("docker run -d --name graphectory-viewer --restart unless-stopped")
    assert "-p 9611:9610" in cmd
    assert f'-v "{graphectory.DATA_DIR}:/data"' in cmd
    assert cmd.endswith("graphectory python graph_construction/live_graph_server.py --port 9610")


def test_the_build_command_works_in_bash_and_powershell() -> None:
    """`;` instead of `&&`, which Windows PowerShell 5.1 rejects."""
    assert "&&" not in graphectory.BUILD_COMMAND
    assert "docker build -t graphectory Graphectory" in graphectory.BUILD_COMMAND


def test_status_reports_a_matching_running_container(docker: FakeDocker) -> None:
    docker.container = _container(graphectory.DATA_DIR, 9610) | {"State": {"Running": True}}
    status = graphectory.viewer_container_status()
    assert (status.docker, status.image, status.exists, status.running) == (True, True, True, True)
    assert status.ports == ("9610",) and status.mounts_data_dir()


def test_status_reports_another_data_folder(docker: FakeDocker, tmp_path: Path) -> None:
    docker.container = _container(tmp_path / "graphectory-data", 9610) | {"State": {"Running": False}}
    status = graphectory.viewer_container_status()
    assert status.exists and not status.running
    assert not status.mounts_data_dir()
    assert status.data_dir == str(tmp_path / "graphectory-data")


def test_status_without_a_container_or_image(docker: FakeDocker) -> None:
    docker.image = False
    status = graphectory.viewer_container_status()
    assert (status.docker, status.image, status.exists) == (True, False, False)


def test_status_without_docker(docker: FakeDocker) -> None:
    docker.installed = False
    assert graphectory.viewer_container_status().docker is False


def test_status_never_raises_on_an_odd_docker_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graphectory, "_docker", lambda *a: SimpleNamespace(returncode=0))
    assert graphectory.viewer_container_status().docker is False


def test_status_never_changes_the_container(docker: FakeDocker) -> None:
    """OpenDraco only reads the container: it never starts, creates or
    removes it."""
    docker.container = _container(graphectory.DATA_DIR, 9612)
    graphectory.viewer_container_status()
    assert {tuple(c[:2]) for c in docker.calls} <= {("image", "inspect"), ("container", "inspect")}


def test_the_api_has_no_startup_hook() -> None:
    """Starting the api must not touch Docker."""
    from api import server
    assert not hasattr(graphectory, "ensure_viewer_container")
    assert not hasattr(graphectory, "start_viewer_in_background")
    assert "graphectory" not in Path(server.__file__).read_text(encoding="utf-8").lower()


# ─── The hook on the run's completion path ───────────────────────────────────
IID = "django__django-10973"


@pytest.fixture
def stubbed_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Everything `/api/inference/run` touches, replaced so a run is a
    few instant steps: a throwaway results tree, no LLM, no clone."""
    import opendraco.config.history as history
    import opendraco.config.loader as loader
    import opendraco.core.workflow.graph_builder as graph_builder
    import opendraco.core.workflow.runner as runner
    import opendraco.core.workflow.state_factory as state_factory
    import opendraco.utils.ollama_preflight as preflight
    import opendraco.utils.patch as patch_utils
    import opendraco.utils.workspace as workspace

    instances = tmp_path / "instances.jsonl"
    instances.write_text(
        json.dumps({"instance_id": IID, "repo": "django/django", "base_commit": "abc"}) + "\n",
        encoding="utf-8",
    )
    dirs = {name: tmp_path / name for name in (
        "PREDICTIONS_DIR", "PREDICTION_TEXT_LOGS_DIR",
        "PREDICTION_CONFIGS_DIR", "INFERENCE_INTERNAL_LOGS_DIR",
    )}
    for name, path in dirs.items():
        monkeypatch.setattr(inference, name, path)
    monkeypatch.setattr(inference, "INSTANCES_PATH", instances)

    state = SimpleNamespace(preflight=lambda cfg, event_sink: None, calls=[], tail=[])
    monkeypatch.setattr(loader, "load_config", lambda name: {"id": name, "edges": []})
    monkeypatch.setattr(history, "current_sha", lambda name: None)
    monkeypatch.setattr(
        preflight, "preflight_models", lambda cfg, event_sink: state.preflight(cfg, event_sink),
    )
    monkeypatch.setattr(runner, "_build_agents", lambda cfg: {})
    monkeypatch.setattr(state_factory, "build_state_class", lambda cfg, agents: object)
    monkeypatch.setattr(state_factory, "build_initial_state", lambda cfg, agents, ctx: {})
    monkeypatch.setattr(
        graph_builder, "build_graph",
        lambda cfg, agents, state_cls: SimpleNamespace(stream=lambda *a, **k: iter(())),
    )
    monkeypatch.setattr(patch_utils, "generate_diff_impl", lambda path: "")
    monkeypatch.setattr(
        workspace, "clone_workspace",
        lambda iid, repo, commit: SimpleNamespace(path=tmp_path),
    )

    def hook(run_dir: str) -> None:
        # The ATIF log must be final by now: read the instance back.
        doc = json.loads((Path(run_dir) / IID / "trajectory.json").read_text(encoding="utf-8"))
        state.calls.append((Path(run_dir).name, doc["session_id"], doc["extra"]["status"]))

    monkeypatch.setattr(inference, "_start_graphectory_publish", hook)
    return state


def _run_to_the_end() -> list[dict[str, Any]]:
    async def drain() -> list[str]:
        resp = await inference.run_inference(
            inference.InferenceRequest(instance_ids=[IID], config="chain"),
        )
        return [chunk async for chunk in resp.body_iterator]

    chunks = asyncio.run(drain())
    return [json.loads(c.removeprefix("data: ")) for c in chunks]


def test_the_hook_runs_once_on_success(stubbed_run: SimpleNamespace) -> None:
    events = _run_to_the_end()
    assert events[-1]["type"] == "done"
    [(folder, run_id, status)] = stubbed_run.calls
    assert folder == f"prediction-{run_id}"
    assert run_id == events[-1]["run_id"] and run_id.startswith("chain-")
    assert status == "done"


def test_the_hook_runs_once_on_error(stubbed_run: SimpleNamespace) -> None:
    def fail(cfg: Any, event_sink: Any) -> None:
        raise OpendracoError("no model")

    stubbed_run.preflight = fail
    events = _run_to_the_end()
    assert events[-1]["type"] == "error"
    [(_, _, status)] = stubbed_run.calls
    assert status == "error"


def test_the_hook_runs_once_on_cancel(stubbed_run: SimpleNamespace) -> None:
    def cancel(cfg: Any, event_sink: Any) -> None:
        inference._cancel_flags[IID] = True

    stubbed_run.preflight = cancel
    events = _run_to_the_end()
    assert events[-1]["type"] == "cancelled"
    [(_, _, status)] = stubbed_run.calls
    assert status == "cancelled"


def test_a_failing_hook_never_breaks_the_run(
    stubbed_run: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(run_dir: str) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(inference, "_start_graphectory_publish", boom)
    events = _run_to_the_end()
    assert events[-1]["type"] == "done"


def test_no_hook_when_the_run_never_opened_a_log(
    stubbed_run: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import opendraco.config.loader as loader

    def broken(name: str) -> dict[str, Any]:
        raise OpendracoError("bad config")

    monkeypatch.setattr(loader, "load_config", broken)
    events = _run_to_the_end()
    assert events[-1]["type"] == "error"
    assert stubbed_run.calls == []
