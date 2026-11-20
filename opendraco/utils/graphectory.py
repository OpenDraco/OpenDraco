"""Local Graphectory: publish runs into the Viewer.

Graphectory turns a recorded agent run into an interactive trajectory
graph. Everything runs on this machine:

- every inference run is recorded as ATIF (`opendraco.utils.atif`): one
  `trajectory.json` per instance under
  `opendraco/logs/inference_logs/<stem>/<instance_id>/`. `publish_run`
  copies them into `<RESULTS_DIR>/graphectory/<run_id>/<instance_id>/`;
- the **Viewer** (`GRAPHECTORY_URL`, e.g. `http://localhost:9610`) is the
  Graphectory Docker container `graphectory-viewer`, built from the ATIF
  fork (`GRAPHECTORY_REPO`, branch `GRAPHECTORY_BRANCH`) with that folder as
  its `/data`. It reads ATIF directly (one graph per instance, id =
  `trajectory_id` = `<run_id>.<instance_id>`), so OpenDraco ships no
  converter. OpenDraco never starts, creates or removes the container: it is
  built and run with plain docker commands (`BUILD_COMMAND`, `run_command`),
  and `viewer_container_status` only reads its state for `opendraco status`.
  `GET /` is the Viewer's liveness check.

`GRAPHECTORY_URL` unset or empty disables all of it. Runs that end are
published in the background by `publish_run_dir` (best-effort, never
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
import shutil
import ssl
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, quote, urlsplit

import certifi

from opendraco.paths import RESULTS_DIR

logger = logging.getLogger(__name__)

# ─── Layout ──────────────────────────────────────────────────────────────────
# The published ATIF runs; the Viewer's container mounts this folder as /data.
DATA_DIR: Path = RESULTS_DIR / "graphectory"
# The data folder's path inside the Viewer's container.
VIEWER_DATA_PATH = "/data"
IMAGE = "graphectory"
CONTAINER = "graphectory-viewer"
# The port the Viewer listens on inside the container.
CONTAINER_PORT = 9610
# The Viewer must read ATIF: the owner's fork, branch feat/atif-mas (stock
# upstream Graphectory cannot).
GRAPHECTORY_REPO = "https://github.com/xiangfengyepan/Graphectory.git"
GRAPHECTORY_BRANCH = "feat/atif-mas"
# Joined with `;`, which bash and PowerShell both accept (`&&` is not valid
# in Windows PowerShell 5.1).
BUILD_COMMAND = (
    f"git clone -b {GRAPHECTORY_BRANCH} {GRAPHECTORY_REPO} Graphectory; "
    f"docker build -t {IMAGE} Graphectory"
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


def graph_link(viewer_url: str, graph_id: str) -> str:
    return f"{viewer_url.rstrip('/')}/api/graph?id={quote(graph_id, safe='')}"


# ─── The Viewer's data folder ────────────────────────────────────────────────
LINKS_FILE = "graphectory-links.json"


def clear_legacy_sessions(data_dir: Path) -> int:
    """Remove the Claude Code sessions the old converter wrote (`state.json`
    + `agents/`): the Viewer reads one format per folder and those would hide
    every ATIF run. Returns how many were removed."""
    if not data_dir.is_dir():
        return 0
    removed = 0
    for child in data_dir.iterdir():
        if child.is_dir() and (child / "state.json").is_file() and (child / "agents").is_dir():
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return removed


def _run_trajectories(run_dir: Path) -> list[tuple[str, Path, dict]]:
    """`(instance_id, path, doc)` for every ATIF file of a run folder."""
    out: list[tuple[str, Path, dict]] = []
    for path in sorted(Path(run_dir).glob("*/trajectory.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict) and isinstance(doc.get("trajectory_id"), str):
            out.append((path.parent.name, path, doc))
    return out


def _copy_world_readable(src: Path, dst: Path) -> None:
    for parent in reversed(dst.parents):
        if not parent.exists():
            parent.mkdir(exist_ok=True)
            os.chmod(parent, 0o755)
    shutil.copyfile(src, dst)
    os.chmod(dst, 0o644)


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


def _check_viewer_url(viewer_url: str) -> SplitResult:
    """`viewer_url` split, or `GraphectoryError` 503 when it is not http(s)."""
    parts = urlsplit(viewer_url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise GraphectoryError(503, f"GRAPHECTORY_URL is not an http(s) URL: {viewer_url!r}")
    return parts


def _viewer_json(viewer_url: str, method: str, path: str, body: Any = None) -> Any:
    """One JSON request to the Viewer. Raises `GraphectoryError`: 503 for a
    bad `GRAPHECTORY_URL`, 504 when the Viewer is unreachable, 502 for an
    error status or an answer that is not JSON."""
    parts = _check_viewer_url(viewer_url)
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


def reload_viewer(viewer_url: str, ids: list[str] | None = None) -> None:
    """Point the Viewer at its data folder again (it reads the folder when
    its data source is set) and, with `ids`, wait until it lists every one
    of those graphs. Raises `GraphectoryError`."""
    answer = _viewer_json(
        viewer_url, "POST", "/api/config", {"trajs": VIEWER_DATA_PATH, "eval_report": ""},
    )
    if not isinstance(answer, dict) or not answer.get("ok"):
        raise GraphectoryError(502, f"The Graphectory Viewer refused its data folder: {answer}")
    if not ids:
        return
    deadline = time.monotonic() + LIST_WAIT_S
    while True:
        listing = _viewer_json(viewer_url, "GET", "/api/graphs")
        graphs = listing.get("graphs") if isinstance(listing, dict) else None
        listed = {g.get("instance_id") for g in graphs or [] if isinstance(g, dict)}
        missing = [i for i in ids if i not in listed]
        if not missing:
            return
        if (isinstance(listing, dict) and listing.get("status") == "complete") \
                or time.monotonic() > deadline:
            raise GraphectoryError(
                502, f"The Graphectory Viewer does not list {missing} after reloading -- "
                     f"it can't read ATIF or doesn't mount {DATA_DIR} as /data "
                     "(`opendraco status` shows what it mounts). Rebuild it from "
                     f"xiangfengyepan/Graphectory {GRAPHECTORY_BRANCH}: {BUILD_COMMAND}",
            )
        time.sleep(0.5)


# ─── Publishing a run ────────────────────────────────────────────────────────
def publish_run(viewer_url: str, run_dir: Path, data_dir: Path | None = None) -> dict[str, str]:
    """Copy a run's ATIF trajectories (`<run_dir>/<instance_id>/trajectory.json`)
    into the Viewer's data folder, remove old converter-made sessions there,
    reload the Viewer until it lists every instance, save the links as
    `<run_dir>/graphectory-links.json` and return `{instance_id: link}`.

    Raises `GraphectoryError`: 404 no trajectories in `run_dir`, 500 the
    data folder is not writable, 503 a bad `GRAPHECTORY_URL`, 502/504 the
    Viewer did not reload, answer or list the run."""
    run_dir = Path(run_dir)
    trajectories = _run_trajectories(run_dir)
    if not trajectories:
        raise GraphectoryError(404, f"no ATIF trajectories in {run_dir.name}")
    _check_viewer_url(viewer_url)
    target = data_dir or DATA_DIR
    run_id = safe_run_id(str(trajectories[0][2].get("session_id") or run_dir.name))
    with _publish_lock:
        try:
            clear_legacy_sessions(target)
            for iid, path, _doc in trajectories:
                _copy_world_readable(path, target / run_id / safe_run_id(iid) / "trajectory.json")
        except OSError as exc:
            raise GraphectoryError(500, f"Could not write the run into {target}: {exc}") from exc
        reload_viewer(viewer_url, [doc["trajectory_id"] for _, _, doc in trajectories])
    links = {iid: graph_link(viewer_url, doc["trajectory_id"]) for iid, _, doc in trajectories}
    try:
        (run_dir / LINKS_FILE).write_text(json.dumps({"links": links}, indent=2), encoding="utf-8")
    except OSError as exc:  # the links are a convenience; the publish worked
        logger.warning("could not save the Graphectory links for %s: %s", run_dir.name, exc)
    return links


def publish_run_dir(viewer_url: str, run_dir: Path) -> dict[str, str] | None:
    """`publish_run` for a finished run. Best-effort: never raises; a
    failure is logged as a warning and gives `None`, a success logs the
    graph links at INFO."""
    name = Path(run_dir).name.removeprefix("prediction-")
    try:
        links = publish_run(viewer_url, Path(run_dir))
    except Exception as exc:  # nothing about a failed publish may reach the run
        logger.warning("Graphectory publish of run %s failed: %s", name, exc)
        return None
    for iid, link in links.items():
        logger.info("Graphectory graph for run %s, instance %s: %s", name, iid, link)
    return links


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


