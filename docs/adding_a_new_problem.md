# Adding a new problem to EvoMas

EvoMas is built so that wiring up a brand-new problem type — program
repair, file translation, math proof checking, whatever — is **three
drop-in files**, no edits in framework code. The framework auto-
discovers what you add.

| You add this file | EvoMas picks it up via |
|---|---|
| A `@tool` function anywhere under `evomas/tools/` | `evomas/mcp/server.py:_discover_tools` walks the whole tree on startup and registers every `BaseTool` attribute + every `*_TOOLS` list it finds |
| `evomas/config/predefined/<topology>.json` | `evomas/config/loader.py` lists predefined configs by reading the folder |
| `scripts/evaluation/<evaluator>.py` with `EVOMAS_EVALUATOR` manifest | `api/routers/evaluation.py` enumerates the folder and imports each script for its manifest |

The rest of this doc walks through the contracts.

---

## 1. Tools — `evomas/tools/<bundle>/`

Tools live anywhere under `evomas/tools/`. Two conventional locations:

- `evomas/tools/<bundle>/` — **task-scoped** bundles (translate,
  websearch, your-new-thing). Use this for tools that belong to one
  problem type.
- `evomas/tools/repo/<bundle>/` — **repo-variant** bundles borrowed
  from external SWE-bench agents (openhands, swe_agent, patchwork,
  ...). Reserved for upstream-aligned re-implementations.

Single `.py` files at the top level (`evomas/tools/lint_tools.py`,
`patch_tools.py`, ...) also work — any module-level `BaseTool` gets
registered. Use a package when you have more than one or two tools.

Minimum shape:

```
evomas/tools/my_bundle/
├── __init__.py
└── my_tool.py
```

`my_tool.py`:

```python
from langchain_core.tools import tool

@tool
def my_tool(arg1: str, arg2: int) -> dict:
    """One-line summary visible to the LLM. Be specific."""
    # ... implementation ...
    return {"ok": True, "value": ...}
```

`__init__.py`:

```python
from evomas.tools.my_bundle.my_tool import my_tool

MY_BUNDLE_TOOLS = [my_tool]   # the name must end in `_TOOLS`
```

The `*_TOOLS` list is optional — `_discover_tools` also picks up the
re-exported `my_tool` attribute directly. The list is still useful as
a stable export when a bundle has many tools and you want grouped
registration / external introspection (`tool_repo_owner_map`).

Restart the API. The tool is now in the MCP registry; any predefined
config can reference it via `"tools": [{"name": "my_tool"}]`.

**Conventions:**

- Tool name (as the LLM sees it) = the decorated function's name.
- Use type hints — the MCP layer derives a JSON Schema from the
  signature.
- Return a dict (or `BaseModel`) so the agent can inspect structured
  fields, not just text.
- If your tool needs the workspace path, read it from
  `os.environ["EVOMAS_WORKSPACE_PATH"]` — the runner exports it
  before invoking the graph (`write_file` in `evomas/tools/translate/`
  is a worked example).
- Tool names must be unique across all bundles; last-registered-wins
  on collision (alphabetical by bundle name within each tier;
  top-level `.py` modules register before bundles).

---

## 2. Config — `evomas/config/predefined/<topology>.json`

Each topology is a JSON file describing the agent graph (entry, end,
edges, per-agent prompts + tools + model knobs). The full schema —
top-level shape, every accepted field on an agent block, the tool
whitelist priority chain, variants — lives in
[`evomas/config/TOPOLOGY_CONFIG.md`](../evomas/config/TOPOLOGY_CONFIG.md).
For a new problem type, the relevant patterns are:

- Use `"class": "Base agent"` when you want a role-less LLM-with-tools
  node and supply prompts + tools entirely in JSON. The translate
  config (`evomas/config/predefined/translate.json`) is a three-agent
  worked example built this way.
- Reference your new tool by name under each agent's `tools` list:
  `"tools": [{ "name": "my_tool" }]`. Auto-discovery (Section 1)
  is what makes the name resolvable.
