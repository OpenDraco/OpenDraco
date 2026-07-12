"""Remote-provider model catalog probes.

Lives next to the per-provider LangChain builders so the topology page
(via the API router) and any future CLI / notebook helper share the
same view of "what models can the user pick". Cached for 5 minutes
because Google + OpenAI both rate-limit `models.list`.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from collections.abc import Callable


_REMOTE_MODELS_TTL_S = 300
_remote_models_cache: dict[str, tuple[float, list[str]]] = {}


def cached_remote(provider: str, fetch: Callable[[], list[str]]) -> list[str]:
    """TTL-cache `fetch()` per provider so the Topology page reload
    doesn't pay a round-trip per click. Exception in `fetch` is swallowed
    to an empty list AND cached — better an empty dropdown for 5min than
    repeated stalls on a flaky network."""
    now = time.time()
    hit = _remote_models_cache.get(provider)
    if hit and (now - hit[0]) < _REMOTE_MODELS_TTL_S:
        return hit[1]
    try:
        models = fetch()
    except Exception:  # noqa: BLE001
        models = []
    _remote_models_cache[provider] = (now, models)
    return models


def gemini_models() -> list[str]:
    """Live `generateContent`-capable Gemini models, minus non-chat shapes
    (TTS / image / lyria / robotics / deep-research / etc)."""
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not key:
        return []
    def fetch() -> list[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        bad = ("-tts", "-image", "lyria", "robotics", "deep-research", "computer-use", "nano-banana", "gemma")
        out: list[str] = []
        for m in data.get("models", []):
            name = m.get("name", "")
            if "generateContent" not in (m.get("supportedGenerationMethods") or []):
                continue
            bare = name.split("/", 1)[1] if name.startswith("models/") else name
            if any(b in bare for b in bad):
                continue
            out.append(f"gemini/{bare}")
        return sorted(out)
    return cached_remote("gemini", fetch)


def openai_models() -> list[str]:
    """Chat-capable OpenAI models from `/v1/models`, filtered by name
    pattern since the response doesn't carry a `chat` flag.

    Honors `OPENAI_BASE_URL` so the same listing works against
    OpenAI-compatible proxies (Together, Groq, etc)."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return []
    def fetch() -> list[str]:
        base = (os.environ.get("OPENAI_BASE_URL", "").strip() or "https://api.openai.com/v1").rstrip("/")
        req = urllib.request.Request(f"{base}/models", headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        good_prefix = ("gpt-", "o1", "o3", "o4", "chatgpt-")
        bad = ("-tts", "-realtime", "-audio", "whisper", "-embedding", "dall-e", "tts-", "babbage", "davinci", "moderation", "-image")
        out: list[str] = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            if not mid.startswith(good_prefix):
                continue
            if any(b in mid for b in bad):
                continue
            out.append(f"openai/{mid}")
        return sorted(out)
    return cached_remote("openai", fetch)
