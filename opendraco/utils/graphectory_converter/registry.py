"""Framework adapter registry — the dispatcher that stays framework-agnostic.

Each framework registers itself from its own module in ``adapters/`` (discovered
automatically), so adding or removing a framework touches only that one file and
this module is never edited per-framework. That is what lets the single-framework
branches merge without conflicts.
"""

from typing import Callable

# name -> converter(run_id, body, title) -> (state dict, wire records)
ADAPTERS: dict[str, Callable] = {}


class ConvertError(ValueError):
    """The body is not a usable run for the given framework (user-facing, 400)."""


def register(name: str, converter: Callable) -> None:
    ADAPTERS[name.strip().lower()] = converter


def run_to_session(framework: str, run_id: str, body: bytes, title: str | None = None):
    """``(state.json dict, wire.jsonl records)`` for one run of a registered framework."""
    fn = ADAPTERS.get((framework or "").strip().lower())
    if fn is None:
        known = ", ".join(sorted(ADAPTERS)) or "none"
        raise ConvertError(f"Unknown framework '{framework}'; use one of: {known}.")
    return fn(run_id, body, title)
