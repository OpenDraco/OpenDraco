"""Apply EvoMas patches to their repos and run the tests, optionally writing a SWE-bench-compatible report layout for the Results page."""
# No `EVOMAS_EVALUATOR` manifest needed -- single_shot dispatch + no
# WSL are the framework defaults. See `docs/adding_a_new_problem.md`.

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Reuse evomas.tools.patch_tools.apply_patch_impl when importable so we get the
# `patch --fuzz=5` fallback for LLM-generated diffs with wrong hunk line numbers.
# scripts/evaluation/<this>.py -- parents[2] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
try:
    from evomas.utils.patch import apply_patch_impl, normalize_patch_impl  # noqa: E402
    _HAS_EVOMAS_PATCH_TOOLS = True
except Exception:  # pragma: no cover
    _HAS_EVOMAS_PATCH_TOOLS = False

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markup import escape as esc

_console = Console(force_terminal=True, highlight=False)


def _print(msg: str) -> None:
    _console.print(msg)


def load_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _parse_list(value: Any) -> list[str]:
    """SWE-bench stores FAIL_TO_PASS / PASS_TO_PASS as a JSON-encoded string."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
    return []


def _workspace_root() -> Path:
    root = Path(tempfile.gettempdir()) / "evomas_workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _git(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True)


def _checkout(commit: str, cwd: Path) -> None:
    """Try a plain checkout, fall back to `git fetch --all` + retry if the SHA isn't local yet."""
    res = _git(["git", "checkout", commit], cwd=cwd)
    if res.returncode == 0:
        return
    # `--depth=1 origin <sha>` is fragile: GitHub requires
    # uploadpack.allowReachableSHA1InWant for arbitrary-SHA fetches, and a
    # shallow history may not contain the parents we need.
    logger.info("checkout %s failed locally; running 'git fetch --all'", commit[:8])
    fetch = _git(["git", "fetch", "--all"], cwd=cwd)
    if fetch.returncode != 0:
        raise subprocess.CalledProcessError(
            fetch.returncode, fetch.args,
            output=fetch.stdout, stderr=fetch.stderr,
        )
    res2 = _git(["git", "checkout", commit], cwd=cwd)
    if res2.returncode != 0:
        msg = (f"git checkout {commit} failed even after `git fetch --all`. "
               f"initial stderr: {res.stderr.strip() or res.stdout.strip()} | "
               f"post-fetch stderr: {res2.stderr.strip() or res2.stdout.strip()}")
        raise subprocess.CalledProcessError(
            res2.returncode, res2.args, output=res2.stdout, stderr=msg,
        )


