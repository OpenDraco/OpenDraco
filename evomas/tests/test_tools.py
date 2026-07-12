import subprocess
from pathlib import Path

import pytest

from evomas.mcp.server import MCPServer, ToolRegistry, get_server
from evomas.tools.lint_tools import run_flake8_impl
from evomas.tools.patch_tools import reset_repo_impl
from evomas.utils.patch import apply_patch_impl, generate_diff_impl
from evomas.tools.repo_tools import list_files_impl, read_file_impl
from evomas.tools.search_tools import search_code_impl

_GOOD_PATCH: str = (
    "diff --git a/calc.py b/calc.py\n"
    "--- a/calc.py\n"
    "+++ b/calc.py\n"
    "@@ -1,5 +1,5 @@\n"
    " def add(a, b):\n"
    "-    return a - b\n"
    "+    return a + b\n"
    " \n"
    " def multiply(a, b):\n"
    "     return a * b\n"
)


# ── tool implementations (unit) ───────────────────────────────────────────────

def test_list_files_finds_python(buggy_repo: Path) -> None:
    files = list_files_impl(str(buggy_repo), "*.py")
    assert "calc.py" in files
    assert "test_calc.py" in files


def test_read_file_with_line_numbers(buggy_repo: Path) -> None:
    content = read_file_impl(str(buggy_repo / "calc.py"), with_line_numbers=True)
    assert "1: def add(a, b):" in content
    assert "return a - b" in content


def test_search_code_ranks_relevant(buggy_repo: Path) -> None:
    results = search_code_impl("add function returns difference", str(buggy_repo))
    assert results
    assert "calc.py" in [r["path"] for r in results]


def test_run_flake8_clean(buggy_repo: Path) -> None:
    result = run_flake8_impl(str(buggy_repo / "calc.py"))
    assert "ok" in result and "output" in result


def test_apply_patch_dry_run(buggy_repo: Path) -> None:
    result = apply_patch_impl(_GOOD_PATCH, str(buggy_repo), dry_run=True)
    assert result["ok"] is True, result["output"]
    assert result["applied"] is False


def test_apply_patch_then_diff(buggy_repo: Path) -> None:
    result = apply_patch_impl(_GOOD_PATCH, str(buggy_repo), dry_run=False)
    assert result["applied"] is True, result["output"]
    diff = generate_diff_impl(str(buggy_repo))
    assert "return a + b" in diff
    assert "return a - b" in diff


def test_apply_patch_rejects_bad_hunk(buggy_repo: Path) -> None:
    # Context lines that do not exist in calc.py — git cannot fuzzy-match them.
    bad = (
        "diff --git a/calc.py b/calc.py\n"
        "--- a/calc.py\n"
        "+++ b/calc.py\n"
        "@@ -100,3 +100,3 @@\n"
        " def nonexistent_function(x, y, z):\n"
        "-    return x - y - z\n"
        "+    return x + y + z\n"
        " \n"
    )
    assert apply_patch_impl(bad, str(buggy_repo), dry_run=True)["ok"] is False


def test_reset_repo(buggy_repo: Path) -> None:
    (buggy_repo / "calc.py").write_text("garbage\n")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=buggy_repo, capture_output=True, text=True
    ).stdout.strip()
    reset_repo_impl(str(buggy_repo), base)
    assert "garbage" not in generate_diff_impl(str(buggy_repo))


# ── MCP server ────────────────────────────────────────────────────────────────

_EXPECTED_TOOLS = {"read_file", "list_files", "search_code", "run_flake8",
                   "apply_patch", "generate_diff", "reset_repo"}


def test_mcp_singleton_identity() -> None:
    assert get_server() is get_server()


def test_mcp_registry_contains_all_tools() -> None:
    server = MCPServer()
    assert _EXPECTED_TOOLS.issubset(set(server.registry.tools.keys()))


def test_mcp_tools_list_schema() -> None:
    listing = MCPServer().registry.list()
    names = {t["name"] for t in listing}
    assert _EXPECTED_TOOLS.issubset(names)
    for entry in listing:
        assert "inputSchema" in entry
        assert "description" in entry


def test_mcp_call_list_files(buggy_repo: Path) -> None:
    server = MCPServer()
    files = server.call("list_files", {"directory": str(buggy_repo), "extension": "*.py"})
    assert "calc.py" in files


def test_mcp_call_read_file(buggy_repo: Path) -> None:
    content = MCPServer().call("read_file", {"path": str(buggy_repo / "calc.py")})
    assert "def add" in content


