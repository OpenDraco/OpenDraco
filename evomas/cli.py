"""EvoMas CLI — single `evomas <subcommand>` entry covering instance
generation, prediction, evaluation, dev servers, notebook export, and
Ollama conveniences. Each subcommand subprocesses a `scripts/` entry
point with extra args forwarded verbatim."""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click
import typer
from typer.core import TyperGroup

from evomas.paths import BASE_DIR as REPO_ROOT, bootstrap

# sys.path push + .env load + writable-folder mkdir — same setup the
# api server runs at import time.
bootstrap()

app = typer.Typer(
    no_args_is_help=True,
    help="EvoMas command-line interface - drives instance generation, "
         "prediction, evaluation, notebook export, dev servers, and the "
         "test runner.",
    add_completion=False,
)
class _OllamaPassthroughGroup(TyperGroup):
    """Forwards unrecognised `evomas ollama <args>` to the local
    `ollama` binary so `evomas ollama -- rm qwen3:8b` works without
    wrapping every verb."""


    def resolve_command(self, ctx: click.Context, args: list[str]):  # type: ignore
        # `# type: ignore`: typer (>=0.26) vendors its own click, so `get_command`
        # / `resolve_command` type their `ctx` as `typer._click.core.Context`,
        # which pyright reports as incompatible with the `click.Context` annotation
        # even though they're the same object at runtime.
        if not args or self.get_command(ctx, args[0]) is not None:  # type: ignore
            return super().resolve_command(ctx, args)  # type: ignore

        forwarded = list(args)

        def _passthrough() -> None:
            raise typer.Exit(
                subprocess.run(
                    ["ollama", *forwarded],
                    env=_ollama_host_env(),
                ).returncode,
            )

        cmd = click.Command(name="<passthrough>", callback=_passthrough, params=[])
        # `[]` so Click doesn't re-parse args; we already have them.
        return cmd.name, cmd, []


ollama_app = typer.Typer(
    no_args_is_help=True,
    cls=_OllamaPassthroughGroup,
    help="Local LLM lifecycle. Subcommands target the Ollama server named "
         "by `OLLAMA_BASE_URL` in evomas/.env (default: localhost:11434)."
         "\n\nUse `evomas ollama -- <args>` to forward arbitrary args to "
         "the `ollama` binary, e.g. `evomas ollama -- rm qwen3:8b`.",
    add_completion=False,
)
run_app = typer.Typer(
    no_args_is_help=True,
    help="Run the SWE-bench pipeline: generate instances -> predict -> evaluate.",
    add_completion=False,
)
app.add_typer(ollama_app, name="ollama")
app.add_typer(run_app, name="run")


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _ollama_host_env() -> dict[str, str]:
    """os.environ copy with `OLLAMA_HOST` derived from `OLLAMA_BASE_URL`
    (the Ollama CLI wants `host:port`, not the full URL)."""
    env = os.environ.copy()
    url = env.get("OLLAMA_BASE_URL", "").strip()
    if url:
        host = url.replace("http://", "").replace("https://", "").rstrip("/")
        env["OLLAMA_HOST"] = host
    return env


def _resolve_swebench_dir() -> Path:
    """Location of the local SWE-bench repo clone used by `--local`
    evaluation, overridable with SWEBENCH_DIR (relative values resolve
    against the repo root). Default: <repo>/SWE-bench. Mirrors the
    resolution in scripts/evaluation/run_swebench_evaluation.py."""
    _sb_dir = os.environ.get("SWEBENCH_DIR", "").strip()
    if not _sb_dir:
        return REPO_ROOT / "SWE-bench"
    return Path(_sb_dir) if Path(_sb_dir).is_absolute() else REPO_ROOT / _sb_dir


def _script_needs_wsl(script_path: Path) -> bool:
    """True iff the script exposes `EVOMAS_EVALUATOR = {"needs_wsl": True}`."""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location(
            f"_cli_manifest_{script_path.stem}", script_path,
        )
        if spec is None or spec.loader is None:
            return False
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception:  # noqa: BLE001
        return False
    manifest = getattr(mod, "EVOMAS_EVALUATOR", None)
    return bool(isinstance(manifest, dict) and manifest.get("needs_wsl"))


