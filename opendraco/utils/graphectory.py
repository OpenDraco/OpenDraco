"""Local Graphectory: publish runs into the Viewer.

Graphectory turns a recorded agent run into an interactive trajectory
graph. Everything runs on this machine:

- the **converter** (`opendraco.utils.graphectory_converter`, from
  graphectory-opendraco) turns a run's inference event log
  (`opendraco/logs/inference_logs/<stem>.ndjson`) into one trajectory, which
  `publish_run` writes into `<RESULTS_DIR>/graphectory/<run_id>/`;
- the **Viewer** (`GRAPHECTORY_URL`, e.g. `http://localhost:9610`) is the
  Graphectory Docker container `graphectory-viewer`, made from the
  `graphectory` image with that folder as its `/data`. OpenDraco never
  starts, creates or removes it: it is built and run with plain docker
  commands (`BUILD_COMMAND`, `run_command`), and `viewer_container_status`
  only reads its state for `opendraco status`. `GET /` is the Viewer's
  liveness check.

`GRAPHECTORY_URL` unset or empty disables all of it. Runs that end are
published in the background by `publish_run_log` (best-effort, never
raises); the Results page's button calls `publish_run`, which raises
`GraphectoryError` so the page can show why it failed.

FastAPI-free like the other `opendraco.utils` helpers; the Results router
translates `GraphectoryError` into an `HTTPException`.
"""
from __future__ import annotations

import http.client
import json
import logging
import os
import re
import ssl
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, urlsplit

import certifi

from opendraco.paths import RESULTS_DIR
from opendraco.utils.graphectory_converter import ConvertError, run_to_session

logger = logging.getLogger(__name__)

# ─── Layout ──────────────────────────────────────────────────────────────────
# The converted runs; the Viewer's container mounts this folder as /data.
DATA_DIR: Path = RESULTS_DIR / "graphectory"
# The data folder's path inside the Viewer's container.
VIEWER_DATA_PATH = "/data"
IMAGE = "graphectory"
CONTAINER = "graphectory-viewer"
# The port the Viewer listens on inside the container.
CONTAINER_PORT = 9610
GRAPHECTORY_REPO = "https://github.com/Intelligent-CAT-Lab/Graphectory.git"
# Joined with `;`, which bash and PowerShell both accept (`&&` is not valid
# in Windows PowerShell 5.1).
BUILD_COMMAND = (
    f"git clone {GRAPHECTORY_REPO} Graphectory; docker build -t {IMAGE} Graphectory"
)


def run_command(port: int = CONTAINER_PORT, data_dir: Path | None = None) -> str:
    """The `docker run` that creates the Viewer's container for `port`,
    with `data_dir` (default `DATA_DIR`) as its /data."""
    return (
        f'docker run -d --name {CONTAINER} --restart unless-stopped '
        f'-p {port}:{CONTAINER_PORT} -v "{data_dir or DATA_DIR}:{VIEWER_DATA_PATH}" '
        f'{IMAGE} python graph_construction/live_graph_server.py --port {CONTAINER_PORT}'
    )

# ─── Timeouts ────────────────────────────────────────────────────────────────
# `opendraco status` is a quick doctor check; a Viewer that needs longer
# than this to answer counts as not reachable.
STATUS_TIMEOUT_S = 5.0
# The Viewer probe target: its root page (it has no health route).
STATUS_PATH = "/"
# One request to the Viewer's API.
VIEWER_TIMEOUT_S = 10.0
# How long `publish_run` waits for the Viewer to list a run after reloading
# its data folder (the Results page's request waits for it).
LIST_WAIT_S = 45.0
# `docker container inspect` for `opendraco status`.
DOCKER_TIMEOUT_S = 15.0

# The rule a run id must follow (it names a folder and a URL parameter).
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_publish_lock = threading.Lock()


