import json
import re
from pathlib import Path
from typing import Any, Literal, Union

from pydantic import BaseModel, Field

from evomas.exceptions.errors import ConfigError

_THIS_DIR: Path = Path(__file__).resolve().parent
PREDEFINED_DIR: Path = _THIS_DIR / "predefined"
LOADED_DIR: Path = _THIS_DIR / "loaded"
AGENT_TYPES_DIR: Path = _THIS_DIR / "agent_types"

ThinkLevel = Union[bool, Literal["low", "medium", "high"]]


class AgentConfig(BaseModel):
    """Per-agent model knobs extracted from the unified config block."""

    model: str = "qwen3.5:9b"
    think: ThinkLevel = True
    num_ctx: int = 4096
    stream: bool = True
    temperature: float = 0.2
    top_k: int = 40
    top_p: float = 0.9
    min_p: float = 0.0
    repeat_penalty: float = 1.1
    repeat_last_n: int = 64
    seed: int = 0
    num_predict: int = -1
    stop: list[str] = Field(default_factory=list)


AGENT_CONFIG_KEYS: frozenset[str] = frozenset(AgentConfig.model_fields.keys())


def _resolve_path(name_or_path: str) -> Path:
    p = Path(name_or_path)
    if p.is_file():
        return p
    # predefined/ → loaded/ → legacy flat root.
    for base in (PREDEFINED_DIR, LOADED_DIR, _THIS_DIR):
        candidate = base / f"{name_or_path}.json"
        if candidate.is_file():
            return candidate
    raise ConfigError(f"config not found: {name_or_path}")


def load_config(name_or_path: str) -> dict[str, Any]:
    """Load a unified config JSON. Accepts a name (e.g. 'star') or an absolute/relative file path."""
    path = _resolve_path(name_or_path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"failed to parse {path}: {exc}") from exc


def agent_config_from_block(block: dict[str, Any]) -> AgentConfig:
    """Project a unified-config agent block down to the model knobs Pydantic schema."""
    return AgentConfig(**{k: v for k, v in block.items() if k in AGENT_CONFIG_KEYS})


# ─── Variant resolution ─────────────────────────────────────────────────────
# `variant: "<RepoId>:<AgentName>"` pulls prompts/tools from
# `agent_types/<RepoId>.json`. Inline values on the block always win;
# the catalog only fills in what's missing.
_JINJA_INCLUDE_RE: re.Pattern[str] = re.compile(
    r"<\s*\w+\s*>\s*\{%[^%]+%\}\s*<\s*/\s*\w+\s*>",
)


def _strip_jinja_includes(text: str) -> str:
    """Drop XML-wrapped Jinja `{% include %}` blocks from catalog prompts —
    EvoMas has no Jinja preprocessor so they'd otherwise reach the LLM verbatim."""
    if not isinstance(text, str):
        return text
    return _JINJA_INCLUDE_RE.sub("", text)


def _load_variant_catalog(repo_id: str) -> dict[str, Any] | None:
    """Read `agent_types/<repo_id>.json` or return None on miss."""
    path = AGENT_TYPES_DIR / f"{repo_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def resolve_variant_block(block: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `block` with `prompts`/`tools` filled from the variant
    catalog when missing. Inline values win; an empty inline value like
    `"tools": []` is honored as an explicit opt-out."""
    variant = block.get("variant")
    if not variant or ":" not in str(variant):
        return block
    repo_id, agent_name = str(variant).split(":", 1)
    catalog = _load_variant_catalog(repo_id)
    if catalog is None:
        return block
    target = next(
        (a for a in (catalog.get("agents") or []) if a.get("name") == agent_name),
        None,
    )
    if target is None:
        return block

    resolved: dict[str, Any] = dict(block)
    if "prompts" not in resolved:
        cat_prompts = target.get("prompts") or {}
        cleaned = {
            k: _strip_jinja_includes(v) if isinstance(v, str) else v
            for k, v in cat_prompts.items()
        }
        if any(cleaned.values()):
            resolved["prompts"] = cleaned
    if "tools" not in resolved:
        cat_tools = target.get("tools") or []
        if cat_tools:
            # Catalog entries are `{name, source_url}`; the block needs `{name, params}`.
            resolved["tools"] = [
                {"name": str(t["name"]), "params": {}}
                for t in cat_tools if t.get("name")
            ]
    return resolved


# ─── Topology-page config listing / validation ──────────────────────────────
# Helpers used by the api topology router to list configs from both roots
# and validate user-uploaded ones. Decoupled from FastAPI — raises
# `ConfigError` on validation failure; the api wraps as HTTP 400.

def scan_config_dir(base: Path, source: str) -> list[dict[str, str]]:
    """`[{stem, id, description, source}, …]` for every `*.json` under `base`.
    `source` is the label written into the `source` field on each entry
    ("predefined" or "loaded"). Malformed JSON files still produce an
    entry with empty `id`/`description` so the UI can surface them as
    broken rather than silently disappearing."""
    out: list[dict[str, str]] = []
    if not base.is_dir():
        return out
    for p in sorted(base.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        out.append({
            "stem": p.stem,
            "id": str(data.get("id") or p.stem),
            "description": str(data.get("description") or ""),
            "source": source,
        })
    return out


def resolve_config_path(
    name: str, *, predefined_dir: Path, loaded_dir: Path,
) -> Path | None:
    """On-disk path of a config by stem — `predefined_dir` first, then `loaded_dir`."""
    for base in (predefined_dir, loaded_dir):
        p = base / f"{name}.json"
        if p.is_file():
            return p
    return None


def validate_loaded_config(data: dict[str, Any], expected_stem: str) -> None:
    """Permissive load gate -- the file just has to be a JSON object.

    Raises `ConfigError` (caller translates to HTTP 400) only on the
    truly unsalvageable shape: not a dict.
    """
    del expected_stem  # retained for API stability; no longer enforced
    if not isinstance(data, dict):
        raise ConfigError("config must be a JSON object")
