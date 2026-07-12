"""Bug reproduction — writes and runs tests that demonstrate the reported bug."""
from __future__ import annotations

from typing import Any, ClassVar

from evomas.agents.llm_tool_agent import LLMToolAgent


class BugReproductionAgent(LLMToolAgent):
    """Reproduce reported bugs by writing and executing minimal repros; writes `reproduction_result: dict` with at least `{reproduced: bool, trace: str}`."""

    AGENT_TYPE: ClassVar[str] = "Bug reproduction"
    name = "bug_reproduction"

    OUTPUT_TYPE: ClassVar[Any] = dict[str, Any]
    OUTPUT_DEFAULT: ClassVar[dict[str, Any]] = {}

    DEFAULT_SYSTEM: ClassVar[str] = (
        "You are a bug-reproduction agent. Given an issue and the workspace, write the "
        "smallest possible script or test that triggers the bug and run it. Confirm the "
        "failure mode matches the issue description before reporting back.\n\n"
        "Workflow:\n"
        "1. Read the issue and identify the failure (exception, wrong output, lint message, …).\n"
        "2. Use `view` / `read_file` to understand the relevant code.\n"
        "3. Use `str_replace_editor` / `edit_file` to create a tiny reproduction file under "
        "/tmp (or the workspace root). Use `execute_bash` (or `execute_ipython_cell`) to run it.\n"
        "4. Report `{reproduced: true|false, trace: <stderr|output>}` then call `finish`."
    )
    DEFAULT_USER: ClassVar[str] = (
        "## Issue\n{issue}\n\n## Workspace\n{workspace}\n\n"
        "Reproduce the bug and report the trace."
    )
    DEFAULT_TOOLS: ClassVar[tuple[str, ...]] = (
        "read_file", "list_files", "search_code",
        "apply_patch", "generate_diff",
    )
    DEFAULT_CONFIG: ClassVar[dict[str, Any]] = {
        "temperature":  0.4,
        "num_ctx":      8192,
        "num_predict":  1024,
    }
