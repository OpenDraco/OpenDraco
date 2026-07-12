"""Topology-page endpoints: unified configs + GitPython-backed history,
MCP tool catalogue, agent-type catalogue, and the Ollama /
remote-provider model dropdown feed. One file because the topology
page consumes them as one surface."""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import threading
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.common import (
    INFERENCE_INTERNAL_LOGS_DIR,
    LOADED_CONFIG_DIR,
    PREDEFINED_CONFIG_DIR,
    logger,
)
from evomas.config.loader import (
    resolve_config_path,
    scan_config_dir,
    validate_loaded_config,
)
from evomas.exceptions.errors import ConfigError
from evomas.mcp.server import tool_repo_owner_map
from evomas.utils.ollama_preflight import pulled_ollama_models_with_catalog

router = APIRouter()


# Ollama + remote-provider model probes live in evomas.* now so the CLI
# can reuse them; the topology dropdown is the only HTTP consumer.


class PullModelRequest(BaseModel):
    model: str


@router.post("/api/models/pull")
async def pull_model(req: PullModelRequest):
    """Stream `ollama pull <model>` progress as SSE.

    Events: `{type: "log", line}` per stdout line, then a terminal
    `{type: "done", code}` (0 = success)."""
    raw = req.model.strip()
    name = raw.removeprefix("ollama/") if raw.startswith("ollama/") else raw
    if not name:
        raise HTTPException(400, "model must be a non-empty string")

    q: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def put(payload: dict | None) -> None:
        loop.call_soon_threadsafe(q.put_nowait, payload)

    def worker() -> None:
        try:
            # utf-8 + errors="replace" avoids cp1252 decode crashes on
            # Windows when Ollama's progress bars contain non-cp1252 glyphs.
            proc = subprocess.Popen(
                ["ollama", "pull", name],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                encoding="utf-8", errors="replace",
            )
        except FileNotFoundError:
            put({"type": "log", "line": "ERROR: `ollama` not on PATH; install Ollama first."})
            put({"type": "done", "code": 127})
            put(None)
            return
        assert proc.stdout is not None
        for line in proc.stdout:
            put({"type": "log", "line": line.rstrip()})
        proc.wait()
        put({"type": "done", "code": proc.returncode})
        put(None)

    threading.Thread(target=worker, daemon=True).start()

    async def generate():
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=600.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'done', 'code': 124})}\n\n"
                return
            if item is None:
                return
            yield f"data: {json.dumps(item, default=str)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/models")
def list_models() -> list[dict[str, Any]]:
    """`[{name, pulled}]` — pulled-locally + curated catalog. Pulled
    first (alphabetical), then unpulled in declared order."""
    return pulled_ollama_models_with_catalog()


# ─── Unified Config Endpoints ────────────────────────────────────────────────
# Configs live in two roots — `predefined/` (read-only, shipped) and
# `loaded/` (writable, user-imported). The loader searches both.

@router.get("/api/configs")
def list_configs() -> list[dict[str, str]]:
    """`[{stem, id, description, source}]` from both config roots."""
    return (
        scan_config_dir(PREDEFINED_CONFIG_DIR, "predefined")
        + scan_config_dir(LOADED_CONFIG_DIR, "loaded")
    )