def _force_rmtree(path: Path) -> None:
    """Remove `path` even when Windows has partially-locked files inside (Defender / OneDrive scans on .git templates are the common culprit)."""
    import os, shutil, stat
    if not path.exists():
        return

    def _on_error(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    shutil.rmtree(path, onerror=_on_error)
    if path.exists():
        subprocess.run(["cmd", "/c", "rmdir", "/S", "/Q", str(path)],
                       capture_output=True)


def _do_clone(url: str, dest: Path) -> None:
    """Clone, retrying at a uuid-suffixed path on the Windows AV `.git/hooks/` `File exists` race so the clone always lands somewhere."""
    import uuid
    res = _git(["git", "clone", url, str(dest)])
    if res.returncode == 0:
        return
    # Windows AV can rehydrate template files inside `.git/hooks/` faster than
    # git can write them (rc=128, "File exists"). Retry once at a fresh path.
    if "File exists" in (res.stderr or "") + (res.stdout or ""):
        fallback = dest.parent / f"{dest.name}-{uuid.uuid4().hex[:8]}"
        logger.warning("clone hit File-exists race; retrying at %s", fallback)
        res2 = _git(["git", "clone", url, str(fallback)])
        if res2.returncode == 0:
            # Rename to original dest so downstream paths stay stable.
            _force_rmtree(dest)
            fallback.rename(dest)
            return
        raise subprocess.CalledProcessError(
            res2.returncode, res2.args,
            output=res2.stdout,
            stderr=f"{res.stderr or ''}\n---\n{res2.stderr or ''}",
        )
    raise subprocess.CalledProcessError(
        res.returncode, res.args, output=res.stdout, stderr=res.stderr,
    )


def clone_or_reuse(repo: str, base_commit: str, keep: bool = False) -> Path:
    dest = _workspace_root() / repo.replace("/", "__")
    if dest.is_dir() and (dest / ".git").is_dir():
        if keep:
            # `--keep` reuses whatever's on disk so the user can iterate on a
            # previous run's state; a conflicting new patch is theirs to manage.
            logger.info("Reusing workspace %s (--keep set; skipping pre-run scrub)", dest)
            return dest
        # Scrub leftover state so a previous run's patch + untracked files
        # don't pollute this test.
        logger.info("Cleaning workspace at %s (base_commit=%s)", dest, base_commit[:8])
        _git(["git", "reset", "--hard", "HEAD"], cwd=dest)
        _git(["git", "clean", "-fdx"], cwd=dest)
        try:
            _checkout(base_commit, cwd=dest)
            return dest
        except subprocess.CalledProcessError as exc:
            logger.warning(
                "in-place checkout failed (%s); falling through to reclone",
                (exc.stderr or "").strip() or exc,
            )
        _force_rmtree(dest)
    elif dest.is_dir():
        logger.info("workspace %s exists but is not a git repo; wiping", dest)
        _force_rmtree(dest)

    logger.info("Cloning %s @ %s", repo, base_commit[:8])
    _do_clone(f"https://github.com/{repo}.git", dest)
    _checkout(base_commit, cwd=dest)
    return dest


def apply_patch(patch: str, workspace: Path) -> tuple[bool, str]:
    """Apply a unified diff via evomas.tools.patch_tools when importable, else plain `git apply` so the script stays usable standalone."""
    if not patch or not patch.strip():
        return False, "empty patch"

    if _HAS_EVOMAS_PATCH_TOOLS:
        normalized = normalize_patch_impl(patch)  # pyright: ignore[reportPossiblyUnboundVariable]
        res = apply_patch_impl(normalized or patch, str(workspace), dry_run=False)  # pyright: ignore[reportPossiblyUnboundVariable]
        if res["applied"]:
            return True, res.get("output") or "patch applied"
        return False, (res.get("output") or "patch did not apply").strip()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".patch", delete=False, encoding="utf-8", newline="\n"
    ) as f:
        f.write(patch)
        patch_path = Path(f.name)
    try:
        check = subprocess.run(
            ["git", "apply", "--check", str(patch_path)],
            cwd=workspace, capture_output=True, text=True
        )
        if check.returncode != 0:
            return False, check.stderr.strip() or check.stdout.strip()
        result = subprocess.run(
            ["git", "apply", str(patch_path)],
            cwd=workspace, capture_output=True, text=True
        )
        if result.returncode != 0:
            return False, result.stderr.strip() or result.stdout.strip()
        return True, ""
    finally:
        patch_path.unlink(missing_ok=True)


def reset_workspace(workspace: Path, base_commit: str) -> None:
    subprocess.run(["git", "checkout", base_commit, "--", "."],
                   cwd=workspace, capture_output=True)


def run_tests(
    workspace: Path,
    fail_to_pass: list[str],
    pass_to_pass: list[str],
) -> dict[str, Any]:
    targets = fail_to_pass + pass_to_pass
    cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short"] + (targets or [])
    result = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True)
    output = result.stdout + result.stderr

    statuses: dict[str, str] = {}
    for line in output.splitlines():
        for status in ("PASSED", "FAILED", "ERROR"):
            if f" {status}" in line:
                tid = line.strip().split()[0]
                statuses[tid] = status

    def _status(test_id: str) -> str:
        if test_id in statuses:
            return statuses[test_id]
        short = test_id.split("::")[-1]
        for k, v in statuses.items():
            if k.endswith(f"::{short}"):
                return v
        return "NOT_RUN"

    ftp_results = {t: _status(t) for t in fail_to_pass}
    ptp_results = {t: _status(t) for t in pass_to_pass}

    ftp_resolved   = all(v == "PASSED" for v in ftp_results.values()) if ftp_results else True
    ptp_maintained = all(v == "PASSED" for v in ptp_results.values()) if ptp_results else True

    # Custom-repo rows have no FTP/PTP lists; the SWE-bench rule would return
    # True for an empty classification axis regardless of pytest's verdict, so
    # fall back to the process return code instead.
    if not fail_to_pass and not pass_to_pass:
        resolved = result.returncode == 0
        rule = "pytest_returncode==0"
    else:
        resolved = ftp_resolved and ptp_maintained
        rule = "FTP_pass AND PTP_pass"

    return {
        "resolved":         resolved,
        "resolved_rule":    rule,
        "ftp_resolved":     ftp_resolved,
        "ptp_maintained":   ptp_maintained,
        "ftp_results":      ftp_results,
        "ptp_results":      ptp_results,
        # Drives the FAIL_TO_PASS bucket for custom-repo instances (which
        # carry no FTP/PTP lists from the dataset).
        "all_test_results": statuses,
        "returncode":       result.returncode,
        "output":           output,
    }


