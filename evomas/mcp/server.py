import importlib
import inspect
import logging
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.tools import BaseTool

from evomas.tools.repo.augment_swebench_agent import AUGMENT_SWEBENCH_AGENT_TOOLS
from evomas.tools.repo.auto_code_rover import AUTO_CODE_ROVER_TOOLS
from evomas.tools.repo.claude_coder import CLAUDE_CODER_TOOLS
from evomas.tools.repo.composio import COMPOSIO_TOOLS
from evomas.tools.repo.debug_gym import DEBUG_GYM_TOOLS
from evomas.tools.repo.joycode_agent import JOYCODE_AGENT_TOOLS
from evomas.tools.repo.lingma_swe_gpt import LINGMA_SWE_GPT_TOOLS
from evomas.tools.repo.openhands import LOC_TOOLS, OPENHANDS_TOOLS
from evomas.tools.repo.patchwork import PATCHWORK_TOOLS
from evomas.tools.repo.suna import SUNA_TOOLS
from evomas.tools.repo.swe_agent import SWE_AGENT_TOOLS
from evomas.tools.repo.trae_agent import TRAE_AGENT_TOOLS

logger = logging.getLogger(__name__)


def _discover_tools() -> list[BaseTool]:
    """One walker for every tool the framework can use. Recursively
    visits `evomas/tools/`:

    - `.py` modules contribute their module-level `BaseTool` attributes
      (`@tool`-decorated functions). Covers `lint_tools.py`,
      `patch_tools.py`, `repo_tools.py`, `search_tools.py`,
      `test_runner.py`, ...
    - Packages contribute their `*_TOOLS` lists/tuples (and any
      `BaseTool` attributes they re-export). Covers task bundles
      (`translate/`, `websearch/`, ...) AND repo-variant bundles
      one level deeper under `repo/<bundle>/` (openhands, swe_agent,
      patchwork, ...).

    At each directory level, `.py` modules are scanned before
    subpackages so `evomas/tools/<x>.py` registers first; bundles
    register later and can overwrite by name (last-registered-wins),
    which matches the original two-step behaviour.

    Drop a new `.py` or bundle folder anywhere under `evomas/tools/`
    and it lights up on the next process start — no edits here."""
    import evomas.tools as tools_pkg

    out: list[BaseTool] = []
    seen: set[int] = set()

    def _emit(val: Any) -> None:
        if isinstance(val, BaseTool) and id(val) not in seen:
            seen.add(id(val))
            out.append(val)

    def _scan(parent: str, paths: list[str]) -> None:
        # Sort: modules (ispkg=False) before packages so top-level
        # core tools register before any same-named bundle entry.
        entries: list[tuple[str, bool]] = [
            (name, ispkg)
            for _finder, name, ispkg in pkgutil.iter_modules(paths)
            if not name.startswith("_")
        ]
        entries.sort(key=lambda kv: (kv[1], kv[0]))
        for name, ispkg in entries:
            full = f"{parent}.{name}"
            try:
                mod = importlib.import_module(full)
            except Exception as exc:  # noqa: BLE001
                logger.warning("tool module %s failed to import: %s", full, exc)
                continue
            for attr in sorted(dir(mod)):
                if attr.startswith("_"):
                    continue
                val = getattr(mod, attr, None)
                if attr.endswith("_TOOLS") and isinstance(val, (list, tuple)):
                    for t in val:
                        _emit(t)
                else:
                    _emit(val)
            if ispkg:
                _scan(full, list(mod.__path__))

    _scan("evomas.tools", list(tools_pkg.__path__))
    return out


@dataclass
class ToolDescriptor:
    name: str
    description: str
    schema: dict[str, Any]
    invoke: Callable[[dict[str, Any]], Any]
    # Original BaseTool kept alongside the invoke closure so consumers
    # that need to bind tools to a LangChain model (LLMToolAgent) don't
    # have to re-import every bundle by hand. None when a descriptor
    # was constructed directly without a backing BaseTool (legacy code).
    tool: BaseTool | None = None


@dataclass
class ToolRegistry:
    tools: dict[str, ToolDescriptor] = field(default_factory=dict)

    def register(self, tool: BaseTool) -> None:
        descriptor = _descriptor_from_tool(tool)
        self.tools[descriptor.name] = descriptor

    def unregister(self, name: str) -> None:
        """Remove a tool by name; no-op when not registered."""
        self.tools.pop(name, None)

    def list(self) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "inputSchema": t.schema}
            for t in self.tools.values()
        ]

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in self.tools:
            raise KeyError(f"unknown tool: {name}")
        logger.info("mcp.call %s args=%s", name, arguments)
        return self.tools[name].invoke(arguments or {})


