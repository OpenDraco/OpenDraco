"""Recursive JSON-safe transformer.

Walks an arbitrary nested structure and replaces anything that
`json.dumps` would reject (datetime, sets, custom objects, …) with
`str(obj)`. Used to mirror an agent's SSE delta into an NDJSON sidecar
without exploding on a value the framework happens to ship today.

Strips the `instance` key from dicts because SWE-bench instance rows are
huge (problem statement, hints, test patch, pass-to-pass list) and the
inference frontend never displays them — they would bloat every event.
"""
from __future__ import annotations

import json
from typing import Any


def safe_serialize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: safe_serialize(v) for k, v in obj.items() if k not in ("instance",)}
    if isinstance(obj, list):
        return [safe_serialize(i) for i in obj]
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)
