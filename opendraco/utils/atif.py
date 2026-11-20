"""ATIF: OpenDraco's run log.

Every inference run is recorded as Harbor's Agent Trajectory Interchange
Format (ATIF-v1.8, https://github.com/harbor-framework/harbor/blob/main/rfcs/0001-trajectory-format.md):
one ``trajectory.json`` per SWE-bench instance under
``<INFERENCE_INTERNAL_LOGS_DIR>/<stem>/<instance_id>/``.

Multi-agent runs use the nested form: the root trajectory is the graph engine,
whose ``llm_call_count: 0`` dispatch steps reference one embedded
``subagent_trajectories`` entry per agent activation (``<agent>#<n>``).

This module is framework-free (stdlib only): a validator for the format's
rules, an atomic writer, and the recorders the inference worker and agents
feed while a run is going.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "ATIF-v1.8"
AGENT_NAME = "opendraco"
TRAJECTORY_FILE = "trajectory.json"


def _package_version() -> str:
    try:
        from importlib.metadata import version
        return version("opendraco")
    except Exception:  # noqa: BLE001 — not installed as a package
        return "0.1.0"

_SOURCES = ("system", "user", "agent")
# Step fields the spec allows only when `source == "agent"`.
_AGENT_ONLY = ("model_name", "reasoning_effort", "reasoning_content", "tool_calls", "metrics")


def now_iso() -> str:
    """Current UTC time as ISO 8601 with a trailing `Z`."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ─── Validation ──────────────────────────────────────────────────────────────

def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}T", value):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return False
    return True


def _is_message(value: Any) -> bool:
    return isinstance(value, (str, list))


def _check_step(step: Any, where: str, expected_id: int, errors: list[str],
                embedded_ids: set[str]) -> None:
    if not isinstance(step, dict):
        errors.append(f"{where}: must be an object")
        return
    if step.get("step_id") != expected_id:
        errors.append(f"{where}: step_id must be {expected_id} (sequential from 1), got {step.get('step_id')!r}")
    source = step.get("source")
    if source not in _SOURCES:
        errors.append(f"{where}: source must be one of {list(_SOURCES)}, got {source!r}")
    if "message" not in step:
        errors.append(f"{where}: message is required")
    elif not _is_message(step["message"]):
        errors.append(f"{where}: message must be a string or an array of content parts")
    if "timestamp" in step and step["timestamp"] is not None and not _valid_timestamp(step["timestamp"]):
        errors.append(f"{where}: timestamp {step['timestamp']!r} is not ISO 8601")
    if source != "agent":
        for field in _AGENT_ONLY:
            if step.get(field) is not None:
                errors.append(f"{where}: {field} is only allowed on agent steps")
    count = step.get("llm_call_count")
    if count is not None and (not isinstance(count, int) or count < 0):
        errors.append(f"{where}: llm_call_count must be a non-negative integer")
    if source == "agent" and count == 0:
        for field in ("metrics", "reasoning_content"):
            if step.get(field) is not None:
                errors.append(f"{where}: {field} must be absent when llm_call_count is 0")

    call_ids: set[str] = set()
    tool_calls = step.get("tool_calls")
    if tool_calls is not None:
        if not isinstance(tool_calls, list):
            errors.append(f"{where}: tool_calls must be an array")
            tool_calls = []
        for j, call in enumerate(tool_calls):
            cw = f"{where}.tool_calls[{j}]"
            if not isinstance(call, dict):
                errors.append(f"{cw}: must be an object")
                continue
            cid = call.get("tool_call_id")
            if not isinstance(cid, str) or not cid:
                errors.append(f"{cw}: tool_call_id is required")
            elif cid in call_ids:
                errors.append(f"{cw}: tool_call_id {cid!r} must be unique within the step")
            else:
                call_ids.add(cid)
            if not isinstance(call.get("function_name"), str) or not call.get("function_name"):
                errors.append(f"{cw}: function_name is required")
            if not isinstance(call.get("arguments"), dict):
                errors.append(f"{cw}: arguments must be an object")

    observation = step.get("observation")
    if observation is not None:
        results = observation.get("results") if isinstance(observation, dict) else None
        if not isinstance(results, list):
            errors.append(f"{where}.observation: results must be an array")
            results = []
        for j, res in enumerate(results):
            rw = f"{where}.observation.results[{j}]"
            if not isinstance(res, dict):
                errors.append(f"{rw}: must be an object")
                continue
            sid = res.get("source_call_id")
            if sid is not None and sid not in call_ids:
                errors.append(f"{rw}: source_call_id {sid!r} matches no tool_call_id in this step")
            if "content" in res and res["content"] is not None and not _is_message(res["content"]):
                errors.append(f"{rw}: content must be a string or an array of content parts")
            refs = res.get("subagent_trajectory_ref")
            if refs is None:
                continue
            if not isinstance(refs, list):
                errors.append(f"{rw}: subagent_trajectory_ref must be an array")
                continue
            for k, ref in enumerate(refs):
                fw = f"{rw}.subagent_trajectory_ref[{k}]"
                if not isinstance(ref, dict):
                    errors.append(f"{fw}: must be an object")
                    continue
                tid, tpath = ref.get("trajectory_id"), ref.get("trajectory_path")
                if not tid and not tpath:
                    errors.append(f"{fw}: needs trajectory_id or trajectory_path")
                elif tid and not tpath and tid not in embedded_ids:
                    errors.append(f"{fw}: trajectory_id {tid!r} matches no embedded subagent")