- The runner derives the final patch from `generate_diff(workspace)`
  automatically — no `finalizer` agent needed unless your flow needs
  explicit post-processing.

---

## 3. Evaluator — `scripts/evaluation/<evaluator>.py`

An evaluator reads a predictions JSONL + an instances JSONL and emits
a SWE-bench-shaped report under `<report-dir>/<model>.<run-id>.json`.
That's it.

Every evaluator script is invoked **the same way** — one subprocess,
no per-bucket loop in the framework. The script reads the predictions
JSONL, does whatever it needs internally (the SWE-bench wrappers
group rows by `(subset, split)` themselves), and writes its report.

The optional manifest exposes a single knob:

```python
"""One-line docstring."""

# OPTIONAL -- omit the dict entirely when defaults fit.
EVOMAS_EVALUATOR = {
    "needs_wsl": False,           # default: False
}

import argparse
# ... rest of the script
```

| Field | Default | When you must override |
|---|---|---|
| `needs_wsl` | `False` | Set `True` only if your script imports POSIX-only deps (the local SWE-bench harness is the lone case today — `swebench` itself is Linux-only) |

A brand-new evaluator with no `EVOMAS_EVALUATOR` dict at all shows up
in the dropdown as `<stem>.py`, runs on the native interpreter, and
gets the unified CLI args. Declare a manifest only to flip `needs_wsl`.

### Single-shot shape (`"shape": "single_shot"`)

The API hands you **every prediction row in one batch** + a generated
instances JSONL. Required CLI surface:

```
python <script>.py
    --instances    <path-to-instances.jsonl>
    --predictions  <path-to-predictions.jsonl>
    --report-dir   <output-dir>
    --run-id       <stable-string>
    --model        <model-name-for-folder-layout>
```

`apply_and_test.py` and `translate_eval.py` are the worked examples.

### Groups shape (`"shape": "groups"`)

The API iterates `(subset, split)` buckets and calls you per-bucket.
Required CLI surface:

```
python <script>.py
    --predictions  <path-to-bucket-predictions.jsonl>
    --subset       <bucket-subset>
    --split        <bucket-split>
    --run-id       <stable-string>
    --report-dir   <output-dir>          # OR --output-dir if no WSL
```

The local-harness path (`needs_wsl: True`) also receives `--max-workers`.

`run_swebench_evaluation.py` (WSL + harness) and
`run_swebench_evaluation_remote.py` (sb-cli) are the worked examples.

### Report shape

Every evaluator writes one summary JSON: `<report-dir>/<model>.<run-id>.json`
with at minimum:

```json
{
  "resolved_ids":  ["instance_id_a", "..."],
  "completed_ids": ["instance_id_a", "...", "instance_id_z"],
  "error_ids":     []
}
```

This is what `experiments/generate_report.py` reads to compute resolve
rates. Additional fields (BLEU scores, per-file detail, etc.) are
yours to add — `translate_eval.py` shows a richer schema with a
`bleu` field and `instances[].files[].score`.

---

## End-to-end: the translate demo

`examples/translate_demo/` puts all three drop-ins together:

- **Tool**: `evomas/tools/translate/write_file.py` — one
  `@tool`-decorated function with `workspace_path` sandboxing.
- **Config**: `evomas/config/predefined/translate.json` — three
  `Base agent`s with prompts that read the source/target languages
  from `instance.problem_statement`.
- **Evaluator**: `scripts/evaluation/translate_eval.py` — BLEU vs
  `<file>.gold` sidecars; single-shot manifest.

Walk through it as a template when scaffolding your own problem type.

---

## Restart checklist

After dropping any of the three:

1. Restart the API server (`evomas api`) — the MCP registry, config
   list, and evaluator dropdown all rebuild at process start.
2. Hard-refresh the frontend tab so it re-fetches `/api/configs`,
   `/api/tools`, and `/api/evaluation/scripts`.

That's it. No code edits in `evomas/`, `api/`, or `app/`.
