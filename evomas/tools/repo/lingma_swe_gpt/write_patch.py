"""lingma_swe_gpt `write_patch` — request a patch from the patcher agent.

The upstream Lingma `ProjectApiManager.write_patch` method invokes
another agent over a `MessageThread`. EvoMas tools don't directly call
other agents — the orchestrator is the one that routes between agents
via topology edges. So this tool is a structured *signal*: it bundles
the current context summary and emits a JSON payload the orchestrator
(or a downstream Patcher node) can pick up.
"""
from __future__ import annotations

import json

from langchain_core.tools import tool


@tool
def write_patch(context_summary: str, workspace: str) -> str:
    """Hand off to a patcher agent: package the current planning
    context and signal that a patch should be written next.

    Args:
        context_summary: a short natural-language summary of the
            relevant files, classes, and intent. The orchestrator (or
            the next agent in the topology) consumes this as the brief
            for patch generation.
        workspace: absolute path to the repo root (passed through so
            the patcher knows which tree to modify).

    Returns a JSON `{"result", "summary", "ok"}` payload. The `result`
    is the handoff envelope; `ok` is always True (the signal itself
    can't fail — failure is observable downstream when the patcher
    runs).
    """
    envelope = {
        "request": "write_patch",
        "workspace": workspace,
        "context_summary": context_summary,
    }
    return json.dumps({
        "result": json.dumps(envelope, ensure_ascii=False),
        "summary": "write_patch handoff prepared",
        "ok": True,
    })