def _run_script(script_name: str, extra_args: list[str]) -> int:
    """Subprocess a `scripts/<name>.py` entry point. Scripts declaring
    `EVOMAS_EVALUATOR.needs_wsl` get auto-wrapped in WSL on Windows."""
    script_path = REPO_ROOT / "scripts" / script_name
    if not script_path.is_file():
        typer.echo(f"script not found: {script_path}", err=True)
        return 1

    if platform.system() == "Windows" and _script_needs_wsl(script_path):
        import shlex
        from evomas.utils.paths import to_wsl
        swebench_py = _resolve_swebench_dir() / "venv" / "bin" / "python"
        inner = " ".join(shlex.quote(a) for a in [
            to_wsl(str(swebench_py)),
            to_wsl(str(script_path)),
            *extra_args,
        ])
        return subprocess.run(["wsl", "--", "bash", "-lc", inner]).returncode

    return subprocess.run(
        [sys.executable, str(script_path), *extra_args],
        cwd=REPO_ROOT,
    ).returncode


def _run_shell_script(script_stem: str, extra_args: list[str]) -> int:
    """Subprocess `scripts/<stem>.ps1` on Windows, `scripts/<stem>.sh`
    elsewhere. Both variants are kept in sync."""
    if platform.system() == "Windows":
        script_path = REPO_ROOT / "scripts" / f"{script_stem}.ps1"
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
               "-File", str(script_path), *extra_args]
    else:
        script_path = REPO_ROOT / "scripts" / f"{script_stem}.sh"
        cmd = ["bash", str(script_path), *extra_args]
    if not script_path.is_file():
        typer.echo(f"script not found: {script_path}", err=True)
        return 1
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


# ─── ollama subcommands ───────────────────────────────────────────────────────
@ollama_app.command("pull")
def ollama_pull(
    model: str = typer.Argument(..., help="Model tag, e.g. `qwen3.5:9b`."),
) -> None:
    """Pull a model on the configured Ollama server.

    Example:  evomas ollama pull qwen3.5:9b
    """
    raise typer.Exit(subprocess.run(["ollama", "pull", model], env=_ollama_host_env()).returncode)


@ollama_app.command("list")
def ollama_list() -> None:
    """List models available on the configured Ollama server.

    Example:  evomas ollama list
    """
    raise typer.Exit(subprocess.run(["ollama", "list"], env=_ollama_host_env()).returncode)


@ollama_app.command("serve")
def ollama_serve(
    cpu_only: bool = typer.Option(
        False, "--cpu-only",
        help="Disable GPU acceleration by exporting OLLAMA_NO_CUDA=1 before serving.",
    ),
) -> None:
    """Start the Ollama server bound to the configured host.

    Example:  evomas ollama serve --cpu-only
    """
    env = _ollama_host_env()
    if cpu_only:
        env["OLLAMA_NO_CUDA"] = "1"
    raise typer.Exit(subprocess.run(["ollama", "serve"], env=env).returncode)


# ─── run subcommands ──────────────────────────────────────────────────────────
_FORWARD_CTX = {"allow_extra_args": True, "ignore_unknown_options": True}