class GraphectoryError(Exception):
    """A failed publish. `status` is the HTTP status the api should answer
    with; `str(exc)` is the message shown on the Results page."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


# ─── Settings ────────────────────────────────────────────────────────────────
def graphectory_base_url() -> str:
    """`GRAPHECTORY_URL` (the Viewer) from the environment (loaded from
    `.env` like `OLLAMA_BASE_URL`). Empty means Graphectory is disabled."""
    return os.environ.get("GRAPHECTORY_URL", "").strip().strip("\"'").strip().rstrip("/")


def is_valid_run_id(run_id: str) -> bool:
    return bool(_ID_RE.fullmatch(run_id))


def safe_run_id(raw: str) -> str:
    """`raw` squeezed into the run-id rule: runs of characters outside
    `[A-Za-z0-9._-]` become one `-`, leading punctuation is dropped, and the
    result is cut to 128 characters. An id with nothing usable left becomes
    `run`."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).lstrip("._-")[:128]
    return cleaned or "run"


def _origin(parts: SplitResult) -> tuple[str, str, int | None]:
    default_port = {"http": 80, "https": 443}.get(parts.scheme)
    try:
        port = parts.port or default_port
    except ValueError:
        port = None
    return parts.scheme.lower(), (parts.hostname or "").lower(), port


def is_on_viewer(link: str, viewer_url: str) -> bool:
    """True when `link` is relative (resolved against the Viewer) or has the
    same scheme, host and port as `viewer_url`."""
    parts = urlsplit(link.strip())
    if not parts.scheme and not parts.netloc:
        return True
    return _origin(parts) == _origin(urlsplit(viewer_url.strip()))


def graph_link(viewer_url: str, run_id: str) -> str:
    return f"{viewer_url.rstrip('/')}/api/graph?id={run_id}"


# ─── Converter ───────────────────────────────────────────────────────────────
def convert_run(run_id: str, log_bytes: bytes, title: str | None = None) -> tuple[dict, list[dict]]:
    """`(state.json dict, wire.jsonl records)` for one OpenDraco run. Raises
    `GraphectoryError` (400) for a log the converter cannot use."""
    try:
        return run_to_session("opendraco", run_id, log_bytes, title)
    except ConvertError as exc:
        raise GraphectoryError(400, f"Graphectory could not convert the run: {exc}") from exc


