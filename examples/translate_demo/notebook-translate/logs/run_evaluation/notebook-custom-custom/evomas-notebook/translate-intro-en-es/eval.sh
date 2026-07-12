#!/usr/bin/env bash
# Reproduce this instance's BLEU score.
python translate_eval.py \
  --instances C:\Users\XF\Desktop\TFG\EvoMas\examples\translate_demo\notebook-translate\instances.jsonl \
  --predictions C:\Users\XF\Desktop\TFG\EvoMas\examples\translate_demo\notebook-translate\prediction-translate.jsonl \
  --report-dir C:\Users\XF\Desktop\TFG\EvoMas\examples\translate_demo\notebook-translate \
  --run-id notebook-custom-custom \
  --model evomas-notebook \
  --threshold 50.0