def _status_icon(val: str) -> str:
    return {"PASSED": "+", "FAILED": "x", "ERROR": "!", "NOT_RUN": "?"}.get(val, val)


def print_result(instance_id: str, apply_ok: bool, apply_msg: str,
                 test: dict[str, Any]) -> None:
    resolved = test["resolved"]
    color = "green" if resolved else "red"
    verdict = "[bold green]RESOLVED[/bold green]" if resolved else "[bold red]NOT RESOLVED[/bold red]"

    t = Table(show_header=True, box=None, padding=(0, 2))
    t.add_column("type", style="dim", no_wrap=True)
    t.add_column("test")
    t.add_column("result", no_wrap=True)
    for tid, s in test["ftp_results"].items():
        icon = f"[green]{_status_icon(s)}[/green]" if s == "PASSED" else f"[red]{_status_icon(s)}[/red]"
        t.add_row("fail->pass", esc(tid.split("::")[-1]), f"{icon} {s}")
    for tid, s in test["ptp_results"].items():
        icon = f"[green]{_status_icon(s)}[/green]" if s == "PASSED" else f"[red]{_status_icon(s)}[/red]"
        t.add_row("regression", esc(tid.split("::")[-1]), f"{icon} {s}")

    body = f"patch: {'applied' if apply_ok else f'[red]FAILED - {esc(apply_msg[:120])}[/red]'}\n"
    body += f"rule:  {esc(test.get('resolved_rule', '?'))}\n"
    if not test["ftp_results"] and not test["ptp_results"]:
        body += f"pytest returncode: {test['returncode']}\n"
    _console.print(Panel(
        body,
        title=f"[bold]{esc(instance_id)}[/bold]  {verdict}",
        border_style=color,
    ))
    if test["ftp_results"] or test["ptp_results"]:
        _console.print(t)


def print_summary(results: list[dict[str, Any]]) -> None:
    resolved = sum(1 for r in results if r.get("resolved"))
    total = len(results)
    color = "green" if resolved == total else "yellow" if resolved > 0 else "red"
    msg = f"Resolved {resolved}/{total} instances"
    _console.print(Panel(f"[bold]{msg}[/bold]", border_style=color))


def _bucket_tests(results: dict[str, str]) -> dict[str, list[str]]:
    """Split {test_id: status} into SWE-bench `success` / `failure` buckets."""
    success = [tid for tid, s in results.items() if s == "PASSED"]
    failure = [tid for tid, s in results.items() if s != "PASSED"]
    return {"success": success, "failure": failure}


def write_instance_report(
    report_dir: Path,
    run_id: str,
    model: str,
    instance_id: str,
    patch: str,
    apply_ok: bool,
    apply_msg: str,
    test: dict[str, Any],
    repo: str = "",
    base_commit: str = "",
    workspace: Path | None = None,
) -> Path:
    """Write the SWE-bench-compatible per-instance files (report.json, patch.diff, test_output.txt, run_instance.log) and return the instance directory.

    No eval.sh is written: the harness wraps a Docker container, while custom
    rows run pytest directly. Custom rows have no FTP/PTP from the dataset, so
    every discovered test goes into FAIL_TO_PASS (the bucket the Results page
    renders).
    """
    inst_dir = report_dir / "logs" / "run_evaluation" / run_id / model / instance_id
    inst_dir.mkdir(parents=True, exist_ok=True)

    patch_is_none = not (patch and patch.strip())

    has_classification = bool(test.get("ftp_results") or test.get("ptp_results"))
    if has_classification:
        ftp_bucket = _bucket_tests(test.get("ftp_results", {}))
        ptp_bucket = _bucket_tests(test.get("ptp_results", {}))
    else:
        ftp_bucket = _bucket_tests(test.get("all_test_results", {}))
        ptp_bucket = {"success": [], "failure": []}

    entry = {
        "patch_is_None":              patch_is_none,
        "patch_exists":               not patch_is_none,
        "patch_successfully_applied": apply_ok,
        "resolved":                   bool(test.get("resolved")),
        "tests_status": {
            "FAIL_TO_PASS": ftp_bucket,
            "PASS_TO_PASS": ptp_bucket,
            "FAIL_TO_FAIL": {"success": [], "failure": []},
            "PASS_TO_FAIL": {"success": [], "failure": []},
        },
        "custom_eval": {
            "pytest_returncode": test.get("returncode", -1),
            "pytest_tail":       (test.get("output") or "")[-2000:],
            "resolved_rule":     test.get("resolved_rule", "?"),
        },
    }
    (inst_dir / "report.json").write_text(
        json.dumps({instance_id: entry}, indent=2),
        encoding="utf-8",
    )
    (inst_dir / "patch.diff").write_text(patch or "", encoding="utf-8")
    (inst_dir / "test_output.txt").write_text(
        test.get("output") or "", encoding="utf-8",
    )
    _write_run_instance_log(
        inst_dir, instance_id, repo, base_commit, workspace,
        patch, patch_is_none, apply_ok, apply_msg, test, entry,
    )
    return inst_dir


