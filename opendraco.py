"""Repo-root entry point: `python opendraco.py <subcommand>`.

Python prefers a file named `opendraco.py` over the sibling `opendraco/` package
when resolving `import opendraco`, so a naive `from opendraco.cli import main`
here would fail with `'opendraco' is not a package`. We sidestep that by
executing `opendraco/cli.py` via runpy — the CLI module's top-level imports
don't touch the `opendraco` namespace, so no shadowing applies.

The preferred entry point is still the `opendraco` console script registered
by `pip install -e .` (see pyproject.toml `[project.scripts]`); this file
exists so the literal `python opendraco.py` invocation from TODO.md works
out of the box.
"""
import runpy
from pathlib import Path


if __name__ == "__main__":
    cli_path = Path(__file__).resolve().parent / "opendraco" / "cli.py"
    runpy.run_path(str(cli_path), run_name="__main__")
