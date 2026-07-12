"""Cross-platform runner for the EvoMas backend (pytest) + frontend (ng test) suites; extras after `--` forward verbatim to the inner runner."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _venv_python() -> Path:
    # install.{sh,ps1} install the venv at ~/.evomas-venv so the repo stays
    # free of build artefacts; start_api.* and the notebooks use the same
    # path. Keep this resolver in sync.
    venv = Path.home() / ".evomas-venv"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _banner(title: str) -> None:
    # Plain ASCII -- Windows' default cp1252 console chokes on box-drawing.
    print(f"\n>>> {title}\n" + "-" * (len(title) + 4), flush=True)


def _run_backend(extra: list[str], integration: bool) -> int:
    venv_py = _venv_python()
    if not venv_py.is_file():
        print(
            f"venv python not found at {venv_py}.\n"
            f"  Set it up by running ./install.sh (or .\\install.ps1 on Windows) "
            f"from the repo root.",
            file=sys.stderr,
        )
        return 1
    cmd = [str(venv_py), "-m", "pytest", "evomas/tests", "-q", *extra]
    env = os.environ.copy()
    if integration:
        env["EVOMAS_RUN_INTEGRATION"] = "1"
    _banner("Backend (pytest)")
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=str(REPO_ROOT), env=env).returncode


def _run_frontend(extra: list[str], integration: bool) -> int:
    """Spawn `ng test` from `app/`; `shell=True` on Windows because `npx` is a `.cmd` shim that subprocess can't locate directly."""
    app_dir = REPO_ROOT / "app"
    if not app_dir.is_dir():
        print(f"frontend directory not found: {app_dir}", file=sys.stderr)
        return 1
    cmd = ["npx", "ng", "test", "--watch=false", *extra]
    env = os.environ.copy()
    if integration:
        env["EVOMAS_RUN_INTEGRATION"] = "1"
    _banner("Frontend (ng test)")
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(
        cmd,
        cwd=str(app_dir),
        env=env,
        shell=(os.name == "nt"),
    ).returncode


def main() -> int:
    # Manual `--` split protects args even if they collide with our own flag
    # names. Typer strips `--` when forwarding from `evomas test`, but
    # parse_known_args below absorbs unknown flags into extras either way.
    argv = list(sys.argv[1:])
    explicit_extras: list[str] = []
    if "--" in argv:
        idx = argv.index("--")
        explicit_extras = argv[idx + 1 :]
        argv = argv[:idx]

    parser = argparse.ArgumentParser(
        description="Run the EvoMas backend (pytest) and/or frontend (ng test) suites.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Pass --backend-only or --frontend-only to scope; "
            "any unknown args (or args after `--`) are forwarded verbatim "
            "to the inner runner."
        ),
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--backend-only", action="store_true",
                       help="skip ng test; extra args go to pytest.")
    scope.add_argument("--frontend-only", action="store_true",
                       help="skip pytest; extra args go to ng test.")
    parser.add_argument("--integration", action="store_true",
                        help="set EVOMAS_RUN_INTEGRATION=1 before running.")
    args, unknown = parser.parse_known_args(argv)
    extras = unknown + explicit_extras

    if extras and not (args.backend_only or args.frontend_only):
        parser.error(
            "extra args are only forwarded when --backend-only or "
            "--frontend-only is set — otherwise pytest flags would leak "
            "into ng test and vice versa. "
            f"unrecognised: {extras}"
        )

    rcs: list[int] = []
    if not args.frontend_only:
        rcs.append(_run_backend(extras if args.backend_only else [], args.integration))
    if not args.backend_only:
        rcs.append(_run_frontend(extras if args.frontend_only else [], args.integration))
    return max(rcs) if rcs else 0


if __name__ == "__main__":
    raise SystemExit(main())