def _validate(doc: Any, prefix: str, errors: list[str], embedded: bool) -> None:
    if not isinstance(doc, dict):
        errors.append(f"{prefix}trajectory must be an object")
        return
    version = doc.get("schema_version")
    if not isinstance(version, str) or not version.startswith("ATIF-v"):
        errors.append(f"{prefix}schema_version is required (e.g. {SCHEMA_VERSION!r})")
    agent = doc.get("agent")
    if not isinstance(agent, dict):
        errors.append(f"{prefix}agent is required")
    else:
        for field in ("name", "version"):
            if not isinstance(agent.get(field), str) or not agent.get(field):
                errors.append(f"{prefix}agent.{field} is required")
        if agent.get("tool_definitions") is not None and not isinstance(agent["tool_definitions"], list):
            errors.append(f"{prefix}agent.tool_definitions must be an array")
    if embedded and (not isinstance(doc.get("trajectory_id"), str) or not doc.get("trajectory_id")):
        errors.append(f"{prefix}trajectory_id is required on an embedded subagent")

    subs = doc.get("subagent_trajectories") or []
    embedded_ids: set[str] = set()
    if not isinstance(subs, list):
        errors.append(f"{prefix}subagent_trajectories must be an array")
        subs = []
    for i, sub in enumerate(subs):
        tid = sub.get("trajectory_id") if isinstance(sub, dict) else None
        if isinstance(tid, str) and tid:
            if tid in embedded_ids:
                errors.append(f"{prefix}subagent_trajectories[{i}]: trajectory_id {tid!r} must be unique")
            embedded_ids.add(tid)

    steps = doc.get("steps")
    if not isinstance(steps, list):
        errors.append(f"{prefix}steps is required and must be an array")
    else:
        for i, step in enumerate(steps):
            _check_step(step, f"{prefix}steps[{i}]", i + 1, errors, embedded_ids)

    for i, sub in enumerate(subs):
        _validate(sub, f"{prefix}subagent_trajectories[{i}].", errors, embedded=True)


def validate_trajectory(doc: Any) -> list[str]:
    """Every ATIF rule `doc` breaks, as readable messages; `[]` when valid.

    Checks required fields, sequential step ids, step sources, agent-only
    fields, `llm_call_count: 0` rules, tool-call / observation references,
    timestamps, and embedded-subagent ids and refs (recursively)."""
    errors: list[str] = []
    _validate(doc, "", errors, embedded=False)
    return errors


# ─── Writing ─────────────────────────────────────────────────────────────────

def write_json_atomic(path: Path, doc: dict) -> None:
    """Write `doc` to `path` so a reader never sees a half-written file:
    write a sibling temp file, then `os.replace` it. Files are 0644 and new
    directories 0755 (the Graphectory container reads them as another uid).
    Values JSON cannot encode are written as their `str()`."""
    path = Path(path)
    for parent in reversed(path.parents):
        if not parent.exists():
            parent.mkdir(exist_ok=True)
            os.chmod(parent, 0o755)
    text = json.dumps(doc, ensure_ascii=False, indent=1, default=str, allow_nan=False)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


