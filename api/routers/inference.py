"""Inference-page endpoints: kick off / cancel / observe an LLM run.

`/api/inference/run` streams agent events over SSE while mirroring the
stream into an NDJSON sidecar for reload-resume. `/api/inference/active`
+ `/api/inference/log-tail` let the page resume an in-flight run after
a refresh without holding open an SSE connection."""
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from api.common import (
    INFERENCE_INTERNAL_LOGS_DIR,
    INSTANCES_PATH,
    LOADED_CONFIG_DIR,
    PREDEFINED_CONFIG_DIR,
    PREDICTION_CONFIGS_DIR,
    PREDICTION_TEXT_LOGS_DIR,
    PREDICTIONS_DIR,
    safe_under,
    logger,
)
from evomas.config.loader import resolve_config_path
from evomas.utils.json_safe import safe_serialize
from evomas.utils.notebook import build_notebook_for_inputs

router = APIRouter()


class InferenceRequest(BaseModel):
    # Legacy single-instance form; falls back when `instance_ids` is omitted.
    instance_id: str | None = None
    # Multi-instance form — worker runs sequentially with
    # `instance_start` / `instance_done` framing on the SSE stream.
    instance_ids: list[str] | None = None
    # Config name (resolved to evomas/config/<name>.json) OR an inline
    # unified-config dict (topology page's "Save to session" flow).
    config: str | dict[str, Any] = ""


# ─── Worker-shared state (module-private) ────────────────────────────────────
_cancel_flags: dict[str, bool] = {}

# Set on worker start, cleared on done/error/cancel. The Inference page
# polls `/api/inference/active` to rebuild its UI from the .log transcript.
_active_run: dict[str, Any] | None = None


