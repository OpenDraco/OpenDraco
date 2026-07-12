"""Generate / update `experiments/EXPERIMENT.md` with a section per run.

Usage:
    python experiments/generate_report.py                  # update all runs
    python experiments/generate_report.py <run-dir-name>   # one run

A run is identified by a folder under `experiments/` containing
`predictions/prediction-*.jsonl` + `evaluations/*.json`. The script
walks the matched NDJSON event streams in `evomas/logs/inference_logs/`
and the text logs in `<run-dir>/predictions/logs/` to extract per-agent
durations, tool-call counts, and token usage (parsed from the
`tokens in=X out=Y total=Z` lines the API emits per-LLM-call).

The output replaces a `<!-- BEGIN run-name -->…<!-- END run-name -->`
block in `EXPERIMENT.md`. Sections for unknown runs are inserted in
mtime order. Sections for runs that no longer exist on disk are left
untouched (delete by hand if you want them gone).
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

EXPERIMENTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXPERIMENTS_DIR.parent
INFERENCE_LOGS = REPO_ROOT / "evomas" / "logs" / "inference_logs"
DOC_PATH = EXPERIMENTS_DIR / "EXPERIMENT.md"

# `[planner] tokens in=2048 out=579 total=2627` — per-LLM-call line.
# `[<instance>] tokens in=… out=… total=… (per-agent: {…})` — per-cell totals.
_TOK_LINE_RE = re.compile(
    r"\[(?P<who>[^\]]+)\]\s+tokens\s+in=(?P<in>\d+)\s+out=(?P<out>\d+)\s+total=(?P<total>\d+)"
)
_PER_AGENT_RE = re.compile(r"per-agent:\s*(\{.*\})")

# Text-log timestamp prefix the Python `logging` default + the notebook's
# basicConfig both emit: `2026-06-01 21:38:22,006 [INFO] ...`. The comma
# separator is for milliseconds — we capture the leading `Y-M-D H:M:S`
# (millisecond precision isn't worth carrying for our per-cell totals).
_LOG_TS_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})")
# `evomas.core.workflow.graph_builder: [locator] -> [patcher] payload=…`
_LOG_HANDOFF_RE = re.compile(
    r"graph_builder:\s*\[(?P<from>[^\]]+)\]\s*->\s*\[(?P<to>[^\]]+)\]"
)
# `evomas.agents.locator: [locator] tool search_code args=…` — the
# canonical tool-call entry point. `evomas.mcp.server: mcp.call …` is
# the duplicate so we skip it to keep counts comparable to NDJSON.
_LOG_TOOL_RE = re.compile(
    r"evomas\.agents\.\S+:\s*\[[^\]]+\]\s+tool\s+(?P<tool>\S+)"
)
# Runner emits `=== running <iid> with …` at cell entry and
# `=== <iid> done: <N>-char patch | tokens in=… ===` at cell exit.
# The pair gives a tighter wall-clock than first→last handoff: it
# covers locator setup before the first handoff AND finalizer wrap-up
# AFTER the last handoff, both of which are real run-time.
_LOG_INSTANCE_RE = re.compile(r"===\s+running\s+(?P<iid>\S+)\s+with")
_LOG_DONE_RE = re.compile(r"===\s+(?P<iid>\S+)\s+done:")
# Notebook-path cell totals live on the `=== <iid> done:` line itself
# (e.g. `done: 1087-char patch | tokens in=6365 out=282 total=6647 ===`).
# Matrix path uses a separate per-agent rollup line, handled above.
_LOG_DONE_TOKENS_RE = re.compile(
    r"done:.*?tokens\s+in=(?P<in>\d+)\s+out=(?P<out>\d+)\s+total=(?P<total>\d+)"
)


def _parse_ts(s: str) -> float | None:
    try:
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        return None


def _safe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _scan_text_log(p: Path) -> dict[str, Any]:
    """Pull per-call and per-cell token rows out of a `<run-id>.log`,
    PLUS the same handoff / tool_call / instance_id signal the API-side
    NDJSON sidecar carries — the notebook path doesn't write NDJSON
    so we have to recover it from the text log instead.

    Per-call tokens: every `[<agent>] tokens in=…` line that ISN'T also
                     a per-cell total (per-cell carries `per-agent: {…}`).
    Per-cell tokens: the final `[<instance>] tokens …` with per-agent dict.
    Handoffs: `graph_builder: [<from>] -> [<to>]` with leading timestamp.
    Tool calls: `evomas.agents.X: [X] tool <name>` (skips mcp.server
                duplicates).
    Instance id: `=== running <iid> with …` from the runner.
    """
    per_call: dict[str, list[dict[str, int]]] = defaultdict(list)
    per_cell_total: dict[str, int] = {}
    per_cell_in_out: dict[str, tuple[int, int]] = {}
    per_cell_per_agent: dict[str, dict[str, int]] = {}
    # Fallback per-instance accumulator: sum per-call tokens between
    # `=== running <iid>` and `=== <iid> done:` markers. Used only when
    # the runner didn't emit a done-line with rollup tokens (e.g. cell
    # crashed mid-execution, OOM, container killed).
    per_cell_calls: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
    current_iid: str | None = None
    handoffs: list[tuple[str, str, float]] = []
    tool_calls = 0
    instance_id: str | None = None
    cell_start_ts: float | None = None
    cell_done_ts: float | None = None
    # Every line's timestamp; we walk these to compute *active* time
    # by summing consecutive-gap intervals that look like real work
    # (cap at IDLE_GAP_S). Larger gaps = system sleep / kernel paused.
    line_timestamps: list[float] = []
    IDLE_GAP_S = 5 * 60  # 5 min: longest plausible single LLM call on slow models
    empty = {
        "per_call": per_call, "per_cell": per_cell_total,
        "per_cell_in_out": per_cell_in_out,
        "per_agent": per_cell_per_agent,
        "handoffs": handoffs, "tool_calls": tool_calls,
        "instance_id": instance_id,
        "cell_start_ts": cell_start_ts, "cell_done_ts": cell_done_ts,
        "active_dur_s": 0.0,
    }
    if not p.exists():
        return empty
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        tsm = _LOG_TS_RE.match(line)
        if tsm:
            line_timestamps.append(
                datetime.strptime(tsm.group("ts"), "%Y-%m-%d %H:%M:%S").timestamp()
            )
        m = _TOK_LINE_RE.search(line)
        if m:
            who = m.group("who")
            tokens = {"input": int(m.group("in")), "output": int(m.group("out")), "total": int(m.group("total"))}
            agent_match = _PER_AGENT_RE.search(line)
            if agent_match:
                per_cell_total[who] = tokens["total"]
                per_cell_in_out[who] = (tokens["input"], tokens["output"])
                agent_blob = agent_match.group(1).replace("'", '"')
                parsed = _safe_json(agent_blob)
                if isinstance(parsed, dict):
                    per_cell_per_agent[who] = {
                        k: int(v.get("total", 0)) if isinstance(v, dict) else 0
                        for k, v in parsed.items()
                    }
            else:
                per_call[who].append(tokens)
                if current_iid is not None:
                    pi, po = per_cell_calls[current_iid]
                    per_cell_calls[current_iid] = (pi + tokens["input"], po + tokens["output"])
            continue
        ho = _LOG_HANDOFF_RE.search(line)
        if ho:
            tsm = _LOG_TS_RE.match(line)
            ts: float = 0.0
            if tsm:
                parsed_ts = datetime.strptime(tsm.group("ts"), "%Y-%m-%d %H:%M:%S").timestamp()
                ts = parsed_ts
            handoffs.append((ho.group("from"), ho.group("to"), ts))
            continue
        if _LOG_TOOL_RE.search(line):
            tool_calls += 1
            continue
        start_m = _LOG_INSTANCE_RE.search(line)
        if start_m:
            if instance_id is None:
                instance_id = start_m.group("iid")
            if cell_start_ts is None:
                tsm = _LOG_TS_RE.match(line)
                if tsm:
                    cell_start_ts = datetime.strptime(tsm.group("ts"), "%Y-%m-%d %H:%M:%S").timestamp()
            current_iid = start_m.group("iid")
            continue
        done_m = _LOG_DONE_RE.search(line)
        if done_m:
            tsm = _LOG_TS_RE.match(line)
            if tsm:
                cell_done_ts = datetime.strptime(tsm.group("ts"), "%Y-%m-%d %H:%M:%S").timestamp()
            tok_m = _LOG_DONE_TOKENS_RE.search(line)
            if tok_m:
                done_iid = done_m.group("iid")
                per_cell_total[done_iid] = int(tok_m.group("total"))
                per_cell_in_out[done_iid] = (int(tok_m.group("in")), int(tok_m.group("out")))
            current_iid = None

    # Fallback: any instance with per-call tokens but no done-line rollup
    # (cell crashed before the runner could write the done marker) gets
    # its totals from the per-call accumulator.
    for iid, (pi, po) in per_cell_calls.items():
        if iid not in per_cell_total and (pi or po):
            per_cell_total[iid] = pi + po
            per_cell_in_out[iid] = (pi, po)

    # Active duration: sum of inter-line gaps, capped at IDLE_GAP_S.
    # Any gap larger than that is system-sleep / kernel-paused (e.g.
    # the laptop suspended for the night while a slow model was
    # mid-call) and gets clamped to 0 so it doesn't pollute the metric.
    ts_sorted = sorted(set(line_timestamps))
    active_s = 0.0
    for i in range(1, len(ts_sorted)):
        gap = ts_sorted[i] - ts_sorted[i - 1]
        if gap <= IDLE_GAP_S:
            active_s += gap

    # Fall back to first/last log-line timestamps when the runner's
    # `=== running` / `=== done` markers aren't in this log (the API
    # matrix path uses a flatter log format without those markers).
    # This is what lets the virtual-handoff synth bracket the first &
    # last agents for matrix runs too, not just notebook runs.
    if cell_start_ts is None and ts_sorted:
        cell_start_ts = ts_sorted[0]
    if cell_done_ts is None and ts_sorted:
        cell_done_ts = ts_sorted[-1]

    return {
        "per_call": per_call, "per_cell": per_cell_total,
        "per_cell_in_out": per_cell_in_out,
        "per_agent": per_cell_per_agent,
        "handoffs": handoffs, "tool_calls": tool_calls,
        "instance_id": instance_id,
        "cell_start_ts": cell_start_ts, "cell_done_ts": cell_done_ts,
        "active_dur_s": active_s,
        # Sorted unique line timestamps — exposed so per-bracket durations
        # can be computed as the sum of intra-bracket gaps capped at
        # IDLE_GAP_S (skips system-sleep), same way `active_dur_s` is
        # computed for the whole cell.
        "line_ts": ts_sorted,
        "idle_gap_s": IDLE_GAP_S,
    }


def _scan_ndjson(p: Path) -> dict[str, Any]:
    """Extract handoffs + tool_call count + response/thinking char counts
    + the instance_id (so the cell can still be labelled when the
    prediction file is still 0 bytes / mid-inference) from one
    prediction's NDJSON event stream."""
    out: dict[str, Any] = {
        "handoffs": [], "tool_calls": 0,
        "response_chars": 0, "thinking_chars": 0,
        "instance_id": None,
    }
    if not p.exists():
        return out
    for line in p.open(encoding="utf-8", errors="replace"):
        evt = _safe_json(line)
        if not isinstance(evt, dict):
            continue
        t = evt.get("type")
        if t == "handoff":
            ts = _parse_ts(evt.get("timestamp", ""))
            if ts is not None:
                out["handoffs"].append((evt.get("from"), evt.get("to"), ts))
        elif t == "tool_call":
            out["tool_calls"] += 1
        elif t == "response":
            out["response_chars"] += len(str(evt.get("content", "")))
        elif t == "thinking_chunk":
            out["thinking_chars"] += len(str(evt.get("chunk", "")))
        elif t in ("instance_start", "start") and not out["instance_id"]:
            iid = evt.get("instance_id")
            if iid:
                out["instance_id"] = iid
    return out