@router.get("/api/configs/{name}")
def get_config(name: str) -> dict:
    path = resolve_config_path(
        name, predefined_dir=PREDEFINED_CONFIG_DIR, loaded_dir=LOADED_CONFIG_DIR,
    )
    if path is None:
        raise HTTPException(404, f"Config '{name}' not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(500, f"Failed to parse {path.name}: {exc}") from exc


class LoadedConfigPayload(BaseModel):
    name: str
    data: dict[str, Any]
    replace: bool = False


@router.post("/api/configs/loaded")
def save_loaded_config(payload: LoadedConfigPayload) -> dict[str, Any]:
    """Persist `loaded/<name>.json`. Rejects overlap with a predefined
    stem; requires `replace=True` to overwrite an existing loaded stem."""
    if "/" in payload.name or "\\" in payload.name or not payload.name:
        raise HTTPException(400, "invalid config name")
    try:
        validate_loaded_config(payload.data, payload.name)
    except ConfigError as exc:
        raise HTTPException(400, str(exc)) from exc

    target = LOADED_CONFIG_DIR / f"{payload.name}.json"
    predefined = PREDEFINED_CONFIG_DIR / f"{payload.name}.json"
    if predefined.is_file():
        raise HTTPException(409, f"a predefined config already uses id '{payload.name}'")
    if target.is_file() and not payload.replace:
        raise HTTPException(409, f"a loaded config already uses id '{payload.name}'")
    LOADED_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload.data, indent=2), encoding="utf-8")
    # Best-effort version-control commit; failures don't propagate.
    sha: str | None = None
    try:
        from evomas.config.history import commit_save
        sha = commit_save(payload.name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("config history commit failed for %s: %s", payload.name, exc)
    return {"ok": True, "stem": payload.name, "path": str(target), "sha": sha}


class RenameConfigPayload(BaseModel):
    new_name: str


@router.patch("/api/configs/loaded/{name}")
def rename_loaded_config(name: str, payload: RenameConfigPayload) -> dict[str, Any]:
    """Rename a loaded config (file + `id` field). Predefined are read-only."""
    new_name = payload.new_name.strip()
    if "/" in new_name or "\\" in new_name or not new_name:
        raise HTTPException(400, "invalid new_name")
    if new_name == name:
        return {"ok": True, "stem": name}

    src = LOADED_CONFIG_DIR / f"{name}.json"
    if not src.is_file():
        raise HTTPException(404, f"loaded config '{name}' not found")
    if (PREDEFINED_CONFIG_DIR / f"{new_name}.json").is_file():
        raise HTTPException(409, f"a predefined config already uses id '{new_name}'")
    dst = LOADED_CONFIG_DIR / f"{new_name}.json"
    if dst.is_file():
        raise HTTPException(409, f"a loaded config already uses id '{new_name}'")

    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(500, f"failed to parse {src.name}: {exc}") from exc
    data["id"] = new_name
    dst.write_text(json.dumps(data, indent=2), encoding="utf-8")
    src.unlink()
    # Two histories, one rename: close the old timeline, start the new.
    try:
        from evomas.config.history import commit_delete, commit_save
        commit_delete(name)
        commit_save(new_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("config history rename commit failed (%s -> %s): %s", name, new_name, exc)
    return {"ok": True, "stem": new_name, "path": str(dst)}


@router.delete("/api/configs/loaded/{name}")
def delete_loaded_config(name: str) -> dict[str, Any]:
    target = LOADED_CONFIG_DIR / f"{name}.json"
    if not target.is_file():
        raise HTTPException(404, f"loaded config '{name}' not found")
    target.unlink()
    try:
        from evomas.config.history import commit_delete
        commit_delete(name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("config history delete commit failed for %s: %s", name, exc)
    return {"ok": True, "stem": name}


# ─── Loaded-config version history (GitPython-backed) ────────────────────────
# History lives in a nested git repo under `evomas/config/loaded/`
# (gitignored at the project root). Every Save writes a commit.

@router.get("/api/configs/loaded/{name}/history")
def list_config_history(name: str) -> dict[str, Any]:
    """Newest-first commits touching `<name>.json`; empty list = no history yet."""
    if "/" in name or "\\" in name or not name:
        raise HTTPException(400, "invalid config name")
    try:
        from evomas.config.history import list_history
        return {"entries": list_history(name)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("history list failed for %s: %s", name, exc)
        raise HTTPException(503, f"history backend unavailable: {exc}") from exc


@router.get("/api/configs/loaded/{name}/history/{sha}")
def get_config_at_sha(name: str, sha: str) -> dict[str, Any]:
    """File contents at `sha` for the history preview pane."""
    if "/" in name or "\\" in name or not name:
        raise HTTPException(400, "invalid config name")
    if not re.fullmatch(r"[0-9a-fA-F]{4,40}", sha):
        raise HTTPException(400, "invalid sha")
    try:
        from evomas.config.history import read_at
        content = read_at(name, sha)
        return {"sha": sha, "content": content}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, f"version not found: {exc}") from exc


@router.delete("/api/configs/loaded/{name}/history/{sha}")
def delete_config_history_entry(name: str, sha: str) -> dict[str, Any]:
    """Drop a single commit from the loaded-configs history.
    Descendants get rebased onto its parent, so their SHAs change —
    older runs pinned to those SHAs will stop matching."""
    if "/" in name or "\\" in name or not name:
        raise HTTPException(400, "invalid config name")
    if not re.fullmatch(r"[0-9a-fA-F]{4,40}", sha):
        raise HTTPException(400, "invalid sha")
    try:
        from evomas.config.history import delete_commit
        new_head = delete_commit(sha)
        if new_head is None:
            raise HTTPException(
                409,
                "cannot delete — commit is the root of history (use "
                "the 'clear this config's history' action instead) or "
                "the SHA is no longer reachable",
            )
        return {"ok": True, "new_head": new_head}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("delete_commit failed for %s: %s", sha, exc)
        raise HTTPException(500, f"delete failed: {exc}") from exc


@router.delete("/api/configs/loaded/{name}/history")
def clear_config_history(name: str) -> dict[str, Any]:
    """Drop every commit touching `<name>.json`. Other configs'
    history entries survive (their commit SHAs are rewritten by the
    cascading rebase, but content + timeline are preserved). The
    working-tree JSON is preserved so the loader still finds it."""
    if "/" in name or "\\" in name or not name:
        raise HTTPException(400, "invalid config name")
    target = LOADED_CONFIG_DIR / f"{name}.json"
    if not target.is_file():
        raise HTTPException(404, f"loaded config '{name}' not found")
    try:
        from evomas.config.history import clear_history_for
        clear_history_for(name)
        return {"ok": True, "stem": name}
    except Exception as exc:  # noqa: BLE001
        logger.warning("clear_config_history failed for %s: %s", name, exc)
        raise HTTPException(500, f"reset failed: {exc}") from exc


@router.get("/api/configs/loaded/{name}/history/{sha}/runs")
def list_runs_for_config_sha(name: str, sha: str) -> dict[str, Any]:
    """Runs whose recorded `config_sha` matches `sha` — drives the
    "N runs" pill in the history sidebar."""
    if "/" in name or "\\" in name or not name:
        raise HTTPException(400, "invalid config name")
    if not re.fullmatch(r"[0-9a-fA-F]{4,40}", sha):
        raise HTTPException(400, "invalid sha")
    matches: list[dict[str, Any]] = []
    if INFERENCE_INTERNAL_LOGS_DIR.is_dir():
        # `run_meta` is always the first event — read one line per sidecar.
        for ndjson in INFERENCE_INTERNAL_LOGS_DIR.glob("*.ndjson"):
            try:
                with ndjson.open("r", encoding="utf-8") as f:
                    first = f.readline()
                if not first.strip():
                    continue
                meta = json.loads(first)
                if meta.get("type") != "run_meta":
                    continue
                if meta.get("config_name") != name:
                    continue
                run_sha = meta.get("config_sha") or ""
                if not run_sha:
                    continue
                if run_sha.startswith(sha) or sha.startswith(run_sha):
                    matches.append({
                        "runId": meta.get("run_id") or ndjson.stem.replace("prediction-", ""),
                        "instanceIds": meta.get("instance_ids") or [],
                        "ts": meta.get("ts") or "",
                    })
            except (OSError, json.JSONDecodeError):
                continue
    matches.sort(key=lambda m: m.get("ts") or "", reverse=True)
    return {"matches": matches}


# ─── MCP tools (read-only) ────────────────────────────────────────────────────
@router.get("/api/tools")
def list_tools() -> list[dict[str, Any]]:
    """MCP tool catalog: `[{name, description, inputSchema, repo}]`.
    `repo` is the bundle folder or `"evomas"` for top-level helpers."""
    from evomas.mcp.server import MCPServer
    owner_map = tool_repo_owner_map()
    catalog = MCPServer().registry.list()
    for entry in catalog:
        entry["repo"] = owner_map.get(entry.get("name", ""), "evomas")
    return catalog


# ─── Agent types (read-only) ──────────────────────────────────────────────────
@router.get("/api/agent-types")
def list_agent_types_endpoint() -> list[dict[str, Any]]:
    """Agent-type catalog with a `variants` array per type (EvoMas
    built-in first, then CSV-derived alternatives)."""
    from evomas.agents.types import list_agent_types
    from evomas.agents.types.variants import list_variants
    catalog = list_agent_types()
    variants_by_type = list_variants()
    for t in catalog:
        t["variants"] = variants_by_type.get(t["type"], [])
    return catalog


@router.get("/api/agent-variants")
def list_agent_variants_endpoint() -> dict[str, list[dict[str, Any]]]:
    """Agent variants grouped by AGENT_TYPE; EvoMas built-in is always first."""
    from evomas.agents.types.variants import list_variants
    return list_variants()
