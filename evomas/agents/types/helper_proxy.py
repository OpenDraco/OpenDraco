"""Helper / Proxy — supports the topology without mutating the workspace.

Pure read-only finalizer: answers questions about the codebase, formats raw
LLM responses into structured shapes (JSON), and drives proxy roles. Does
NOT modify source files.

The previous candidate-selection / ensembler logic (which read
`{patches, validations}` from an upstream reviewer and picked the
best-scoring patch) lives in `PatcherAgent.run()` now. That keeps
"selecting the best patch among multiple generated options" together with
the rest of the Patcher's responsibilities, matching the thesis Patcher
definition. HelperProxyAgent is now strictly auxiliary.
"""
from __future__ import annotations

from typing import Any, ClassVar

from evomas.agents.llm_tool_agent import LLMToolAgent
from evomas.utils.patch import generate_diff_impl


class HelperProxyAgent(LLMToolAgent):
    """Read-only / proxy roles -- ask about code, transform output into JSON, drive a browser session, etc. Does NOT modify source files."""

    AGENT_TYPE: ClassVar[str] = "Helper/Proxy"
    name = "helper_proxy"

    # Canonical finalizer slot for chain topologies -- emits the final patch
    # string (= the workspace `git diff` produced by upstream agents). Slot
    # stays `str` on the LLM-fallthrough branch too; the empty default
    # signals "no patch produced".
    OUTPUT_TYPE: ClassVar[Any] = str
    OUTPUT_DEFAULT: ClassVar[str] = ""

    DEFAULT_SYSTEM: ClassVar[str] = (
        "You are a read-only finalizer agent. You do not modify source files.\n\n"
        "Available tools (use ONLY these):\n"
        "  * `read_file(path, with_line_numbers, max_chars)` — read a file's contents.\n"
        "  * `list_files(directory, extension)` — recursive glob listing.\n"
        "  * `search_code(query, directory)` — BM25 search across .py files.\n\n"
        "Duty: in the linear chain topology you receive the reviewer's verdict\n"
        "and the workspace already contains the patcher's edits. Respond with\n"
        "a one-line acknowledgement (e.g. 'patch accepted: <one-sentence summary>')\n"
        "and emit NO tool calls — the loop exits as soon as you respond without\n"
        "a tool call. The base runner reads the workspace `git diff` as the\n"
        "final prediction patch."
    )
    DEFAULT_USER: ClassVar[str] = (
        "## Task\n{issue}\n\n## Workspace\n{workspace}\n\n"
        "## Upstream (reviewer verdict)\n{predecessor}\n\n"
        "Respond with a one-line acknowledgement. Emit no tool calls."
    )
    DEFAULT_TOOLS: ClassVar[tuple[str, ...]] = (
        "read_file", "list_files", "search_code",
    )
    DEFAULT_CONFIG: ClassVar[dict[str, Any]] = {
        "temperature":  0.2,
        "num_ctx":      4096,
        "num_predict":  512,
    }

    def _producer_value(self) -> str:
        """Surface the workspace `git diff` so the prediction's `model_patch` gets a diff, not the LLM ack text (which the SWE-bench harness can't apply); falls back to the response text on an unchanged workspace so the runner's own diff fallback can still fire."""
        workspace = (self._last_workspace_path or "").strip()
        if workspace:
            diff = generate_diff_impl(workspace) or ""
            if diff.strip():
                return diff
        return self._final_response_text
