"""Local Graphectory: publish a run into the Viewer.

`publish_run` converts a run's inference log with the built-in converter
(`opendraco.utils.graphectory_converter`), writes it into
`<RESULTS_DIR>/graphectory` and reloads the Viewer until it lists the run; a
finished run is published in the background. The `graphectory-viewer`
container is only ever inspected, never changed. These tests use a scripted
stand-in Viewer on a loopback port (stdlib `http.server`), a stand-in
converter (plus the real one on a small log) and a stubbed `docker`, so no
network or Docker is needed.
"""
from __future__ import annotations

import asyncio
import json
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

LOG_TEXT = (
    json.dumps({"type": "run_meta", "run_id": "chain-4f7d9f56", "config_name": "chain"}) + "\n"
    + json.dumps({"type": "agent_event", "agent": "locator", "delta": {"note": "héllo"}}) + "\n"
)
LOGGER_NAME = graphectory.logger.name
# Captured before any test patches it.
REAL_DATA_DIR = graphectory.DATA_DIR


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """No test may write into the real `<RESULTS_DIR>/graphectory`."""
    data_dir = tmp_path / "isolated-results" / "graphectory"
    monkeypatch.setattr(graphectory, "DATA_DIR", data_dir)
    return data_dir


# ─── Stand-ins ───────────────────────────────────────────────────────────────
@dataclass
class FakeViewer:
    """Loopback stand-in for the Graphectory Viewer: `POST /api/config`
    (re)loads `data_dir`, `GET /api/graphs` lists its runs, `GET /` is up."""
    url: str
    data_dir: Path
    requests: list[tuple[str, str, Any]] = field(default_factory=list)
    config_ok: bool = True
    list_runs: bool = True
    loaded: bool = False


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
                ids = sorted(p.parent.name for p in state.data_dir.glob("*/state.json")) \
                    if state.loaded and state.list_runs else []
                self._send(200, {"status": "complete", "graphs": [{"instance_id": i} for i in ids]})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            state.requests.append(("POST", self.path, body))
            if self.path == "/api/config" and state.config_ok:
                state.loaded = True
                self._send(200, {"ok": True, "trajs": body["trajs"], "agent_type": "claude"})
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


class FakeConvertError(ValueError):
    pass


@pytest.fixture
def fake_converter(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, bytes, Any]]:
    """The built-in converter's `run_to_session` replaced by a stand-in that
    records its calls and refuses a log containing `BAD`."""
    calls: list[tuple[str, str, bytes, Any]] = []

    def run_to_session(framework: str, run_id: str, body: bytes, title: Any = None):
        calls.append((framework, run_id, body, title))
        if b"BAD" in body:
            raise FakeConvertError("The OpenDraco event log records no agent activity.")
        return ({"title": title, "custom": {"sourceFramework": "Claude Code"}},
                [{"type": "context.append_loop_event", "event": {"n": 1}},
                 {"type": "context.append_loop_event", "event": {"note": "héllo"}}])

    monkeypatch.setattr(graphectory, "run_to_session", run_to_session)
    monkeypatch.setattr(graphectory, "ConvertError", FakeConvertError)
    return calls


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


# ─── The built-in converter ──────────────────────────────────────────────────
# A minimal OpenDraco inference event log: one instance, two agents.
REAL_LOG = "\n".join(json.dumps(e) for e in [
    {"type": "run_meta", "run_id": "chain-0000abcd", "config_name": "chain",
     "config_sha": None, "instance_ids": ["demo__demo-1"], "ts": "2026-11-06T10:00:00"},
    {"type": "instance_start", "instance_id": "demo__demo-1", "index": 0, "total": 1},
    {"type": "start", "instance_id": "demo__demo-1", "config": "chain"},
    {"type": "agent_input", "agent": "locator", "inputs": {"problem_statement": "fix it"}},
    {"type": "tool_call", "agent": "locator", "tool": "search_code",
     "args_preview": "query=foo", "result_preview": "2 items"},
    {"type": "response", "agent": "locator", "content": "Found it in foo.py"},
    {"type": "agent_event", "agent": "locator", "delta": {"location": "foo.py"}},
    {"type": "handoff", "from": "locator", "to": "patcher", "keys": ["location"],
     "summary": "location", "preview": "foo.py", "timestamp": "2026-11-06T10:00:05"},
    {"type": "response", "agent": "patcher", "content": "Patched foo.py"},
    {"type": "agent_event", "agent": "patcher", "delta": {"patch": "diff"}},
    {"type": "instance_done", "instance_id": "demo__demo-1", "index": 0, "total": 1,
     "output_path": "x.jsonl", "run_id": "chain-0000abcd", "patch": ""},
    {"type": "done", "instance_ids": ["demo__demo-1"], "output_path": "x.jsonl",
     "run_id": "chain-0000abcd"},
]) + "\n"


