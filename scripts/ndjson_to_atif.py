"""Convert legacy inference `.ndjson` logs into ATIF run folders.

usage: python scripts/ndjson_to_atif.py [<prediction-…ndjson> ...] [--publish]

OpenDraco used to keep each inference run as a stream of UI events in
`opendraco/logs/inference_logs/<stem>.ndjson`. Runs are now recorded as ATIF
(`opendraco.utils.atif`): `<stem>/<instance_id>/trajectory.json`. This script
turns old logs into that layout, once, so nothing has to read `.ndjson` any
more. With no files it converts every `.ndjson` in the logs folder that has
no run folder yet. `--publish` also publishes each converted run into the
Graphectory Viewer when `GRAPHECTORY_URL` is set.

Old logs kept previews only, so the result is best-effort: tool arguments and
results stay truncated (`{"preview": "..."}`), tool calls get synthesized ids,
and tokens are per-agent totals. The `.ndjson` files are left in place.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # run as a file: make `opendraco` importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opendraco.paths import INFERENCE_INTERNAL_LOGS_DIR, INSTANCES_PATH  # noqa: E402
from opendraco.utils.atif import (  # noqa: E402
    AgentTrajectoryRecorder,
    InstanceRecorder,
    RunRecorder,
    validate_trajectory,
    write_json_atomic,
)

LOGS_DIR: Path = INFERENCE_INTERNAL_LOGS_DIR
NOTES = (
    "Converted from a legacy OpenDraco .ndjson log: arguments/results are "
    "previews, no tool-call ids or per-call tokens."
)


def load_instances() -> dict[str, dict]:
    """SWE-bench instances by id (for the issue text), or `{}`."""
    out: dict[str, dict] = {}
    try:
        with INSTANCES_PATH.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict) and obj.get("instance_id"):
                    out[obj["instance_id"]] = obj
    except OSError:
        pass
    return out


def _issue(instance: dict | None) -> str:
    if not instance:
        return ""
    parts = [instance.get("problem_statement") or ""]
    if instance.get("hints_text"):
        parts.append("\n## Hints\n" + instance["hints_text"])
    return "\n".join(p for p in parts if p).strip()


class _InstanceReplay:
    """Replays one instance's legacy events into its `InstanceRecorder`.

    Legacy logs emit an agent's live events (thinking, responses, tool calls)
    *before* its `agent_input` / `agent_event`, which the old worker only
    wrote once the node finished; so live events are buffered per agent and
    replayed into a new activation when its `agent_event` arrives."""

    def __init__(self, inst: InstanceRecorder) -> None:
        self.inst = inst
        self.live: dict[str, list[dict]] = {}
        self.inputs: dict[str, dict] = {}
        self.open: dict[str, tuple[AgentTrajectoryRecorder, dict, list[dict]]] = {}
        self.tokens: dict[str, dict] = {}

    def event(self, ev: dict) -> None:
        kind, agent = ev.get("type"), str(ev.get("agent") or "")
        if kind in ("thinking_chunk", "response", "tool_call") and agent:
            self.live.setdefault(agent, []).append(ev)
        elif kind == "agent_input" and agent:
            self.inputs[agent] = ev.get("inputs") or {}
        elif kind == "agent_event" and agent:
            self._close(agent)
            rec = self.inst.begin_activation(agent, self.inputs.pop(agent, {}),
                                             model_name=None, tool_definitions=[])
            self._replay(rec, self.live.pop(agent, []))
            self.open[agent] = (rec, ev.get("delta") or {}, [])
        elif kind == "handoff":
            src = str(ev.get("from") or "")
            if src in self.open:
                self.open[src][2].append({k: ev.get(k) for k in ("to", "summary", "preview", "timestamp")})
        elif kind == "agent_tokens" and agent:
            self.tokens[agent] = {k: ev.get(k, 0) for k in ("input", "output", "total")}

    @staticmethod
    def _replay(rec: AgentTrajectoryRecorder, events: list[dict]) -> None:
        thinking = ""
        for ev in events:
            if ev["type"] == "thinking_chunk":
                thinking += str(ev.get("chunk") or "")
            elif ev["type"] == "response":
                rec.llm_call(message=str(ev.get("content") or ""), reasoning=thinking,
                             tool_calls=[], usage={}, model_name=None)
                thinking = ""
            elif ev["type"] == "tool_call":
                rec.tool_result(None, str(ev.get("result_preview") or ""),
                                name=str(ev.get("tool") or "tool"),
                                args={"preview": str(ev.get("args_preview") or "")})

    def _close(self, agent: str) -> None:
        if agent in self.open:
            rec, delta, handoffs = self.open.pop(agent)
            self.inst.end_activation(rec, summary="", delta=delta, handoffs=handoffs)

    def close_all(self) -> None:
        for agent in list(self.open):
            self._close(agent)
        for agent, tokens in self.tokens.items():
            self.inst.set_agent_tokens(agent, tokens)


def convert_ndjson(ndjson_path: Path, out_root: Path, instances: dict[str, dict] | None = None) -> Path:
    """Write the ATIF folder `<out_root>/<stem>/` for one legacy log and
    return it. Raises `ValueError` for a log without a usable `run_meta`."""
    ndjson_path = Path(ndjson_path)
    events: list[dict] = []
    for line in ndjson_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    meta = next((e for e in events if e.get("type") == "run_meta"), None)
    if meta is None or not meta.get("instance_ids"):
        raise ValueError(f"{ndjson_path.name}: no run_meta with instance_ids")
    instances = instances or {}
    ids = [str(i) for i in meta["instance_ids"]]
    run_info = {k: meta.get(k) for k in ("run_id", "config_name", "config_sha", "instance_ids", "ts")}
    run_info["run_id"] = run_info.get("run_id") or ndjson_path.stem.removeprefix("prediction-")
    run = RunRecorder(
        Path(out_root) / ndjson_path.stem, run_info=run_info,
        agent_extra={"config_name": meta.get("config_name"), "config_sha": meta.get("config_sha")},
        instances=[(iid, _issue(instances.get(iid))) for iid in ids], notes=NOTES,
    )
    current: _InstanceReplay | None = None
    for ev in events:
        kind = ev.get("type")
        if kind == "instance_start" and ev.get("instance_id") in ids:
            current = _InstanceReplay(run.instance(ev["instance_id"]))
            current.inst.start()
        elif kind == "instance_done" and current is not None:
            current.close_all()
            current.inst.finish("done", model_patch=str(ev.get("patch") or ""))
            current = None
        elif kind in ("error", "cancelled"):
            if current is not None:
                current.close_all()
            status = "error" if kind == "error" else "cancelled"
            message = str(ev.get("message") or ("Cancelled by user" if status == "cancelled" else "error"))
            error = {"message": message, "traceback": ev.get("traceback")} if status == "error" else None
            run.fail_unfinished(status, message, error)
            current = None
        elif current is not None:
            current.event(ev)
    if current is not None:  # the log just stops: the run was interrupted
        current.close_all()
    run.fail_unfinished("cancelled", "The run stopped before it finished")
    _strip_timestamps(run.run_dir)
    return run.run_dir


def _strip_timestamps(run_dir: Path) -> None:
    """Legacy logs have no per-step times; the recorder stamped the
    conversion time, which would show made-up durations. Drop them."""
    for path in run_dir.glob("*/trajectory.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for traj in [doc, *(doc.get("subagent_trajectories") or [])]:
            for step in traj.get("steps") or []:
                step.pop("timestamp", None)
        write_json_atomic(path, doc)


def _pending(logs: Path) -> list[Path]:
    return sorted(p for p in logs.glob("*.ndjson") if not (logs / p.stem).is_dir())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--publish", action="store_true",
                        help="also publish each converted run into Graphectory (GRAPHECTORY_URL)")
    args = parser.parse_args(argv)
    files = args.files or _pending(LOGS_DIR)
    if not files:
        print("nothing to convert")
        return 0
    instances = load_instances()
    failed = False
    for path in files:
        try:
            run_dir = convert_ndjson(path, path.parent, instances)
        except (OSError, ValueError) as exc:
            print(f"{path.name}: {exc}")
            failed = True
            continue
        errors = [
            f"{traj.parent.name}: {e}"
            for traj in sorted(run_dir.glob("*/trajectory.json"))
            for e in validate_trajectory(json.loads(traj.read_text(encoding="utf-8")))
        ]
        if errors:
            failed = True
            print(f"{path.name}: converted with {len(errors)} validation error(s):")
            for e in errors:
                print(f"  {e}")
        else:
            print(f"{path.name}: converted -> {run_dir}")
        if args.publish:
            from opendraco.utils.graphectory import graphectory_base_url, publish_run_dir
            viewer_url = graphectory_base_url()
            if viewer_url:
                links = publish_run_dir(viewer_url, run_dir)
                print(f"  published: {links}" if links else "  publish failed (see the log)")
            else:
                print("  not published: GRAPHECTORY_URL is not set")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
