"""OpenHands `IPythonTool` — execute a Python snippet.

The upstream tool runs against a long-lived IPython kernel with
variable persistence; EvoMas uses a fresh `python -c` subprocess per
call, so variables defined in one invocation do not survive to the
next. Output is captured (stdout + stderr) and length-capped.
"""
from __future__ import annotations

import subprocess

from langchain_core.tools import tool

from evomas.tools.repo.openhands._helpers import _truncate


@tool
def IPythonTool(code: str) -> str:
    """Run a Python snippet in a fresh subprocess. Returns captured
    stdout + stderr (truncated to the shared output cap). Variables
    do NOT persist between calls in this implementation. Times out
    after 60 seconds."""
    try:
        proc = subprocess.run(
            ["python", "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return "Error: cell timed out after 60s."
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    return _truncate(out.strip() or "(no output)")