@router.post("/api/inference/run")
async def run_inference(req: InferenceRequest):
    ids: list[str] = []
    if req.instance_ids:
        ids = [i for i in req.instance_ids if i]
    elif req.instance_id:
        ids = [req.instance_id]
    if not ids:
        raise HTTPException(400, "Provide `instance_id` or `instance_ids`")

    # Resolve every id up front so we 404 before kicking off LLM work.
    by_id: dict[str, dict] = {}
    if INSTANCES_PATH.exists():
        with INSTANCES_PATH.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line.strip())
                    iid = obj.get("instance_id")
                    if iid in ids and iid not in by_id:
                        by_id[iid] = obj
                except json.JSONDecodeError:
                    pass
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise HTTPException(404, f"Instance(s) not found: {missing}")

    for iid in ids:
        _cancel_flags[iid] = False

    q: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    # Log writers opened once the run_id is known. `put()` mirrors every
    # SSE event into log_state["fh"] (NDJSON sidecar for resume-on-reload);
    # text_log_state["handler"] is the FileHandler for the user-facing .log.
    log_state: dict[str, Any] = {"fh": None}
    text_log_state: dict[str, Any] = {"handler": None}

    def put(data: dict) -> None:
        loop.call_soon_threadsafe(q.put_nowait, data)
        fh = log_state.get("fh")
        if fh is not None:
            try:
                fh.write(json.dumps(data, default=str) + "\n")
                fh.flush()
            except (OSError, ValueError):
                pass

    def worker() -> None:
        global _active_run
        try:
            from evomas.config.loader import load_config
            from evomas.core.workflow.graph_builder import build_graph
            from evomas.core.workflow.runner import _build_agents
            from evomas.core.workflow.state_factory import (
                build_initial_state,
                build_state_class,
            )
            from evomas.utils.patch import generate_diff_impl
            from evomas.utils.workspace import clone_workspace

            if isinstance(req.config, dict):
                put({"type": "status", "message": "Using inline session config…"})
                cfg = req.config
                config_name = str(cfg.get("id") or "session")
            else:
                put({"type": "status", "message": f"Loading config '{req.config}'…"})
                cfg = load_config(req.config)
                config_name = str(req.config)

            # One run = one UID, shared between prediction file + evaluation dir.
            run_uid = uuid.uuid4().hex[:8]
            run_id = f"{config_name}-{run_uid}"
            stem = f"prediction-{run_id}"
            put({
                "type": "run_id",
                "run_id": run_id,
                "output_path": str(PREDICTIONS_DIR / f"{stem}.jsonl"),
            })
            # Re-create dirs at request time so wiping `results/` between
            # restarts doesn't break the next run.
            PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
            PREDICTION_TEXT_LOGS_DIR.mkdir(parents=True, exist_ok=True)
            PREDICTION_CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
            INFERENCE_INTERNAL_LOGS_DIR.mkdir(parents=True, exist_ok=True)
            output_path = str(PREDICTIONS_DIR / f"{stem}.jsonl")
            text_log_path = str(PREDICTION_TEXT_LOGS_DIR / f"{stem}.log")
            internal_log_path = str(INFERENCE_INTERNAL_LOGS_DIR / f"{stem}.ndjson")
            config_snapshot_path = str(PREDICTION_CONFIGS_DIR / f"{stem}.json")
            Path(output_path).write_text("", encoding="utf-8")
            # Snapshot the resolved config so Results can hand it back later.
            Path(config_snapshot_path).write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            log_state["fh"] = open(internal_log_path, "w", encoding="utf-8", buffering=1)

            # `run_meta` is the NDJSON header — config name + git SHA so the
            # History panel can resolve "runs that used this version".
            try:
                from evomas.config.history import current_sha as _current_sha
                _config_sha = _current_sha(config_name) if not isinstance(req.config, dict) else None
            except Exception:  # noqa: BLE001
                _config_sha = None
            put({
                "type": "run_meta",
                "run_id": run_id,
                "config_name": config_name,
                "config_sha": _config_sha,
                "instance_ids": list(ids),
                "ts": datetime.now().isoformat(),
            })

            # Preflight: pull any referenced Ollama models that aren't on
            # disk yet. Progress events route through put() → SSE so the
            # log panel renders live progress.
            from evomas.exceptions.errors import EvomasError as _EvomasError
            from evomas.utils.ollama_preflight import preflight_models
            try:
                preflight_models(cfg, event_sink=put)
            except _EvomasError as exc:
                put({"type": "error", "message": str(exc)})
                return

            # User-facing text log: every `logger.info(...)` agents emit.
            # Detached in `finally` so lines don't bleed into the next run.
            import logging as _logging
            _root_logger = _logging.getLogger()
            _text_log_handler = _logging.FileHandler(text_log_path, mode="w", encoding="utf-8")
            _text_log_handler.setFormatter(_logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s"
            ))
            _text_log_handler.setLevel(_logging.INFO)
            if _root_logger.level > _logging.INFO or _root_logger.level == 0:
                _root_logger.setLevel(_logging.INFO)
            _root_logger.addHandler(_text_log_handler)
            text_log_state["handler"] = _text_log_handler

            # Active-run pointer for reload-resume.
            _active_run = {
                "run_id": run_id,
                "config_label": str(config_name),
                "instance_ids": list(ids),
                "log_path": internal_log_path,
                "started_at": int(datetime.now().timestamp() * 1000),
            }

            # ─── Helpers shared across the per-instance loop ────────────
            def _make_think_cb(agent_name: str) -> Any:
                def _cb(chunk: str) -> None:
                    put({"type": "thinking_chunk", "agent": agent_name, "chunk": chunk})
                return _cb

            def _make_response_cb(agent_name: str) -> Any:
                """Fires once per `_invoke()` with the full LLM response."""
                def _cb(text: str) -> None:
                    put({"type": "response", "agent": agent_name, "content": text})
                return _cb

            def _result_preview(tool: str, result: Any) -> str:
                if isinstance(result, list):
                    return f"{len(result)} items"
                if isinstance(result, dict):
                    if "ok" in result or "applied" in result:
                        ok = result.get("ok", result.get("applied", "?"))
                        return f"ok={ok}"
                    return str(result)[:80]
                return str(result)[:80]

            _PATH_KEYS = {"path", "file_path", "directory", "repo_path"}

            def _args_preview(tool: str, args: dict) -> str:
                skip = {"patch_str", "with_line_numbers", "max_chars"}
                parts = []
                for k, v in args.items():
                    if k in skip:
                        continue
                    val = str(v)
                    if k in _PATH_KEYS and len(val) > 35:
                        parts_path = val.replace("\\", "/").rstrip("/").split("/")
                        val = "…/" + "/".join(parts_path[-2:])
                    else:
                        val = val[:40]
                    parts.append(f"{k}={val}")
                return ", ".join(parts)

            def _make_tool_cb(agent_name: str) -> Any:
                def _cb(tool: str, args: dict, result: Any) -> None:
                    put({
                        "type": "tool_call",
                        "agent": agent_name,
                        "tool": tool,
                        "args_preview": _args_preview(tool, args),
                        "result_preview": _result_preview(tool, result),
                    })
                return _cb

            # ─── Per-instance loop (sequential) ─────────────────────────
            for idx, iid in enumerate(ids):
                if any(_cancel_flags.get(x) for x in ids):
                    put({"type": "cancelled"})
                    return

                instance = by_id[iid]
                instance_started_at = int(datetime.now().timestamp() * 1000)
                put({"type": "instance_start", "instance_id": iid, "index": idx, "total": len(ids)})

                put({"type": "status", "message": f"Cloning workspace for {iid}…"})
                workspace = clone_workspace(
                    instance["instance_id"],
                    instance["repo"],
                    instance["base_commit"],
                )
                # Sandboxed tools (write_file, ...) read this env var.
                import os as _os
                _os.environ["EVOMAS_WORKSPACE_PATH"] = str(workspace.path)

                issue_parts: list[str] = []
                if instance.get("problem_statement"):
                    issue_parts.append(instance["problem_statement"])
                if instance.get("hints_text"):
                    issue_parts.append("\n## Hints\n" + instance["hints_text"])
                issue_text = "\n".join(issue_parts).strip()

                # Order matters: build_state_class reads each agent's
                # OUTPUT_TYPE ClassVar.
                agents = _build_agents(cfg)

                for agent_name, agent in agents.items():
                    agent.on_think = _make_think_cb(agent_name)
                    agent.on_response = _make_response_cb(agent_name)
                    agent.on_tool = _make_tool_cb(agent_name)

                state_cls = build_state_class(cfg, agents)
                graph = build_graph(cfg, agents, state_cls)

                initial_state = build_initial_state(
                    cfg,
                    agents,
                    {
                        "instance": instance,
                        "workspace_path": str(workspace.path),
                        "issue_text": issue_text,
                    },
                )

                put({"type": "start", "instance_id": iid, "config": req.config})

                # Edge maps powering `agent_input` (predecessors) and
                # per-edge `handoff` events (successors).
                predecessors: dict[str, list[str]] = {}
                successors: dict[str, list[str]] = {}
                for edge in (cfg.get("edges") or []):
                    if isinstance(edge, dict):
                        src = str(edge.get("from") or "")
                        dst = str(edge.get("to") or "")
                        predecessors.setdefault(dst, []).append(src)
                        successors.setdefault(src, []).append(dst)

                def _preview(val: Any) -> Any:
                    """600-char truncation, matches the delta path below."""
                    if isinstance(val, str):
                        return val[:600] + "\n…(truncated)" if len(val) > 600 else val
                    if isinstance(val, list) and val and all(isinstance(x, str) for x in val):
                        return [
                            (x[:600] + "\n…(truncated)" if len(x) > 600 else x)
                            for x in val
                        ]
                    return val

                accumulated: dict[str, Any] = {}
                seen_agents: set[str] = set()
                for chunk in graph.stream(initial_state, config={"recursion_limit": 75}):
                    if any(_cancel_flags.get(x) for x in ids):
                        put({"type": "cancelled"})
                        return
                    for agent_name, delta in chunk.items():
                        if agent_name.startswith("__") or delta is None:
                            continue
                        if agent_name not in seen_agents:
                            # First observation — emit what predecessors
                            # put into state before this agent ran.
                            inputs: dict[str, Any] = {}
                            for pred in predecessors.get(agent_name, []):
                                if pred and pred in accumulated:
                                    inputs[pred] = safe_serialize(_preview(accumulated[pred]))
                            put({
                                "type": "agent_input",
                                "agent": agent_name,
                                "inputs": inputs,
                            })
                            seen_agents.add(agent_name)
                        accumulated.update(delta)
                        safe_delta = safe_serialize(delta)
                        # Truncate long patch strings in list-valued slots;
                        # producer-keyed slots make the field name vary.
                        for k, v in list(safe_delta.items()):
                            if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
                                safe_delta[k] = [
                                    (x[:600] + "\n…(truncated)" if len(x) > 600 else x)
                                    for x in v
                                ]
                        put({"type": "agent_event", "agent": agent_name, "delta": safe_delta})
                        # One `handoff` per outgoing edge. Prefer the
                        # producer slot `delta[agent_name]`; fall back to
                        # the whole delta when the agent wrote elsewhere.
                        targets_for_node = successors.get(agent_name, [])
                        if targets_for_node:
                            from evomas.utils.handoff import (
                                preview_payload as _preview_payload,
                                summarize_payload as _summarize_payload,
                            )
                            raw_primary = delta.get(agent_name, delta)
                            handoff_summary = _summarize_payload(raw_primary)
                            handoff_preview = _preview_payload(raw_primary)
                            handoff_keys = sorted(delta.keys())
                            handoff_ts = datetime.now().isoformat()
                            for _tgt in targets_for_node:
                                put({
                                    "type": "handoff",
                                    "from": agent_name,
                                    "to": _tgt,
                                    "keys": handoff_keys,
                                    "summary": handoff_summary,
                                    "preview": handoff_preview,
                                    "timestamp": handoff_ts,
                                })

                # `model_patch` is a unified diff or empty -- the end-node
                # slot is only used when it actually contains `diff --git `
                # (virtual-patcher pattern), so LLM phrases like "null" /
                # "done" can't leak into the prediction.
                workspace_diff = generate_diff_impl(str(workspace.path)) or ""
                if workspace_diff.strip():
                    final_patch: str = workspace_diff
                else:
                    end_field = cfg.get("end")
                    end_key: str = (
                        end_field if isinstance(end_field, str)
                        else (end_field[-1] if end_field else "")
                    )
                    slot = str(accumulated.get(end_key) or "")
                    final_patch = slot if "diff --git " in slot else ""

                # Sum per-agent token counts across the run.
                tokens_in = sum(int(a.tokens.get("input", 0))  for a in agents.values())
                tokens_out = sum(int(a.tokens.get("output", 0)) for a in agents.values())
                tokens_total = sum(int(a.tokens.get("total", 0))  for a in agents.values())
                logger.info(
                    "[%s] tokens in=%d out=%d total=%d (per-agent: %s)",
                    iid, tokens_in, tokens_out, tokens_total,
                    {n: a.tokens for n, a in agents.items()},
                )
                # Per-agent token chips — emitted after the chain since
                # the graph stream has no per-agent "done" event.
                for agent_name, agent in agents.items():
                    put({
                        "type": "agent_tokens",
                        "agent": agent_name,
                        "input":  int(agent.tokens.get("input", 0)),
                        "output": int(agent.tokens.get("output", 0)),
                        "total":  int(agent.tokens.get("total", 0)),
                    })

                pred = {
                    "instance_id": iid,
                    "model_patch": final_patch,
                    "model_name_or_path": "evomas",
                    "run_id": run_id,
                    "tokens": {"input": tokens_in, "output": tokens_out, "total": tokens_total},
                    # Forward subset/split so the Evaluation page can partition.
                    "subset": instance.get("subset", "lite"),
                    "split":  instance.get("split", "dev"),
                    "started_at": instance_started_at,
                    "ended_at": int(datetime.now().timestamp() * 1000),
                }
                with open(output_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(pred) + "\n")

                put({
                    "type": "instance_done",
                    "instance_id": iid,
                    "index": idx,
                    "total": len(ids),
                    "output_path": output_path,
                    "run_id": run_id,
                    "patch": final_patch,
                })

            put({
                "type": "done",
                "instance_ids": ids,
                "output_path": output_path,
                "run_id": run_id,
            })

        except Exception as exc:
            import traceback as _tb
            put({"type": "error", "message": str(exc), "traceback": _tb.format_exc()})
        finally:
            fh = log_state.get("fh")
            if fh is not None:
                try:
                    fh.close()
                except OSError:
                    pass
            handler = text_log_state.get("handler")
            if handler is not None:
                try:
                    import logging as _logging
                    _logging.getLogger().removeHandler(handler)
                    handler.close()
                except (OSError, ValueError):
                    pass
            _active_run = None
            loop.call_soon_threadsafe(q.put_nowait, None)

    threading.Thread(target=worker, daemon=True).start()

    async def generate():
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=600.0)
            except asyncio.TimeoutError:
                yield 'data: {"type":"error","message":"Timeout waiting for response"}\n\n'
                break
            if item is None:
                break
            yield f"data: {json.dumps(item, default=str)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/inference/cancel/{instance_id}")
