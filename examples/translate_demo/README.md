# EvoMas translate-task demo

This directory holds one fully-worked example of the **file-translation
pipeline** described in `evomas/config/predefined/translate.json`.
Everything you need to run it end-to-end is here:

| File | Role |
|---|---|
| `translate_instances.jsonl` | One synthetic instance pointing at `EvoMas/translate-demo-intro-en` on GitHub (commit `66da274`). |
| `repos/intro-en/intro.md` | The source file (English) — also the seed commit of the org repo. |
| `repos/intro-en/intro.md.gold` | Human reference translation (Spanish). The evaluator BLEU-scores the agent's output against this. Pushed to the org repo alongside the source so `clone_workspace` has access. |

## End-to-end flow

1. **The repo is already on GitHub.** `EvoMas/translate-demo-intro-en`
   (private) holds the source + gold sidecar at commit `66da274`.
   `clone_workspace` resolves the `repo` field as `owner/name` and
   clones via `https://github.com/EvoMas/translate-demo-intro-en.git`
   — the same mechanism the SWE-bench custom instances use. Local
   working copy is at `repos/intro-en/` for editing convenience; push
   any changes to keep the org copy authoritative.

2. **Generate the notebook.**
   ```bash
   evomas notebook \
     --config translate \
     --instances examples/translate_demo/translate_instances.jsonl \
     --output notebooks/translate-demo.ipynb
   ```
   The notebook bakes the four-agent chain (locator → translator →
   reviewer → finalizer) into Section 2 of the file, alongside the
   inlined instance row.

3. **Execute the notebook.**
   ```bash
   jupyter nbconvert --to notebook --execute --inplace \
     --ExecutePreprocessor.timeout=-1 \
     --ExecutePreprocessor.kernel_name=evomas \
     notebooks/translate-demo.ipynb
   ```
   Outputs land under `notebook-translate/`: the translated
   `intro.md`, an `inference.log` text log, and a
   `prediction-translate.jsonl` carrying the unified-diff `model_patch`.

4. **Score the translation.**
   ```bash
   python scripts/evaluation/translate_eval.py \
     --instances examples/translate_demo/translate_instances.jsonl \
     --predictions notebook-translate/prediction-translate.jsonl \
     --report-dir notebook-translate \
     --run-id notebook-translate-custom \
     --model evomas-translate \
     --threshold 50
   ```
   sacrebleu is preferred when available; the evaluator falls back to
   an inline BLEU-4 implementation when it isn't installed. Threshold
   is corpus-BLEU; default 50 is a forgiving bar for the small qwen
   models — bump to 70+ for serious comparison.

5. **Roll the result into the experiment log.** Copy
   `notebook-translate/` into `experiments/<descriptive-name>/` with
   the standard restructure (predictions/ + evaluations/ +
   predictions/logs/) and `python experiments/generate_report.py`
   picks up the new section.

## Authoring more instances

Drop a folder under `examples/translate_demo/repos/<your-input>/`
containing exactly:

- the file(s) to translate
- a `<file>.gold` sidecar per file with the reference translation

Then push it to the EvoMas org and append a row to
`translate_instances.jsonl`:

```bash
cd examples/translate_demo/repos/<your-input>
git init --initial-branch=main
git add . && git -c user.email=demo@evomas.local -c user.name=demo commit -m "<your-input>: source + gold"
gh repo create EvoMas/translate-demo-<your-input> --private --source=. --remote=origin --push
git rev-parse HEAD   # copy the SHA into translate_instances.jsonl
```

```json
{
  "instance_id": "translate-<your-input>",
  "repo": "EvoMas/translate-demo-<your-input>",
  "base_commit": "<sha>",
  "problem_statement": "Translate from <SRC> to <TGT>.",
  "subset": "translate",
  "split": "custom"
}
```

`problem_statement` is what the locator + translator agents read for
the language pair — phrasing is free-form, the prompts in
`translate.json` are robust to any variation that names a source and
target language.
