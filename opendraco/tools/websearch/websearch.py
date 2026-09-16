"""`websearch` — DuckDuckGo text search exposed as a LangChain tool.

Lets an agent answer a free-form question by pulling fresh hits from
the open web. The agent gets `title / url / snippet` triplets back and
can cite or summarise them. The tool is intentionally cheap (no JS
rendering, no full-page fetch) — for tasks that need page contents,
the agent should follow up with a separate fetch tool.

Sandboxing note: unlike `read_file` / `write_file`, this tool has no
workspace concept — searches are stateless and don't touch disk.
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import tool


@tool
def websearch(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search the web via DuckDuckGo. Returns up to `max_results` hits,
    each as `{title, url, snippet}`. Use this when you need current
    information the model can't recall from training (recent releases,
    news, niche facts, library docs)."""
    try:
        from ddgs import DDGS  # pyright: ignore[reportMissingImports]
    except ImportError:
        return {
            "ok": False,
            "error": "ddgs not installed; `pip install ddgs` to enable websearch.",
            "results": [],
        }

    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query", "results": []}

    n = max(1, min(int(max_results or 5), 20))
    try:
        raw = list(DDGS().text(q, max_results=n))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"search failed: {exc}", "results": []}

    results = [
        {
            "title": (r.get("title") or "").strip(),
            "url": (r.get("href") or r.get("url") or "").strip(),
            "snippet": (r.get("body") or r.get("snippet") or "").strip(),
        }
        for r in raw
    ]
    return {"ok": True, "query": q, "results": results}
