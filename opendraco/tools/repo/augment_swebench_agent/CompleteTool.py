"""augment_swebench_agent `CompleteTool` — task-completion marker.

Behavior-faithful interface mirror of the upstream augment-swebench-agent
`CompleteTool`: a deliberate end-of-turn signal that records the
outcome. OpenDraco-authored body — writes a `.opendraco/state.json` marker
into the workspace (when provided) so an out-of-process orchestrator
can observe the completion, and always returns the JSON record.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def CompleteTool(result: str = "", workspace: str = "", agent: str = "augment") -> str:
    """Mark `agent` as done with optional `result`. Returns JSON
    `{agent, completed, result, ts}`. When `workspace` is set, drops
    a `.opendraco/state.json` file inside it for out-of-process callers."""
    record = {"agent": agent, "completed": True, "result": result, "ts": time.time()}
    if workspace:
        try:
            p = Path(workspace) / ".opendraco"
            p.mkdir(parents=True, exist_ok=True)
            (p / "state.json").write_text(json.dumps(record), encoding="utf-8")
        except OSError:
            pass
    logger.info("[augment.complete] %s", record)
    return json.dumps(record)
