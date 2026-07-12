"""Build a reproduce-this-run Jupyter notebook.

Lives in `evomas.utils` (not `api/`) so non-FastAPI callers can produce
notebooks too.
"""
from __future__ import annotations

import json
import pprint
from pathlib import Path
from typing import Any


from evomas.paths import BASE_DIR as _BASE_DIR
from evomas.paths import INSTANCES_PATH as _DEFAULT_INSTANCES_PATH
from evomas.paths import PREDICTION_CONFIGS_DIR as _DEFAULT_CONFIGS_DIR


def resolve_evaluator(stem: str) -> tuple[str, bool]:
    """Validate `scripts/evaluation/<stem>.py` exists and parse its
    `EVOMAS_EVALUATOR.needs_wsl` flag (defaults False). Raises
    FileNotFoundError if the script is missing."""
    script_path = _BASE_DIR / "scripts" / "evaluation" / f"{stem}.py"
    if not script_path.is_file():
        raise FileNotFoundError(
            f"Evaluator script not found: scripts/evaluation/{stem}.py"
        )
    import re as _re
    needs_wsl = False
    m = _re.search(
        r"EVOMAS_EVALUATOR\s*=\s*(\{[^}]*\})",
        script_path.read_text(encoding="utf-8"),
    )
    if m and '"needs_wsl": True' in m.group(1):
        needs_wsl = True
    return stem, needs_wsl


def _resolve_instance_plan(
    instance_ids: list[str], instances_path: Path,
) -> tuple[dict[tuple[str, str], list[str]], list[dict[str, Any]]]:
    """Return `(swebench_groups, custom_rows)` for the notebook to
    rehydrate its instances at runtime.

    `swebench_groups`: `{(subset, split): [ids]}` — fetched fresh from
    HuggingFace at runtime. `custom_rows`: full row dicts inlined into
    the notebook (no upstream to fetch). The on-disk cache is consulted
    ONLY at notebook-gen time; the generated notebook never reads it.
    """
    swebench_groups: dict[tuple[str, str], list[str]] = {}
    custom_rows: list[dict[str, Any]] = []

    by_id: dict[str, dict[str, Any]] = {}
    if instances_path.is_file():
        wanted = set(instance_ids)
        with instances_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                iid = rec.get("instance_id")
                if iid in wanted:
                    by_id[iid] = rec

    # `custom-` id prefix is back-compat — predates the `subset` field.
    SWEBENCH_SUBSETS = {"lite", "full", "verified", "multimodal"}
    for iid in instance_ids:
        row = by_id.get(iid)
        subset = (row or {}).get("subset")
        is_swebench_row = (
            not iid.startswith("custom-")
            and isinstance(subset, str)
            and subset in SWEBENCH_SUBSETS
        )
        if not is_swebench_row:
            if row is not None:
                # Strip patch/test_patch — unused inline, bloat the notebook.
                custom_rows.append({
                    "instance_id":       row.get("instance_id"),
                    "repo":              row.get("repo", ""),
                    "base_commit":       row.get("base_commit", ""),
                    "problem_statement": row.get("problem_statement", ""),
                    "hints_text":        row.get("hints_text", ""),
                    "subset":            row.get("subset", "custom"),
                    "split":             row.get("split", "custom"),
                })
            continue
        assert isinstance(subset, str)  # narrowed by is_swebench_row above
        split = (row or {}).get("split") or "dev"
        swebench_groups.setdefault((subset, split), []).append(iid)

    return swebench_groups, custom_rows