def test_mcp_call_search_code(buggy_repo: Path) -> None:
    results = MCPServer().call("search_code", {
        "query": "add subtract difference",
        "directory": str(buggy_repo),
        "top_k": 5,
    })
    assert any(r["path"] == "calc.py" for r in results)


def test_mcp_call_apply_patch_dry_run(buggy_repo: Path) -> None:
    result = MCPServer().call("apply_patch", {
        "patch_str": _GOOD_PATCH,
        "repo_path": str(buggy_repo),
        "dry_run": True,
    })
    assert result["ok"] is True
    assert result["applied"] is False


def test_mcp_call_reset_repo(buggy_repo: Path) -> None:
    (buggy_repo / "calc.py").write_text("garbage\n")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=buggy_repo, capture_output=True, text=True
    ).stdout.strip()
    MCPServer().call("reset_repo", {"repo_path": str(buggy_repo), "base_commit": base})
    assert "garbage" not in generate_diff_impl(str(buggy_repo))


def test_mcp_call_unknown_tool_raises() -> None:
    with pytest.raises(KeyError, match="unknown tool"):
        MCPServer().call("nonexistent_tool", {})


def test_mcp_handle_tools_list() -> None:
    resp = MCPServer().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert resp["id"] == 1
    assert "tools" in resp["result"]


def test_mcp_handle_tools_call(buggy_repo: Path) -> None:
    resp = MCPServer().handle({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "list_files", "arguments": {"directory": str(buggy_repo)}},
    })
    assert "content" in resp["result"]


def test_mcp_handle_unknown_method() -> None:
    resp = MCPServer().handle({"jsonrpc": "2.0", "id": 3, "method": "bogus", "params": {}})
    assert "error" in resp
    assert resp["error"]["code"] == -32601


# ── agents use the MCP singleton ──────────────────────────────────────────────

def test_agents_share_mcp_singleton() -> None:
    # Type-level agent bases (any of them; pick three across roles) all read
    # the same MCP server instance via `get_server()`.
    from evomas.agents.types import LocatorAgent, PatcherAgent, ReviewerAgent

    server = get_server()
    assert LocatorAgent().mcp is server
    assert PatcherAgent().mcp is server
    assert ReviewerAgent().mcp is server


# ── apply_description_fix (deterministic class-1 fixer) ───────────────────────

def _setup_description_repo(tmp_path: Path) -> Path:
    """Mini repo with the canonical description-class bug shape: a class
    whose first-sentence docstring describes the desired message, but the
    `description=` argument carries a stale wording."""
    repo = tmp_path / "rule_repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "rule_l031.py").write_text(
        '"""Module-level docstring."""\n'
        '\n'
        'class Rule_L031:\n'
        '    """Avoid using table aliases in join conditions."""\n'
        '\n'
        '    def __init__(self):\n'
        '        self.description = "Avoid using aliases in join conditions"\n'
        '        self._other = None\n'
        '\n'
        '    def evaluate(self, segment):\n'
        '        return None\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@e.local"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


def test_apply_description_fix_resolves_class_one(tmp_path: Path) -> None:
    """A class-1 description bug gets detected, derived, and applied in one
    deterministic call. The file on disk reflects the docstring-derived
    replacement; the function returns ok=True with the unified diff."""
    from evomas.tools.patch_tools import apply_description_fix_impl

    repo = _setup_description_repo(tmp_path)
    issue = 'The rule L031 emits "Avoid using aliases in join conditions" but the docstring says otherwise.'

    result = apply_description_fix_impl(issue, str(repo))
    assert result["ok"] is True, result
    assert result["bug_class"] == 1
    assert result["file"].endswith("rule_l031.py")
    # The fix collapses "table aliases" → "aliases" via _FILLER_REPLACEMENTS.
    assert "aliases" in result["new_string"]
    assert result["patch"].startswith("diff --git")
    # File on disk reflects the replacement.
    content = (repo / "src" / "rule_l031.py").read_text(encoding="utf-8")
    assert result["new_string"] in content


def test_apply_description_fix_skips_non_class_one(tmp_path: Path) -> None:
    """A behaviour-class issue (no quoted-string match) returns ok=False so
    the calling agent can fall through to the general workflow."""
    from evomas.tools.patch_tools import apply_description_fix_impl

    repo = _setup_description_repo(tmp_path)
    issue = "Performance regression: the linter is too slow on large files."

    result = apply_description_fix_impl(issue, str(repo))
    assert result["ok"] is False
    assert result["bug_class"] in (2, 3)


def test_apply_description_fix_is_in_mcp_registry() -> None:
    """The tool is registered on the default MCP server."""
    assert "apply_description_fix" in MCPServer().registry.tools