# ─── Recording ───────────────────────────────────────────────────────────────

def _jsonable(value: Any) -> Any:
    """`value` as strict JSON data: dict keys become strings, NaN/±inf
    become `"nan"`/`"inf"`/`"-inf"`, and anything else JSON can't encode
    (Path, bytes, sets, objects) becomes its `str()`. Never raises."""
    if isinstance(value, str) or value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        return {k if isinstance(k, str) else str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value)


def _text(value: Any) -> str:
    """A tool result / message as text: strings as-is, JSON data as JSON,
    anything else via `str()`."""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple, int, float, bool)) or value is None:
        return json.dumps(_jsonable(value), ensure_ascii=False)
    return str(value)


def read_run_info(path: Path, head_bytes: int = 65536) -> dict | None:
    """A trajectory's `extra.run` (run id, config name + SHA, instance ids,
    ts) without parsing the whole file: the recorder writes `extra` right
    after the ids, so it is in the first bytes. Falls back to a full parse
    (e.g. files from other producers); `None` when unreadable."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(head_bytes).decode("utf-8", errors="replace")
    except OSError:
        return None
    at = head.find('"run":')
    if at >= 0:
        start = head.find("{", at)
        try:
            run, _ = json.JSONDecoder().raw_decode(head, start)
            if isinstance(run, dict):
                return run
        except ValueError:
            pass
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    run = (doc.get("extra") or {}).get("run") if isinstance(doc, dict) else None
    return run if isinstance(run, dict) else None


def _number_steps(steps: list[dict]) -> list[dict]:
    return [{"step_id": i + 1, **step} for i, step in enumerate(steps)]


class AgentTrajectoryRecorder:
    """One agent activation, embedded in its instance's trajectory as
    `subagent_trajectories[]` with id `<agent>#<n>`. Created only by
    `InstanceRecorder.begin_activation`; every call rewrites the file."""

    def __init__(self, trajectory_id: str, agent_name: str, activation: int,
                 model_name: str | None, tool_definitions: list[dict],
                 lock: threading.RLock, flush: Callable[[], None]) -> None:
        self.trajectory_id = trajectory_id
        self.agent_name = agent_name
        self._activation = activation
        self._model_name = model_name
        self._tool_definitions = _jsonable(tool_definitions or [])
        self._lock = lock
        self._flush = flush
        self._steps: list[dict] = []
        self._tool_seq = 0
        self.tokens: dict[str, int] = {"input": 0, "output": 0, "total": 0}

    def prompt(self, source: Literal["system", "user"], message: str) -> None:
        with self._lock:
            self._steps.append({"timestamp": now_iso(), "source": source, "message": _text(message)})
            self._flush()

    def llm_call(self, *, message: str, reasoning: str, tool_calls: list[dict],
                 usage: dict[str, int], model_name: str | None) -> None:
        """One LLM inference: `tool_calls` items are `{"id", "name", "args"}`;
        `usage` is `{"input", "output", "total"}` for this call alone."""
        usage = usage or {}
        tin, tout = int(usage.get("input", 0) or 0), int(usage.get("output", 0) or 0)
        step: dict[str, Any] = {
            "timestamp": now_iso(), "source": "agent", "llm_call_count": 1,
            "message": _text(message or ""),
        }
        if model_name or self._model_name:
            step["model_name"] = model_name or self._model_name
        if reasoning:
            step["reasoning_content"] = reasoning
        if tool_calls:
            step["tool_calls"] = [
                {"tool_call_id": str(c.get("id")), "function_name": str(c.get("name") or "tool"),
                 "arguments": _jsonable(c.get("args") or {})}
                for c in tool_calls
            ]
        if tin or tout:
            step["metrics"] = {"prompt_tokens": tin, "completion_tokens": tout}
        with self._lock:
            self._steps.append(step)
            self.tokens["input"] += tin
            self.tokens["output"] += tout
            self.tokens["total"] += int(usage.get("total", 0) or 0) or (tin + tout)
            self._flush()

    def tool_result(self, call_id: str | None, content: Any, *, name: str = "",
                    args: dict | None = None, error: bool = False) -> None:
        """The result of a tool call. With `call_id`, it is attached to the
        latest LLM step that made that call; without one (a tool the agent
        called programmatically), it becomes its own `llm_call_count: 0` step."""
        result: dict[str, Any] = {"source_call_id": call_id, "content": _text(content)}
        if error:
            result["extra"] = {"error": True}
        with self._lock:
            target = None
            if call_id is not None:
                for step in reversed(self._steps):
                    if any(c["tool_call_id"] == call_id for c in step.get("tool_calls") or []):
                        target = step
                        break
            if target is None:
                self._tool_seq += 1
                cid = call_id or f"tool-{self._tool_seq}"
                result["source_call_id"] = cid
                target = {
                    "timestamp": now_iso(), "source": "agent", "llm_call_count": 0,
                    "message": "",
                    "tool_calls": [{"tool_call_id": cid, "function_name": name or "tool",
                                    "arguments": _jsonable(args or {})}],
                }
                self._steps.append(target)
            target.setdefault("observation", {"results": []})["results"].append(result)
            self._flush()

    def to_dict(self) -> dict:
        with self._lock:
            agent: dict[str, Any] = {"name": self.agent_name, "version": _package_version()}
            if self._model_name:
                agent["model_name"] = self._model_name
            if self._tool_definitions:
                agent["tool_definitions"] = self._tool_definitions
            agent["extra"] = {"activation": self._activation}
            return _jsonable({
                "schema_version": SCHEMA_VERSION,
                "trajectory_id": self.trajectory_id,
                "agent": agent,
                "steps": _number_steps(self._steps),
                "final_metrics": {
                    "total_prompt_tokens": self.tokens["input"],
                    "total_completion_tokens": self.tokens["output"],
                    "total_steps": len(self._steps),
                },
            })


class InstanceRecorder:
    """The root trajectory of one SWE-bench instance: the graph engine's
    dispatch steps plus one embedded subagent per agent activation."""

    def __init__(self, path: Path, *, run_info: dict, agent_extra: dict,
                 instance_id: str, index: int, total: int, issue: str,
                 notes: str | None = None) -> None:
        self.path = Path(path)
        self.notes = notes
        self.instance_id = instance_id
        self.trajectory_id = f"{run_info.get('run_id')}.{instance_id}"
        self._run_info = _jsonable(run_info)
        self._agent_extra = _jsonable(agent_extra)
        self._index, self._total = index, total
        self._lock = threading.RLock()
        self._steps: list[dict] = [{"timestamp": now_iso(), "source": "user", "message": issue or ""}]
        self._subagents: list[AgentTrajectoryRecorder] = []
        self._dispatch: dict[int, dict] = {}  # id(recorder) → its dispatch result
        self._activations: dict[str, int] = {}
        self._agent_tokens: dict[str, dict[str, int]] = {}
        self.status = "queued"
        self._error: dict | None = None
        self._model_patch: str | None = None

    # ── lifecycle ──
    def start(self) -> None:
        with self._lock:
            self.status = "running"
            self.flush()

    def begin_activation(self, agent: str, inputs: dict[str, Any], *,
                         model_name: str | None, tool_definitions: list[dict]) -> AgentTrajectoryRecorder:
        with self._lock:
            n = self._activations.get(agent, 0) + 1
            self._activations[agent] = n
            rec = AgentTrajectoryRecorder(
                f"{agent}#{n}", agent, n, model_name, tool_definitions, self._lock, self.flush,
            )
            self._subagents.append(rec)
            call_id = f"dispatch-{len(self._subagents)}"
            result: dict[str, Any] = {
                "source_call_id": call_id,
                "subagent_trajectory_ref": [{"trajectory_id": rec.trajectory_id}],
            }
            self._steps.append({
                "timestamp": now_iso(), "source": "agent", "llm_call_count": 0,
                "message": f"dispatch {agent}",
                "tool_calls": [{"tool_call_id": call_id, "function_name": "run_agent",
                                "arguments": {"agent": agent, "inputs": _jsonable(inputs or {})}}],
                "observation": {"results": [result]},
            })
            self._dispatch[id(rec)] = result
            self.flush()
            return rec

    def end_activation(self, rec: AgentTrajectoryRecorder, *, summary: str,
                       delta: dict, handoffs: list[dict]) -> None:
        with self._lock:
            result = self._dispatch.get(id(rec))
            if result is not None:
                result["content"] = _text(summary or "")
                result["extra"] = {
                    "delta_keys": sorted(str(k) for k in (delta or {})),
                    "delta": _jsonable(delta or {}),
                    "handoffs": _jsonable(handoffs or []),
                }
            self.flush()

    def system_event(self, event: Literal["error", "cancelled"], message: str,
                     extra: dict | None = None) -> None:
        with self._lock:
            self._steps.append({
                "timestamp": now_iso(), "source": "system", "message": message,
                "extra": {"event": event, **_jsonable(extra or {})},
            })
            self.flush()

    def finish(self, status: Literal["done", "error", "cancelled"], *,
               model_patch: str = "", error: dict | None = None) -> None:
        with self._lock:
            self.status = status
            if status == "done":
                self._model_patch = model_patch or ""
            if error is not None:
                self._error = _jsonable(error)
            self.flush()

    def set_agent_tokens(self, agent: str, tokens: dict[str, int]) -> None:
        """Override an agent's token totals (for logs that only kept
        per-agent totals, e.g. converted legacy runs)."""
        with self._lock:
            self._agent_tokens[agent] = {k: int(tokens.get(k, 0) or 0) for k in ("input", "output", "total")}
            self.flush()

    @property
    def finished(self) -> bool:
        return self.status in ("done", "error", "cancelled")

    # ── output ──
    def _per_agent(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for rec in self._subagents:
            acc = out.setdefault(rec.agent_name, {"input": 0, "output": 0, "total": 0})
            for k in acc:
                acc[k] += rec.tokens[k]
        out.update(self._agent_tokens)
        return out

    def to_dict(self) -> dict:
        with self._lock:
            per_agent = self._per_agent()
            extra: dict[str, Any] = {
                "run": self._run_info, "instance_id": self.instance_id,
                "index": self._index, "total": self._total, "status": self.status,
            }
            if self._error is not None:
                extra["error"] = self._error
            if self._model_patch is not None:
                extra["model_patch"] = self._model_patch
            # `extra` (with the run's identity) comes first so readers that
            # only need it (`read_run_info`) can stop after a few bytes.
            doc: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "session_id": self._run_info.get("run_id"),
                "trajectory_id": self.trajectory_id,
                "extra": extra,
                "agent": {"name": AGENT_NAME, "version": _package_version(), "extra": self._agent_extra},
                "steps": _number_steps(self._steps),
                "final_metrics": {
                    "total_prompt_tokens": sum(a["input"] for a in per_agent.values()),
                    "total_completion_tokens": sum(a["output"] for a in per_agent.values()),
                    "total_steps": len(self._steps),
                    "extra": {"per_agent": per_agent},
                },
            }
            if self.notes:
                doc["notes"] = self.notes
            if self._subagents:
                doc["subagent_trajectories"] = [rec.to_dict() for rec in self._subagents]
            return _jsonable(doc)

    def flush(self) -> None:
        """Rewrite this instance's `trajectory.json` atomically. Never raises:
        a failed write is logged and the run goes on."""
        with self._lock:
            try:
                write_json_atomic(self.path, self.to_dict())
            except (OSError, TypeError, ValueError) as exc:
                logger.warning("could not write ATIF trajectory %s: %s", self.path, exc)


class RunRecorder:
    """All instances of one inference run, in `<run_dir>/<instance_id>/trajectory.json`.
    Every instance's file is created (`status: "queued"`) up front, so a run
    that fails before its first instance still leaves a record."""

    def __init__(self, run_dir: Path, *, run_info: dict, agent_extra: dict,
                 instances: list[tuple[str, str]], notes: str | None = None) -> None:
        self.run_dir = Path(run_dir)
        total = len(instances)
        self._instances: dict[str, InstanceRecorder] = {}
        for index, (iid, issue) in enumerate(instances):
            inst = InstanceRecorder(
                self.run_dir / iid / TRAJECTORY_FILE, run_info=run_info, agent_extra=agent_extra,
                instance_id=iid, index=index, total=total, issue=issue, notes=notes,
            )
            self._instances[iid] = inst
            inst.flush()

    def instance(self, instance_id: str) -> InstanceRecorder:
        return self._instances[instance_id]

    def fail_unfinished(self, status: Literal["error", "cancelled"], message: str,
                        error: dict | None = None) -> None:
        for inst in self._instances.values():
            if not inst.finished:
                inst.system_event(status, message, error)
                inst.finish(status, error=error)