@run_app.command(
    "instances",
    context_settings=_FORWARD_CTX,
    help=(
        "Generate the SWE-bench instances JSONL. Pulls a slice of the "
        "HuggingFace dataset and writes it as JSONL for the prediction step. "
        "Pass --custom-repo + --custom-problem to append one synthetic "
        "custom-repo row instead of pulling from HuggingFace."
        "\n\nExample:  evomas run instances --subset lite --split dev --output swebench_instances.jsonl --limit 5"
        "\nExample:  evomas run instances --subset lite --split custom --output swebench_instances.jsonl --custom-repo owner/name --custom-problem \"calc returns difference\""
    ),
)
def run_instances(
    ctx: typer.Context,
    subset: str = typer.Option(
        ..., "--subset",
        help="SWE-bench subset to pull: lite | full | verified.",
    ),
    split: str = typer.Option(
        ..., "--split",
        help="Dataset split: dev | test | train.",
    ),
    output: str = typer.Option(
        ..., "--output",
        help="Output JSONL path.",
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit",
        help="Smoke-test: keep only the first N instances.",
    ),
    append: bool = typer.Option(
        False, "--append",
        help="Keep existing lines for other (subset, split) pairs in the output file.",
    ),
    custom_repo: Optional[str] = typer.Option(
        None, "--custom-repo",
        help=(
            "GitHub 'owner/name' or URL. Switches to custom-repo mode "
            "(skips the HuggingFace pull and appends one synthetic row "
            "with subset='custom'/split='custom')."
        ),
    ),
    custom_problem: Optional[str] = typer.Option(
        None, "--custom-problem",
        help="Problem statement for the custom row. Required with --custom-repo.",
    ),
    custom_base_commit: Optional[str] = typer.Option(
        None, "--custom-base-commit",
        help="Base commit SHA. Defaults to the remote HEAD via `git ls-remote`.",
    ),
    custom_instance_id: Optional[str] = typer.Option(
        None, "--custom-instance-id",
        help="Override the auto-generated `custom-<owner>-<name>-<sha[:7]>` id.",
    ),
) -> None:
    forwarded: list[str] = [
        "--subset", subset, "--split", split, "--output", output,
    ]
    if limit is not None:
        forwarded += ["--limit", str(limit)]
    if append:
        forwarded.append("--append")
    if custom_repo:
        forwarded += ["--custom-repo", custom_repo]
    if custom_problem:
        forwarded += ["--custom-problem", custom_problem]
    if custom_base_commit:
        forwarded += ["--custom-base-commit", custom_base_commit]
    if custom_instance_id:
        forwarded += ["--custom-instance-id", custom_instance_id]
    forwarded.extend(ctx.args)
    raise typer.Exit(_run_script("generate_swebench_instances.py", forwarded))


@run_app.command(
    "prediction",
    context_settings=_FORWARD_CTX,
    help=(
        "Generate EvoMas predictions for the instances JSONL. Runs the "
        "configured LangGraph topology against each instance and emits "
        "one model_patch per line into the predictions JSONL. Rows without "
        "`repo`/`base_commit` skip the clone step and run against a "
        "throwaway tmpdir workspace — useful for chat/websearch-style "
        "configs that don't need source files."
        "\n\nExample:  evomas run prediction --instances swebench_instances.jsonl --output evomas_predictions.jsonl --config chain"
    ),
)
def run_prediction(
    ctx: typer.Context,
    instances: str = typer.Option(
        ..., "--instances",
        help="Path to the JSONL produced by `evomas run instances`.",
    ),
    output: str = typer.Option(
        ..., "--output",
        help="Output predictions JSONL.",
    ),
    config: str = typer.Option(
        ..., "--config",
        help=(
            "Config name (resolved against evomas/config/predefined/ then "
            "loaded/) or a path to a JSON file."
        ),
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit",
        help="Smoke-test: process only the first N instances.",
    ),
) -> None:
    forwarded: list[str] = [
        "--instances", instances, "--output", output, "--config", config,
    ]
    if limit is not None:
        forwarded += ["--limit", str(limit)]
    forwarded.extend(ctx.args)
    raise typer.Exit(_run_script("generate_evomas_predictions.py", forwarded))


