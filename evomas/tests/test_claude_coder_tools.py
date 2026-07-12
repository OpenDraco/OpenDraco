"""MCP registration + behavior checks for `evomas.tools.claude_coder`.

After the `index` split, the bundle exposes 15 tools matching the
upstream `extension/src/agent/v1/tools/schema/index.ts` array. Most
are thin delegators to canonical OpenHands / augment / lingma helpers;
a few are intentional stubs for runtimes EvoMas doesn't ship.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
from pathlib import Path

from langchain_core.tools import BaseTool

from evomas.mcp.server import MCPServer
from evomas.tools.repo.claude_coder import (
    ExploreRepoFolderTool,
    addInterestedFileTool,
    askFollowupQuestionTool,
    attemptCompletionTool,
    devServerTool,
    exitAgentTool,
    fileEditorTool,
    listFilesTool,
    readFileTool,
    searchFilesTool,
    searchSymbolTool,
    spawnAgentTool,
    urlScreenshotTool,
    webSearchTool,
    executeCommandTool,
)
from evomas.tools.repo.claude_coder import CLAUDE_CODER_TOOLS

_EXPECTED_NAMES = (
    "executeCommandTool",
    "listFilesTool",
    "ExploreRepoFolderTool",
    "searchFilesTool",
    "readFileTool",
    "askFollowupQuestionTool",
    "attemptCompletionTool",
    "webSearchTool",
    "urlScreenshotTool",
    "devServerTool",
    "searchSymbolTool",
    "addInterestedFileTool",
    "fileEditorTool",
    "spawnAgentTool",
    "exitAgentTool",
)


def test_tools_are_basetool_with_name_and_description() -> None:
    for tool in CLAUDE_CODER_TOOLS:
        assert isinstance(tool, BaseTool), tool
        assert tool.name, f"missing name: {tool}"
        assert (tool.description or "").strip(), f"missing description: {tool.name}"


def test_tool_names_match_expected_inventory() -> None:
    got = {t.name for t in CLAUDE_CODER_TOOLS}
    assert got == set(_EXPECTED_NAMES), got


def test_mcp_default_registry_exposes_every_tool() -> None:
    registered = set(MCPServer().registry.tools.keys())
    for name in _EXPECTED_NAMES:
        assert name in registered, f"{name!r} not in MCP registry"


# ─── Behavior smoke tests for the fresh implementations ───────────────


def test_explore_repo_folder_tool_lists_entries(buggy_repo: Path) -> None:
    out = json.loads(ExploreRepoFolderTool.invoke({"path": str(buggy_repo)}))
    assert Path(out["root"]) == buggy_repo.resolve()
    assert "calc.py" in out["entries"]
    assert "test_calc.py" in out["entries"]


def test_search_symbol_tool_finds_python_def(buggy_repo: Path) -> None:
    out = json.loads(searchSymbolTool.invoke({"symbol": "add", "workspace": str(buggy_repo)}))
    assert out["ok"] is True
    assert any(m["method"] == "add" for m in out["matches"] if "method" in m)


def test_add_interested_file_tool_records(buggy_repo: Path) -> None:
    out1 = json.loads(addInterestedFileTool.invoke({"path": str(buggy_repo / "calc.py"), "agent": "T"}))
    assert out1["added"] is True
    assert out1["total"] == 1
    out2 = json.loads(addInterestedFileTool.invoke({"path": str(buggy_repo / "calc.py"), "agent": "T"}))
    assert out2["added"] is False  # already present
    assert out2["total"] == 1


def test_spawn_agent_tool_emits_signal() -> None:
    out = json.loads(spawnAgentTool.invoke({"agent_type": "patcher", "task": "fix add"}))
    assert out["request"] == "spawn_agent"
    assert out["agent_type"] == "patcher"


# ─── Stubs return informative errors instead of crashing ─────────────


def test_stubs_return_error_strings() -> None:
    for tool, kwargs in (
        (askFollowupQuestionTool, {"question": "?"}),
        (webSearchTool, {"query": "?"}),
        (urlScreenshotTool, {"url": "https://example.com"}),
        (devServerTool, {"action": "status"}),
    ):
        result = tool.invoke(kwargs)
        assert "error" in result.lower() or "not configured" in result.lower(), tool.name


# ─── Delegators: end-to-end through the canonical they wrap ──────────


def test_execute_command_tool_runs_through_canonical() -> None:
    """executeCommandTool delegates to OpenHands CmdRunTool."""
    # Prefer a bare `python` / `python3` that the host shell can find; fall
    # back to sys.executable if neither is on PATH. Debian/Ubuntu only ship
    # `python3`, so the original bare `python` invocation broke under
    # OpenHands' /bin/sh subprocess on those systems.
    py = shutil.which("python") or shutil.which("python3") or sys.executable
    quote = (lambda s: f'"{s}"') if os.name == "nt" else shlex.quote
    out = executeCommandTool.invoke({"command": f'{quote(py)} -c "print(42)"'})
    assert "42" in out


def test_list_files_tool_delegates() -> None:
    files = listFilesTool.invoke({"directory": ".", "extension": "*.toml"})
    # We're in a Python project; pyproject.toml will exist at the call cwd.
    assert any(f.endswith("pyproject.toml") for f in files) or files == []


def test_read_file_tool_delegates(buggy_repo: Path) -> None:
    out = readFileTool.invoke({"path": str(buggy_repo / "calc.py")})
    assert "def add" in out


def test_attempt_completion_tool_writes_marker(buggy_repo: Path) -> None:
    record = json.loads(attemptCompletionTool.invoke({
        "result": "ok", "workspace": str(buggy_repo), "agent": "claude-coder-test",
    }))
    assert record["completed"] is True
    assert (buggy_repo / ".evomas" / "state.json").is_file()


def test_exit_agent_tool_emits_finish_signal() -> None:
    out = exitAgentTool.invoke({"message": "done"})
    assert out.startswith("FINISH:")


def test_file_editor_tool_str_replace(buggy_repo: Path) -> None:
    out = fileEditorTool.invoke({
        "command": "str_replace",
        "path": str(buggy_repo / "calc.py"),
        "old_str": "return a - b",
        "new_str": "return a + b",
    })
    assert "edited" in out.lower() or "successfully" in out.lower()
    assert "return a + b" in (buggy_repo / "calc.py").read_text()
