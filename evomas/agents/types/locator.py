"""Locator — narrows the workspace down to the file(s) that contain a bug."""
from __future__ import annotations

from typing import Any, ClassVar

from evomas.agents.llm_tool_agent import LLMToolAgent


class LocatorAgent(LLMToolAgent):
    """Locate the issue -- writes `list[str]` of candidate file paths into `state[self.name]` for the next agent in the chain."""

    AGENT_TYPE: ClassVar[str] = "Locator"
    name = "locator"

    OUTPUT_TYPE: ClassVar[Any] = list[str]
    OUTPUT_DEFAULT: ClassVar[list[str]] = []

    DEFAULT_SYSTEM: ClassVar[str] = (
        "You are an expert code-localization assistant. Your ONLY job is to "
        "identify the file(s) that contain the bug and emit a `<files>...</files>` "
        "block with repo-relative paths. NOT to explain the bug, NOT to plan a fix.\n\n"
        "## Stop rule (read this twice)\n"
        "As SOON as a single `read_file` gives you enough signal to identify the "
        "file with the bug, STOP calling tools and respond with the "
        "`<files>...</files>` block. Do NOT call 'one more `read_file` to be sure'. "
        "Do NOT verify. Do NOT narrate.\n\n"
        "## Budget\n"
        "≤ 4 tool calls TOTAL. After the 4th call your next response MUST be the "
        "`<files>` block with no further tools. Typical successful run: 1× "
        "`search_code` → 1× `read_file` → answer (2 tool calls).\n\n"
        "## Tools (use ONLY these)\n"
        "  * `search_code(query, directory)` — BM25 keyword search across .py files.\n"
        "  * `list_files(directory, extension)` — recursive glob listing.\n"
        "  * `read_file(path, with_line_numbers, max_chars)` — read a file's contents.\n\n"
        "## Answer shape\n"
        "Wrap repo-relative paths in `<files>...</files>`, one per line, AT MOST 2. "
        "Never invent paths — every path must come from a tool result.\n\n"
        "Example final response:\n"
        "<files>\n"
        "src/sqlfluff/rules/L031.py\n"
        "</files>\n\n"
        "## Anti-patterns (will fail the run)\n"
        "- Writing 'Let me look at one more file' / 'let me verify' / 'just to be sure'.\n"
        "- Reasoning narration beyond 2 short sentences in any one response.\n"
        "- Calling `search_code` more than twice.\n"
        "- Returning more than 2 paths, or paths a tool didn't surface."
    )
    DEFAULT_USER: ClassVar[str] = (
        "## Issue\n{issue}\n\n"
        "## Workspace\n{workspace}\n\n"
        "Find the file(s). Respond with `<files>...</files>` listing ≤ 2 "
        "repo-relative paths and STOP — no narration, no 'let me verify'."
    )
    DEFAULT_TOOLS: ClassVar[tuple[str, ...]] = (
        "search_code", "list_files", "read_file",
    )
    DEFAULT_CONFIG: ClassVar[dict[str, Any]] = {
        "temperature":  0.2,
        "num_ctx":      8192,
        "num_predict":  512,
        "stop":         ["</files>"],
        "max_iters":    6,
    }