@run_app.command(
    "evaluation",
    context_settings=_FORWARD_CTX,
    help=(
        "Run SWE-bench evaluation on a predictions JSONL."
        "\n\n  --local  (default) - SWE-bench Docker harness; full per-instance "
        "logs (eval.sh, patch.diff, test_output.txt) under <report-dir>/logs/. "
        "Needs Docker; on Windows the wrapper shells out to WSL (`swebench` is "
        "POSIX-only)."
        "\n  --remote           - submits to swebench.com via sb-cli "
        "(needs SWEBENCH_API_KEY; verdicts only, no per-instance logs)."
        "\n\nExample (predictions carry subset/split per row):"
        "\n  evomas run evaluation --predictions evomas_predictions.jsonl"
        "\nExample (force every row into one bucket):"
        "\n  evomas run evaluation --predictions evomas_predictions.jsonl --subset lite --split dev"
        "\nExample (remote):"
        "\n  evomas run evaluation --remote --predictions evomas_predictions.jsonl"
    ),
)
def run_evaluation(
    ctx: typer.Context,
    predictions: str = typer.Option(
        ..., "--predictions",
        help="Path to the predictions JSONL.",
    ),
    split: Optional[str] = typer.Option(
        None, "--split",
        help=(
            "Override per-row split (forces every row into this bucket). "
            "Omit to let the underlying script read each row's own split. "
            "Local accepts dev | test | train; remote only dev / test."
        ),
    ),
    subset: Optional[str] = typer.Option(
        None, "--subset",
        help=(
            "Override per-row subset. Omit to let each row's own subset "
            "decide. Local accepts lite | full | verified; remote accepts "
            "lite | verified | multimodal (the hosted API has no 'full')."
        ),
    ),
    max_workers: int = typer.Option(
        8, "--max-workers",
        help="Parallel harness workers (--local only; ignored on --remote).",
    ),
    run_id: Optional[str] = typer.Option(
        None, "--run-id",
        help="Override the auto-generated `evomas-<split>-<timestamp>` run id.",
    ),
    report_dir: Optional[str] = typer.Option(
        None, "--report-dir",
        help="Where reports land. Default: `./sb-cli-reports` for --remote.",
    ),
    remote: bool = typer.Option(
        False, "--remote/--local",
        help="--local (default) runs the Docker harness for full logs; --remote submits via sb-cli.",
    ),
) -> None:
    if remote:
        # Remote only forwards common args; max-workers is local-only.
        forwarded: list[str] = ["--predictions", predictions]
        if subset:
            forwarded += ["--subset", subset]
        if split:
            forwarded += ["--split", split]
        if run_id:
            forwarded += ["--run-id", run_id]
        if report_dir:
            forwarded += ["--output-dir", report_dir]
        forwarded.extend(ctx.args)
        raise typer.Exit(_run_script("evaluation/run_swebench_evaluation_remote.py", forwarded))

    forwarded = [
        "--predictions", predictions,
        "--max-workers", str(max_workers),
    ]
    if subset:
        forwarded += ["--subset", subset]
    if split:
        forwarded += ["--split", split]
    if run_id:
        forwarded += ["--run-id", run_id]
    if report_dir:
        forwarded += ["--report-dir", report_dir]
    forwarded.extend(ctx.args)
    raise typer.Exit(_run_script("evaluation/run_swebench_evaluation.py", forwarded))


# ─── server entry points ──────────────────────────────────────────────────────
@app.command()
def web() -> None:
    """Start the Angular frontend dev server.

    Example:  evomas web
    """
    raise typer.Exit(_run_shell_script("start_frontend", []))


@app.command()
def api() -> None:
    """Start the FastAPI backend.

    Example:  evomas api
    """
    raise typer.Exit(_run_shell_script("start_api", []))


# ─── status / doctor ──────────────────────────────────────────────────────────
_OK = "[ OK ]"
_WARN = "[WARN]"
_FAIL = "[FAIL]"
# Marker -> colour. typer/click strips these ANSI codes automatically when the
# output isn't a TTY (piped, or captured by CliRunner in the tests), so the
# plain-text markers still match there.
_STATUS_COLOR = {
    _OK: typer.colors.GREEN,
    _WARN: typer.colors.YELLOW,
    _FAIL: typer.colors.RED,
}


def _print_section(title: str, *, blank_before: bool = True) -> None:
    prefix = "\n" if blank_before else ""
    typer.echo(prefix + typer.style(title, fg=typer.colors.CYAN, bold=True))


def _path_present(path: Path) -> bool:
    """True if `path` exists in any form -- including a symlink entry whose
    target can't be resolved from here. The SWE-bench harness venv is built
    inside WSL, so `SWE-bench/venv/bin/python` is a symlink into the Linux
    filesystem: from Windows `exists()`/`is_file()` both return False (and a
    raw `stat()` even raises WinError 1920), yet the entry is really there.
    `lexists` (an `lstat`, no link-follow) catches that case."""
    try:
        return os.path.exists(path) or os.path.lexists(path)
    except OSError:
        return False


def _print_check(status: str, label: str, detail: str = "") -> None:
    # Plain ASCII markers -- Windows' default cp1252 console chokes on the
    # nicer check/cross glyphs (same reason run_tests.py avoids box-drawing).
    colour = _STATUS_COLOR.get(status)
    marker = typer.style(status, fg=colour, bold=True) if colour else status
    line = f"  {marker}  {typer.style(label, bold=True)}"
    if detail:
        line += f" -- {detail}"
    typer.echo(line)


