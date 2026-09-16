# OpenDraco CLI

The `opendraco` command wraps every entry point. Run `opendraco <command> --help`
for details on each command's args and options. Installed by `install.sh` /
`install.ps1` — see [Install on machine](../README.md#install-on-machine).

The `opendraco` command wraps every entry point. Run `opendraco <command> --help` for details on each command's args and options.

## Ollama (model management)

Every `ollama` subcommand respects `OLLAMA_BASE_URL` from `opendraco/.env`, so a remote Ollama works the same way as a local one.

**`opendraco ollama pull <model>`** — pull a model tag onto the configured Ollama server.

```bash
opendraco ollama pull qwen3.5:9b
```

**`opendraco ollama list`** — list models already present on the server.

```bash
opendraco ollama list
```

**`opendraco ollama serve [--cpu-only]`** — start the Ollama daemon bound to `OLLAMA_BASE_URL`. `--cpu-only` exports `OLLAMA_NO_CUDA=1` (useful when a tiny GPU would OOM on the model you're targeting).

```bash
opendraco ollama serve --cpu-only
```

## Run (inference + evaluation pipeline)

**`opendraco run instances`** — generate the SWE-bench instances JSONL by pulling a slice of the HuggingFace dataset. Pass `--custom-repo` + `--custom-problem` to append one synthetic row instead.

```bash
opendraco run instances --subset lite --split dev --output swebench_instances.jsonl --limit 5
```

**`opendraco run prediction`** — drive the configured LangGraph topology over every instance in the JSONL and emit one `model_patch` per line.

```bash
opendraco run prediction --instances swebench_instances.jsonl --output opendraco_predictions.jsonl --config hyperagent_star
```

**`opendraco run evaluation`** — score a predictions JSONL. Default `--local` runs the SWE-bench Docker harness (full per-instance logs under `<report-dir>/logs/`; needs Docker, +WSL on Windows). `--remote` submits to [swebench.com](https://www.swebench.com/) via `sb-cli` — verdicts only, no logs, requires `SWEBENCH_API_KEY`.

```bash
opendraco run evaluation --predictions opendraco_predictions.jsonl --subset lite --split dev
opendraco run evaluation --remote --predictions opendraco_predictions.jsonl --subset lite --split dev
```

## Re-evaluation / debugging utilities

**`opendraco apply`** — re-run pytest against a stored prediction's patch (clone → apply → pytest). Useful for inspecting *why* a custom-repo instance didn't resolve without rerunning inference.

```bash
opendraco apply \
  --predictions opendraco_predictions.jsonl \
  --instances   swebench_instances.jsonl \
  --instance-id sqlfluff__sqlfluff-1625
```

**`opendraco notebook`** — export a reproduce-this-run Jupyter notebook. Two input modes:
- From a prediction JSONL (`--predictions`): includes the comparison section that diffs a fresh re-run against the original `model_patch`. Mirrors the Results page button.
- From inputs (`--config` + `--instances`): no baseline to diff against, so the comparison section is skipped. Mirrors the Inference page download button.

`--evaluator` is required and baked into the notebook's section 5; pass the filename stem under `scripts/evaluation/` (no `.py`) that matches your task — `apply_and_test` for code-repair via pytest, `run_swebench_evaluation` for the SWE-bench POSIX harness, `translate_eval` for BLEU-graded translation tasks, etc.

```bash
opendraco notebook --predictions results/predictions/prediction-<run-id>.jsonl --evaluator apply_and_test
opendraco notebook --config hyperagent_star --instances swebench_instances.jsonl --evaluator run_swebench_evaluation --output reproducer.ipynb
```
