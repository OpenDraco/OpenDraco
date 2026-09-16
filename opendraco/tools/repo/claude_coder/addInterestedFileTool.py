"""claude_coder `addInterestedFileTool` — record files in an in-process
'interested' list.

Each agent (keyed by `agent` argument, defaulting to the global slot)
maintains a small set of paths it has flagged as relevant. Stateless
between processes — wiped on import. Useful for short-lived
trajectories where the agent wants a private scratchpad of "files
worth re-reading later".
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Per-agent set of interested paths. Keyed by `agent`; defaults shared.
_INTERESTED: dict[str, set[str]] = {}


@tool
def addInterestedFileTool(path: str, agent: str = "_default") -> str:
    """Add `path` to `agent`'s interested-files set. Returns JSON
    `{agent, added, total, files}` — `added` is True when the path
    was newly inserted (False if already present); `total` is the
    new size of the set; `files` is the sorted list."""
    bucket = _INTERESTED.setdefault(agent, set())
    added = path not in bucket
    bucket.add(path)
    payload = {
        "agent": agent,
        "added": added,
        "total": len(bucket),
        "files": sorted(bucket),
    }
    logger.info("[claude_coder.addInterestedFileTool] %s", payload)
    return json.dumps(payload)