def _write_run_instance_log(
    inst_dir: Path,
    instance_id: str,
    repo: str,
    base_commit: str,
    workspace: Path | None,
    patch: str,
    patch_is_none: bool,
    apply_ok: bool,
    apply_msg: str,
    test: dict[str, Any],
    report_entry: dict[str, Any],
) -> None:
    """Emit run_instance.log in SWE-bench harness format so the Results page's syntax-highlighting works unchanged."""
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]

    lines: list[str] = []
    lines.append(f"{_now()} - INFO - Preparing workspace for {instance_id} (no container -- custom-repo eval)...")
    if repo:
        lines.append(f"{_now()} - INFO - Repo: {repo} @ {base_commit or '?'}")
    if workspace:
        lines.append(f"{_now()} - INFO - Workspace path: {workspace}")
    if patch_is_none:
        lines.append(f"{_now()} - WARNING - model_patch is empty -- nothing to apply.")
    else:
        lines.append(f"{_now()} - INFO - Intermediate patch for {instance_id} written to {inst_dir / 'patch.diff'}, now applying...")
        if apply_ok:
            lines.append(f"{_now()} - INFO - >>>>> Applied Patch:")
            lines.append((apply_msg or "patch applied").strip())
        else:
            lines.append(f"{_now()} - ERROR - patch did not apply: {apply_msg.strip() or 'unknown'}")
    lines.append(f"{_now()} - INFO - eval.sh is not generated for custom-repo evaluation -- pytest is invoked directly.")
    lines.append(f"{_now()} - INFO - Running tests via `python -m pytest` (rule: {test.get('resolved_rule', '?')})")
    lines.append(f"{_now()} - INFO - pytest returncode: {test.get('returncode', -1)}")
    lines.append(f"{_now()} - INFO - Test output for {instance_id} written to {inst_dir / 'test_output.txt'}")
    lines.append(f"{_now()} - INFO - Grading answer for {instance_id}...")
    lines.append(f"{_now()} - INFO - report: {json.dumps({instance_id: report_entry})}")
    lines.append(f"Result for {instance_id}: resolved: {bool(test.get('resolved'))}")
    (inst_dir / "run_instance.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_run_summary(
    report_dir: Path,
    run_id: str,
    model: str,
    per_instance: list[dict[str, Any]],
) -> Path:
    """Mirror SWE-bench's <model>.<run-id>.json aggregate."""
    completed_ids = [r["instance_id"] for r in per_instance if r.get("completed")]
    resolved_ids  = [r["instance_id"] for r in per_instance if r.get("resolved")]
    error_ids     = [r["instance_id"] for r in per_instance if r.get("error")]

    summary = {
        "schema_version":      2,
        "run_id":              run_id,
        "model":               model,
        "generated_at":        datetime.now(timezone.utc).isoformat(),
        "total_instances":     len(per_instance),
        "submitted_instances": len(per_instance),
        "completed_instances": len(completed_ids),
        "resolved_instances":  len(resolved_ids),
        "completed_ids":       completed_ids,
        "incomplete_ids":      [r["instance_id"] for r in per_instance if not r.get("completed")],
        "error_ids":           error_ids,
        "resolved_ids":        resolved_ids,
    }
    out = report_dir / f"{model}.{run_id}.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply patches and run tests.")
    parser.add_argument("--instances",   required=True, help="Instance JSONL file")
    parser.add_argument("--predictions", required=True, help="Predictions JSONL file")
    parser.add_argument("--keep",        action="store_true",
                        help="Keep patch applied (do not reset workspace after testing)")
    parser.add_argument("--report-dir",  default="",
                        help="When set, also write SWE-bench-compatible reports under "
                             "<report-dir>/logs/run_evaluation/<run-id>/<model>/<instance_id>/")
    parser.add_argument("--run-id",      default="",
                        help="Run identifier used in the report path. Defaults to a timestamp.")
    parser.add_argument("--model",       default="evomas-custom",
                        help="Model name used in the report path. Default: 'evomas-custom'.")
    parser.add_argument("--instance-id", dest="instance_id", default="",
                        help="When set, narrow the apply+test loop to this single "
                             "instance_id. Must exist in both --instances and "
                             "--predictions; otherwise the script exits with an error.")
    args = parser.parse_args()

    report_dir = Path(args.report_dir).resolve() if args.report_dir else None
    run_id = args.run_id or f"apply-and-test-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    model = args.model

    instances   = {r["instance_id"]: r for r in load_jsonl(args.instances)}
    predictions = {r["instance_id"]: r for r in load_jsonl(args.predictions)}

    common = [iid for iid in predictions if iid in instances]
    if args.instance_id:
        if args.instance_id not in common:
            _print(
                f"[red]--instance-id {args.instance_id!r} is not in the "
                f"intersection of --instances and --predictions.[/red]"
            )
            sys.exit(1)
        common = [args.instance_id]
    if not common:
        _print("[red]No matching instance_ids found between the two files.[/red]")
        sys.exit(1)

    logger.info("Evaluating %d instance(s)", len(common))

    all_results: list[dict[str, Any]] = []
    per_instance_summary: list[dict[str, Any]] = []
    for iid in common:
        inst = instances[iid]
        pred = predictions[iid]
        patch = pred.get("model_patch", "")
        repo        = inst["repo"]
        base_commit = inst["base_commit"]
        ftp = _parse_list(inst.get("FAIL_TO_PASS", []))
        ptp = _parse_list(inst.get("PASS_TO_PASS", []))

        logger.info("-- %s --", iid)

        workspace = None
        clone_error: str | None = None
        try:
            workspace = clone_or_reuse(repo, base_commit, keep=args.keep)
        except subprocess.CalledProcessError as cpe:
            detail = (cpe.stderr or "").strip() or (cpe.output or "").strip() or str(cpe)
            logger.error("Clone failed (rc=%s): %s", cpe.returncode, detail)
            clone_error = detail
        except Exception as exc:  # noqa: BLE001
            logger.error("Clone failed: %s", exc)
            clone_error = str(exc)

        if clone_error is not None:
            all_results.append({"instance_id": iid, "resolved": False})
            per_instance_summary.append({
                "instance_id": iid, "completed": False, "resolved": False, "error": True,
            })
            if report_dir:
                empty_test = {
                    "resolved": False, "resolved_rule": "clone_failed",
                    "ftp_results": {}, "ptp_results": {}, "all_test_results": {},
                    "returncode": -1, "output": f"clone failed: {clone_error}",
                }
                write_instance_report(
                    report_dir, run_id, model, iid, patch, False,
                    apply_msg=clone_error or "clone failed",
                    test=empty_test,
                    repo=repo, base_commit=base_commit, workspace=None,
                )
            continue
        assert workspace is not None

        apply_ok, apply_msg = apply_patch(patch, workspace)
        if not apply_ok:
            logger.warning("Patch did not apply: %s", apply_msg)

        # Run tests even on apply failure so the report shows a baseline.
        test = run_tests(workspace, ftp, ptp)
        test["instance_id"] = iid
        all_results.append(test)
        per_instance_summary.append({
            "instance_id": iid,
            "completed":   True,
            "resolved":    bool(test["resolved"]),
            "error":       False,
        })

        print_result(iid, apply_ok, apply_msg, test)
        logger.debug("pytest output:\n%s", test["output"])

        if report_dir:
            write_instance_report(
                report_dir, run_id, model, iid, patch, apply_ok,
                apply_msg=apply_msg, test=test,
                repo=repo, base_commit=base_commit, workspace=workspace,
            )

        if not args.keep:
            reset_workspace(workspace, base_commit)

    if report_dir:
        out = write_run_summary(report_dir, run_id, model, per_instance_summary)
        logger.info("Run summary -> %s", out)

    print_summary(all_results)


if __name__ == "__main__":
    main()