def _docker_daemon_running() -> Optional[bool]:
    """True if `docker info` succeeds, False if the CLI is present but the
    daemon is unreachable, None if the docker CLI isn't installed at all."""
    if shutil.which("docker") is None:
        return None
    try:
        rc = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=15,
        ).returncode
    except (subprocess.TimeoutExpired, OSError):
        return False
    return rc == 0


def _ollama_reachable(url: str) -> Optional[bool]:
    """True if the Ollama server answers at `url`, False on connection
    error / timeout, None if no URL is configured."""
    url = (url or "").strip()
    if not url:
        return None
    import urllib.error
    import urllib.request
    endpoint = url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(endpoint, timeout=3) as resp:  # noqa: S310
            return 200 <= resp.status < 500
    except (urllib.error.URLError, OSError, ValueError):
        return False


@app.command(
    "status",
    help=(
        "Doctor-style readiness check (read-only): prerequisites (python, "
        "git, ollama, docker, node), the .env files, the ~/.evomas-venv, the "
        "SWE-bench clone + its harness venv, and whether the Docker daemon "
        "and Ollama server are reachable."
        "\n\nExample:  evomas status"
    ),
)
def status() -> None:
    typer.echo(typer.style("EvoMas status", bold=True) + "\n")

    # ── Prerequisites (CLIs on PATH) ────────────────────────────────────────
    _print_section("Prerequisites", blank_before=False)
    py_detail = f"{platform.python_version()} ({sys.executable})"
    _print_check(_OK, "python", py_detail)
    for name, why in (
        ("git", "needed to clone the SWE-bench harness and repos under test"),
        ("ollama", "hosts the local LLM each agent calls"),
        ("docker", "runs the SWE-bench harness for `evomas run evaluation --local`"),
        ("npm", "builds/serves the Angular frontend (`evomas web`)"),
    ):
        found = shutil.which(name)
        if found:
            _print_check(_OK, name, found)
        else:
            _print_check(_WARN, name, f"not on PATH -- {why}")

    # ── Environment files ───────────────────────────────────────────────────
    _print_section("Environment files")
    for rel in ("evomas/.env", "api/.env"):
        path = REPO_ROOT / rel
        if path.is_file():
            _print_check(_OK, rel, "present")
        else:
            example = f"{rel}.example"
            _print_check(_WARN, rel, f"missing -- run `cp {example} {rel}`")

    # ── Python venv ─────────────────────────────────────────────────────────
    _print_section("Python venv")
    venv_dir = Path.home() / ".evomas-venv"
    venv_py = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv_py.is_file():
        _print_check(_OK, "~/.evomas-venv", str(venv_py))
    else:
        _print_check(
            _WARN, "~/.evomas-venv",
            "not found -- run ./install.sh (or .\\install.ps1 on Windows)",
        )

    # ── SWE-bench harness (local evaluation only) ───────────────────────────
    _print_section("SWE-bench harness (local evaluation only)")
    sb_dir = _resolve_swebench_dir()
    if sb_dir.is_dir():
        _print_check(_OK, "clone", str(sb_dir))
        # POSIX-only harness venv; on Windows it lives under WSL's Linux tree,
        # so bin/python is a symlink Windows can't resolve -- _path_present
        # (lexists) still detects the entry.
        sb_py = sb_dir / "venv" / "bin" / "python"
        if _path_present(sb_py):
            _print_check(_OK, "harness venv", str(sb_py))
        else:
            _print_check(
                _WARN, "harness venv",
                f"missing at {sb_py} -- build it (POSIX-only; use WSL on Windows)",
            )
    else:
        _print_check(
            _WARN, "clone",
            f"missing at {sb_dir} -- `git clone "
            "https://github.com/SWE-bench/SWE-bench.git` (only needed for --local eval)",
        )

    # ── Live services ───────────────────────────────────────────────────────
    _print_section("Live services")
    daemon = _docker_daemon_running()
    if daemon is True:
        _print_check(_OK, "docker daemon", "reachable")
    elif daemon is False:
        _print_check(_WARN, "docker daemon", "not reachable -- is Docker Desktop running?")
    else:
        _print_check(_WARN, "docker daemon", "docker CLI not installed")

    ollama_url = os.environ.get("OLLAMA_BASE_URL", "").strip() or "http://localhost:11434"
    reachable = _ollama_reachable(ollama_url)
    if reachable is True:
        _print_check(_OK, "ollama server", ollama_url)
    else:
        _print_check(_WARN, "ollama server", f"not reachable at {ollama_url}")

    typer.echo("")
    raise typer.Exit(0)


