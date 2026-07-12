"""Evaluation entry-point scripts: take a predictions JSONL + instances
JSONL and emit per-instance verdicts in SWE-bench-shaped report files.

- `apply_and_test.py`              — custom-row evaluator (`subset=custom`); clones the repo, applies the patch, runs pytest.
- `run_swebench_evaluation.py`     — local SWE-bench Docker harness wrapper.
- `run_swebench_evaluation_remote.py` — remote sb-cli wrapper (no Docker).
- `translate_eval.py`              — translation-task BLEU evaluator (vs `<file>.gold` sidecars).

Wrapped by `evomas` CLI commands (`evomas run evaluation`, `evomas apply`)
which dispatch via `evomas.cli._run_script("evaluation/<name>.py", ...)`.
"""
