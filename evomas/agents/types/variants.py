"""Agent-variant catalog merging built-in EvoMas types with repo-derived variants under `evomas/config/agent_types/*.json`; powers the Topology palette's per-type variant dropdown."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from evomas.agents.types import TYPE_COLORS, list_agent_types

logger = logging.getLogger(__name__)

_CONFIG_DIR: Path = Path(__file__).resolve().parents[2] / "config" / "agent_types"


def _builtin_variants() -> list[dict[str, Any]]:
    """One variant per built-in AGENT_TYPE; Topology dropdown shows the EvoMas default first."""
    out: list[dict[str, Any]] = []
    for t in list_agent_types():
        agent_type = t["type"]
        out.append({
            "key":            f"evomas:{agent_type}",
            "label":          f"EvoMas · default",
            "repo":           "evomas",
            "name":           agent_type,
            "agent_type":     agent_type,
            "source_url":     "",
            "description":    t.get("description", ""),
            "default_system": t.get("default_system", ""),
            "default_user":   t.get("default_user", ""),
            "default_proxy":  "",
            "default_tools":  list(t.get("default_tools") or []),
            "default_config": dict(t.get("default_config") or {}),
        })
    return out


def _repo_variants() -> list[dict[str, Any]]:
    """One variant per agent across every `evomas/config/agent_types/*.json`."""
    out: list[dict[str, Any]] = []
    if not _CONFIG_DIR.is_dir():
        return out
    for path in sorted(_CONFIG_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("skipping %s: %s", path.name, exc)
            continue
        repo_id = data.get("id") or path.stem
        for agent in data.get("agents") or []:
            name = (agent.get("name") or "").strip()
            agent_type = (agent.get("agent_type") or "").strip()
            if not name or not agent_type:
                continue
            prompts = agent.get("prompts") or {}
            tools = [t.get("name") for t in (agent.get("tools") or []) if t.get("name")]
            out.append({
                "key":            f"{repo_id}:{name}",
                "label":          f"{repo_id} · {name}",
                "repo":           repo_id,
                # Drives the dropped-node id; normalized client-side via
                # `normalizeNodeBase`.
                "name":           name,
                "agent_type":     agent_type,
                "source_url":     agent.get("source_url") or "",
                "description":    agent.get("short_description") or "",
                "default_system": prompts.get("system") or "",
                "default_user":   prompts.get("user") or "",
                "default_proxy":  prompts.get("proxy") or "",
                "default_tools":  tools,
                "default_config": {},
            })
    return out


def list_variants() -> dict[str, list[dict[str, Any]]]:
    """Variants grouped by canonical AGENT_TYPE; built-in EvoMas variant is always first since the frontend treats the first entry as the default selection."""
    grouped: dict[str, list[dict[str, Any]]] = {t: [] for t in TYPE_COLORS}
    for v in _builtin_variants():
        grouped.setdefault(v["agent_type"], []).append(v)
    for v in _repo_variants():
        grouped.setdefault(v["agent_type"], []).append(v)
    return grouped


__all__ = ["list_variants"]