def build_notebook_for_prediction(
    path: Path,
    *,
    evaluator: str,
    configs_dir: Path | None = None,
    instances_path: Path | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build a notebook reproducing the run that produced `path` (a
    prediction JSONL). Raises FileNotFoundError if `path` is missing."""
    if not path.is_file():
        raise FileNotFoundError(f"prediction file not found: {path}")

    cfg_dir = configs_dir if configs_dir is not None else _DEFAULT_CONFIGS_DIR
    inst_path = instances_path if instances_path is not None else _DEFAULT_INSTANCES_PATH

    instance_ids: list[str] = []
    baseline_patches: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            iid = rec.get("instance_id")
            if isinstance(iid, str):
                instance_ids.append(iid)
                bp = rec.get("model_patch")
                if isinstance(bp, str):
                    baseline_patches[iid] = bp

    # Inline the snapshot so the notebook survives later edits/deletes
    # of the source config.
    cfg_snapshot_path = cfg_dir / (path.stem + ".json")
    config_data: dict[str, Any] = {}
    if cfg_snapshot_path.is_file():
        try:
            config_data = json.loads(cfg_snapshot_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    run_id = path.stem
    if run_id.startswith("prediction-"):
        run_id = run_id[len("prediction-"):]

    evaluator_stem, needs_wsl = resolve_evaluator(evaluator)
    swebench_groups, custom_rows = _resolve_instance_plan(instance_ids, inst_path)
    notebook = _build_reproduction_notebook(
        run_id=run_id,
        source_jsonl=str(path),
        config_data=config_data,
        instance_ids=instance_ids,
        baseline_patches=baseline_patches,
        swebench_groups=swebench_groups,
        custom_rows=custom_rows,
        evaluator=evaluator_stem,
        evaluator_needs_wsl=needs_wsl,
    )
    return run_id, notebook


def build_notebook_for_inputs(
    *,
    instance_ids: list[str],
    config_data: dict[str, Any],
    evaluator: str,
    run_id_label: str | None = None,
    instances_path: Path | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build a notebook from raw inputs (no prediction file yet). The
    comparative-diff section is omitted — nothing to diff against."""
    inst_path = instances_path if instances_path is not None else _DEFAULT_INSTANCES_PATH
    cfg_id = str(config_data.get("id") or "session")
    run_id = run_id_label or cfg_id

    evaluator_stem, needs_wsl = resolve_evaluator(evaluator)
    swebench_groups, custom_rows = _resolve_instance_plan(instance_ids, inst_path)
    notebook = _build_reproduction_notebook(
        run_id=run_id,
        source_jsonl=f"<inference page: {cfg_id} x {len(instance_ids)} instance(s)>",
        config_data=config_data,
        instance_ids=instance_ids,
        baseline_patches=None,
        swebench_groups=swebench_groups,
        custom_rows=custom_rows,
        evaluator=evaluator_stem,
        evaluator_needs_wsl=needs_wsl,
    )
    return run_id, notebook


def _build_reproduction_notebook(
    *,
    run_id: str,
    source_jsonl: str,
    config_data: dict[str, Any],
    instance_ids: list[str],
    baseline_patches: dict[str, str] | None,
    swebench_groups: dict[tuple[str, str], list[str]],
    custom_rows: list[dict[str, Any]],
    evaluator: str,
    evaluator_needs_wsl: bool,
) -> dict[str, Any]:
    """Build the nbformat-v4 dict. Plain dict, no `nbformat` import —
    structure is small enough to maintain inline."""
    def md(text: str) -> dict[str, Any]:
        return {"cell_type": "markdown", "metadata": {}, "source": text}

    def code(text: str) -> dict[str, Any]:
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": text,
        }

    # pprint, not json.dumps: the CONFIG cell needs Python literals
    # (True/False/None); JSON's true/false/null would NameError.
    cfg_repr = pprint.pformat(config_data, indent=4, width=100, sort_dicts=False)
    ids_repr = pprint.pformat(instance_ids, indent=4, width=100)

    cells: list[dict[str, Any]] = [
        md(
            f"# Reproduce `{run_id}`\n"
            f"\n"
            f"Generated from `{source_jsonl}`. The notebook replays inference + "
            f"evaluation against the exact config snapshot that produced the "
            f"original run, so a re-execution should produce a comparable "
            f"`model_patch` (LLM determinism caveats notwithstanding).\n"
            f"\n"
            f"- **Instances:** {len(instance_ids)}\n"
            f"- **Config id:** `{config_data.get('id', '(unknown)')}`\n"
        ),
        md(
            "## 1. Setup\n"
            "\n"
            "The notebook's `kernelspec.name = \"evomas\"` (see metadata at "
            "the bottom of the file) tells Jupyter / VSCode to auto-pick the "
            "interpreter `install.ps1` / `install.sh` registered for "
            "`~/.evomas-venv`. As a safety net the first cell also prepends "
            "the venv's site-packages to `sys.path` — so even if the kernel "
            "falls back to a generic Python 3 (different machine, no "
            "`install.ps1` run), the evomas imports still resolve. Adjust "
            "`OLLAMA_BASE_URL` if your Ollama daemon isn't on the default "
            "host; `SWEBENCH_API_KEY` is only required by the remote-eval "
            "cell at the bottom.\n"
            "\n"
            "### Picking the kernel in VSCode\n"
            "\n"
            "If VSCode opens the notebook outside the EvoMas workspace "
            "(e.g. straight from `~/Downloads`), it won't auto-resolve the "
            "kernelspec and asks you to **Select Kernel**. Two-tier picker:\n"
            "\n"
            "- **\"Python Environments…\"** lists raw Python interpreters "
            "discovered by the Python extension (system Python, conda envs, "
            "`.venv`/`venv` folders inside workspaces). `~/.evomas-venv` is "
            "outside the conventional discovery paths, so it does NOT show "
            "up here.\n"
            "- **\"Jupyter Kernel…\"** lists registered Jupyter kernelspecs "
            "(`%APPDATA%\\jupyter\\kernels\\*` on Windows, "
            "`~/.local/share/jupyter/kernels/*` on Linux/mac). This is "
            "where the EvoMas one lives — pick **\"Python 3 (EvoMas)\"** "
            "here. VSCode remembers the choice per-notebook so you only "
            "have to do it once.\n"
            "\n"
            "If the entry doesn't appear there: `Ctrl+Shift+P` → "
            "**\"Developer: Reload Window\"** so the Jupyter extension "
            "re-scans kernelspecs, or run `jupyter kernelspec list` to "
            "confirm `evomas` is registered (if not, re-run "
            "`install.ps1` / `install.sh`)."
        ),
        code(
            "import os\n"
            "import sys\n"
            "import json\n"
            "import subprocess\n"
            "from pathlib import Path\n"
            "\n"
            "# Defensive sys.path prepend so `import evomas...` still\n"
            "# resolves when the kernel isn't the evomas-venv one.\n"
            "_venv = Path.home() / '.evomas-venv'\n"
            "if _venv.is_dir() and str(_venv) not in sys.executable:\n"
            "    for _sp in (_venv / 'Lib' / 'site-packages',\n"
            "                _venv / 'lib' / 'site-packages'):\n"
            "        if _sp.is_dir() and str(_sp) not in sys.path:\n"
            "            sys.path.insert(0, str(_sp))\n"
            "\n"
            "import evomas.paths  # noqa: F401  # triggers load_dotenv(evomas/.env)\n"
            "\n"
            "from evomas.core.workflow.runner import run as run_evomas\n"
            "from evomas.utils.instances import fetch_swebench_instances\n"
            "\n"
            "# Mirror logging to a per-run text file so generate_report.py\n"
            "# can mine the same lines the API matrix path writes.\n"
            "import logging\n"
            f"RUN_OUTPUT_DIR = Path('notebook-{run_id}').resolve()\n"
            "RUN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)\n"
            "LOG_FILE = RUN_OUTPUT_DIR / 'inference.log'\n"
            "logging.basicConfig(\n"
            "    level=logging.INFO,\n"
            "    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',\n"
            "    force=True,\n"
            "    handlers=[\n"
            "        logging.StreamHandler(),\n"
            "        logging.FileHandler(LOG_FILE, encoding='utf-8'),\n"
            "    ],\n"
            ")\n"
            "print(f'Mirroring inference logs to {LOG_FILE}')\n"
        ),
        md(
            "### Environment variables\n"
            "\n"
            "All run-time configuration the notebook needs lives in this "
            "cell — edit values here rather than chasing them through the "
            "code. Each assignment **overrides** whatever is in the "
            "environment / .env when the cell runs.\n"
            "\n"
            "- **`OLLAMA_BASE_URL`** — where the Ollama daemon serves.\n"
            "- **`SWEBENCH_API_KEY`** — required by the remote-eval cell "
            "(section 5) when running `--remote` against sb-cli. Local "
            "Docker harness runs don't need it.\n"
            "- **`EVOMAS_INSTANCES`** — override the SWE-bench instance "
            "cache location. The next cell already searches sensible "
            "defaults; only set this if your cache is somewhere "
            "non-standard.\n"
            "- **`GOOGLE_API_KEY` / `OPENAI_API_KEY`** — only needed if the "
            "inlined config picks a Gemini / OpenAI model instead of Ollama.\n"
        ),
        code(
            "# Edit values here; each assignment overrides the inherited\n"
            "# environment / .env. Uncomment the lines you need.\n"
            "os.environ['OLLAMA_BASE_URL'] = 'http://localhost:11434'\n"
            "# os.environ['SWEBENCH_API_KEY'] = 'swb_...'\n"
            "# os.environ['EVOMAS_INSTANCES'] = '/path/to/swebench_instances.jsonl'\n"
            "# os.environ['GOOGLE_API_KEY']   = '...'\n"
            "# os.environ['OPENAI_API_KEY']   = '...'\n"
            "\n"
            "# Echo the effective values (mask secrets) so you can verify the cell ran.\n"
            "for _k in ('OLLAMA_BASE_URL', 'SWEBENCH_API_KEY', 'EVOMAS_INSTANCES',\n"
            "           'GOOGLE_API_KEY', 'OPENAI_API_KEY'):\n"
            "    _v = os.environ.get(_k, '')\n"
            "    if not _v:\n"
            "        print(f'  {_k:<18} <unset>')\n"
            "    elif _k.endswith('_API_KEY'):\n"
            "        print(f'  {_k:<18} {_v[:6]}***({len(_v)} chars)')\n"
            "    else:\n"
            "        print(f'  {_k:<18} {_v}')\n"
        ),
        md(
            "## 2. Inlined config\n"
            "\n"
            "Exact resolved config the original run used. Tweak hyperparameters "
            "here if you want to experiment with variations.\n"
            "\n"
            "The cell below the config dict renders a mermaid diagram of the "
            "topology so you can see the agent-graph shape at a glance. The "
            "diagram is regenerated from `CONFIG['edges']` + `CONFIG['agents']` "
            "every time the cell runs, so edits to the dict above are "
            "reflected immediately."
        ),
        code(f"CONFIG = {cfg_repr}"),
        code(
            "from IPython.display import Markdown, display\n"
            "\n"
            "def _topology_mermaid(cfg):\n"
            "    \"\"\"Render the topology as a Mermaid flowchart.\n"
            "\n"
            "    Mirrors what the topology page's cytoscape canvas shows:\n"
            "    virtual START/END boundary nodes, one node per agent with\n"
            "    its class as a second-line label, edges directed left-to-\n"
            "    right. Renders inline in Jupyter Lab + VSCode Jupyter; if\n"
            "    the cell falls back to plain text the source stays readable.\n"
            "    \"\"\"\n"
            "    lines = ['graph LR']\n"
            "    lines.append('    START((START))')\n"
            "    lines.append('    END((END))')\n"
            "    for name, block in (cfg.get('agents') or {}).items():\n"
            "        cls = (block or {}).get('class', '') or ''\n"
            "        label = f'{name}<br/><i>{cls}</i>' if cls else name\n"
            "        # Backticks break the mermaid parser; strip them.\n"
            "        label = label.replace('`', '')\n"
            "        lines.append(f'    {name}[\"{label}\"]')\n"
            "    entry = cfg.get('entry') or ''\n"
            "    if entry:\n"
            "        lines.append(f'    START --> {entry}')\n"
            "    for e in (cfg.get('edges') or []):\n"
            "        if isinstance(e, dict) and e.get('from') and e.get('to'):\n"
            "            lines.append(f'    {e[\"from\"]} --> {e[\"to\"]}')\n"
            "    end_field = cfg.get('end')\n"
            "    ends = (\n"
            "        [end_field] if isinstance(end_field, str) and end_field\n"
            "        else list(end_field or [])\n"
            "    )\n"
            "    # `→ END` only for nodes with no outgoing edges, same\n"
            "    # rule as `graph_builder.py`.\n"
            "    out_sources = {e.get('from') for e in (cfg.get('edges') or [])\n"
            "                   if isinstance(e, dict)}\n"
            "    for n in ends:\n"
            "        if n and n not in out_sources:\n"
            "            lines.append(f'    {n} --> END')\n"
            "    return '\\n'.join(lines)\n"
            "\n"
            "display(Markdown('```mermaid\\n' + _topology_mermaid(CONFIG) + '\\n```'))\n"
        ),
        md(
            "## 3. Instances\n"
            "\n"
            "Self-contained: the notebook regenerates its own instances "
            "from zero each run. SWE-bench rows get pulled fresh from "
            "HuggingFace (cached under `~/.cache/huggingface`); custom "
            "rows are reconstructed from the minimal inputs the user "
            "added via the Inference page's `+ Custom` modal."
        ),
        code(f"INSTANCE_IDS = {ids_repr}\n"),
        code(
            f"# `{{(subset, split): [ids]}}` — one HuggingFace fetch per group.\n"
            f"SWEBENCH_GROUPS = {pprint.pformat(dict(swebench_groups), indent=4, width=100)}\n"
        ),
        code(
            f"# Custom-instance inputs inlined — no upstream to fetch.\n"
            f"CUSTOM_ROWS = {pprint.pformat(custom_rows, indent=4, width=100, sort_dicts=False)}\n"
        ),
        code(
            f"output_dir = RUN_OUTPUT_DIR\n"
            f"output_path = output_dir / 'prediction-{run_id}.jsonl'\n"
            "INSTANCES_PATH = output_dir / 'instances.jsonl'\n"
            "\n"
            "selected = []\n"
            "for (subset, split), ids in SWEBENCH_GROUPS.items():\n"
            "    print(f'Fetching {len(ids)} {subset}/{split} row(s) from HuggingFace…')\n"
            "    selected.extend(fetch_swebench_instances(subset, split, instance_ids=ids))\n"
            "selected.extend(CUSTOM_ROWS)\n"
            "\n"
            "with INSTANCES_PATH.open('w', encoding='utf-8') as _fh:\n"
            "    for _row in selected:\n"
            "        _fh.write(json.dumps(_row, ensure_ascii=False) + '\\n')\n"
            "print(f'Wrote {len(selected)} instance row(s) -> {INSTANCES_PATH}')\n"
            "\n"
            "_have = {i['instance_id'] for i in selected}\n"
            "missing = [iid for iid in INSTANCE_IDS if iid not in _have]\n"
            "if missing:\n"
            "    print('Missing rows (id not found in HF or in CUSTOM_ROWS):', missing)\n"
            "print(f'Ready to run {len(selected)} instance(s).')\n"
        ),
        md(
            "## 4. Inference\n"
            "\n"
            "Re-runs the EvoMas workflow for each instance with the inlined "
            "config. All notebook-produced artefacts (prediction JSONL, "
            "evaluation reports, custom-instance sidecar) land under one "
            f"per-run folder at `notebook-{run_id}/` so they stay grouped "
            "together and don't mix with UI/CLI runs in the repo's "
            "`results/` tree."
        ),
        code(
            "from evomas.exceptions.errors import OllamaMemoryError\n"
            "\n"
            "predictions = []\n"
            "with open(output_path, 'w', encoding='utf-8') as out:\n"
            "    for inst in selected:\n"
            "        iid = inst['instance_id']\n"
            "        print(f'--- {iid} ---')\n"
            "        try:\n"
            "            patch = run_evomas(inst, config=CONFIG)\n"
            "        except OllamaMemoryError as exc:\n"
            "            print(f'Ollama OOM; aborting: {exc}')\n"
            "            break\n"
            "        except Exception as exc:\n"
            "            print(f'run failed on {iid}: {exc}')\n"
            "            patch = ''\n"
            "        rec = {\n"
            "            'instance_id': iid,\n"
            "            'model_patch': patch,\n"
            "            'model_name_or_path': 'evomas-notebook',\n"
            "        }\n"
            "        predictions.append(rec)\n"
            "        out.write(json.dumps(rec) + '\\n')\n"
            "print(f'Wrote {len(predictions)} prediction(s) to {output_path}.')\n"
        ),
        md(
            "## 5. Evaluation\n"
            "\n"
            f"Runs `scripts/evaluation/{evaluator}.py` — the evaluator chosen "
            "at notebook-generation time (the `--evaluator` flag on `evomas "
            "notebook`). Forwards through the unified evaluator CLI contract: "
            "`--predictions / --instances / --report-dir / --run-id / --model`. "
            f"Output lands at `<report-dir>/{{model}}.{{run-id}}.json` plus "
            f"per-instance folders under `<report-dir>/logs/run_evaluation/"
            f"<run-id>/<model>/<instance>/`."
            + (
                "\n\nThis evaluator is marked `needs_wsl=True`, so on Windows "
                "the script is wrapped through WSL (the harness is POSIX-only)."
                if evaluator_needs_wsl else ""
            )
        ),
        code(
            f"EVALUATOR_STEM = {evaluator!r}\n"
            f"EVALUATOR_NEEDS_WSL = {evaluator_needs_wsl!r}\n"
            "\n"
            "first = selected[0] if selected else None\n"
            "SUBSET = (first or {}).get('subset', 'lite')\n"
            "SPLIT  = (first or {}).get('split',  'dev')\n"
            "\n"
            "eval_report_dir = output_dir\n"
            "\n"
            "import platform\n"
            "from evomas.paths import BASE_DIR as _BASE_DIR\n"
            "_script = _BASE_DIR / 'scripts' / 'evaluation' / f'{EVALUATOR_STEM}.py'\n"
            "if EVALUATOR_NEEDS_WSL and platform.system() == 'Windows':\n"
            "    from evomas.utils.paths import to_wsl\n"
            "    cmd = [\n"
            "        'wsl', '--', 'python3', to_wsl(str(_script)),\n"
            "        '--predictions', to_wsl(str(output_path)),\n"
            "        '--instances',   to_wsl(str(INSTANCES_PATH)),\n"
            "        '--report-dir',  to_wsl(str(eval_report_dir)),\n"
            "        '--run-id',      f'notebook-{SUBSET}-{SPLIT}',\n"
            "        '--model',       'evomas-notebook',\n"
            "    ]\n"
            "else:\n"
            "    cmd = [\n"
            "        sys.executable, str(_script),\n"
            "        '--predictions', str(output_path),\n"
            "        '--instances',   str(INSTANCES_PATH),\n"
            "        '--report-dir',  str(eval_report_dir),\n"
            "        '--run-id',      f'notebook-{SUBSET}-{SPLIT}',\n"
            "        '--model',       'evomas-notebook',\n"
            "    ]\n"
            "print(f'Evaluating via {EVALUATOR_STEM}.py')\n"
            "print('+ ' + ' '.join(cmd))\n"
            "\n"
            "eval_proc = subprocess.Popen(\n"
            "    cmd,\n"
            "    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,\n"
            "    text=True, bufsize=1, encoding='utf-8', errors='replace',\n"
            ")\n"
            "assert eval_proc.stdout is not None\n"
            "for line in eval_proc.stdout:\n"
            "    print(line, end='')\n"
            "eval_proc.wait()\n"
            "print(f'\\n[evaluation finished with exit code {eval_proc.returncode}]')\n"
            "\n"
            "logs_root = eval_report_dir / 'logs' / 'run_evaluation'\n"
            "if logs_root.is_dir():\n"
            "    print('\\nPer-instance artifacts:')\n"
            "    for inst_dir in sorted(logs_root.rglob('*/')):\n"
            "        if (inst_dir / 'report.json').is_file():\n"
            "            print(f'  {inst_dir}')\n"
            "for summary in sorted(eval_report_dir.glob('*.json')):\n"
            "    print(f'Summary: {summary}')\n"
        ),
    ]

    # Compare-with-original section only when a baseline exists to diff.
    if baseline_patches is not None:
        cells.extend([
            md(
                "## 6. Compare with the original run\n"
                "\n"
                "The notebook keeps the original `model_patch` per instance so you "
                "can diff the new and old runs side-by-side. Different patches with "
                "the same `resolved` verdict often mean both LLM outputs happened "
                "to satisfy the test suite differently."
            ),
            code(
                "import difflib\n"
                "import html as _html\n"
                "from IPython.display import HTML, display\n"
                "\n"
                "BASELINE_PATCHES = "
                + pprint.pformat(baseline_patches, indent=4, width=120) + "\n"
                "\n"
                "\n"
                "def _render_diff(old: str, new: str, title: str) -> str:\n"
                "    \"\"\"Build a GitHub-style colored unified diff. Each line\n"
                "    is escaped + wrapped in a div so longer patches stay\n"
                "    legible (no wrapping) and the +/- colors render even when\n"
                "    Jupyter's CSS doesn't ship a diff theme.\n"
                "    \"\"\"\n"
                "    diff_lines = list(difflib.unified_diff(\n"
                "        old.splitlines(), new.splitlines(),\n"
                "        fromfile='baseline', tofile='new',\n"
                "        lineterm='',\n"
                "    ))\n"
                "    if not diff_lines:\n"
                "        return (f'<div style=\"color:#888;font-style:italic\">'\n"
                "                f'{_html.escape(title)} — identical to baseline'\n"
                "                f'</div>')\n"
                "    rows = []\n"
                "    for line in diff_lines:\n"
                "        esc = _html.escape(line) or '&nbsp;'\n"
                "        if line.startswith('+++') or line.startswith('---'):\n"
                "            color, bg = '#666', 'transparent'\n"
                "        elif line.startswith('@@'):\n"
                "            color, bg = '#a371f7', 'rgba(163,113,247,0.10)'\n"
                "        elif line.startswith('+'):\n"
                "            color, bg = '#2ea043', 'rgba(46,160,67,0.16)'\n"
                "        elif line.startswith('-'):\n"
                "            color, bg = '#f85149', 'rgba(248,81,73,0.16)'\n"
                "        else:\n"
                "            color, bg = 'inherit', 'transparent'\n"
                "        rows.append(\n"
                "            f'<div style=\"color:{color};background:{bg};'\n"
                "            f'white-space:pre;font-family:monospace;'\n"
                "            f'padding:0 6px\">{esc}</div>'\n"
                "        )\n"
                "    return (\n"
                "        f'<div style=\"font-weight:bold;margin-top:8px\">'\n"
                "        f'{_html.escape(title)}</div>'\n"
                "        + ''.join(rows)\n"
                "    )\n"
                "\n"
                "\n"
                "parts = []\n"
                "for rec in predictions:\n"
                "    iid = rec['instance_id']\n"
                "    new_p = rec.get('model_patch') or ''\n"
                "    old_p = BASELINE_PATCHES.get(iid, '')\n"
                "    if new_p.strip() == '' and old_p.strip() == '':\n"
                "        parts.append(\n"
                "            f'<div style=\"color:#888;font-style:italic;margin-top:8px\">'\n"
                "            f'{iid} — both new and baseline patches are empty</div>'\n"
                "        )\n"
                "        continue\n"
                "    parts.append(_render_diff(old_p, new_p, iid))\n"
                "\n"
                "display(HTML(''.join(parts) or '<i>no predictions to compare</i>'))\n"
            ),
        ])

    return {
        "cells": cells,
        "metadata": {
            # `evomas` kernelspec registered by `install.ps1` via `python
            # -m ipykernel install --user --name evomas`. Falls back to
            # any Python 3 kernel via the setup cell's sys.path prepend.
            "kernelspec": {
                "name": "evomas",
                "display_name": "Python 3 (EvoMas)",
                "language": "python",
            },
            "language_info": {
                "name": "python",
                "mimetype": "text/x-python",
                "file_extension": ".py",
            },
            "evomas": {
                "generated_from": source_jsonl,
                "run_id": run_id,
                "instance_count": len(instance_ids),
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