def write_session(data_dir: Path, run_id: str, state: dict, records: list[dict]) -> Path:
    """`<data_dir>/<run_id>/state.json` + `agents/main/wire.jsonl`, the
    Claude Code session layout the stock Viewer reads."""
    session = data_dir / run_id
    (session / "agents" / "main").mkdir(parents=True, exist_ok=True)
    (session / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    with open(session / "agents" / "main" / "wire.jsonl", "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return session


# ─── Viewer HTTP ─────────────────────────────────────────────────────────────
def _tls_context() -> ssl.SSLContext:
    """The system trust store plus certifi's bundle. On some Windows
    machines OpenSSL builds the chain of a current Let's Encrypt
    certificate through an expired root from the system store and fails
    with "certificate has expired"; certifi's bundle (the one requests
    and httpx use) gives it a valid path. Verification stays on."""
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cafile=certifi.where())
    return ctx


def _new_connection(parts: SplitResult, timeout: float) -> http.client.HTTPConnection:
    """A not-yet-connected `http.client` connection to an http(s) URL with
    a host. `http.client` never follows redirects and sends no `Origin`;
    https uses the certifi-backed context. Raises `ValueError` for an
    invalid port."""
    host = parts.hostname or ""
    port = parts.port
    if parts.scheme == "https":
        return http.client.HTTPSConnection(host, port, timeout=timeout, context=_tls_context())
    return http.client.HTTPConnection(host, port, timeout=timeout)


def _probe_ok(base_url: str, path: str, accept: str) -> bool:
    """True when `GET <base_url><path>` answers 200 within `STATUS_TIMEOUT_S`."""
    parts = urlsplit(base_url.strip().rstrip("/"))
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        conn = _new_connection(parts, STATUS_TIMEOUT_S)
    except ValueError:
        return False
    try:
        conn.request("GET", f"{parts.path}{path}", headers={"Accept": accept})
        return conn.getresponse().status == 200
    except (OSError, http.client.HTTPException):
        return False
    finally:
        conn.close()


def graphectory_reachable(base_url: str) -> bool:
    """True when the Viewer's root page (`<base_url>/`) answers 200 within
    `STATUS_TIMEOUT_S`. The `opendraco status` check for `GRAPHECTORY_URL`."""
    return _probe_ok(base_url, STATUS_PATH, "text/html")


def _viewer_json(viewer_url: str, method: str, path: str, body: Any = None) -> Any:
    """One JSON request to the Viewer. Raises `GraphectoryError`: 503 for a
    bad `GRAPHECTORY_URL`, 504 when the Viewer is unreachable, 502 for an
    error status or an answer that is not JSON."""
    parts = urlsplit(viewer_url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise GraphectoryError(503, f"GRAPHECTORY_URL is not an http(s) URL: {viewer_url!r}")
    try:
        conn = _new_connection(parts, VIEWER_TIMEOUT_S)
    except ValueError as exc:
        raise GraphectoryError(503, f"GRAPHECTORY_URL has an invalid port: {viewer_url!r}") from exc
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        conn.request(method, f"{parts.path.rstrip('/')}{path}", body=data, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
    except (OSError, http.client.HTTPException) as exc:
        raise GraphectoryError(
            504, f"Could not reach the Graphectory Viewer at {viewer_url}: {exc} -- is the "
                 f"'{CONTAINER}' container running? (`opendraco status` checks it)",
        ) from exc
    finally:
        conn.close()
    try:
        answer = json.loads(raw.decode("utf-8", errors="replace") or "null")
    except ValueError:
        answer = None
    if not 200 <= resp.status < 300:
        detail = answer.get("error") if isinstance(answer, dict) else None
        raise GraphectoryError(
            502, f"The Graphectory Viewer answered {method} {path} with HTTP {resp.status}"
                 + (f": {detail}" if detail else ""),
        )
    if answer is None:
        raise GraphectoryError(502, f"The Graphectory Viewer's answer to {path} is not JSON")
    return answer


def reload_viewer(viewer_url: str, run_id: str | None = None) -> None:
    """Point the Viewer at its data folder again (it reads the folder when
    its data source is set) and, with `run_id`, wait until it lists that
    run. Raises `GraphectoryError`."""
    answer = _viewer_json(
        viewer_url, "POST", "/api/config", {"trajs": VIEWER_DATA_PATH, "eval_report": ""},
    )
    if not isinstance(answer, dict) or not answer.get("ok"):
        raise GraphectoryError(502, f"The Graphectory Viewer refused its data folder: {answer}")
    if run_id is None:
        return
    deadline = time.monotonic() + LIST_WAIT_S
    while True:
        listing = _viewer_json(viewer_url, "GET", "/api/graphs")
        graphs = listing.get("graphs") if isinstance(listing, dict) else None
        if any(isinstance(g, dict) and g.get("instance_id") == run_id for g in graphs or []):
            return
        if (isinstance(listing, dict) and listing.get("status") == "complete") \
                or time.monotonic() > deadline:
            raise GraphectoryError(
                502, f"The Graphectory Viewer does not list run {run_id!r} after reloading -- "
                     f"its container must mount {DATA_DIR} as /data (`opendraco status` "
                     "shows what it mounts)",
            )
        time.sleep(0.5)


# ─── Publishing a run ────────────────────────────────────────────────────────
def publish_run(viewer_url: str, run_id: str, title: str, log_text: str,
                data_dir: Path | None = None) -> str:
    """Convert a run's whole inference log, write it into the Viewer's data
    folder, reload the Viewer until it lists the run, and return the run's
    graph link. `run_id` is sanitised with `safe_run_id`.

    Raises `GraphectoryError`: 400 a log the converter cannot use, 500 the
    data folder is not writable, 503 a bad `GRAPHECTORY_URL`, 502/504 the
    Viewer did not reload or answer."""
    run_id = safe_run_id(run_id)
    state, records = convert_run(run_id, log_text.encode("utf-8"), title)
    with _publish_lock:
        try:
            write_session(data_dir or DATA_DIR, run_id, state, records)
        except OSError as exc:
            raise GraphectoryError(
                500, f"Could not write the run into {data_dir or DATA_DIR}: {exc}",
            ) from exc
        reload_viewer(viewer_url, run_id)
    return graph_link(viewer_url, run_id)


def publish_run_log(viewer_url: str, run_id: str, title: str, log_text: str) -> str | None:
    """`publish_run` for a finished run. Best-effort: never raises; a
    failure is logged as a warning and gives `None`, a success logs the
    graph link at INFO."""
    safe_id = safe_run_id(run_id)
    try:
        graph = publish_run(viewer_url, run_id, title, log_text)
    except Exception as exc:  # nothing about a failed publish may reach the run
        logger.warning("Graphectory publish of run %s failed: %s", safe_id, exc)
        return None
    logger.info("Graphectory graph for run %s: %s", safe_id, graph)
    return graph


# ─── The Viewer's container (read-only) ──────────────────────────────────────
def _docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=DOCKER_TIMEOUT_S,
    )


def viewer_port(viewer_url: str) -> int | None:
    """The port in `GRAPHECTORY_URL` (80/443 by scheme when absent), or
    `None` for a URL without a usable one."""
    parts = urlsplit(viewer_url.strip())
    try:
        return parts.port or {"http": 80, "https": 443}.get(parts.scheme)
    except ValueError:
        return None


def _same_path(a: str, b: Path) -> bool:
    try:
        return Path(a).resolve() == b.resolve()
    except OSError:
        return False


@dataclass
class ContainerStatus:
    """What `opendraco status` reports about the `graphectory-viewer`
    container. `docker` is False without a usable docker CLI; `image` is
    whether the `graphectory` image is built; `exists` / `running` describe
    the container; `data_dir` / `ports` are what it mounts as /data and
    publishes the Viewer on."""
    docker: bool = True
    image: bool = False
    exists: bool = False
    running: bool = False
    data_dir: str = ""
    ports: tuple[str, ...] = ()

    def mounts_data_dir(self) -> bool:
        return bool(self.data_dir) and _same_path(self.data_dir, DATA_DIR)


def viewer_container_status() -> ContainerStatus:
    """The `graphectory` image's and `graphectory-viewer` container's state,
    read with `docker image inspect` / `docker container inspect`. Never
    changes anything; never raises (anything unexpected reads as "docker
    not available")."""
    try:
        return _read_container_status()
    except Exception:
        return ContainerStatus(docker=False)


def _read_container_status() -> ContainerStatus:
    try:
        image = _docker("image", "inspect", IMAGE).returncode == 0
        result = _docker("container", "inspect", CONTAINER)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ContainerStatus(docker=False)
    if result.returncode != 0:
        return ContainerStatus(image=image)
    try:
        info = json.loads(result.stdout)[0]
    except (ValueError, IndexError, TypeError, KeyError):
        return ContainerStatus(image=image, exists=True)
    mounts = {m.get("Destination"): m.get("Source", "") for m in info.get("Mounts") or []}
    bindings = (info.get("HostConfig") or {}).get("PortBindings") or {}
    ports = tuple(sorted(
        str(b.get("HostPort")) for b in bindings.get(f"{CONTAINER_PORT}/tcp") or []
        if b.get("HostPort")
    ))
    return ContainerStatus(
        image=image, exists=True,
        running=bool((info.get("State") or {}).get("Running")),
        data_dir=mounts.get(VIEWER_DATA_PATH, ""), ports=ports,
    )