# ─── apply (re-run pytest against a prediction's patch) ──────────────────────
@app.command(
    "apply",
    context_settings=_FORWARD_CTX,
    help=(
        "Apply a prediction's patch to its repo and run the project's "
        "tests. With --instance-id, only the matching row in both "
        "--predictions and --instances is processed."
        "\n\nExample:  evomas apply --predictions evomas_predictions.jsonl --instances swebench_instances.jsonl --instance-id sqlfluff__sqlfluff-1625"
        "\nExample:  evomas apply --predictions evomas_predictions.jsonl --instances swebench_instances.jsonl --instance-id custom-<owner>-<name>-<short-sha> --report-dir results/evaluations"
    ),
)
def apply(
    ctx: typer.Context,
    predictions: str = typer.Option(
        ..., "--predictions",
        help="Path to the JSONL produced by `evomas run prediction`.",
    ),
    instances: str = typer.Option(
        ..., "--instances",
        help="Path to the JSONL produced by `evomas run instances`.",
    ),
    instance_id: Optional[str] = typer.Option(
        None, "--instance-id",
        help="When set, narrow the apply+test loop to this single instance_id.",
    ),
    keep: bool = typer.Option(
        False, "--keep",
        help="Keep the patch applied (don't reset workspace after testing).",
    ),
    report_dir: Optional[str] = typer.Option(
        None, "--report-dir",
        help="When set, write SWE-bench-compatible reports under this directory.",
    ),
    run_id: Optional[str] = typer.Option(
        None, "--run-id",
        help="Override the auto-generated `apply-and-test-<ts>` run id.",
    ),
    model: Optional[str] = typer.Option(
        None, "--model",
        help="Model name used in the report path. Default: 'evomas-custom'.",
    ),
) -> None:
    forwarded: list[str] = ["--predictions", predictions, "--instances", instances]
    if instance_id:
        forwarded += ["--instance-id", instance_id]
    if keep:
        forwarded.append("--keep")
    if report_dir:
        forwarded += ["--report-dir", report_dir]
    if run_id:
        forwarded += ["--run-id", run_id]
    if model:
        forwarded += ["--model", model]
    forwarded.extend(ctx.args)
    raise typer.Exit(_run_script("evaluation/apply_and_test.py", forwarded))


# ─── test runner ──────────────────────────────────────────────────────────────
@app.command(
    "test",
    context_settings=_FORWARD_CTX,
    help=(
        "Run pytest (backend) and ng test (frontend). Extra args after `--` "
        "are forwarded verbatim to the inner runner."
        "\n\nExample:  evomas test --backend-only -- -k apply_description_fix"
        "\nExample:  evomas test --frontend-only --integration -- --include \"src/integration/**\""
    ),
)
def test(
    ctx: typer.Context,
    backend_only: bool = typer.Option(
        False, "--backend-only",
        help="Skip ng test; forward extras to pytest only.",
    ),
    frontend_only: bool = typer.Option(
        False, "--frontend-only",
        help="Skip pytest; forward extras to ng test only.",
    ),
    integration: bool = typer.Option(
        False, "--integration",
        help="Set EVOMAS_RUN_INTEGRATION=1 before running.",
    ),
) -> None:
    if backend_only and frontend_only:
        typer.echo("Cannot use --backend-only and --frontend-only together.", err=True)
        raise typer.Exit(2)
    forwarded: list[str] = []
    if backend_only:
        forwarded.append("--backend-only")
    if frontend_only:
        forwarded.append("--frontend-only")
    if integration:
        forwarded.append("--integration")
    forwarded.extend(ctx.args)
    raise typer.Exit(_run_script("run_tests.py", forwarded))