def test_the_built_in_converter_turns_a_log_into_a_claude_code_session() -> None:
    """No install needed: the converter ships with OpenDraco."""
    state, records = graphectory.convert_run("chain-0000abcd", REAL_LOG.encode("utf-8"), "t")
    assert state["custom"]["sourceFramework"] == "Claude Code"
    assert records and all(r["type"] == "context.append_loop_event" for r in records)
    text = json.dumps(records)
    assert "locator" in text and "patcher" in text


def test_the_built_in_converter_refuses_a_log_without_agents() -> None:
    with pytest.raises(graphectory.GraphectoryError) as exc:
        graphectory.convert_run("r1", b'{"type": "status", "message": "hi"}\n')
    assert exc.value.status == 400
    assert str(exc.value).startswith("Graphectory could not convert the run:")


# ─── publish_run ─────────────────────────────────────────────────────────────
def test_publish_writes_the_session_reloads_the_viewer_and_returns_the_link(
    fake_viewer: FakeViewer, fake_converter: list,
) -> None:
    link = graphectory.publish_run(
        fake_viewer.url, "chain-4f7d9f56", "chain chain-4f7d9f56", LOG_TEXT, fake_viewer.data_dir,
    )
    assert link == f"{fake_viewer.url}/api/graph?id=chain-4f7d9f56"
    [(framework, run_id, body, title)] = fake_converter
    assert (framework, run_id, title) == ("opendraco", "chain-4f7d9f56", "chain chain-4f7d9f56")
    assert body == LOG_TEXT.encode("utf-8")

    session = fake_viewer.data_dir / "chain-4f7d9f56"
    assert json.loads((session / "state.json").read_text(encoding="utf-8"))["custom"] == {
        "sourceFramework": "Claude Code"}
    wire = (session / "agents" / "main" / "wire.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(l)["event"] for l in wire] == [{"n": 1}, {"note": "héllo"}]

    assert ("POST", "/api/config", {"trajs": "/data", "eval_report": ""}) in fake_viewer.requests
    assert fake_viewer.requests[-1][:2] == ("GET", "/api/graphs")


def test_publish_sanitises_the_run_id(fake_viewer: FakeViewer, fake_converter: list) -> None:
    link = graphectory.publish_run(fake_viewer.url, "my run/1", "t", LOG_TEXT, fake_viewer.data_dir)
    assert link.endswith("/api/graph?id=my-run-1")
    assert (fake_viewer.data_dir / "my-run-1" / "state.json").is_file()


def test_an_unconvertible_log_is_a_400_and_writes_nothing(
    fake_viewer: FakeViewer, fake_converter: list,
) -> None:
    with pytest.raises(graphectory.GraphectoryError) as exc:
        graphectory.publish_run(fake_viewer.url, "r1", "t", "BAD", fake_viewer.data_dir)
    assert exc.value.status == 400
    assert "no agent activity" in str(exc.value)
    assert not fake_viewer.data_dir.exists()
    assert fake_viewer.requests == []


def test_an_unreachable_viewer_is_a_504_naming_the_container(
    tmp_path: Path, fake_converter: list,
) -> None:
    with pytest.raises(graphectory.GraphectoryError) as exc:
        graphectory.publish_run(f"http://127.0.0.1:{_closed_port()}", "r1", "t", LOG_TEXT, tmp_path)
    assert exc.value.status == 504
    assert "graphectory-viewer" in str(exc.value) and "opendraco status" in str(exc.value)


def test_a_viewer_that_refuses_its_data_folder_is_a_502(
    fake_viewer: FakeViewer, fake_converter: list,
) -> None:
    fake_viewer.config_ok = False
    with pytest.raises(graphectory.GraphectoryError) as exc:
        graphectory.publish_run(fake_viewer.url, "r1", "t", LOG_TEXT, fake_viewer.data_dir)
    assert exc.value.status == 502
    assert "bad data source" in str(exc.value)


def test_a_viewer_that_never_lists_the_run_is_a_502(
    fake_viewer: FakeViewer, fake_converter: list,
) -> None:
    """E.g. a container whose /data is another folder."""
    fake_viewer.list_runs = False
    with pytest.raises(graphectory.GraphectoryError) as exc:
        graphectory.publish_run(fake_viewer.url, "r1", "t", LOG_TEXT, fake_viewer.data_dir)
    assert exc.value.status == 502
    assert "does not list run 'r1'" in str(exc.value)


@pytest.mark.parametrize("url", ["", "ftp://x", "http://"])
def test_a_bad_viewer_url_is_a_503(tmp_path: Path, fake_converter: list, url: str) -> None:
    with pytest.raises(graphectory.GraphectoryError) as exc:
        graphectory.publish_run(url, "r1", "t", LOG_TEXT, tmp_path)
    assert exc.value.status == 503


def test_publish_run_log_never_raises_and_warns(
    tmp_path: Path, fake_converter: list, caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    assert graphectory.publish_run_log(f"http://127.0.0.1:{_closed_port()}", "r1", "t", LOG_TEXT) is None
    assert not (REAL_DATA_DIR / "r1").exists()
    assert any(r.levelno == logging.WARNING and "r1" in r.getMessage() for r in caplog.records)


def test_publish_run_log_logs_the_link_at_info(
    fake_viewer: FakeViewer, fake_converter: list, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(graphectory, "DATA_DIR", fake_viewer.data_dir)
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    graph = graphectory.publish_run_log(fake_viewer.url, "r1", "t", LOG_TEXT)
    assert graph == f"{fake_viewer.url}/api/graph?id=r1"
    assert any(r.levelno == logging.INFO and graph in r.getMessage() for r in caplog.records)


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
    inference._start_graphectory_publish("chain", "chain-4f7d9f56", "unused.ndjson")
    assert started == []


def test_the_end_of_run_publish_saves_the_link_beside_the_log(
    tmp_path: Path, fake_viewer: FakeViewer, fake_converter: list,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPHECTORY_URL", fake_viewer.url)
    monkeypatch.setattr(graphectory, "DATA_DIR", fake_viewer.data_dir)
    log = tmp_path / "prediction-chain-4f7d9f56.ndjson"
    log.write_text(LOG_TEXT, encoding="utf-8")
    threads: list[threading.Thread] = []
    real_thread = threading.Thread

    def spy(*args: Any, **kwargs: Any) -> threading.Thread:
        threads.append(real_thread(*args, **kwargs))
        return threads[-1]

    monkeypatch.setattr(inference, "threading", SimpleNamespace(Thread=spy))
    inference._start_graphectory_publish("chain", "chain-4f7d9f56", str(log))
    [thread] = threads
    assert thread.daemon is True
    thread.join(10)
    saved = json.loads((tmp_path / "prediction-chain-4f7d9f56.graphectory-link.json")
                       .read_text(encoding="utf-8"))
    assert saved == {"graph": f"{fake_viewer.url}/api/graph?id=chain-4f7d9f56",
                     "run_id": "chain-4f7d9f56"}


def test_an_unreadable_log_file_warns_and_does_not_raise(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    inference._publish_log_file("http://127.0.0.1:9", "chain", "r1", str(tmp_path / "missing.ndjson"))
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

    def hook(config_name: str, run_id: str, log_path: str) -> None:
        # The log must be complete and closed by now: read it back.
        lines = Path(log_path).read_text(encoding="utf-8").splitlines()
        state.calls.append((config_name, run_id, json.loads(lines[-1])["type"]))

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
    [(config_name, run_id, last_event)] = stubbed_run.calls
    assert config_name == "chain"
    assert run_id == events[-1]["run_id"] and run_id.startswith("chain-")
    assert last_event == "done"


def test_the_hook_runs_once_on_error(stubbed_run: SimpleNamespace) -> None:
    def fail(cfg: Any, event_sink: Any) -> None:
        raise OpendracoError("no model")

    stubbed_run.preflight = fail
    events = _run_to_the_end()
    assert events[-1]["type"] == "error"
    [(_, _, last_event)] = stubbed_run.calls
    assert last_event == "error"


def test_the_hook_runs_once_on_cancel(stubbed_run: SimpleNamespace) -> None:
    def cancel(cfg: Any, event_sink: Any) -> None:
        inference._cancel_flags[IID] = True

    stubbed_run.preflight = cancel
    events = _run_to_the_end()
    assert events[-1]["type"] == "cancelled"
    [(_, _, last_event)] = stubbed_run.calls
    assert last_event == "cancelled"


def test_a_failing_hook_never_breaks_the_run(
    stubbed_run: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(config_name: str, run_id: str, log_path: str) -> None:
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