def _scan_run(run_dir: Path) -> dict[str, Any] | None:
    """Build the full per-run summary or return None if nothing's there."""
    pred_dir = run_dir / "predictions"
    eval_dir = run_dir / "evaluations"
    text_log_dir = pred_dir / "logs"
    if not pred_dir.is_dir():
        return None

    preds = sorted(pred_dir.glob("prediction-*.jsonl"), key=lambda p: p.stat().st_mtime)
    evals = sorted(eval_dir.glob("*.json"), key=lambda p: p.stat().st_mtime) if eval_dir.is_dir() else []
    if not preds:
        return None

    # Per-cell verdicts keyed by (run_id, iid). Two layouts to handle:
    #  - Matrix: each eval file is one cell; its stem ends with the
    #    matching `prediction-<run_id>` stem (e.g.
    #    `evomas.evaluation-prometheus_tree-00bbc63e.json` ↔
    #    `prediction-prometheus_tree-00bbc63e.jsonl`).
    #  - Notebook: a single eval file carries verdicts for every
    #    instance the notebook ran; the filename doesn't encode the
    #    prediction run_id, so we fall back to iid-only lookup.
    eval_by_run_id: dict[str, dict[str, str]] = {}
    eval_by_iid_any: dict[str, str] = {}
    for ev in evals:
        d = _safe_json(ev.read_text(encoding="utf-8")) or {}
        m = re.search(r"evaluation-(.+)$", ev.stem)
        rid = m.group(1) if m else ev.stem
        verdicts: dict[str, str] = {}
        for iid in d.get("resolved_ids", []):
            verdicts[iid] = "PASS"
        for iid in d.get("completed_ids", []):
            if iid not in d.get("resolved_ids", []):
                verdicts[iid] = "FAIL"
        for iid in d.get("error_ids", []):
            verdicts[iid] = "ERROR"
        # SWE-bench harness adds a fourth bucket: predictions with an
        # empty `model_patch` are short-circuited (no Docker, no pytest)
        # and listed under `empty_patch_ids`. Treat them as FAIL so they
        # don't fall through to "pending" — the harness deliberately
        # didn't grade them, that IS the verdict.
        for iid in d.get("empty_patch_ids", []):
            verdicts.setdefault(iid, "FAIL")
        eval_by_run_id[rid] = verdicts
        eval_by_iid_any.update(verdicts)

    cells: list[dict[str, Any]] = []
    per_agent_dur: dict[str, list[float]] = defaultdict(list)
    tokens_total = {"input": 0, "output": 0, "total": 0}
    per_agent_tokens: dict[str, dict[str, int]] = defaultdict(lambda: {"input": 0, "output": 0, "total": 0})
    llm_calls_count: dict[str, int] = defaultdict(int)
    llm_calls_in_total = 0
    llm_calls_out_total = 0

    for p in preds:
        run_id = p.stem[len("prediction-"):]
        try:
            obj = _safe_json(p.read_text(encoding="utf-8")) or {}
        except OSError:
            obj = {}
        iid = obj.get("instance_id") or ""
        patch_len = len(obj.get("model_patch") or obj.get("patch") or "")

        nd = _scan_ndjson(INFERENCE_LOGS / f"prediction-{run_id}.ndjson")
        tok = _scan_text_log(text_log_dir / f"prediction-{run_id}.log")
        # NDJSON path = API matrix run. Text-log path = notebook run
        # (the FileHandler in the setup cell mirrors logging to disk).
        # Prefer NDJSON when present (richer event schema), fall back
        # to the regex-derived signal from the text log otherwise.
        handoffs = nd["handoffs"] or tok["handoffs"]
        tool_call_count = nd["tool_calls"] or tok["tool_calls"]
        if not iid:
            iid = nd["instance_id"] or tok["instance_id"] or "?"
        # Prefer the runner's start/done markers for cell duration —
        # they bracket the whole cell, not just the inter-handoff span.
        # Fall back to first/last handoff when one marker is missing
        # (truncated logs, NDJSON-only API path, etc.).
        cell_start_ts = tok["cell_start_ts"] if tok["cell_start_ts"] is not None else (handoffs[0][2] if handoffs else None)
        cell_end_ts   = tok["cell_done_ts"]  if tok["cell_done_ts"]  is not None else (handoffs[-1][2] if handoffs else None)
        # Prefer active-time (sum of inter-line gaps capped at 5 min)
        # over raw end-start: skips system-sleep / kernel-paused stretches
        # that would otherwise inflate single-cell durations to 14+ hours
        # when the laptop suspends mid-run.
        if tok["active_dur_s"] and tok["active_dur_s"] > 0:
            cell_dur = tok["active_dur_s"]
        elif cell_start_ts is not None and cell_end_ts is not None and cell_end_ts > cell_start_ts:
            cell_dur = cell_end_ts - cell_start_ts
        else:
            cell_dur = 0.0
        # Dedup hub-style BROADCAST handoffs first: a Router/hub emits N
        # `hub -> <each-possible-target>` events at the same timestamp
        # to declare the possible next nodes, then exactly ONE of those
        # targets actually runs (whichever shows up as the next handoff's
        # `from`). Without dedup the pair-loop sees prev[1]=target_A but
        # cur[0]=hub on the duplicate dispatches and skips them, which
        # means the chosen worker agent never gets bracketed.
        #
        # At cell-terminating broadcasts (no next handoff to disambiguate)
        # we KEEP ALL of them — the pair-loop's prev[1]==cur[0] check
        # naturally drops the spurious ones and the virtual end-handoff
        # pairs with the right last broadcast.
        deduped: list[tuple[str, str, float]] = []
        i = 0
        while i < len(handoffs):
            cur = handoffs[i]
            j = i + 1
            while j < len(handoffs) and handoffs[j][0] == cur[0] and handoffs[j][2] == cur[2]:
                j += 1
            if j - i == 1 or j == len(handoffs):
                deduped.extend(handoffs[i:j])
            else:
                # Mid-cell broadcasts with a next handoff to disambiguate.
                next_from = handoffs[j][0]
                chosen = next((b for b in handoffs[i:j] if b[1] == next_from), handoffs[i])
                deduped.append(chosen)
            i = j

        # Synthesize virtual handoffs at cell boundaries so the FIRST
        # agent (no preceding handoff) and the LAST agent (no subsequent
        # handoff) get bracketed too. Without these, locator + finalizer
        # thinking time is invisible in the per-agent table even though
        # it shows up in cell duration.
        bracketed = list(deduped)
        if bracketed and cell_start_ts is not None and cell_start_ts < bracketed[0][2]:
            first_agent = bracketed[0][0]
            bracketed.insert(0, ("__start__", first_agent, cell_start_ts))
        if bracketed and cell_end_ts is not None and cell_end_ts > bracketed[-1][2]:
            last_agent = bracketed[-1][1]
            bracketed.append((last_agent, "__end__", cell_end_ts))
        # Per-bracket duration: sum of intra-bracket line-gaps capped
        # at IDLE_GAP_S (matches how `active_dur_s` is computed). Without
        # this, a single overnight suspend during a bracket inflates the
        # raw clock-delta to ~12h, which then trips the outlier guard and
        # drops the bracket entirely.
        line_ts = tok.get("line_ts") or []
        idle_gap = tok.get("idle_gap_s") or 300
        def _active_between(t0: float, t1: float) -> float:
            if t1 <= t0:
                return 0.0
            window = [t for t in line_ts if t0 <= t <= t1]
            if len(window) < 2:
                return min(t1 - t0, idle_gap)
            s = 0.0
            for k in range(1, len(window)):
                gap = window[k] - window[k - 1]
                if gap <= idle_gap:
                    s += gap
            return s

        agent_calls = max(0, len(bracketed) - 1)
        for i in range(1, len(bracketed)):
            prev = bracketed[i - 1]
            cur = bracketed[i]
            if prev[1] != cur[0]:
                continue
            d = _active_between(prev[2], cur[2])
            if d > 0:
                per_agent_dur[cur[0]].append(d)

        cell_tokens = tok["per_cell"].get(iid, 0)
        cell_per_agent_tokens = tok["per_agent"].get(iid, {})
        for who, calls in tok["per_call"].items():
            llm_calls_count[who] += len(calls)
            for c in calls:
                llm_calls_in_total += c["input"]
                llm_calls_out_total += c["output"]
        for who, total in cell_per_agent_tokens.items():
            per_agent_tokens[who]["total"] += total
        if iid in tok["per_cell"]:
            tokens_total["total"] += cell_tokens

        # Per-cell verdict: match the eval to THIS prediction's run_id
        # first (matrix layout), then fall back to any eval containing
        # this iid (notebook layout has 1 eval for many iids).
        status = eval_by_run_id.get(run_id, {}).get(iid) or eval_by_iid_any.get(iid) or "pending"

        cell_in, cell_out = tok.get("per_cell_in_out", {}).get(iid, (0, 0))
        cells.append({
            "run_id": run_id,
            "instance_id": iid,
            "patch_len": patch_len,
            "status": status,
            "agent_calls": agent_calls,
            "cell_dur_s": cell_dur,
            "cell_start_ts": cell_start_ts,
            "cell_end_ts": cell_end_ts,
            "tool_calls": tool_call_count,
            "response_chars": nd["response_chars"],
            "thinking_chars": nd["thinking_chars"],
            "tokens_total": cell_tokens,
            "tokens_in": cell_in,
            "tokens_out": cell_out,
            "tokens_per_agent": cell_per_agent_tokens,
        })

    # Run-level active time = sum of per-cell active durations.
    # Each cell_dur_s already excludes idle gaps via the IDLE_GAP_S
    # clamp in _scan_text_log, so a serial run's sum gives true
    # compute wall-clock — system sleeps between/within cells don't
    # inflate the figure.
    span_s = sum(c["cell_dur_s"] for c in cells)

    mtimes = [p.stat().st_mtime for p in preds] + [e.stat().st_mtime for e in evals]

    # Cell-level counts: a cell counts as "evaluated" once a verdict
    # is attached to it; PASS / FAIL / ERROR break the evaluated bucket
    # down. Distinct from the matrix-historic per-iid counts which
    # over-collapsed when the same iid was attempted across configs.
    n_pass = sum(1 for c in cells if c["status"] == "PASS")
    n_fail = sum(1 for c in cells if c["status"] == "FAIL")
    n_err  = sum(1 for c in cells if c["status"] == "ERROR")
    n_evaluated_cells = n_pass + n_fail + n_err
    resolved_iids = sorted({c["instance_id"] for c in cells if c["status"] == "PASS"})

    return {
        "run_dir": run_dir.name,
        "started_at": datetime.fromtimestamp(min(mtimes)).strftime("%Y-%m-%d %H:%M:%S") if mtimes else "?",
        "span_s": span_s,
        "n_predictions": len(preds),
        "n_evaluations": n_evaluated_cells,
        "n_resolved": n_pass,
        "n_not_resolved": n_fail,
        "n_errored": n_err,
        "resolved_ids": resolved_iids,
        "cells": cells,
        "per_agent_dur": {
            k: {
                "n": len(v),
                "mean_s": sum(v) / len(v),
                "median_s": sorted(v)[len(v) // 2],
                "total_s": sum(v),
            }
            for k, v in per_agent_dur.items()
        },
        "tokens_total": tokens_total,
        "per_agent_tokens": dict(per_agent_tokens),
        "llm_calls_count": dict(llm_calls_count),
        "llm_calls_in_total": llm_calls_in_total,
        "llm_calls_out_total": llm_calls_out_total,
    }


def _fmt_dur(s: float) -> str:
    if s < 60:
        return f"{s:.1f} s"
    if s < 3600:
        # < 1h: "Xmin Ys" when seconds-part is non-trivial, else "Xmin".
        m, rem = divmod(int(round(s)), 60)
        return f"{m}min {rem}s" if rem else f"{m}min"
    # >= 1h: "Xh Ymin" — drop the minute-part only when it rounds to 0.
    h, rem = divmod(int(round(s)), 3600)
    m = rem // 60
    return f"{h}h {m}min" if m else f"{h}h"


def _render_run(run: dict[str, Any]) -> str:
    name = run["run_dir"]
    cells = run["cells"]
    n_eval = run["n_evaluations"]
    n_resolved = run["n_resolved"]
    n_preds = run["n_predictions"]
    pct = (n_resolved / n_eval * 100) if n_eval else 0.0

    lines: list[str] = []
    lines.append(f"## {name}\n")
    lines.append(f"- **Started**: {run['started_at']}")
    lines.append(f"- **Active wall-clock**: {_fmt_dur(run['span_s'])} (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)")
    lines.append(f"- **Predictions written**: {n_preds}")
    lines.append(f"- **Evaluated**: {n_eval}")
    lines.append(f"- **Resolved**: {n_resolved} / {n_eval} = **{pct:.1f} %** of evaluated, {(n_resolved/n_preds*100 if n_preds else 0):.1f} % of attempted")
    lines.append("")

    # Per-cell table
    lines.append("### Per-cell outcomes\n")
    lines.append("| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |")
    lines.append("|---|---|---:|---:|---:|---|---:|")
    status_glyph = {
        "PASS":    "🟢 PASS",
        "FAIL":    "🔴 FAIL",
        "ERROR":   "⚫ ERROR",
        "pending": "⏳ pending",
    }
    for c in cells:
        total_tok = c["tokens_total"] or 0
        in_tok = c.get("tokens_in", 0) or 0
        out_tok = c.get("tokens_out", 0) or 0
        if total_tok and (in_tok or out_tok):
            tok_str = f"{total_tok:,} ({in_tok:,} + {out_tok:,})"
        else:
            tok_str = f"{total_tok:,}"
        status_str = status_glyph.get(c["status"], c["status"])
        lines.append(
            f"| `{c['instance_id']}` | {status_str} | {c['agent_calls']} | "
            f"{c['tool_calls']} | {_fmt_dur(c['cell_dur_s'])} | {tok_str} | {c['patch_len']} |"
        )
    lines.append("")

    # Per-agent timing
    if run["per_agent_dur"]:
        lines.append("### Per-agent timing\n")
        lines.append("| Agent | LLM calls (paired) | Mean | Median | Total |")
        lines.append("|---|---:|---:|---:|---:|")
        for who, st in sorted(run["per_agent_dur"].items(), key=lambda kv: -kv[1]["total_s"]):
            lines.append(
                f"| `{who}` | {st['n']} | {_fmt_dur(st['mean_s'])} | "
                f"{_fmt_dur(st['median_s'])} | {_fmt_dur(st['total_s'])} |"
            )
        lines.append("")

    # Per-agent token usage
    if run["per_agent_tokens"]:
        lines.append("### Token usage per agent (sum across all cells)\n")
        lines.append("| Agent | LLM calls | Total tokens |")
        lines.append("|---|---:|---:|")
        for who, totals in sorted(run["per_agent_tokens"].items(), key=lambda kv: -kv[1]["total"]):
            n = run["llm_calls_count"].get(who, 0)
            lines.append(f"| `{who}` | {n} | {totals['total']:,} |")
        lines.append("")

    # Aggregate
    if run["llm_calls_in_total"] or run["llm_calls_out_total"]:
        in_t = run["llm_calls_in_total"]
        out_t = run["llm_calls_out_total"]
        n_calls = sum(run["llm_calls_count"].values())
        lines.append("### LLM call totals\n")
        lines.append(f"- **Total LLM calls**: {n_calls:,}")
        lines.append(f"- **Total tokens**: {in_t + out_t:,} ({in_t:,} + {out_t:,})")
        lines.append("")

    if run["resolved_ids"]:
        lines.append("### Resolved instances\n")
        for r in run["resolved_ids"]:
            lines.append(f"- `{r}`")
        lines.append("")

    return "\n".join(lines)


_BEGIN = "<!-- BEGIN {name} -->"
_END   = "<!-- END {name} -->"


def _splice_section(doc: str, name: str, body: str) -> str:
    begin = _BEGIN.format(name=name)
    end = _END.format(name=name)
    wrapped = f"{begin}\n{body}{end}\n"
    if begin in doc and end in doc:
        head, _, rest = doc.partition(begin)
        _, _, tail = rest.partition(end)
        # Drop trailing newlines after end marker so the splice doesn't accumulate blanks.
        tail = tail.lstrip("\n")
        return head + wrapped + ("\n" + tail if tail else "")
    # New section: append at end, before any trailing blanks.
    return doc.rstrip() + "\n\n" + wrapped


_DOC_HEADER = """# EvoMas — experiment log

Per-run breakdown of resolve rate, wall-clock, agent-call timing,
and LLM token usage.

Run rows correspond to result folders under `experiments/`. The script
that maintains this file is `experiments/generate_report.py`:

```
python experiments/generate_report.py                  # refresh all runs
python experiments/generate_report.py <folder-name>    # refresh one
```

**Data source notes**
- *Resolve outcomes*: read from each run's `evaluations/*.json` (the SWE-bench harness report; `resolved_ids` / `completed_ids`).
- *Per-cell wall-clock + agent timing*: derived from `handoff` events in `evomas/logs/inference_logs/prediction-<run>.ndjson` (timestamps between consecutive handoffs).
- *Tool-call counts + response/thinking chars*: counted directly from the same NDJSON stream.
- *Token usage*: parsed from the per-LLM-call lines in `<run-dir>/predictions/logs/prediction-<run>.log` (`[<agent>] tokens in=X out=Y total=Z`). These are real counts emitted by the Ollama/LiteLLM dispatcher, not approximations.

"""


def update_doc(only: str | None = None) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else _DOC_HEADER

    if only:
        candidates = [EXPERIMENTS_DIR / only]
    else:
        candidates = [p for p in EXPERIMENTS_DIR.iterdir() if p.is_dir() and p.name not in ("old", "__pycache__")]

    # Order new sections by oldest activity so the doc reads chronologically.
    sorted_runs = sorted(
        [d for d in candidates if d.is_dir()],
        key=lambda d: min(
            (f.stat().st_mtime for f in d.rglob("*") if f.is_file()),
            default=0,
        ),
    )

    for run_dir in sorted_runs:
        info = _scan_run(run_dir)
        if not info:
            print(f"  skip {run_dir.name} (no predictions yet)")
            continue
        body = _render_run(info)
        doc = _splice_section(doc, run_dir.name, body)
        print(f"  refreshed {run_dir.name}")

    DOC_PATH.write_text(doc, encoding="utf-8", newline="\n")
    print(f"wrote {DOC_PATH}")


if __name__ == "__main__":
    update_doc(sys.argv[1] if len(sys.argv) > 1 else None)
