"""LLM provider dispatch for the EvoMas framework.

Public surface:
  * `build_chat(config, **overrides) -> BaseChatModel` -- the single entry
    point agents call. Parses `config.model` as `<provider>/<model-id>`
    (LiteLLM-style) and forwards to the per-provider builder in this
    package.
  * `parse_provider(model_str) -> (provider, bare_model)` -- the prefix
    parser, exposed for tests / introspection.
  * `llm_invoke`, `TokenUsage` -- re-exported from
    `langchain_ollama_model` since the streaming loop + token accounting
    are provider-agnostic (every LangChain ChatModel exposes `.stream()`
    and `usage_metadata`).

Supported provider prefixes:
  * `ollama/<model>`   -- local Ollama via langchain-ollama.
  * `gemini/<model>`   -- Google Gemini via langchain-google-genai.
  * `openai/<model>`   -- OpenAI / Azure / proxy via langchain-openai.

Bare model names without a `/` (e.g. `"qwen3.5:9b"`) are treated as
`ollama/<name>` for backward compatibility with the predefined configs
shipped before multi-provider support landed.
"""
from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel

from evomas.config.loader import AgentConfig
from evomas.exceptions.errors import ConfigError
from evomas.models.langchain_ollama_model import (
    TokenUsage,
    build_chat_ollama,
    llm_invoke,
)

__all__ = ["build_chat", "parse_provider", "llm_invoke", "TokenUsage"]


def parse_provider(model: str) -> tuple[str, str]:
    """Split a `<provider>/<model-id>` string into its two halves.

    Unprefixed input (no `/`) falls back to ollama so existing JSON configs
    written before multi-provider support keep working.
    """
    if "/" not in model:
        return "ollama", model
    provider, _, bare = model.partition("/")
    return provider.strip().lower(), bare.strip()


def build_chat(config: AgentConfig, **overrides: Any) -> BaseChatModel:
    """Construct the right ChatModel for `config.model`'s provider prefix.

    A shallow copy of the config is forwarded to the provider builder with
    the bare model id (prefix removed), so per-provider modules never have
    to re-parse.
    """
    provider, bare_model = parse_provider(config.model)
    cfg = config.model_copy(update={"model": bare_model})

    if provider == "ollama":
        return build_chat_ollama(cfg, **overrides)
    if provider == "gemini":
        # Imported lazily so users without `langchain-google-genai` (or
        # without GOOGLE_API_KEY) don't pay the import cost / can still
        # run Ollama-only configs.
        from evomas.models.langchain_gemini_model import build_chat_gemini
        return build_chat_gemini(cfg, **overrides)
    if provider == "openai":
        from evomas.models.langchain_openai_model import build_chat_openai
        return build_chat_openai(cfg, **overrides)

    raise ConfigError(
        f"unknown LLM provider {provider!r} in model={config.model!r}; "
        f"supported prefixes: 'ollama/', 'gemini/', 'openai/' "
        f"(or no prefix for ollama backward-compat)"
    )
