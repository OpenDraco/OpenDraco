"""Curated catalog of Ollama models available on the public registry.

Why a hardcoded list? Ollama's CLI doesn't expose the full registry catalog
on older versions (no `ollama search`), and the public registry at
`https://ollama.com/library/` has no public REST endpoint. A hand-curated
snapshot keeps the model picker working offline and gives the topology
page a stable list to render without making the user remember exact
model+tag combinations.

Update this list when new popular models land. Each entry is the
`<name>:<tag>` form that `ollama pull` accepts directly, prefixed with
`ollama/` so the AgentConfig provider router can dispatch to the right
backend (matches the shape `_ollama_models()` returns from
`/api/tags`).
"""
from __future__ import annotations

# Ordered roughly by popularity / general-purpose suitability. The
# Topology page renders them in this order so the most-likely pick lands
# near the top of the dropdown.
OLLAMA_CATALOG: tuple[str, ...] = (
    # ─── General-purpose chat ───────────────────────────────────────
    "ollama/qwen3:8b",
    "ollama/qwen3:14b",
    "ollama/qwen3:32b",
    "ollama/qwen3.5:9b",
    "ollama/llama3.3:70b",
    "ollama/llama3.2:1b",
    "ollama/llama3.2:3b",
    "ollama/llama3.1:8b",
    "ollama/llama3.1:70b",
    "ollama/llama3:8b",
    "ollama/llama3:70b",
    "ollama/gemma3:1b",
    "ollama/gemma3:4b",
    "ollama/gemma3:12b",
    "ollama/gemma3:27b",
    "ollama/mistral:7b",
    "ollama/mistral-nemo:12b",
    "ollama/mixtral:8x7b",
    "ollama/mixtral:8x22b",
    "ollama/phi3:3.8b",
    "ollama/phi3:14b",
    "ollama/phi4:14b",
    # ─── Code-specialised ───────────────────────────────────────────
    "ollama/codellama:7b",
    "ollama/codellama:13b",
    "ollama/codellama:34b",
    "ollama/codellama:70b",
    "ollama/deepseek-coder:6.7b",
    "ollama/deepseek-coder-v2:16b",
    "ollama/qwen2.5-coder:7b",
    "ollama/qwen2.5-coder:14b",
    "ollama/qwen2.5-coder:32b",
    # ─── Reasoning / long-context ───────────────────────────────────
    "ollama/deepseek-r1:7b",
    "ollama/deepseek-r1:14b",
    "ollama/deepseek-r1:70b",
    "ollama/gpt-oss:20b",
    "ollama/gpt-oss:120b",
    # ─── Vision ─────────────────────────────────────────────────────
    "ollama/llava:7b",
    "ollama/llava:13b",
    "ollama/llava:34b",
    "ollama/llama3.2-vision:11b",
)
