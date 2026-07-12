"""auto_code_rover `agent_write_patch` tool.

Upstream reference: https://github.com/AutoCodeRoverSG/auto-code-rover/blob/main/app/agents/agent_write_patch.py

Lightweight shim that lets a Patcher agent write a unified-diff patch as a
single string. Delegates to `evomas.tools.patch_tools.apply_patch_impl` so
the patch is applied against the workspace immediately and the registered
behavior matches the rest of the EvoMas patch tooling.
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

from evomas.utils.patch import apply_patch_impl

logger = logging.getLogger(__name__)


@tool
def agent_write_patch(patch: str, repo_path: str = ".") -> str:
    """Write a unified-diff patch to the workspace.

    The `patch` argument must be a fully-formed unified diff (the kind
    `git diff` produces). The patch is applied with `git apply` against
    `repo_path`. Returns "ok" on success or the apply error verbatim.
    """
    if not patch or not patch.strip():
        return "Error: empty patch — produce a unified diff first."
    try:
        result = apply_patch_impl(patch_str=patch, repo_path=repo_path)
        return "ok" if result.get("ok") else f"Error: {result.get('output', 'apply failed')}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent_write_patch failed")
        return f"Error: {exc}"
