<div align="center">

<img src="app/public/favicon.svg" alt="EvoMas logo" width="96" height="96" />

# EvoMas

**Evolutionary multi-agent framework for [SWE-bench](https://www.swebench.com/)–style automated program repair.**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/langgraph)
[![Ollama](https://img.shields.io/badge/Ollama-000000?logo=ollama&logoColor=white)](https://ollama.com/)
[![Angular](https://img.shields.io/badge/Angular-21-DD0031?logo=angular&logoColor=white)](https://angular.dev/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![SWE--bench](https://img.shields.io/badge/SWE--bench-Lite%20%2F%20Verified-blue)](https://www.swebench.com/)

</div>

EvoMas wires LangGraph multi-agent topologies (locator → patcher → reviewer chains, hubs with conditional dispatch, parallel ensembles) over local Ollama or hosted OpenAI / Gemini models, runs them against SWE-bench instances, and scores the resulting patches through the official Docker harness. A FastAPI backend exposes inference + evaluation as SSE streams; an Angular frontend renders the topology graph, the live tool-call timeline, and a Results page that diffs new runs against archived predictions.

## Quick start

From a fresh clone to a topology graph in your browser — assumes Python 3.12+, Node 18+, Ollama, and Docker are already installed (see [Prerequisites](#prerequisites)).

```bash
# 1. Set up the venv, copy the .env files, clone + build the SWE-bench
#    harness (when Docker — plus WSL2 on Windows — is present), and
#    register the `evomas` command on your $PATH
./install.sh                 # or .\install.ps1 on Windows

# 2. (optional) install.sh already copied evomas/.env + api/.env from their
#    .example files — the defaults work for a local-only Ollama setup. Edit
#    them only if you need remote hosts or hosted-model API keys.

# 3. Pull the model used by the shipped predefined topologies
evomas ollama pull qwen3.5:9b

# 4. Sanity-check the toolchain, then start the backend (terminal 1) and
#    the Angular frontend (terminal 2)
evomas status
evomas api
evomas web
```

Open <http://localhost:4200>, pick a predefined topology (e.g. `hyperagent_star`), pick an instance from the dropdown, and hit **Run**. The Inference page streams the live tool-call timeline; when it's done, the Results page shows the patch + harness verdict side-by-side.

Prefer a CLI-only flow? Skip step 4 and run:

```bash
evomas run instances  --subset lite --split dev --output swebench_instances.jsonl --limit 1
evomas run prediction --instances swebench_instances.jsonl --config hyperagent_star --output evomas_predictions.jsonl
evomas run evaluation --predictions evomas_predictions.jsonl --subset lite --split dev
```

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

The install script checks for the prerequisites above — **only Python is mandatory** (it aborts without it); Ollama, Docker, Node.js, and WSL2 are feature-gated, so the installer warns and continues without them. It then creates a venv at `~/.evomas-venv` (reusing it if already present, kept in the user's home so the repo stays free of build artefacts), runs `pip install -e ".[dev]"` (which reads `pyproject.toml` for dependencies + registers the `evomas` console command), regenerates `requirements.txt` as a lockfile, registers an `evomas` Jupyter kernel, installs the Angular frontend's npm dependencies (when npm is present), clones **and builds** the SWE-bench harness into `<repo>/SWE-bench` when its prerequisites are present — Docker on Linux/macOS, Docker + WSL2 on Windows (see [SWE-bench harness](#swe-bench-harness-local-evaluation-only)); otherwise it skips that step with a note. Finally it copies `evomas/.env` + `api/.env` from their `.example` files (never clobbering existing ones), and appends an `evomas` function to your shell rc (`$PROFILE` on Windows, `~/.zshrc` / `~/.bashrc` / `~/.config/fish/config.fish` on Linux/macOS) so the command is reachable from any directory.

Open a new shell (or `source` the rc file) so the profile change takes effect, then verify — `evomas status` prints a colour-coded readiness check of the whole toolchain:

```bash
evomas --help
evomas status
```

### Setup fails or imports break after an upgrade

The install script is intentionally non-destructive — it reuses any existing `~/.evomas-venv`. If a previous install left the venv in a broken state (missing packages, mismatched versions, `ModuleNotFoundError`), delete it and rerun the installer (`rm -r` works in both bash and PowerShell, which aliases it to `Remove-Item -Recurse`):

```
rm -r ~/.evomas-venv
```

Then rerun the platform-appropriate install command from the Install section above. (`uninstall.sh` / `uninstall.ps1` remove the venv and the rest of the install for you — see [Uninstall](#uninstall).)

### Uninstall

To reverse the install — remove the `~/.evomas-venv`, strip the `evomas` function from your shell rc / `$PROFILE`, unregister the `evomas` Jupyter kernel, and clear `app/node_modules`:

```bash
bash uninstall.sh            # or .\uninstall.ps1 on Windows
```

Your data is left untouched by default. Add `--purge` to *also* delete the `SWE-bench/` clone and the `evomas/.env` + `api/.env` files (which hold your API keys):

```bash
bash uninstall.sh --purge    # or .\uninstall.ps1 --purge on Windows
```

Open a new shell afterwards so the removed `evomas` function clears from your session.

### SWE-bench harness (local evaluation only)

`evomas run evaluation` (and the Evaluation page) defaults to `--local`, which runs the official **SWE-bench Docker harness**. That harness is *not* a pip dependency of EvoMas — it lives in a sibling clone at `<repo>/SWE-bench` with its own venv at `SWE-bench/venv/`. `install.sh` / `install.ps1` **clone the repo and build its venv for you** (idempotently) — but only when the harness's prerequisites are present, since there's no point setting it up on a box that can't run it: **Docker** on Linux/macOS, **Docker + WSL2** on Windows (the venv is POSIX-only, so on Windows the installer builds it inside WSL). If those aren't installed, the installer skips the whole step with a note; install them and rerun, or follow the manual steps below. EvoMas auto-discovers the harness: it uses the active interpreter if `swebench` is importable, otherwise it falls back to `<repo>/SWE-bench/venv/`.

**Manual setup (fallback when the installer skipped it).** The harness is **POSIX-only**, so the venv must be a Linux venv. On **Windows you must do this inside WSL** — open a WSL shell first (`wsl`), then run the commands below there. On Linux / macOS run them directly. (`git clone` is only needed if the installer didn't already create `SWE-bench/`.)

```bash
# On Windows ONLY: drop into WSL first, then continue inside it
wsl

# From the EvoMas repo root (Linux / macOS / WSL)
git clone https://github.com/SWE-bench/SWE-bench.git   # skip if install.* already cloned it
cd SWE-bench
python3 -m venv venv
source venv/bin/activate      # activate the venv first
pip install -e .              # installs the `swebench` package into the venv
```

This step is only needed for **local** evaluation. Inference-only flows and `evomas run evaluation --remote` (the hosted leaderboard via `sb-cli`) don't require it. The `SWE-bench/` clone stays out of git (it's git-ignored / excluded from the public mirror).

## Environment

Two `.env` files drive the framework. `install.sh` / `install.ps1` already copy them from the `.example` files on first run (without overwriting existing ones), so you normally just edit the values. To create them by hand — `cp` is an alias for `Copy-Item` in PowerShell, so the same line works in both shells:

```
cp evomas/.env.example evomas/.env
cp api/.env.example    api/.env
```

### `evomas/.env` — agent runtime

| Variable | Purpose |
|---|---|
| `OLLAMA_BASE_URL` | URL the Ollama server every `ollama/*` agent targets. Default: `http://localhost:11434`. |
| `GOOGLE_API_KEY` | Required only when at least one agent's `model` starts with `gemini/`. Get a key at [Google AI Studio](https://aistudio.google.com/app/apikey). |
| `OPENAI_API_KEY` | Required only when at least one agent's `model` starts with `openai/`. Get a key at [OpenAI Platform](https://platform.openai.com/api-keys). |
| `OPENAI_BASE_URL` | Optional. Override the OpenAI endpoint — useful for Azure OpenAI, OpenRouter, or a local LiteLLM proxy. |
| `WANDB_API_KEY` | Optional. Only needed if you call `init_weave()`. |
| `EVOMAS_GRAPH_MAX_REVISITS` | Optional. Per-node revisit budget for the LangGraph runtime; total super-step cap is `EVOMAS_GRAPH_MAX_REVISITS × num_agents`. Bounds cycles in cyclic topologies. Default: `2`. |
| `SWEBENCH_API_KEY` | Required for `evomas run evaluation --remote` (hosted SWE-bench leaderboard via `sb-cli`). Not needed for local Docker evaluation. |
| `SWEBENCH_DIR` | Optional. Location of the local SWE-bench repo clone used by `--local` evaluation; its harness venv must live at `<SWEBENCH_DIR>/venv`. Relative paths resolve against the repo root. Default: `<repo>/SWE-bench`. |
| `RESULTS_DIR` | Optional. Where predictions + evaluations are written. Relative paths resolve against the repo root. Default: `<repo>/results`. Also accepted in `api/.env`, where it takes precedence. |

> **Local evaluation needs the SWE-bench repo on disk.** The harness is discovered at `SWEBENCH_DIR` (default `<repo>/SWE-bench/`, venv at `<SWEBENCH_DIR>/venv/`). Clone it as described in [SWE-bench harness (local evaluation only)](#swe-bench-harness-local-evaluation-only). Inference-only flows and `--remote` evaluation don't need it.

### `api/.env` — FastAPI backend

| Variable | Purpose |
|---|---|
| `API_HOST`, `API_PORT` | Bind address for the FastAPI backend. Default: `0.0.0.0:8000`. |
| `RESULTS_DIR` | Same key as in `evomas/.env`; setting it here **overrides** the evomas value. Useful for running the API against a per-environment results folder (e.g. an integration-test matrix) without touching the framework-wide setting. |

Each agent picks its LLM provider via the `model` field's prefix (LiteLLM-style):

```json
"locator":  { "class": "Locator",      "model": "ollama/qwen3.5:9b",     ... }
"patcher":  { "class": "Patcher",      "model": "gemini/gemini-1.5-pro", ... }
"reviewer": { "class": "Reviewer",     "model": "openai/gpt-4o-mini",     ... }
```

The full set of built-in agent classes is `Router`, `Locator`, `Patcher`, `Reviewer`, `Bug reproduction`, `Helper/Proxy`, and `Base agent` (a generic LLM-with-tools fallback). See [evomas/config/TOPOLOGY_CONFIG.md](./evomas/config/TOPOLOGY_CONFIG.md) for what each one is for.

A bare model name without a `/` (e.g. `"qwen3.5:9b"`) is treated as `ollama/...` for backward compatibility with the shipped predefined configs.

## Topology configs

A run is driven by one JSON file describing the agent graph: which agents run, in what order, with which prompts, tools, and model knobs. Two folders hold them:

| Folder | What lives there |
|---|---|
| `evomas/config/predefined/` | Ships with EvoMas — reference topologies (one per upstream multi-agent paper). Treated as read-only by the Topology page: edits here are kept in git. |
| `evomas/config/loaded/` | User-uploaded or exported configs. Empty on a fresh clone. The Topology page's **Export config…** button writes here; `POST /api/topology/save` does too. Files here override `predefined/` when names collide. |

There's also `evomas/config/agent_types/` — per-upstream-repo *variant catalogs* (`OpenHands.json`, `joycode-agent.json`, etc.). A config block can reference one with `"variant": "<RepoId>:<AgentName>"` to inherit that upstream agent's prompts and tools without copying them into the JSON.

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

Edits are picked up on every `/api/inference/run` call — no API restart needed. For the full schema (every accepted field, tool-whitelist semantics, variant resolution, worked examples for chain / star / conditional dispatch), see [evomas/config/TOPOLOGY_CONFIG.md](./evomas/config/TOPOLOGY_CONFIG.md).

## Extending to a new problem type

EvoMas auto-discovers tools, topology configs, and evaluator scripts — adding a brand-new problem type (program repair, file translation, math proof checking, etc.) is **three drop-in files**, no edits in framework code:

- a `@tool`-decorated Python module under `evomas/tools/<bundle>/` (any new tool the agents need — `evomas/tools/repo/<bundle>/` is reserved for upstream-aligned repo-variant bundles)
- a topology JSON under `evomas/config/predefined/` (the agent graph + prompts)
- an evaluator script under `scripts/evaluation/` (reads a predictions JSONL, writes a SWE-bench-shaped report)

Restart the API, hard-refresh the frontend, and the new tools, the new topology, and the new evaluator all appear in the UI. The end-to-end guide — covering the drop-in shape for each artifact, the optional `EVOMAS_EVALUATOR` manifest, and the worked translate-task demo as a template — lives in [docs/adding_a_new_problem.md](./docs/adding_a_new_problem.md).

## CLI Commands

The `evomas` command wraps every entry point. Run `evomas <command> --help` for details on each command's args and options.

### Ollama (model management)

Every `ollama` subcommand respects `OLLAMA_BASE_URL` from `evomas/.env`, so a remote Ollama works the same way as a local one.

**`evomas ollama pull <model>`** — pull a model tag onto the configured Ollama server.

```bash
evomas ollama pull qwen3.5:9b
```

**`evomas ollama list`** — list models already present on the server.

```bash
evomas ollama list
```

**`evomas ollama serve [--cpu-only]`** — start the Ollama daemon bound to `OLLAMA_BASE_URL`. `--cpu-only` exports `OLLAMA_NO_CUDA=1` (useful when a tiny GPU would OOM on the model you're targeting).

```bash
evomas ollama serve --cpu-only
```

### Run (inference + evaluation pipeline)

**`evomas run instances`** — generate the SWE-bench instances JSONL by pulling a slice of the HuggingFace dataset. Pass `--custom-repo` + `--custom-problem` to append one synthetic row instead.

```bash
evomas run instances --subset lite --split dev --output swebench_instances.jsonl --limit 5
```

**`evomas run prediction`** — drive the configured LangGraph topology over every instance in the JSONL and emit one `model_patch` per line.

```bash
evomas run prediction --instances swebench_instances.jsonl --output evomas_predictions.jsonl --config hyperagent_star
```

**`evomas run evaluation`** — score a predictions JSONL. Default `--local` runs the SWE-bench Docker harness (full per-instance logs under `<report-dir>/logs/`; needs Docker, +WSL on Windows). `--remote` submits to [swebench.com](https://www.swebench.com/) via `sb-cli` — verdicts only, no logs, requires `SWEBENCH_API_KEY`.

```bash
evomas run evaluation --predictions evomas_predictions.jsonl --subset lite --split dev
evomas run evaluation --remote --predictions evomas_predictions.jsonl --subset lite --split dev
```

### Re-evaluation / debugging utilities

**`evomas apply`** — re-run pytest against a stored prediction's patch (clone → apply → pytest). Useful for inspecting *why* a custom-repo instance didn't resolve without rerunning inference.

```bash
evomas apply \
  --predictions evomas_predictions.jsonl \
  --instances   swebench_instances.jsonl \
  --instance-id sqlfluff__sqlfluff-1625
```

**`evomas notebook`** — export a reproduce-this-run Jupyter notebook. Two input modes:
- From a prediction JSONL (`--predictions`): includes the comparison section that diffs a fresh re-run against the original `model_patch`. Mirrors the Results page button.
- From inputs (`--config` + `--instances`): no baseline to diff against, so the comparison section is skipped. Mirrors the Inference page download button.

`--evaluator` is required and baked into the notebook's section 5; pass the filename stem under `scripts/evaluation/` (no `.py`) that matches your task — `apply_and_test` for code-repair via pytest, `run_swebench_evaluation` for the SWE-bench POSIX harness, `translate_eval` for BLEU-graded translation tasks, etc.

```bash
evomas notebook --predictions results/predictions/prediction-<run-id>.jsonl --evaluator apply_and_test
evomas notebook --config hyperagent_star --instances swebench_instances.jsonl --evaluator run_swebench_evaluation --output reproducer.ipynb
```

### Tests

**`evomas test [--integration]`** — run the backend pytest suite *and* the frontend Angular tests. `--backend-only` / `--frontend-only` scope to one half; `--integration` sets `EVOMAS_RUN_INTEGRATION=1` for opt-in slow tests (the SWE-bench matrix spec, Ollama connectivity check). Args after `--` forward verbatim to the inner runner.

```bash
evomas test                                         # full suite (pytest + ng test)
evomas test --backend-only -- -k apply_description  # pytest, filter by name
evomas test --frontend-only --integration           # opt into the integration matrix
```

### Servers

**`evomas web`** — start the Angular frontend dev server on `:4200`. Reads `apiBaseUrl` from `app/src/environments/environment.ts`.

```bash
evomas web
```

**`evomas api`** — start the FastAPI backend on `API_HOST:API_PORT` (defaults `0.0.0.0:8000`). The inference / evaluation / results endpoints used by the frontend live here.

```bash
evomas api
```

### Diagnostics

**`evomas status`** — a read-only, colour-coded doctor check. Reports the prerequisites (python, git, ollama, docker, node), the `evomas/.env` + `api/.env` files, the `~/.evomas-venv`, the SWE-bench clone + its harness venv, and whether the Docker daemon and Ollama server are reachable. Run it after `install.sh` / `install.ps1` to confirm the toolchain is ready.

```bash
evomas status
```

## Acknowledgments

EvoMas builds directly on the [SWE-bench](https://www.swebench.com/) evaluation framework — its Docker harness, dataset format, and `subset/split` semantics are reused verbatim, with custom-row support layered on top for the synthetic-instance flow.

The shipped predefined topologies are EvoMas-authored, but their prompts and tool palettes mirror 22 open-source multi-agent / coding projects (OpenHands, HyperAgent, JoyCode, Lingma SWE-GPT, ExpeRepair, SWE-agent, aider, claude-coder, trae-agent, …). EvoMas re-implements every tool from scratch against the MCP binding contract — no upstream code is vendored — so the credit covers prompt **design**, tool **naming**, and **intended behaviour**. Two acknowledgement files carry the full provenance with commit-pinned `source_url` deep-links and per-repo license posture:

- [`evomas/config/agent_types/ACKNOWLEDGEMENTS.md`](./evomas/config/agent_types/ACKNOWLEDGEMENTS.md) — agent-prompt catalogue (22 repos, the variants surfaced in the Topology page picker).
- [`evomas/tools/repo/ACKNOWLEDGEMENTS.md`](./evomas/tools/repo/ACKNOWLEDGEMENTS.md) — tool-implementation catalogue (12 repos, the per-`<repo>/` subdirs under `evomas/tools/repo/`).

The framework itself is built on [LangChain](https://www.langchain.com/) + [LangGraph](https://www.langchain.com/langgraph) for the agent graph runtime, [Ollama](https://ollama.com/) / [LiteLLM](https://github.com/BerriAI/litellm)-style model dispatch, [FastAPI](https://fastapi.tiangolo.com/) for the backend, and [Angular](https://angular.dev/) for the frontend topology canvas.
