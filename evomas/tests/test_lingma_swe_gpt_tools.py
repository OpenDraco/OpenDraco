"""MCP registration + behavioral checks for `evomas.tools.lingma_swe_gpt`.

After the Lingma replacement, the bundle exposes 8 stateless search +
patch-handoff tools. This file mirrors the OpenHands-shaped checks in
`evomas/tests/test_tools.py` (every tool is a LangChain `BaseTool`,
non-empty name/description, registered with MCP) and adds light
behavior tests using a tiny ephemeral repo fixture so the
`search_class*` / `search_method*` / `search_code*` paths get
exercised end-to-end.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

from evomas.mcp.server import MCPServer
from evomas.tools.repo.lingma_swe_gpt import (
    search_class,
    search_class_in_file,
    search_method_in_file,
    search_method_in_class,
    search_method,
    search_code_in_file,
    write_patch,
)
from evomas.tools.repo.lingma_swe_gpt import LINGMA_SWE_GPT_TOOLS

# Lingma's `search_code` is the canonical EvoMas BM25 search tool —
# re-exported, NOT in LINGMA_SWE_GPT_TOOLS (would duplicate-register
# with MCP). Its behavior is covered by `test_tools.test_mcp_call_search_code`.
_EXPECTED_NAMES = (
    "search_class",
    "search_class_in_file",
    "search_method_in_file",
    "search_method_in_class",
    "search_method",
    "search_code_in_file",
    "write_patch",
)


def test_tools_are_basetool_with_name_and_description() -> None:
    """Every tool satisfies the LangChain `BaseTool` contract."""
    for tool in LINGMA_SWE_GPT_TOOLS:
        assert isinstance(tool, BaseTool), tool
        assert tool.name, f"missing name: {tool}"
        assert (tool.description or "").strip(), f"missing description: {tool.name}"


def test_tool_names_match_expected_inventory() -> None:
    """Exported names match the variant catalog at
    `evomas/config/agent_types/Lingma_SWE_GPT.json`."""
    got = {t.name for t in LINGMA_SWE_GPT_TOOLS}
    assert got == set(_EXPECTED_NAMES), got


def test_mcp_default_registry_exposes_every_tool() -> None:
    """MCP's `default_registry()` registers every tool in the bundle."""
    registered = set(MCPServer().registry.tools.keys())
    for name in _EXPECTED_NAMES:
        assert name in registered, f"{name!r} not in MCP registry"


# ─── Behavior tests on a tiny ephemeral repo ───────────────────────────


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Two-file repo with a Calculator class + a helper module."""
    (tmp_path / "calc.py").write_text(
        "class Calculator:\n"
        "    def add(self, a, b):\n"
        "        return a + b\n"
        "\n"
        "    def subtract(self, a, b):\n"
        "        return a - b\n"
        "\n"
        "\n"
        "def standalone_helper():\n"
        "    return 42\n",
        encoding="utf-8",
    )
    (tmp_path / "util.py").write_text(
        "class Logger:\n"
        "    def log(self, msg):\n"
        "        print(msg)\n",
        encoding="utf-8",
    )
    return tmp_path


def test_search_class_finds_class(sample_repo: Path) -> None:
    out = json.loads(search_class.invoke({"class_name": "Calculator", "workspace": str(sample_repo)}))
    assert out["ok"] is True
    assert "calc.py:1" in out["result"]
    assert "Calculator" in out["result"]


def test_search_class_misses_unknown(sample_repo: Path) -> None:
    out = json.loads(search_class.invoke({"class_name": "Nope", "workspace": str(sample_repo)}))
    assert out["ok"] is False


def test_search_class_in_file_scoped(sample_repo: Path) -> None:
    out = json.loads(search_class_in_file.invoke({
        "class_name": "Calculator", "file_name": "calc.py", "workspace": str(sample_repo),
    }))
    assert out["ok"] is True
    out2 = json.loads(search_class_in_file.invoke({
        "class_name": "Calculator", "file_name": "util.py", "workspace": str(sample_repo),
    }))
    assert out2["ok"] is False


def test_search_method_in_file(sample_repo: Path) -> None:
    out = json.loads(search_method_in_file.invoke({
        "method_name": "add", "file_name": "calc.py", "workspace": str(sample_repo),
    }))
    assert out["ok"] is True
    assert "Calculator.add" in out["result"]


def test_search_method_in_class(sample_repo: Path) -> None:
    out = json.loads(search_method_in_class.invoke({
        "method_name": "add", "class_name": "Calculator", "workspace": str(sample_repo),
    }))
    assert out["ok"] is True
    out2 = json.loads(search_method_in_class.invoke({
        "method_name": "log", "class_name": "Calculator", "workspace": str(sample_repo),
    }))
    # `log` is on Logger, not Calculator → not found
    assert out2["ok"] is False


def test_search_method_workspace_wide(sample_repo: Path) -> None:
    out = json.loads(search_method.invoke({
        "method_name": "standalone_helper", "workspace": str(sample_repo),
    }))
    assert out["ok"] is True
    assert "calc.py" in out["result"]


def test_search_code_in_file_finds_match(sample_repo: Path) -> None:
    out = json.loads(search_code_in_file.invoke({
        "code_str": "a + b", "file_name": "calc.py", "workspace": str(sample_repo),
    }))
    assert out["ok"] is True
    assert "calc.py:" in out["result"]


def test_search_code_in_file_missing_file(sample_repo: Path) -> None:
    out = json.loads(search_code_in_file.invoke({
        "code_str": "anything", "file_name": "nope.py", "workspace": str(sample_repo),
    }))
    assert out["ok"] is False


def test_write_patch_emits_handoff(sample_repo: Path) -> None:
    out = json.loads(write_patch.invoke({
        "context_summary": "fix the bug in calc.py", "workspace": str(sample_repo),
    }))
    assert out["ok"] is True
    envelope = json.loads(out["result"])
    assert envelope["request"] == "write_patch"
    assert envelope["workspace"] == str(sample_repo)
    assert envelope["context_summary"] == "fix the bug in calc.py"
