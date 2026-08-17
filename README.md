<div align="center">

<img src="app/public/favicon.svg" alt="OpenDraco logo" width="96" height="96" />

# OpenDraco

**Open-source platform for designing, executing, evaluating, and comparing multi-agent topologies for Software Engineering tasks.**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/langgraph)
[![Ollama](https://img.shields.io/badge/Ollama-000000?logo=ollama&logoColor=white)](https://ollama.com/)
[![Angular](https://img.shields.io/badge/Angular-21-DD0031?logo=angular&logoColor=white)](https://angular.dev/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![SWE--bench](https://img.shields.io/badge/SWE--bench-Lite%20%2F%20Verified-blue)](https://www.swebench.com/)

</div>

Large Language Models increasingly power agentic solutions for complex Software Engineering (SE) tasks — program understanding, testing, code review, automated program repair (APR). Multi-agent systems address these tasks by coordinating specialized roles such as planning, code localization, patch generation, and review. Their effectiveness, however, is strongly shaped by the **communication topology**: which agents interact, and how information flows among them.

In existing systems that topology is usually hard-coded into the orchestration logic. Changing an agent, adding a feedback loop, or comparing alternative structures therefore takes substantial implementation effort. That coupling hinders reproducible experimentation and prevents topology from being studied as a design variable — and general-purpose workflow builders, while they simplify agent composition, offer limited support for *designing, executing, evaluating, and comparing* multi-agent architectures on SE tasks.

**OpenDraco turns multi-agent topology into a configurable, executable, and versioned artifact.** You model agents as nodes and communication channels as edges, and configure each agent's role, prompt, tools, model, and decoding parameters. OpenDraco compiles that specification into a [LangGraph](https://www.langchain.com/langgraph) workflow, so agents can be added, replaced, or rewired between executions **without modifying the framework's core implementation**. It supports both local models through [Ollama](https://ollama.com/) and external LLM APIs (OpenAI, Gemini).

A FastAPI backend exposes inference + evaluation as SSE streams; an Angular frontend renders the topology graph, the live tool-call timeline, and a Results page that diffs new runs against archived predictions. The shipped topologies cover the usual structural families — locator → patcher → reviewer chains, hubs with conditional dispatch, hierarchical trees, parallel ensembles.

## Task instantiations

OpenDraco is task-agnostic. A task is defined by three drop-in artifacts — tools, a topology config, and an evaluator — that the framework auto-discovers, with no edits to `opendraco/`, `api/`, or `app/` (see [Extending to a new problem type](#extending-to-a-new-problem-type)). Three instantiations ship with the repo:

| Instantiation | What it does | Ships as |
|---|---|---|
| **Automated program repair** — the benchmarked case, see [Benchmark](#benchmark-apr-on-swe-bench) | Runs a topology over SWE-bench instances and scores the emitted patches through the official Docker harness. | 8 predefined topologies (`chain`, `hyperagent_star`, `openhands_star`, `prometheus_tree`, …) + `run_swebench_evaluation.py` / `apply_and_test.py` |
| **Repository translation** | Locates files in a repo, rewrites them in the target language, reviews the output; graded by BLEU against `.gold` sidecars. | `translate.json` + `opendraco/tools/translate/` + `translate_eval.py` |
| **Tool-assisted web search** | Answers a free-form question with web-search tools instead of repo tools. | `websearch.json` + `opendraco/tools/websearch/` + `websearch_eval.py` |

The translation and web-search demos exist precisely to show that tasks beyond APR need no changes to the core implementation.

## Benchmark: APR on SWE-bench

APR is the instantiation OpenDraco has been measured on, integrated end-to-end with the [SWE-bench](https://www.swebench.com/) evaluation harness:

- Across **eight topologies** with a fixed local model, the number of resolved synthetic instances ranged from **three to five out of five**, while execution time ranged from **17 to 42 minutes**.
- On **23 SWE-bench Lite instances**, a sequential topology and a more complex one both resolved **two** issues — but the sequential topology required **39.78% less time** and **47.32% fewer tokens**.

The insight in this setting: **more agents do not necessarily produce better outcomes**, and topology introduces measurable effectiveness–cost trade-offs. Making that variable cheap to change, re-run, and compare is the point of the platform.

### The five synthetic instances

The "five out of five" above is a difficulty ladder of purpose-built repositories, each seeding exactly one bug with a pytest suite that fails until it's fixed. They exist because SWE-bench Lite instances are slow and coarse for topology comparison: a ladder from *one wrong operator* to *a bug that reads correctly line-by-line* separates topologies that a pass/fail on two Lite issues cannot.

| # | Difficulty | Repo | The seeded bug |
|---|---|---|---|
| 1 | Trivial | `EvoMas/evomas-instance-trivial` | `is_even.py` returns `n % 2 == 1` where it should return `n % 2 == 0`. `test_is_even.py` exercises positive, negative and zero inputs. |
| 2 | Easy | `EvoMas/evomas-instance-easy` | A small calculator module carrying one deliberate arithmetic bug. |
| 3 | Medium | `EvoMas/evomas-instance-medium` | `rotate.py:rotate_left` slices `arr[n:] + arr[:n]`, which silently breaks once `n >= len(arr)` — `rotate_left([1,2,3], 3)` yields `[]` instead of `[1,2,3]`. One-line fix: normalize with `n = n % len(arr)`. |
| 4 | Hard | `EvoMas/evomas-instance-hard` | `accumulator.py:accumulate(value, history=[])` — a mutable default argument shared across every call, so state leaks between them. Fix is `history=None` plus an `if history is None` guard. |
| 5 | Expert | `EvoMas/evomas-instance-expert` | `cleanup.py:remove_negatives` pops from the list it is iterating with `enumerate`, so indices shift and consecutive negatives are skipped. Every line reads correct in isolation; only the output values expose it. |

Each row is a **custom-subset** instance (`subset` = `split` = `custom`) pinned to a `base_commit`, so the ladder is reproducible across runs. Custom rows carry no `test_patch` / `FAIL_TO_PASS`, so the SWE-bench Docker harness can't grade them — score these with **`apply_and_test`** (clone → apply patch → pytest), which is what the Evaluation page selects automatically when every prediction row is custom.

<details>
<summary>JSONL rows — append to <code>swebench_instances.jsonl</code></summary>

```jsonl
{"repo": "EvoMas/evomas-instance-trivial", "instance_id": "custom-EvoMas-evomas-instance-trivial-18757fd", "base_commit": "18757fdacb59343425bf22a821a10d8978de7f5d", "problem_statement": "evomas-instance-trivial\nSynthetic SWE-bench instance for EvoMas APR evaluation - trivial difficulty.\n\nA one-function Python module (`is_even.py`) returns the wrong boolean: `n % 2 == 1` should be `n % 2 == 0`. A failing pytest suite (`test_is_even.py`) exercises the bug across positive, negative and zero inputs.", "hints_text": "", "subset": "custom", "split": "custom"}
{"repo": "EvoMas/evomas-instance-easy", "instance_id": "custom-EvoMas-evomas-instance-easy-fcf59bc", "base_commit": "fcf59bcfe0533b786f1b57e63bfdf1163c6905ed", "problem_statement": "evomas-test-instance\nSynthetic test repository for EvoMas APR evaluation.\n\nContains a simple Python calculator module with a deliberate bug for testing automated program repair.", "hints_text": "", "subset": "custom", "split": "custom"}
{"repo": "EvoMas/evomas-instance-medium", "instance_id": "custom-EvoMas-evomas-instance-medium-a406a76", "base_commit": "a406a76824b3f74bb4b808a2dc1e7d0aee0f7811", "problem_statement": "evomas-instance-medium\nSynthetic SWE-bench instance for EvoMas APR evaluation - medium difficulty.\n\n`rotate.py:rotate_left(arr, n)` slices the input with `arr[n:] + arr[:n]`. This works for `n < len(arr)` but silently breaks for `n >= len(arr)`: e.g. `rotate_left([1, 2, 3], 3)` returns `[]` instead of `[1, 2, 3]`, and `rotate_left([1, 2, 3], 5)` returns `[]` instead of `[2, 3, 1]`. The fix is one line - normalize `n` modulo the array length before the slice (`n = n % len(arr)`).", "hints_text": "", "subset": "custom", "split": "custom"}
{"repo": "EvoMas/evomas-instance-hard", "instance_id": "custom-EvoMas-evomas-instance-hard-ad94202", "base_commit": "ad94202ad8c9f02c2521fda1c7181d1c4af027b9", "problem_statement": "evomas-instance-hard\nSynthetic SWE-bench instance for EvoMas APR evaluation - hard difficulty.\n\nClassic Python pitfall: `accumulator.py:accumulate(value, history=[])` uses a mutable default argument, so every call without an explicit `history` shares the same list object. The test `test_independent_default_calls` fails because state leaks across calls. The fix is `history=None` + `if history is None: history = []`.", "hints_text": "", "subset": "custom", "split": "custom"}
{"repo": "EvoMas/evomas-instance-expert", "instance_id": "custom-EvoMas-evomas-instance-expert-a2e3735", "base_commit": "a2e3735795413732cdd80dc5d0b147e323425748", "problem_statement": "evomas-instance-expert\nSynthetic SWE-bench instance for EvoMas APR evaluation - expert difficulty.\n\n`cleanup.py:remove_negatives` mutates the list while iterating over it: after `items.pop(i)` every subsequent index shifts down by one but `enumerate(items)` keeps marching forward, so consecutive negative values get silently skipped. The function appears correct line-by-line - only the output values reveal the iterator-semantics bug. A correct fix uses a list comprehension, reverse iteration, or builds a new list.", "hints_text": "", "subset": "custom", "split": "custom"}
```

Or add them one at a time — the Inference page's custom-repo box does the same thing. `--subset` / `--split` are required but ignored in custom mode: the row is always tagged `custom`/`custom`. Omit `--custom-base-commit` to pin the current remote HEAD instead.

```bash
opendraco run instances --subset lite --split dev --output swebench_instances.jsonl \
  --custom-repo EvoMas/evomas-instance-trivial \
  --custom-problem "is_even.py returns n % 2 == 1 where it should return n % 2 == 0." \
  --custom-base-commit 18757fdacb59343425bf22a821a10d8978de7f5d
```

</details>

## Quick start

From a fresh clone to a topology graph in your browser — assumes Python 3.12+, Node 18+, Ollama, and Docker are already installed (see [Prerequisites](#prerequisites)).

```bash
# 1. Set up the venv, copy the .env files, clone + build the SWE-bench
#    harness (when Docker — plus WSL2 on Windows — is present), and
#    register the `opendraco` command on your $PATH
./install.sh                 # or .\install.ps1 on Windows

# 2. (optional) install.sh already copied opendraco/.env + api/.env from their
#    .example files — the defaults work for a local-only Ollama setup. Edit
#    them only if you need remote hosts or hosted-model API keys.

# 3. Pull the model used by the shipped predefined topologies
opendraco ollama pull qwen3.5:9b

# 4. Sanity-check the toolchain, then start the backend (terminal 1) and
#    the Angular frontend (terminal 2)
opendraco status
opendraco api
opendraco web
```

Open <http://localhost:4200>, pick a predefined topology (e.g. `hyperagent_star`), pick an instance from the dropdown, and hit **Run**. The Inference page streams the live tool-call timeline; when it's done, the Results page shows the patch + harness verdict side-by-side.

Prefer a CLI-only flow? Skip step 4 and run:

```bash
opendraco run instances  --subset lite --split dev --output swebench_instances.jsonl --limit 1
opendraco run prediction --instances swebench_instances.jsonl --config hyperagent_star --output opendraco_predictions.jsonl
opendraco run evaluation --predictions opendraco_predictions.jsonl --subset lite --split dev
```

The same three commands drive every task type — swap `--config` for another topology and `--evaluator` / the Evaluation page for the matching scorer. To compare topologies, rerun step 2 with a different `--config` against the same instances file.

## Prerequisites

| Tool | Why | Where to get it |
|---|---|---|
| Python 3.12+ (3.12.6 is the dev baseline) | Runs the agent framework and the FastAPI backend. | https://www.python.org/downloads/ |
| Ollama | Hosts the local LLM each agent calls. | https://ollama.com/download |
| Docker (Desktop on Windows/macOS, Engine on Linux) | Required for SWE-bench evaluation (the harness runs each instance in a container). Not needed for inference-only flows. On Windows the harness invocation is shelled through WSL; on macOS / Linux it runs natively. | https://www.docker.com/products/docker-desktop/  ·  https://docs.docker.com/engine/install/ |
| Node.js 18+ | Builds and serves the Angular frontend. | https://nodejs.org/ |
| WSL2 (Windows only) | The SWE-bench harness ships POSIX-only steps; on Windows the API server shells out via `wsl ...`. Not needed on macOS / Linux. | https://learn.microsoft.com/windows/wsl/install |

## Install

Windows (PowerShell):

```powershell
.\install.ps1
```

Linux / macOS (bash):

```bash
chmod +x install.sh 
bash install.sh
```

The install script checks for the prerequisites above — **only Python is mandatory** (it aborts without it); Ollama, Docker, Node.js, and WSL2 are feature-gated, so the installer warns and continues without them. It then creates a venv at `~/.opendraco-venv` (reusing it if already present, kept in the user's home so the repo stays free of build artefacts), runs `pip install -e ".[dev]"` (which reads `pyproject.toml` for dependencies + registers the `opendraco` console command), regenerates `requirements.txt` as a lockfile, registers an `opendraco` Jupyter kernel, installs the Angular frontend's npm dependencies (when npm is present), clones **and builds** the SWE-bench harness into `<repo>/SWE-bench` when its prerequisites are present — Docker on Linux/macOS, Docker + WSL2 on Windows (see [SWE-bench harness](#swe-bench-harness-local-evaluation-only)); otherwise it skips that step with a note. Finally it copies `opendraco/.env` + `api/.env` from their `.example` files (never clobbering existing ones), and appends an `opendraco` function to your shell rc (`$PROFILE` on Windows, `~/.zshrc` / `~/.bashrc` / `~/.config/fish/config.fish` on Linux/macOS) so the command is reachable from any directory.

Open a new shell (or `source` the rc file) so the profile change takes effect, then verify — `opendraco status` prints a colour-coded readiness check of the whole toolchain:

```bash
opendraco --help
opendraco status
```

### Setup fails or imports break after an upgrade

The install script is intentionally non-destructive — it reuses any existing `~/.opendraco-venv`. If a previous install left the venv in a broken state (missing packages, mismatched versions, `ModuleNotFoundError`), delete it and rerun the installer (`rm -r` works in both bash and PowerShell, which aliases it to `Remove-Item -Recurse`):

```
rm -r ~/.opendraco-venv
```

Then rerun the platform-appropriate install command from the Install section above. (`uninstall.sh` / `uninstall.ps1` remove the venv and the rest of the install for you — see [Uninstall](#uninstall).)

### Uninstall

To reverse the install — remove the `~/.opendraco-venv`, strip the `opendraco` function from your shell rc / `$PROFILE`, unregister the `opendraco` Jupyter kernel, and clear `app/node_modules`:

```bash
bash uninstall.sh            # or .\uninstall.ps1 on Windows
```

Your data is left untouched by default. Add `--purge` to *also* delete the `SWE-bench/` clone and the `opendraco/.env` + `api/.env` files (which hold your API keys):

```bash
bash uninstall.sh --purge    # or .\uninstall.ps1 --purge on Windows
```

Open a new shell afterwards so the removed `opendraco` function clears from your session.

### SWE-bench harness (local evaluation only)

`opendraco run evaluation` (and the Evaluation page) defaults to `--local`, which runs the official **SWE-bench Docker harness**. That harness is *not* a pip dependency of OpenDraco — it lives in a sibling clone at `<repo>/SWE-bench` with its own venv at `SWE-bench/venv/`. `install.sh` / `install.ps1` **clone the repo and build its venv for you** (idempotently) — but only when the harness's prerequisites are present, since there's no point setting it up on a box that can't run it: **Docker** on Linux/macOS, **Docker + WSL2** on Windows (the venv is POSIX-only, so on Windows the installer builds it inside WSL). If those aren't installed, the installer skips the whole step with a note; install them and rerun, or follow the manual steps below. OpenDraco auto-discovers the harness: it uses the active interpreter if `swebench` is importable, otherwise it falls back to `<repo>/SWE-bench/venv/`.

**Manual setup (fallback when the installer skipped it).** The harness is **POSIX-only**, so the venv must be a Linux venv. On **Windows you must do this inside WSL** — open a WSL shell first (`wsl`), then run the commands below there. On Linux / macOS run them directly. (`git clone` is only needed if the installer didn't already create `SWE-bench/`.)

```bash
# On Windows ONLY: drop into WSL first, then continue inside it
wsl

# From the OpenDraco repo root (Linux / macOS / WSL)
git clone https://github.com/SWE-bench/SWE-bench.git   # skip if install.* already cloned it
cd SWE-bench
python3 -m venv venv
source venv/bin/activate      # activate the venv first
pip install -e .              # installs the `swebench` package into the venv
```

This step is only needed for **local** evaluation. Inference-only flows and `opendraco run evaluation --remote` (the hosted leaderboard via `sb-cli`) don't require it. The `SWE-bench/` clone stays out of git (it's git-ignored / excluded from the public mirror).

## Environment

Two `.env` files drive the framework. `install.sh` / `install.ps1` already copy them from the `.example` files on first run (without overwriting existing ones), so you normally just edit the values. To create them by hand — `cp` is an alias for `Copy-Item` in PowerShell, so the same line works in both shells:

```
cp opendraco/.env.example opendraco/.env
cp api/.env.example    api/.env
```

### `opendraco/.env` — agent runtime

| Variable | Purpose |
|---|---|
| `OLLAMA_BASE_URL` | URL the Ollama server every `ollama/*` agent targets. Default: `http://localhost:11434`. |
| `GOOGLE_API_KEY` | Required only when at least one agent's `model` starts with `gemini/`. Get a key at [Google AI Studio](https://aistudio.google.com/app/apikey). |
| `OPENAI_API_KEY` | Required only when at least one agent's `model` starts with `openai/`. Get a key at [OpenAI Platform](https://platform.openai.com/api-keys). |
| `OPENAI_BASE_URL` | Optional. Override the OpenAI endpoint — useful for Azure OpenAI, OpenRouter, or a local LiteLLM proxy. |
| `WANDB_API_KEY` | Optional. Only needed if you call `init_weave()`. |
| `OPENDRACO_GRAPH_MAX_REVISITS` | Optional. Per-node revisit budget for the LangGraph runtime; total super-step cap is `OPENDRACO_GRAPH_MAX_REVISITS × num_agents`. Bounds cycles in cyclic topologies. Default: `2`. |
| `SWEBENCH_API_KEY` | Required for `opendraco run evaluation --remote` (hosted SWE-bench leaderboard via `sb-cli`). Not needed for local Docker evaluation. |
| `SWEBENCH_DIR` | Optional. Location of the local SWE-bench repo clone used by `--local` evaluation; its harness venv must live at `<SWEBENCH_DIR>/venv`. Relative paths resolve against the repo root. Default: `<repo>/SWE-bench`. |
| `RESULTS_DIR` | Optional. Where predictions + evaluations are written. Relative paths resolve against the repo root. Default: `<repo>/results`. Also accepted in `api/.env`, where it takes precedence. |

> **Local evaluation needs the SWE-bench repo on disk.** The harness is discovered at `SWEBENCH_DIR` (default `<repo>/SWE-bench/`, venv at `<SWEBENCH_DIR>/venv/`). Clone it as described in [SWE-bench harness (local evaluation only)](#swe-bench-harness-local-evaluation-only). Inference-only flows and `--remote` evaluation don't need it.

### `api/.env` — FastAPI backend

| Variable | Purpose |
|---|---|
| `API_HOST`, `API_PORT` | Bind address for the FastAPI backend. Default: `0.0.0.0:8000`. |
| `RESULTS_DIR` | Same key as in `opendraco/.env`; setting it here **overrides** the opendraco value. Useful for running the API against a per-environment results folder (e.g. an integration-test matrix) without touching the framework-wide setting. |

Each agent picks its LLM provider via the `model` field's prefix (LiteLLM-style):

```json
"locator":  { "class": "Locator",      "model": "ollama/qwen3.5:9b",     ... }
"patcher":  { "class": "Patcher",      "model": "gemini/gemini-1.5-pro", ... }
"reviewer": { "class": "Reviewer",     "model": "openai/gpt-4o-mini",     ... }
```

The full set of built-in agent classes is `Router`, `Locator`, `Patcher`, `Reviewer`, `Bug reproduction`, `Helper/Proxy`, and `Base agent` (a generic LLM-with-tools fallback). See [opendraco/config/TOPOLOGY_CONFIG.md](./opendraco/config/TOPOLOGY_CONFIG.md) for what each one is for.

A bare model name without a `/` (e.g. `"qwen3.5:9b"`) is treated as `ollama/...` for backward compatibility with the shipped predefined configs.

## Topology configs

A run is driven by one JSON file describing the agent graph: which agents run, in what order, with which prompts, tools, and model knobs. Two folders hold them:

| Folder | What lives there |
|---|---|
| `opendraco/config/predefined/` | Ships with OpenDraco — reference topologies (one per upstream multi-agent paper). Treated as read-only by the Topology page: edits here are kept in git. |
| `opendraco/config/loaded/` | User-uploaded or exported configs. Empty on a fresh clone. The Topology page's **Export config…** button writes here; `POST /api/topology/save` does too. Files here override `predefined/` when names collide. |

There's also `opendraco/config/agent_types/` — per-upstream-repo *variant catalogs* (`OpenHands.json`, `joycode-agent.json`, etc.). A config block can reference one with `"variant": "<RepoId>:<AgentName>"` to inherit that upstream agent's prompts and tools without copying them into the JSON.

### Minimal shape

```jsonc
{
  "id":          "my-chain",
  "description": "Locator → Patcher → Reviewer → Finalizer.",
  "entry":       "locator",
  "end":         "finalizer",
  "edges": [
    { "from": "locator",  "to": "patcher"  },
    { "from": "patcher",  "to": "reviewer" },
    { "from": "reviewer", "to": "finalizer" }
  ],
  "agents": {
    "locator":   { "class": "Locator",      "model": "ollama/qwen3.5:9b" },
    "patcher":   { "class": "Patcher",      "model": "ollama/qwen3.5:9b" },
    "reviewer":  { "class": "Reviewer",     "model": "ollama/qwen3.5:9b" },
    "finalizer": { "class": "Helper/Proxy", "model": "ollama/qwen3.5:9b" }
  }
}
```

Edits are picked up on every `/api/inference/run` call — no API restart needed. For the full schema (every accepted field, tool-whitelist semantics, variant resolution, worked examples for chain / star / conditional dispatch), see [opendraco/config/TOPOLOGY_CONFIG.md](./opendraco/config/TOPOLOGY_CONFIG.md).

## Extending to a new problem type

Nothing in the framework core is APR-specific. OpenDraco auto-discovers tools, topology configs, and evaluator scripts, so adding a brand-new problem type (program repair, file translation, web research, math proof checking, …) is **three drop-in files**, no edits in framework code:

- a `@tool`-decorated Python module under `opendraco/tools/<bundle>/` (any new tool the agents need — `opendraco/tools/repo/<bundle>/` is reserved for upstream-aligned repo-variant bundles)
- a topology JSON under `opendraco/config/predefined/` (the agent graph + prompts)
- an evaluator script under `scripts/evaluation/` (reads a predictions JSONL, writes a SWE-bench-shaped report)

Restart the API, hard-refresh the frontend, and the new tools, the new topology, and the new evaluator all appear in the UI. The end-to-end guide — covering the drop-in shape for each artifact, the optional `OPENDRACO_EVALUATOR` manifest, and the shipped translate / websearch tasks as worked templates — lives in [docs/adding_a_new_problem.md](./docs/adding_a_new_problem.md).

## CLI Commands

The `opendraco` command wraps every entry point. Run `opendraco <command> --help` for details on each command's args and options.

### Ollama (model management)

Every `ollama` subcommand respects `OLLAMA_BASE_URL` from `opendraco/.env`, so a remote Ollama works the same way as a local one.

**`opendraco ollama pull <model>`** — pull a model tag onto the configured Ollama server.

```bash
opendraco ollama pull qwen3.5:9b
```

**`opendraco ollama list`** — list models already present on the server.

```bash
opendraco ollama list
```

**`opendraco ollama serve [--cpu-only]`** — start the Ollama daemon bound to `OLLAMA_BASE_URL`. `--cpu-only` exports `OLLAMA_NO_CUDA=1` (useful when a tiny GPU would OOM on the model you're targeting).

```bash
opendraco ollama serve --cpu-only
```

### Run (inference + evaluation pipeline)

**`opendraco run instances`** — generate the SWE-bench instances JSONL by pulling a slice of the HuggingFace dataset. Pass `--custom-repo` + `--custom-problem` to append one synthetic row instead.

```bash
opendraco run instances --subset lite --split dev --output swebench_instances.jsonl --limit 5
```

**`opendraco run prediction`** — drive the configured LangGraph topology over every instance in the JSONL and emit one `model_patch` per line.

```bash
opendraco run prediction --instances swebench_instances.jsonl --output opendraco_predictions.jsonl --config hyperagent_star
```

**`opendraco run evaluation`** — score a predictions JSONL. Default `--local` runs the SWE-bench Docker harness (full per-instance logs under `<report-dir>/logs/`; needs Docker, +WSL on Windows). `--remote` submits to [swebench.com](https://www.swebench.com/) via `sb-cli` — verdicts only, no logs, requires `SWEBENCH_API_KEY`.

```bash
opendraco run evaluation --predictions opendraco_predictions.jsonl --subset lite --split dev
opendraco run evaluation --remote --predictions opendraco_predictions.jsonl --subset lite --split dev
```

### Re-evaluation / debugging utilities

**`opendraco apply`** — re-run pytest against a stored prediction's patch (clone → apply → pytest). Useful for inspecting *why* a custom-repo instance didn't resolve without rerunning inference.

```bash
opendraco apply \
  --predictions opendraco_predictions.jsonl \
  --instances   swebench_instances.jsonl \
  --instance-id sqlfluff__sqlfluff-1625
```

**`opendraco notebook`** — export a reproduce-this-run Jupyter notebook. Two input modes:
- From a prediction JSONL (`--predictions`): includes the comparison section that diffs a fresh re-run against the original `model_patch`. Mirrors the Results page button.
- From inputs (`--config` + `--instances`): no baseline to diff against, so the comparison section is skipped. Mirrors the Inference page download button.

`--evaluator` is required and baked into the notebook's section 5; pass the filename stem under `scripts/evaluation/` (no `.py`) that matches your task — `apply_and_test` for code-repair via pytest, `run_swebench_evaluation` for the SWE-bench POSIX harness, `translate_eval` for BLEU-graded translation tasks, etc.

```bash
opendraco notebook --predictions results/predictions/prediction-<run-id>.jsonl --evaluator apply_and_test
opendraco notebook --config hyperagent_star --instances swebench_instances.jsonl --evaluator run_swebench_evaluation --output reproducer.ipynb
```

### Tests

**`opendraco test [--integration]`** — run the backend pytest suite *and* the frontend Angular tests. `--backend-only` / `--frontend-only` scope to one half; `--integration` sets `OPENDRACO_RUN_INTEGRATION=1` for opt-in slow tests (the SWE-bench matrix spec, Ollama connectivity check). Args after `--` forward verbatim to the inner runner.

```bash
opendraco test                                         # full suite (pytest + ng test)
opendraco test --backend-only -- -k apply_description  # pytest, filter by name
opendraco test --frontend-only --integration           # opt into the integration matrix
```

### Servers

**`opendraco web`** — start the Angular frontend dev server on `:4200`. Reads `apiBaseUrl` from `app/src/environments/environment.ts`.

```bash
opendraco web
```

**`opendraco api`** — start the FastAPI backend on `API_HOST:API_PORT` (defaults `0.0.0.0:8000`). The inference / evaluation / results endpoints used by the frontend live here.

```bash
opendraco api
```

### Diagnostics

**`opendraco status`** — a read-only, colour-coded doctor check. Reports the prerequisites (python, git, ollama, docker, node), the `opendraco/.env` + `api/.env` files, the `~/.opendraco-venv`, the SWE-bench clone + its harness venv, and whether the Docker daemon and Ollama server are reachable. Run it after `install.sh` / `install.ps1` to confirm the toolchain is ready.

```bash
opendraco status
```

## Acknowledgments

The APR instantiation builds directly on the [SWE-bench](https://www.swebench.com/) evaluation framework — its Docker harness, dataset format, and `subset/split` semantics are reused verbatim, with custom-row support layered on top for the synthetic-instance flow. The instance/prediction JSONL shape is also what the task-agnostic evaluator contract is modelled on, so non-APR tasks reuse the same pipeline.

The shipped predefined topologies are OpenDraco-authored, but their prompts and tool palettes mirror 22 open-source multi-agent / coding projects (OpenHands, HyperAgent, JoyCode, Lingma SWE-GPT, ExpeRepair, SWE-agent, aider, claude-coder, trae-agent, …). OpenDraco re-implements every tool from scratch against the MCP binding contract — no upstream code is vendored — so the credit covers prompt **design**, tool **naming**, and **intended behaviour**. Two acknowledgement files carry the full provenance with commit-pinned `source_url` deep-links and per-repo license posture:

- [`opendraco/config/agent_types/ACKNOWLEDGEMENTS.md`](./opendraco/config/agent_types/ACKNOWLEDGEMENTS.md) — agent-prompt catalogue (22 repos, the variants surfaced in the Topology page picker).
- [`opendraco/tools/repo/ACKNOWLEDGEMENTS.md`](./opendraco/tools/repo/ACKNOWLEDGEMENTS.md) — tool-implementation catalogue (12 repos, the per-`<repo>/` subdirs under `opendraco/tools/repo/`).

The framework itself is built on [LangChain](https://www.langchain.com/) + [LangGraph](https://www.langchain.com/langgraph) for the agent graph runtime, [Ollama](https://ollama.com/) / [LiteLLM](https://github.com/BerriAI/litellm)-style model dispatch, [FastAPI](https://fastapi.tiangolo.com/) for the backend, and [Angular](https://angular.dev/) for the frontend topology canvas.