def cancel_inference(instance_id: str) -> dict:
    _cancel_flags[instance_id] = True
    return {"ok": True}


@router.get("/api/inference/active")
def inference_active() -> dict[str, Any]:
    """Snapshot of the in-flight run, or `{active: false}`. Used by the
    Inference page on reload to rehydrate the UI."""
    if _active_run is None:
        return {"active": False}
    return {"active": True, **_active_run}


class NotebookRequest(BaseModel):
    """Payload for `/api/inference/notebook` — same shape as
    `InferenceRequest` (so the frontend can reuse its config-and-ids
    state) minus the SSE-only run knobs."""
    instance_ids: list[str]
    config: str | dict[str, Any] = ""
    evaluator: str = ""


@router.post("/api/inference/notebook")
def build_inference_notebook(req: NotebookRequest) -> Response:
    """Reproduce-this-run notebook built from the Inference page's
    current (config, instance_ids) selection. No baseline patches yet —
    the notebook omits the compare-with-original section.

    Accepts either a config name (resolved against
    `evomas/config/predefined|loaded/`) or an inline unified-config dict
    (the topology page's "Save to session" payload)."""
    if not req.instance_ids:
        raise HTTPException(400, "instance_ids must be non-empty")
    evaluator_stem = (req.evaluator or "").strip()
    if not evaluator_stem:
        raise HTTPException(400, "evaluator stem is required")

    if isinstance(req.config, dict):
        cfg_data = req.config
    else:
        name = (req.config or "").strip()
        if not name:
            raise HTTPException(400, "config name or inline dict required")
        cfg_path = resolve_config_path(
            name,
            predefined_dir=PREDEFINED_CONFIG_DIR,
            loaded_dir=LOADED_CONFIG_DIR,
        )
        if cfg_path is None:
            raise HTTPException(404, f"config '{name}' not found")
        try:
            cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(500, f"failed to parse {cfg_path.name}: {exc}") from exc

    try:
        run_id, notebook = build_notebook_for_inputs(
            instance_ids=list(req.instance_ids),
            config_data=cfg_data,
            instances_path=INSTANCES_PATH,
            evaluator=evaluator_stem,
        )
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    body = json.dumps(notebook, indent=1)
    return Response(
        content=body,
        media_type="application/x-ipynb+json",
        headers={
            "Content-Disposition": f'attachment; filename="notebook-{run_id}.ipynb"',
        },
    )


@router.get("/api/inference/log-tail")
def inference_log_tail(path: str, offset: int = 0) -> dict[str, Any]:
    """Tail bytes of the internal NDJSON log from `offset` onward."""
    p = safe_under(INFERENCE_INTERNAL_LOGS_DIR, path)
    if not p.is_file():
        raise HTTPException(404, "log file not found")
    size = p.stat().st_size
    if offset > size:
        offset = 0  # truncated/replaced; restart from the top
    with p.open("rb") as fh:
        fh.seek(offset)
        chunk = fh.read()
    is_running = _active_run is not None and Path(_active_run["log_path"]) == p
    return {
        "raw": chunk.decode("utf-8", errors="replace"),
        "offset": offset + len(chunk),
        "is_running": is_running,
    }
