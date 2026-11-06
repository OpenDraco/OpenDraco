"""
converter/wire.py

Turn a parsed ``RunLog`` into a single **super-agent** Claude Code
*wire* session the stock Graphectory viewer can browse and render.

Graphectory is single-agent. A multi-agent run is shown as one agent whose turns
are every agent's activations, in run order, each opened by a **recall** step that
names the agent and what it received. So the one graph still shows each agent's
boundary (a recall node) and its work, and because the history is linear a patch
by an earlier agent correctly makes a later agent's tests read as validation.

The per-step parsing (``activation_steps``) follows Graphectory's per-agent step
parsing so the nodes match; the graph itself is built by the viewer.
"""

import re
from typing import Any, Optional

from .log import (
    MESSAGE_TYPES,
    MODEL_CALL,
    TOOL_CALL,
    TOOL_RESULT,
    Activation,
    RunLog,
)

# Model-call purposes that are the agent doing work (and so open a step).
STEP_PURPOSES = {"work", "tool_turn"}

_TOOL_FAILURE_PREFIX = "tool failure:"
_EXIT_CODE_RE = re.compile(r"\Aexit code (-?\d+)\nstdout:\n")
_TIMEOUT_RE = re.compile(r"\Athe command did not finish within [\d.]+ seconds and was stopped")


def result_is_error(tool_name: str, result: str) -> Optional[bool]:
    """Failure as the result text records it; None where the text does not say."""
    if result.startswith(_TOOL_FAILURE_PREFIX):
        return True
    if tool_name == "bash":
        if _TIMEOUT_RE.match(result):
            return True
        match = _EXIT_CODE_RE.match(result)
        if match:
            return int(match.group(1)) != 0
    return None


def _cause_lines(run: RunLog, act: Activation) -> list[str]:
    lines = []
    parent = run.parent_deliveries
    for uuid in act.new_causes:
        delivery = run.deliveries.get(uuid) or parent.get(uuid)
        if delivery is None:
            lines.append("from the parent run" if run.forked_from else "from a delivery not in this log")
        else:
            lines.append(f"from {delivery.get('from_agent') or '?'}: {delivery.get('value') or ''}")
    return lines


def activation_steps(run: RunLog, act: Activation, *, include_causes: bool = True) -> list[dict]:
    """The steps of one activation: ``{"thought": str, "calls": [call...]}``.

    With *include_causes* False the deliveries that opened the turn are left out
    of the first thought, because the flattener shows them in the recall step.
    """
    steps: list[dict] = []
    buffer: list[list] = []
    current: Optional[dict] = None
    open_calls: dict[str, list[dict]] = {}

    def close_step(mcuuid: Optional[str] = None) -> dict:
        nonlocal current
        current = {"parts": [(part[0], part[1]) for part in buffer], "calls": [], "_mcuuid": mcuuid}
        buffer.clear()
        steps.append(current)
        return current

    for record in act.records:
        rtype = record["type"]
        if rtype in MESSAGE_TYPES:
            text = record.get("content")
            if isinstance(text, str) and text:
                msgid = record.get("message_id")
                msgid = msgid if isinstance(msgid, str) and msgid else None
                if buffer and buffer[-1][0] == rtype and buffer[-1][2] == msgid:
                    buffer[-1][1] += text
                else:
                    buffer.append([rtype, text, msgid])
        elif rtype == MODEL_CALL:
            if record.get("purpose") in STEP_PURPOSES:
                uuid = record.get("uuid")
                close_step(uuid if isinstance(uuid, str) and uuid else None)
        elif rtype == TOOL_CALL:
            call = record.get("call") if isinstance(record.get("call"), dict) else {}
            args = call.get("args")
            entry = {
                "name": str(call.get("name") or "tool"),
                "args": args if isinstance(args, dict) else {"_raw": args},
                "observation": "",
                "is_error": None,
            }
            mcuuid = record.get("model_call_uuid")
            step = None
            if isinstance(mcuuid, str) and mcuuid:
                step = next((s for s in steps if s.get("_mcuuid") == mcuuid), None)
            if step is None:
                step = current if current is not None and not buffer else close_step()
            step["calls"].append(entry)
            open_calls.setdefault(str(call.get("id") or ""), []).append(entry)
        elif rtype == TOOL_RESULT:
            waiting = open_calls.get(str(record.get("call_id") or ""))
            if waiting:
                entry = waiting.pop(0)
                result = record.get("result")
                entry["observation"] = result if isinstance(result, str) else str(result)
                flag = record.get("is_error")
                code = record.get("exit_code")
                if isinstance(flag, bool):
                    entry["is_error"] = flag
                elif isinstance(code, int) and not isinstance(code, bool):
                    entry["is_error"] = code != 0
                else:
                    entry["is_error"] = result_is_error(entry["name"], entry["observation"])
        elif rtype == "error":
            buffer.append(["error", f"error: {record.get('message') or ''}", None])

    if buffer:
        close_step()

    for step in reversed(steps):
        if step["calls"]:
            break
        answer = "".join(text for kind, text in step["parts"] if kind == "message").strip()
        if answer:
            step["parts"] = [(k, t) for k, t in step["parts"] if k != "message"]
            step["calls"].append({"name": "final_answer", "args": {"text": answer},
                                  "observation": "", "is_error": None})
            break

    if include_causes:
        context = _cause_lines(run, act)
        if context:
            if not steps:
                steps.append({"parts": [], "calls": []})
            steps[0]["parts"] = [("context", line) for line in context] + steps[0]["parts"]

    out = []
    for step in steps:
        thought = "\n\n".join(text.strip() for _, text in step["parts"] if text.strip())
        if thought or step["calls"]:
            out.append({"thought": thought, "calls": step["calls"]})
    return out


