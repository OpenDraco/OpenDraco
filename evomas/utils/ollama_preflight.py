"""Pre-run pull of any Ollama models the config references but the local
Ollama server doesn't have on disk yet. Fail-fast: raises `EvomasError`
on missing binary or non-zero pull, so the user sees the issue up front
rather than as a cryptic 404 deep inside LangChain mid-run."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.request
from collections.abc import Callable
from typing import Any

from evomas.exceptions.errors import EvomasError

logger = logging.getLogger(__name__)


def ollama_base_url() -> str:
    """`OLLAMA_BASE_URL` env override, defaulting to the local daemon.
    Single source of truth — preflight + topology dropdown + pull-progress
    SSE all read through here."""
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").strip().strip("\"'")


def _list_pulled() -> set[str]:
    """Models the local Ollama server reports via `/api/tags`, in
    `ollama/<name>` form for direct comparison with config model ids.
    Returns empty set on probe error so the preflight will attempt every
    required pull (safer than skipping one)."""
    try:
        url = f"{ollama_base_url()}/api/tags"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {f"ollama/{m['name']}" for m in (data.get("models") or [])}
    except Exception as exc:
        logger.info("ollama /api/tags probe failed (%s); preflight will attempt every config model", exc)
        return set()


def pulled_ollama_models() -> list[str]:
    """Sorted list of locally-pulled Ollama model ids (`ollama/<name>`).
    Same probe as `_list_pulled`, returned as a list so the topology
    dropdown can render them deterministically."""
    return sorted(_list_pulled())


def pulled_ollama_models_with_catalog() -> list[dict[str, Any]]:
    """Pulled models first (alphabetical), then unpulled catalog entries
    in declared registry order. Drives the topology dropdown — `pulled:
    False` entries trigger an `ollama pull` preflight at run start."""
    from evomas.models.ollama_catalog import OLLAMA_CATALOG
    pulled = _list_pulled()
    out: list[dict[str, Any]] = []
    for name in sorted(pulled):
        out.append({"name": name, "pulled": True})
    seen = set(pulled)
    for name in OLLAMA_CATALOG:
        if name in seen:
            continue
        out.append({"name": name, "pulled": False})
        seen.add(name)
    return out


def collect_required_ollama_models(cfg: dict[str, Any]) -> list[str]:
    """Dedup list of `ollama/<name>` ids the config references. Bare
    names are normalized to the prefixed form since the provider router
    defaults to Ollama with no prefix. Gemini/OpenAI entries are skipped
    (their availability is checked at LLM-init time)."""
    seen: set[str] = set()
    out: list[str] = []
    for block in (cfg.get("agents") or {}).values():
        model = (block or {}).get("model") or ""
        if not isinstance(model, str) or not model.strip():
            continue
        m = model.strip()
        if m.startswith("gemini/") or m.startswith("openai/"):
            continue
        bare = m.removeprefix("ollama/")
        full = f"ollama/{bare}"
        if full in seen:
            continue
        seen.add(full)
        out.append(full)
    return out


def preflight_models(
    cfg: dict[str, Any],
    event_sink: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Ensure every Ollama model the config references is on disk, pulling
    any missing ones. Raises `EvomasError` on missing binary or non-zero pull.

    `event_sink` receives SSE-style progress dicts when set — the API
    worker passes its queue `put()` so the Inference page can render
    live pull progress; CLI passes None and falls back to logger lines."""
    required = collect_required_ollama_models(cfg)
    if not required:
        return

    pulled = _list_pulled()
    missing = [m for m in required if m not in pulled]
    if not missing:
        return

    logger.info("preflight: %d Ollama model(s) not yet pulled: %s", len(missing), missing)

    # Forward OLLAMA_HOST so `ollama pull` hits the same server agents
    # will use. Without this, if OLLAMA_BASE_URL points at a remote box
    # (e.g. a LAN GPU server) the CLI pulls into the LOCAL daemon and
    # the run still 404s after 5GB downloaded.
    env = os.environ.copy()
    base_url = ollama_base_url()
    env["OLLAMA_HOST"] = base_url

    for model in missing:
        bare = model.removeprefix("ollama/")
        if event_sink:
            event_sink({"type": "preflight_pull_start", "model": model})
        else:
            logger.info("preflight: pulling %s on %s …", bare, base_url)
        try:
            proc = subprocess.Popen(
                ["ollama", "pull", bare],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                env=env,
                # encoding+errors are essential on Windows: the default
                # cp1252 decoder dies on Ollama's UTF-8 progress glyphs
                # mid-pull (UnicodeDecodeError).
                encoding="utf-8", errors="replace",
            )
        except FileNotFoundError as exc:
            raise EvomasError(
                f"Cannot pull `{bare}`: the `ollama` binary is not on PATH. "
                f"Install Ollama from https://ollama.com and re-run, or "
                f"pre-pull the model on the host that runs the local "
                f"Ollama server."
            ) from exc

        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip()
            if event_sink:
                event_sink({"type": "preflight_log", "model": model, "line": line})
            elif line:
                logger.info("preflight[%s]: %s", bare, line)
        proc.wait()
        if event_sink:
            event_sink({"type": "preflight_pull_done", "model": model, "code": proc.returncode})

        if proc.returncode != 0:
            raise EvomasError(
                f"`ollama pull {bare}` failed with exit code {proc.returncode}. "
                f"The config requires this model but it isn't available "
                f"locally and the pull was rejected. Check the model name "
                f"against https://ollama.com/library and verify your "
                f"network connection to ollama.com."
            )
