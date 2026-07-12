# Topology config reference

Every EvoMas run is driven by a single JSON file that defines the graph of
agents (nodes) and how state flows between them (edges). This document is
the source-of-truth schema.

## Where configs live

```
evomas/config/
├── predefined/   # checked-in, read-only via the API
├── loaded/       # user-uploaded at runtime
└── agent_types/  # variant catalogs (per upstream repo)
```

| Directory | Purpose | Edit policy |
|---|---|---|
| `predefined/` | Reference topologies shipped with EvoMas (one per upstream multi-agent paper — `agentscope_hybrid`, `experepair_star`, `hyperagent_star`, `joycode_star`, `lingxi_star`, `openhands_star`, `prometheus_tree`). | Treated as read-only by the UI; safe to edit on disk and commit. The "Export config…" button in the Topology page produces a copy in `loaded/` so the predefined original stays untouched. |
| `loaded/` | Working area for user-created or exported configs. Populated by the **Export config…** button or by `POST /api/topology/save`. Empty on a fresh clone — many integration tests should NOT depend on a file being present here. | Free to edit / delete. Files here override `predefined/` when names collide (the loader's `resolve_config_path` walks `predefined/ → loaded/`). |
| `agent_types/` | Variant catalogs mirroring upstream multi-agent repos (`OpenHands.json`, `joycode-agent.json`, `Lingxi.json`, etc.). Each catalog defines per-agent prompts + tools that a config block can pull in via `"variant": "<RepoId>:<AgentName>"`. | Edit when adding/refreshing a repo variant. Catalog tools have `source_url` fields pointing at the upstream commit — preserve that mirror semantic. |

The loader resolves a config name as `predefined/<name>.json → loaded/<name>.json → <repo>/evomas/config/<name>.json` (legacy flat root, kept for backward compat). First hit wins.

## Top-level shape

```jsonc
{
  "id":          "my-pipeline",          // human label (matches filename stem by convention)
  "description": "Locator → patcher → reviewer → finalizer.",
  "entry":       "locator",              // starting node id (must appear in `agents`)
  "end":         "finalizer",            // terminal node id OR list of ids ["a", "b"]
  "edges":       [ { "from": "locator", "to": "patcher" }, ... ],
  "agents":      { "locator": { ... }, "patcher": { ... }, ... }
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | string | Identifier surfaced in the UI dropdown. Convention: matches the filename stem. |
| `description` | string | Free-form. Shown in the topology page card; embed thesis-justifying prose here. |
| `entry` | string | Node id of the first agent to run. Must exist in `agents`. |
| `end` | string or string[] | Terminal node(s). The runner stops when state writes into any `end` slot. List form is for branchy topologies that can finish on multiple paths. |
| `edges` | array | Directed edges. Each entry: `{ "from": "<src>", "to": "<dst>" }`. Cycles are allowed; the LangGraph runtime caps revisits via `EVOMAS_GRAPH_MAX_REVISITS`. |
| `agents` | object | Map of `<node_id> → <agent block>`. See [Agent block](#agent-block). |

## Agent block

Each `agents.<id>` block:

```jsonc
{
  "class":   "Patcher",                  // AGENT_TYPE label OR Python class name
  "variant": "joycode-agent:PatchEngine",// optional, see [Variants]
  "model":   "ollama/qwen3.5:9b",        // LiteLLM-style provider/model
  "think":   true,
  "num_ctx": 16384,
  "stream":  true,
  "temperature": 0,
  "top_k": 40, "top_p": 0.9, "min_p": 0,
  "repeat_penalty": 1.1, "repeat_last_n": 64,
  "seed": 0,
  "num_predict": 2048,
  "stop":    ["</patch>"],
  "max_iters": 12,
  "prompts": { "system": "...", "user": "..." },   // optional override
  "tools":   [ { "name": "apply_patch" }, ... ],   // optional override
  "fallback": { "enabled": true, "guarantee_change": true }
}
```

### Required fields

- `class` — the agent type. Accepts either:
  - the AGENT_TYPE label: `Router`, `Locator`, `Patcher`, `Reviewer`, `Bug reproduction`, `Helper/Proxy`, `Planner/Orchestrator`, `Environment setup`, `Base agent`
  - or the Python class name: `LocatorAgent`, `PatcherAgent`, `ReviewerAgent`, `HelperProxyAgent`, `Router`, `GenericAgent`, `BugReproductionAgent`, etc.
- `model` — provider-prefixed: `ollama/<id>` | `gemini/<id>` | `openai/<id>`. A bare `qwen3.5:9b` is treated as `ollama/qwen3.5:9b` for backward compat with the legacy chain config.

### Model knobs

Map 1:1 to Pydantic `AgentConfig` (see `evomas/config/loader.py:18`). Defaults: `think=true`, `num_ctx=4096`, `stream=true`, `temperature=0.2`, `top_k=40`, `top_p=0.9`, `min_p=0.0`, `repeat_penalty=1.1`, `repeat_last_n=64`, `seed=0`, `num_predict=-1`, `stop=[]`.

`think` accepts `true | false | "low" | "medium" | "high"`. The string levels map to LiteLLM's reasoning-effort knob (where the provider supports it).

### Optional fields

- `max_iters` — per-agent tool-loop cap. Once an agent has called `max_iters` tools without ending, the runner forces a final answer. Default depends on the agent class (see `evomas/agents/types/<class>.py:DEFAULT_CONFIG`).
- `prompts.system` / `prompts.user` / `prompts.proxy` — inline override of the agent class's default prompts. Variables `{issue}`, `{workspace}`, `{instance_id}`, `{predecessor}`, and any upstream node id are substituted.
- `tools` — explicit whitelist of MCP tool names this agent can call. **See [Tool whitelist](#tool-whitelist).**
- `variant` — pull `prompts` + `tools` defaults from a catalog. See [Variants](#variants).
- `fallback` — available on any LLM-tool agent. `enabled=true` runs a single-shot patch attempt at end-of-run if the workspace has no `git diff`, so the agent at least produces some output instead of an empty patch. `guarantee_change=true` is a last-resort: if even the single-shot attempt produced no diff, the runner "touches" a tracked file (preferring `README.*`, otherwise the first `git ls-files` entry) so the harness gets a non-empty diff to apply. Implementation: `evomas/agents/llm_tool_agent.py:57-60` and `:186-194`.

## Tool whitelist

Priority chain (highest wins, full **replace** — no merging across layers):

| Layer | Triggered by |
|---|---|
| **Inline `tools`** in the agent block | Field present (even `"tools": []`) |
| **Variant catalog `tools`** | Block has `variant` AND no inline `tools` |
| **Class `DEFAULT_TOOLS`** | No block `tools`, no variant catalog tools |
| **Permissive (every MCP tool callable)** | All of the above empty/absent |

Concretely:

- `"tools": []` → **zero tools** (strictest mode, agent can only emit text).
- Omitting `tools` entirely → falls through to the next layer.
- `"tools": [{"name": "apply_patch"}, {"name": "read_file", "params": {"max_chars": 8000}}]` → exact whitelist; `params` pins call-site defaults the agent code can override.

Loader code: `evomas/config/loader.py:93` (variant injection) + `evomas/agents/base_agent.py:70` (whitelist resolution).

## Variants

A `variant: "<RepoId>:<AgentName>"` looks up `evomas/config/agent_types/<RepoId>.json` and copies that catalog entry's `prompts` and `tools` into the block — but **only** for fields the block hasn't already set inline. Used to faithfully mirror upstream multi-agent repos without forking every prompt into the predefined configs.

22 catalog files ship under `agent_types/`, one per upstream multi-agent repo: `aider`, `augment-swebench-agent`, `auto_code_rover`, `claude-coder`, `composio`, `DARS-Agent`, `debug-gym`, `ExpeRepair`, `HyperAgent`, `joycode-agent`, `KGCompass`, `Lingma_SWE_GPT`, `Lingxi`, `mini-SWE-agent`, `OpenHands`, `OrcaLoca`, `patchwork`, `programmer`, `R2E-Gym`, `suna`, `SWE_agent`, `trae_agent`.

See [`agent_types/ACKNOWLEDGEMENTS.md`](./agent_types/ACKNOWLEDGEMENTS.md) for the upstream URL, agent count, tool count, and license posture of each one.

Variant strings reference the catalog's `id` field plus the `name` of one of its `agents[]` entries. Missing variant or unknown name = silent no-op (block stays as-is).

## Worked examples

### Star with conditional dispatch (`predefined/joycode_star.json`)

A `Router` hub picks which spoke to run next; the Patcher uses a variant from the `joycode-agent` catalog so it inherits the upstream prompts + tools.

```jsonc
{
  "id": "joycode_star",
  "entry": "hub",
  "end":   "finalizer",
  "edges": [
    { "from": "hub", "to": "locator"  }, { "from": "locator",  "to": "hub" },
    { "from": "hub", "to": "patcher"  }, { "from": "patcher",  "to": "hub" },
    { "from": "hub", "to": "reviewer" }, { "from": "reviewer", "to": "hub" },
    { "from": "hub", "to": "finalizer" }
  ],
  "agents": {
    "hub":     { "class": "Router", "prompts": { "system": "...", "user": "..." }, "max_iters": 1 },
    "locator": { "class": "Locator" },
    "patcher": { "class": "Patcher", "variant": "joycode-agent:PatchEngine", "stop": ["</patch>"], "max_iters": 12 },
    "reviewer":{ "class": "Reviewer", "stop": ["</review>"] },
    "finalizer": { "class": "Helper/Proxy" }
  }
}
```

The `Router` is a control node, not a domain role — its job is to write the **id of the next node to visit** into its output slot, and the graph runtime branches on that string. Hub-style topologies use it to iterate worker-by-worker; without it, the hub's outgoing edges would fan out to every spoke in parallel.

## Editing checklist

1. **Pick a starting point.** Copy a `predefined/*.json` into `loaded/` (or use the Topology page's "Export config…" button).
2. **Edit safely.** Inline JSON edits are fine; validation is permissive (loader only enforces "is a JSON object"). The runtime catches missing node ids, unreferenced edges, etc. at load time with a `ConfigError`.
3. **Class names.** Use the AGENT_TYPE labels (`Locator`, `Patcher`, ...) — they're shorter and match what `evomas/agents/types/__init__.py:TYPE_REGISTRY` recognizes.
4. **Add a tool whitelist** only when the class default is too broad (or too narrow). For most patchers, the class default `Patcher.DEFAULT_TOOLS` is the right baseline.
5. **Use `variant`** when you want a topology to read like its upstream paper — pulls prompts + tools from the matching catalog in `agent_types/`.
6. **Inline `prompts`** for one-off overrides (Router dispatch logic, custom dispatcher messages). Otherwise rely on the class default in `evomas/agents/types/<class>.py:DEFAULT_SYSTEM`.
7. **Wire edges deliberately.** Cycles are allowed and bounded by `EVOMAS_GRAPH_MAX_REVISITS × num_agents` super-steps; for a fan-out hub topology, use a `Router` class on the hub so dispatch is conditional, not parallel.

## Quick reference

| Question | Look here |
|---|---|
| What model knobs are accepted? | `evomas/config/loader.py` — `AgentConfig` Pydantic model |
| Which classes can I put in `class`? | `evomas/agents/types/__init__.py` — `TYPE_REGISTRY` |
| What does each class's prompt + tool default look like? | `evomas/agents/types/<class>.py` — `DEFAULT_SYSTEM` / `DEFAULT_USER` / `DEFAULT_TOOLS` |
| How do variants resolve? | `evomas/config/loader.py:93` — `resolve_variant_block` |
| How are tools whitelisted at runtime? | `evomas/agents/base_agent.py:70` |
| Which configs ship with EvoMas? | `evomas/config/predefined/` |
| How do I save my own? | `evomas/config/loaded/` (via UI export or direct file write) |
