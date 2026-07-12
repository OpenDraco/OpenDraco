"""trae_agent `TaskDoneTool` — completion marker (trae's name for it).

Functionally equivalent to augment-swebench-agent's `CompleteTool`,
but kept as a separate MCP registration because trae's upstream uses
this distinct name. Catalogs that reference `TaskDoneTool` resolve
here; catalogs that reference `CompleteTool` resolve to augment's.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def TaskDoneTool(result: str = "", workspace: str = "", agent: str = "trae") -> str:
    """Mark `agent` as done with optional `result`. Returns JSON
    `{agent, completed, result, ts}`. When `workspace` is set, drops
    a `.evomas/state.json` file inside it."""
    record = {"agent": agent, "completed": True, "result": result, "ts": time.time()}
    if workspace:
        try:
            p = Path(workspace) / ".evomas"
            p.mkdir(parents=True, exist_ok=True)
            (p / "state.json").write_text(json.dumps(record), encoding="utf-8")
        except OSError:
            pass
    logger.info("[trae.task_done] %s", record)
    return json.dumps(record)