def _descriptor_from_tool(tool: BaseTool) -> ToolDescriptor:
    name: str = tool.name
    description: str = (tool.description or "").strip()
    schema = _extract_schema(tool)

    def invoke(arguments: dict[str, Any]) -> Any:
        return tool.invoke(arguments)

    return ToolDescriptor(name=name, description=description, schema=schema, invoke=invoke, tool=tool)


def _extract_schema(tool: BaseTool) -> dict[str, Any]:
    try:
        args_schema = getattr(tool, "args_schema", None)
        if args_schema is not None and hasattr(args_schema, "model_json_schema"):
            return args_schema.model_json_schema()
    except Exception as exc:
        logger.debug("could not extract pydantic schema for %s: %s", tool.name, exc)
    sig = inspect.signature(getattr(tool, "func", tool))  # pyright: ignore[reportArgumentType]
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param in sig.parameters.values():
        if param.name in {"self", "cls"}:
            continue
        properties[param.name] = {"type": "string"}
        if param.default is inspect.Parameter.empty:
            required.append(param.name)
    return {"type": "object", "properties": properties, "required": required}


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    # Every tool reachable under `evomas/tools/` — top-level @tool fns
    # AND bundle `*_TOOLS` lists, repo-variant ones recursed too. One
    # walk, no manual imports.
    for tool in _discover_tools():
        registry.register(tool)
    return registry


class MCPServer:
    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry: ToolRegistry = registry or default_registry()

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        return self.registry.call(name, arguments)

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        method = message.get("method")
        params: dict[str, Any] = message.get("params") or {}
        msg_id = message.get("id")
        try:
            if method == "tools/list":
                return self._ok(msg_id, {"tools": self.registry.list()})
            if method == "tools/call":
                name = params.get("name") or ""
                arguments = params.get("arguments") or {}
                result = self.registry.call(name, arguments)
                return self._ok(msg_id, {"content": result})
            return self._error(msg_id, -32601, f"method not found: {method}")
        except KeyError as exc:
            return self._error(msg_id, -32602, str(exc))
        except Exception as exc:
            logger.exception("mcp server error: %s", exc)
            return self._error(msg_id, -32000, str(exc))

    @staticmethod
    def _ok(msg_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    @staticmethod
    def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        }


_server: MCPServer | None = None


def get_server() -> MCPServer:
    global _server
    if _server is None:
        _server = MCPServer()
    return _server


_TOOL_REPO_OWNER_CACHE: dict[str, str] | None = None


def tool_repo_owner_map() -> dict[str, str]:
    """`tool_name -> owner` map. The owner is the `evomas/tools/<repo>/`
    folder the tool was registered from, or `"evomas"` for the top-level
    `evomas/tools/*.py` helpers (apply_patch, read_file, search_code, …).

    Cached at module level so repeated calls don't re-walk the bundles.
    Used by the topology page's `/api/tools` endpoint to group the
    Add-tool dropdown by owner; could just as well be used by a CLI
    `evomas tools list --owner X` in the future.
    """
    global _TOOL_REPO_OWNER_CACHE
    if _TOOL_REPO_OWNER_CACHE is not None:
        return _TOOL_REPO_OWNER_CACHE
    bundles: list[tuple[str, Any]] = [
        ("augment_swebench_agent", AUGMENT_SWEBENCH_AGENT_TOOLS),
        ("auto_code_rover",        AUTO_CODE_ROVER_TOOLS),
        ("claude_coder",           CLAUDE_CODER_TOOLS),
        ("composio",               COMPOSIO_TOOLS),
        ("debug_gym",              DEBUG_GYM_TOOLS),
        ("joycode_agent",          JOYCODE_AGENT_TOOLS),
        ("lingma_swe_gpt",         LINGMA_SWE_GPT_TOOLS),
        # OpenHands ships two bundles under one folder; share the owner.
        ("openhands",              OPENHANDS_TOOLS),
        ("openhands",              LOC_TOOLS),
        ("patchwork",              PATCHWORK_TOOLS),
        ("suna",                   SUNA_TOOLS),
        ("swe_agent",              SWE_AGENT_TOOLS),
        ("trae_agent",             TRAE_AGENT_TOOLS),
    ]
    out: dict[str, str] = {}
    for owner, bundle in bundles:
        for tool in bundle:
            name = getattr(tool, "name", None)
            if not name:
                continue
            # First-seen owner wins (handles cross-bundle re-exports).
            out.setdefault(name, owner)
    _TOOL_REPO_OWNER_CACHE = out
    return out