def _event(event: dict) -> dict:
    return {"type": "context.append_loop_event", "event": event}


def _ordered_activations(run: RunLog) -> list[Activation]:
    """Every non-abandoned activation in run (superstep, then sequence) order."""
    acts = [a for a in run.activations if a.status != "abandoned"]
    return sorted(acts, key=lambda a: (a.superstep, a.seq))


def _recall_thought(run: RunLog, act: Activation) -> str:
    head = f"⟲ recall — {run.display_name(act.agent_id)} ({act.agent_id})"
    head += f" · superstep {act.superstep}"
    if act.local_turn is not None:
        head += f" · turn {act.local_turn}"
    causes = _cause_lines(run, act)
    return head + ("\n" + "\n".join(causes) if causes else "\n(entry point)")


def flatten_to_wire(run: RunLog) -> list[dict]:
    """The whole run as one Claude-wire event stream (a list of records)."""
    records: list[dict] = []
    step_no = 0
    call_no = 0

    def emit_step(thought: str, calls: list[dict]) -> None:
        nonlocal step_no, call_no
        step_uuid = f"step-{step_no}"
        step_no += 1
        records.append(_event({"type": "step.begin", "uuid": step_uuid, "step": step_no}))
        if thought:
            records.append(_event({"type": "content.part", "stepUuid": step_uuid,
                                   "part": {"type": "text", "text": thought}}))
        for call in calls:
            call_id = f"call-{call_no}"
            call_no += 1
            records.append(_event({"type": "tool.call", "stepUuid": step_uuid,
                                   "toolCallId": call_id, "name": call["name"],
                                   "args": call["args"]}))
            result: dict[str, Any] = {"output": call["observation"]}
            if call["is_error"] is not None:
                result["isError"] = call["is_error"]
            records.append(_event({"type": "tool.result", "toolCallId": call_id, "result": result}))

    for act in _ordered_activations(run):
        emit_step(_recall_thought(run, act), [])  # the agent's recall / boundary node
        for step in activation_steps(run, act, include_causes=False):
            emit_step(step["thought"], step["calls"])

    if not records:  # a run with no agent activity still needs a renderable node
        emit_step("No agent activity recorded in this run.", [])
    return records


def build_session(run: RunLog, run_id: str, title: Optional[str] = None) -> tuple[dict, list[dict]]:
    """``(state.json dict, wire.jsonl records)`` for one super-agent session."""
    agent_count = len(run.agent_ids)
    state = {
        "title": title or run_id,
        "custom": {
            "sourceFramework": "Claude Code",
            "runId": run.run_id or run_id,
            "agents": agent_count,
            "status": run.status,
        },
    }
    return state, flatten_to_wire(run)