# ─── notebook export ─────────────────────────────────────────────────────────
@app.command(
    "notebook",
    help=(
        "Export a reproduce-this-run Jupyter notebook (.ipynb). Two modes:"
        "\n  - From an existing prediction JSONL (--predictions): includes"
        " the compare-with-original section that diffs the re-run against"
        " the original model_patch. Mirrors the Results page button."
        "\n  - From inputs (--config + --instances): no baseline to diff"
        " against, so the comparative section is omitted. Mirrors the"
        " Inference page download button."
        "\n\nExample:  evomas notebook --predictions results/predictions/prediction-<run-id>.jsonl --evaluator apply_and_test"
    ),
)
def notebook(
    predictions: Optional[str] = typer.Option(
        None, "--predictions",
        help="Path to the prediction JSONL. Mutually exclusive with --config.",
    ),
    config: Optional[str] = typer.Option(
        None, "--config",
        help="Config name (stem) to bake into the notebook. Resolved against "
             "evomas/config/predefined/ then loaded/. Mutually exclusive with --predictions.",
    ),
    instances: Optional[str] = typer.Option(
        None, "--instances",
        help="Path to a JSONL file whose lines carry `instance_id` (the same "
             "shape `evomas run instances` writes). Each row's `instance_id` "
             "is fed to the builder. Required with --config; ignored with "
             "--predictions (which already carries the ids).",
    ),
    evaluator: str = typer.Option(
        ..., "--evaluator",
        help="Filename stem under `scripts/evaluation/` (no `.py`) to bake "
             "into the notebook's section 5. Common choices: "
             "`apply_and_test` (code-repair via pytest), "
             "`run_swebench_evaluation` (SWE-bench POSIX harness), "
             "`translate_eval` (BLEU vs .gold sidecars). Required — pick "
             "the grader that matches your task.",
    ),
    output: Optional[str] = typer.Option(
        None, "--output",
        help="Where to write the .ipynb. Defaults to a sensible stem in the cwd.",
    ),
) -> None:
    from evomas.utils.notebook import (
        build_notebook_for_inputs, build_notebook_for_prediction,
    )

    if bool(predictions) == bool(config):
        typer.echo(
            "Pass exactly one of --predictions or --config.", err=True,
        )
        raise typer.Exit(2)

    if predictions:
        pred_path = Path(predictions).resolve()
        try:
            run_id, nb = build_notebook_for_prediction(pred_path, evaluator=evaluator)
        except FileNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
        default_stem = pred_path.stem
    else:
        assert config is not None
        if not instances:
            typer.echo("--instances is required with --config.", err=True)
            raise typer.Exit(2)
        inst_path = Path(instances).resolve()
        if not inst_path.is_file():
            typer.echo(f"Instances file not found: {inst_path}", err=True)
            raise typer.Exit(1)
        ids: list[str] = []
        for raw_line in inst_path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            iid = row.get("instance_id")
            if isinstance(iid, str) and iid:
                ids.append(iid)
        if not ids:
            typer.echo(f"No instance_id rows in {inst_path}.", err=True)
            raise typer.Exit(1)
        # Resolve config via the same loader the topology page uses.
        from evomas.config.loader import resolve_config_path
        from evomas.paths import LOADED_CONFIG_DIR, PREDEFINED_CONFIG_DIR
        cfg_path = resolve_config_path(
            config, predefined_dir=PREDEFINED_CONFIG_DIR, loaded_dir=LOADED_CONFIG_DIR,
        )
        if cfg_path is None:
            typer.echo(f"Config '{config}' not found.", err=True)
            raise typer.Exit(1)
        try:
            cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            typer.echo(f"Failed to parse {cfg_path}: {exc}", err=True)
            raise typer.Exit(1)
        # Pass the user-supplied JSONL as the cache the row lookup
        # reads — that's where the (subset, split) per id and the
        # custom-row inputs live.
        try:
            run_id, nb = build_notebook_for_inputs(
                instance_ids=ids, config_data=cfg_data,
                instances_path=inst_path, evaluator=evaluator,
            )
        except FileNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
        default_stem = f"notebook-{run_id}"

    out_path = Path(output) if output else Path.cwd() / f"{default_stem}.ipynb"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(nb, indent=1), encoding="utf-8")
    typer.echo(f"Wrote reproduce-this-run notebook for {run_id} -> {out_path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
