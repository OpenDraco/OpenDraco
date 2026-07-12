"""Repo-root entry point: `python evomas.py <subcommand>`.

Python prefers a file named `evomas.py` over the sibling `evomas/` package
when resolving `import evomas`, so a naive `from evomas.cli import main`
here would fail with `'evomas' is not a package`. We sidestep that by
executing `evomas/cli.py` via runpy — the CLI module's top-level imports
don't touch the `evomas` namespace, so no shadowing applies.

The preferred entry point is still the `evomas` console script registered
by `pip install -e .` (see pyproject.toml `[project.scripts]`); this file
exists so the literal `python evomas.py` invocation from TODO.md works
out of the box.
"""
import runpy
from pathlib import Path


if __name__ == "__main__":
    cli_path = Path(__file__).resolve().parent / "evomas" / "cli.py"
    runpy.run_path(str(cli_path), run_name="__main__")
