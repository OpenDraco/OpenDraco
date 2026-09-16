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

## Prerequisites

These are what the machine install needs. The [Docker path](#docker-no-install)
needs none of them — only Docker itself.

| Tool | Why | Where to get it |
|---|---|---|
| Python 3.12+ (3.12.6 is the dev baseline) | Runs the agent framework and the FastAPI backend. | https://www.python.org/downloads/ |
| Ollama | Hosts the local LLM each agent calls. | https://ollama.com/download |
| Docker (Desktop on Windows/macOS, Engine on Linux) | Required for SWE-bench evaluation (the harness runs each instance in a container). Not needed for inference-only flows. On Windows the harness invocation is shelled through WSL; on macOS / Linux it runs natively. | https://www.docker.com/products/docker-desktop/  ·  https://docs.docker.com/engine/install/ |
| Node.js 18+ | Builds and serves the Angular frontend. | https://nodejs.org/ |
| WSL2 (Windows only) | The SWE-bench harness ships POSIX-only steps; on Windows the API server shells out via `wsl ...`. Not needed on macOS / Linux. | https://learn.microsoft.com/windows/wsl/install |

## Quick start

Two ways to get from a fresh clone to a topology graph in your browser:

| Path | What it needs | Best for |
|---|---|---|
| **[Docker](#docker-no-install)** | Only Docker | Trying OpenDraco out — nothing is installed on the host |
| **[On your machine](#on-your-machine)** | Python 3.12+, Node 18+, Ollama, Docker | Day-to-day development and local SWE-bench evaluation |

> **Set up your `.env` files first.** Both paths read `opendraco/.env` and `api/.env` for the Ollama endpoint and any hosted-model API keys — see [Environment](#environment) for every variable and its default. The install script creates both files for you; for the Docker path, copy them from their `.example` files before building.

### Docker (no install)

Only Docker is required — nothing is installed on the host, and no Docker
socket is mounted.

```bash
docker compose up          # builds the images, starts Ollama, pulls a model
```

Then open <http://localhost:4200>. The backend is on
<http://localhost:8000> and Ollama on `11434`.

The first run downloads the model into a named volume (a couple of GB);
later runs reuse it. To use a different one:

```bash
OPENDRACO_MODEL=qwen3.5:9b docker compose up
```

Ollama runs on CPU in this setup. For NVIDIA acceleration, install the
container toolkit and add a `deploy.resources.reservations.devices` block with
`capabilities: [gpu]` to the `ollama` service.

Saved configurations and run results live in the `configs` and `results`
volumes, so they survive `docker compose down` (add `-v` to discard them).

**The four services.** `docker compose exec` takes the service name — there is no
default, so `docker compose exec api …` rather than `docker compose exec …`:

| Service | What it is | Reach it with |
|---|---|---|
| `api` | FastAPI backend + the `opendraco` package, on `:8000`. The CLI is installed here. | `docker compose exec api opendraco status` |
| `web` | nginx serving the built Angular bundle, on `:4200`. | `docker compose exec web nginx -t` |
| `ollama` | The Ollama server, on `:11434`. Models land in the `ollama` volume. | `docker compose exec ollama ollama list` |
| `model-pull` | One-shot: pulls `$OPENDRACO_MODEL` into that volume, then exits. | `docker compose up model-pull` |

Pull models through the `ollama` service, not `api` — the `ollama` binary is not
in the api image, so the Topology page's pull button and
`docker compose exec api ollama …` both fail there. On PowerShell the inline form
`OPENDRACO_MODEL=… docker compose up` is a parse error; use
`$env:OPENDRACO_MODEL = "qwen3.5:9b"; docker compose up`, or put the value in a
root `.env`.

When `OLLAMA_BASE_URL` points at a host or remote Ollama, the `ollama` and
`model-pull` services are unused — start just what you need with
`docker compose up -d api web`.

**SWE-bench evaluation.** The default profile covers inference and the
clone-apply-test evaluator that grades the synthetic instances, which needs only
git and network access. The official SWE-bench harness starts a container per
instance, so it needs a Docker daemon — the `swebench` package and the `docker`
client are already in the image, and this overlay supplies the socket:

```bash
docker compose -f docker-compose.yml -f docker-compose.swebench.yml up
```

That hands the `api` container full control of the host's Docker daemon, which is
root-equivalent access to the machine. Reasonable for a benchmark you are running
yourself, which is why it is opt-in per command rather than the default — the
container otherwise executes LLM-authored patches. Inference and `--remote`
evaluation never need it.

### On your machine

Assumes Python 3.12+, Node 18+, Ollama, and Docker are already installed (see
[Prerequisites](#prerequisites)). What the script does step by step, how to
repair a broken venv, and how to undo it all live in
[Install on machine](#install-on-machine).

```bash
# 1. Set up the venv, copy the .env files, clone + build the SWE-bench
#    harness (when Docker — plus WSL2 on Windows — is present), and
#    register the `opendraco` command on your $PATH
./install.sh                 # or .\install.ps1 on Windows

# 2. (optional) install.sh already copied opendraco/.env + api/.env from their
#    .example files — the defaults work for a local-only Ollama setup. Edit
#    them only if you need remote hosts or hosted-model API keys; every
#    variable is documented in the Environment section below.

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

## Install on machine

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

Then rerun the platform-appropriate install command from the [Install on machine](#install-on-machine) section above. (`uninstall.sh` / `uninstall.ps1` remove the venv and the rest of the install for you — see [Uninstall](#uninstall).)

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

## CLI Commands

The `opendraco` command wraps every entry point — Ollama model management, the
instances → prediction → evaluation pipeline, and the re-evaluation utilities.
Each command's arguments, options and worked examples live in
[docs/CLI.md](./docs/CLI.md); `opendraco <command> --help` prints the same thing.

## Extending to a new problem type

Nothing in the framework core is APR-specific. OpenDraco auto-discovers tools, topology configs, and evaluator scripts, so adding a brand-new problem type (program repair, file translation, web research, math proof checking, …) is **three drop-in files**, no edits in framework code:

- a `@tool`-decorated Python module under `opendraco/tools/<bundle>/` (any new tool the agents need — `opendraco/tools/repo/<bundle>/` is reserved for upstream-aligned repo-variant bundles)
- a topology JSON under `opendraco/config/predefined/` (the agent graph + prompts)
- an evaluator script under `scripts/evaluation/` (reads a predictions JSONL, writes a SWE-bench-shaped report)

Restart the API, hard-refresh the frontend, and the new tools, the new topology, and the new evaluator all appear in the UI. The end-to-end guide — covering the drop-in shape for each artifact, the optional `OPENDRACO_EVALUATOR` manifest, and the shipped translate / websearch tasks as worked templates — lives in [docs/adding_a_new_problem.md](./docs/adding_a_new_problem.md).

## Experiments and benchmark

The task instantiations that ship with the repo, the APR benchmark OpenDraco has been
measured on, and the raw record behind every number — run notebooks, per-instance
inference logs, predictions, and SWE-bench harness reports — live in a separate
repository:

**[OpenDraco/experiments](https://github.com/OpenDraco/experiments)** — start with
[`BENCHMARK.md`](https://github.com/OpenDraco/experiments/blob/master/BENCHMARK.md) for the task instantiations and the
benchmark results, and [`EXPERIMENT.md`](https://github.com/OpenDraco/experiments/blob/master/EXPERIMENT.md) for a
generated summary of every run.

## Acknowledgments

The APR instantiation builds directly on the [SWE-bench](https://www.swebench.com/) evaluation framework — its Docker harness, dataset format, and `subset/split` semantics are reused verbatim, with custom-row support layered on top for the synthetic-instance flow. The instance/prediction JSONL shape is also what the task-agnostic evaluator contract is modelled on, so non-APR tasks reuse the same pipeline.

The shipped predefined topologies are OpenDraco-authored, but their prompts and tool palettes mirror 22 open-source multi-agent / coding projects (OpenHands, HyperAgent, JoyCode, Lingma SWE-GPT, ExpeRepair, SWE-agent, aider, claude-coder, trae-agent, …). OpenDraco re-implements every tool from scratch against the MCP binding contract — no upstream code is vendored — so the credit covers prompt **design**, tool **naming**, and **intended behaviour**. Two acknowledgement files carry the full provenance with commit-pinned `source_url` deep-links and per-repo license posture:

- [`opendraco/config/agent_types/ACKNOWLEDGEMENTS.md`](./opendraco/config/agent_types/ACKNOWLEDGEMENTS.md) — agent-prompt catalogue (22 repos, the variants surfaced in the Topology page picker).
- [`opendraco/tools/repo/ACKNOWLEDGEMENTS.md`](./opendraco/tools/repo/ACKNOWLEDGEMENTS.md) — tool-implementation catalogue (12 repos, the per-`<repo>/` subdirs under `opendraco/tools/repo/`).

The framework itself is built on [LangChain](https://www.langchain.com/) + [LangGraph](https://www.langchain.com/langgraph) for the agent graph runtime, [Ollama](https://ollama.com/) / [LiteLLM](https://github.com/BerriAI/litellm)-style model dispatch, [FastAPI](https://fastapi.tiangolo.com/) for the backend, and [Angular](https://angular.dev/) for the frontend topology canvas.
