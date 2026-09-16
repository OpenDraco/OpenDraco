"""Top-level entry-point scripts wrapped by `opendraco.cli`.

The `opendraco` console command (and the repo-root `opendraco.py` shim) dispatch
to `generate_swebench_instances.py` + `generate_opendraco_predictions.py` in
this directory, and to the evaluators under `scripts/evaluation/` (see
that package's `__init__.py`). The package marker exists so `api/server.py`
can do `from scripts.generate_swebench_instances import build_instances`
without `scripts/` being interpreted as a namespace package.
"""
