# EvoMas — experiment log

Per-run breakdown of resolve rate, wall-clock, agent-call timing,
and LLM token usage.

Run rows correspond to result folders under `experiments/`. The script
that maintains this file is `experiments/generate_report.py`:

```
python experiments/generate_report.py                  # refresh all runs
python experiments/generate_report.py <folder-name>    # refresh one
```

**Data source notes**
- *Resolve outcomes*: read from each run's `evaluations/*.json` (the SWE-bench harness report; `resolved_ids` / `completed_ids`).
- *Per-cell wall-clock + agent timing*: derived from `handoff` events in `evomas/logs/inference_logs/prediction-<run>.ndjson` (timestamps between consecutive handoffs).
- *Tool-call counts + response/thinking chars*: counted directly from the same NDJSON stream.
- *Token usage*: parsed from the per-LLM-call lines in `<run-dir>/predictions/logs/prediction-<run>.log` (`[<agent>] tokens in=X out=Y total=Z`). These are real counts emitted by the Ollama/LiteLLM dispatcher, not approximations.

<!-- BEGIN notebook-chain-2b-5custom -->
## notebook-chain-2b-5custom

- **Started**: 2026-06-03 23:28:36
- **Active wall-clock**: 7min 45s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 0 / 5 = **0.0 %** of evaluated, 0.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🔴 FAIL | 4 | 21 | 1min 28s | 87,680 (82,659 + 5,021) | 1087 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 4 | 22 | 1min 35s | 113,418 (108,478 + 4,940) | 1789 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🔴 FAIL | 4 | 11 | 1min 35s | 43,775 (37,633 + 6,142) | 511 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🔴 FAIL | 4 | 19 | 1min 55s | 75,942 (68,688 + 7,254) | 2209 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🔴 FAIL | 4 | 21 | 1min 12s | 88,064 (84,081 + 3,983) | 435 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 57.0 s | 50.0 s | 4min 45s |
| `reviewer` | 5 | 21.0 s | 20.0 s | 1min 45s |
| `locator` | 5 | 10.0 s | 7.0 s | 50.0 s |
| `finalizer` | 5 | 5.0 s | 3.0 s | 25.0 s |

### LLM call totals

- **Total LLM calls**: 118
- **Total tokens**: 408,879 (381,539 + 27,340)
<!-- END notebook-chain-2b-5custom -->

<!-- BEGIN notebook-chain-4b-5custom -->
## notebook-chain-4b-5custom

- **Started**: 2026-06-03 23:39:17
- **Active wall-clock**: 9min 53s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 4 / 5 = **80.0 %** of evaluated, 80.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 4 | 11 | 1min 54s | 35,439 (33,199 + 2,240) | 256 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🟢 PASS | 4 | 10 | 1min 48s | 37,841 (35,696 + 2,145) | 305 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 4 | 9 | 1min 52s | 30,408 (28,168 + 2,240) | 310 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 4 | 14 | 2min 17s | 46,242 (43,478 + 2,764) | 454 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 4 | 10 | 2min 2s | 36,676 (34,177 + 2,499) | 514 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 1min 3s | 1min | 5min 14s |
| `reviewer` | 5 | 38.8 s | 36.0 s | 3min 14s |
| `locator` | 5 | 11.0 s | 12.0 s | 55.0 s |
| `finalizer` | 5 | 6.0 s | 6.0 s | 30.0 s |

### LLM call totals

- **Total LLM calls**: 64
- **Total tokens**: 186,606 (174,718 + 11,888)

### Resolved instances

- `custom-EvoMas-evomas-instance-easy-fcf59bc`
- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-chain-4b-5custom -->

<!-- BEGIN notebook-chain-9b-5custom -->
## notebook-chain-9b-5custom

- **Started**: 2026-06-04 00:41:34
- **Active wall-clock**: 29min 2s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 4 / 5 = **80.0 %** of evaluated, 80.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 4 | 12 | 4min 40s | 42,900 (40,792 + 2,108) | 256 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 4 | 11 | 6min | 41,054 (38,189 + 2,865) | 310 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🟢 PASS | 4 | 13 | 6min 58s | 49,791 (46,428 + 3,363) | 269 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 4 | 13 | 6min 14s | 50,647 (47,704 + 2,943) | 517 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 4 | 11 | 5min 10s | 42,213 (39,772 + 2,441) | 507 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 3min 5s | 3min 10s | 15min 26s |
| `reviewer` | 5 | 2min 6s | 2min 13s | 10min 31s |
| `locator` | 5 | 22.4 s | 24.0 s | 1min 52s |
| `finalizer` | 5 | 14.6 s | 14.0 s | 1min 13s |

### LLM call totals

- **Total LLM calls**: 79
- **Total tokens**: 226,605 (212,885 + 13,720)

### Resolved instances

- `custom-EvoMas-evomas-instance-easy-fcf59bc`
- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-chain-9b-5custom -->

<!-- BEGIN notebook-agentscope_hybrid-5custom -->
## notebook-agentscope_hybrid-5custom

- **Started**: 2026-06-04 01:17:57
- **Active wall-clock**: 35min 21s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 4 / 5 = **80.0 %** of evaluated, 80.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 6 | 12 | 5min 59s | 48,061 (45,347 + 2,714) | 256 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 6 | 11 | 7min 3s | 45,755 (42,414 + 3,341) | 310 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🟢 PASS | 6 | 14 | 8min 9s | 56,351 (52,465 + 3,886) | 269 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 6 | 13 | 7min 11s | 55,269 (51,925 + 3,344) | 517 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 6 | 12 | 6min 59s | 48,880 (45,561 + 3,319) | 507 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 3min 5s | 3min 10s | 15min 25s |
| `reviewer` | 5 | 2min 15s | 2min 12s | 11min 14s |
| `locator` | 5 | 46.0 s | 43.0 s | 3min 50s |
| `orchestrator` | 10 | 17.9 s | 19.0 s | 2min 59s |
| `finalizer` | 5 | 22.6 s | 20.0 s | 1min 53s |

### LLM call totals

- **Total LLM calls**: 91
- **Total tokens**: 254,316 (237,712 + 16,604)

### Resolved instances

- `custom-EvoMas-evomas-instance-easy-fcf59bc`
- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-agentscope_hybrid-5custom -->

<!-- BEGIN notebook-experepair_star-5custom -->
## notebook-experepair_star-5custom

- **Started**: 2026-06-04 01:59:53
- **Active wall-clock**: 41min 18s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 3 / 5 = **60.0 %** of evaluated, 60.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 6 | 7 | 6min 23s | 38,109 (35,069 + 3,040) | 258 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 6 | 7 | 6min 56s | 40,052 (36,749 + 3,303) | 310 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🔴 FAIL | 6 | 5 | 14min 20s | 34,407 (27,407 + 7,000) | 511 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 6 | 6 | 7min 10s | 36,335 (32,939 + 3,396) | 517 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 6 | 9 | 6min 29s | 48,878 (45,830 + 3,048) | 507 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 5min 1s | 3min 35s | 25min 7s |
| `hub` | 15 | 27.0 s | 25.0 s | 6min 45s |
| `reviewer` | 5 | 1min 9s | 1min 9s | 5min 43s |
| `search` | 5 | 44.6 s | 45.0 s | 3min 43s |

### LLM call totals

- **Total LLM calls**: 66
- **Total tokens**: 197,781 (177,994 + 19,787)

### Resolved instances

- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-experepair_star-5custom -->

<!-- BEGIN notebook-hyperagent_star-5custom -->
## notebook-hyperagent_star-5custom

- **Started**: 2026-06-04 02:30:10
- **Active wall-clock**: 29min 35s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 5 / 5 = **100.0 %** of evaluated, 100.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 6 | 7 | 7min 9s | 47,249 (44,044 + 3,205) | 266 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🟢 PASS | 6 | 7 | 4min 22s | 42,220 (40,328 + 1,892) | 305 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🟢 PASS | 6 | 7 | 5min 43s | 44,253 (41,676 + 2,577) | 236 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 6 | 9 | 6min 27s | 53,025 (50,094 + 2,931) | 507 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 6 | 7 | 5min 54s | 42,441 (39,753 + 2,688) | 517 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `editor` | 5 | 3min 44s | 3min 37s | 18min 40s |
| `planner` | 15 | 22.1 s | 23.0 s | 5min 31s |
| `navigator` | 5 | 49.0 s | 48.0 s | 4min 5s |
| `finalizer` | 5 | 15.8 s | 15.0 s | 1min 19s |

### LLM call totals

- **Total LLM calls**: 69
- **Total tokens**: 229,188 (215,895 + 13,293)

### Resolved instances

- `custom-EvoMas-evomas-instance-easy-fcf59bc`
- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-medium-a406a76`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-hyperagent_star-5custom -->

<!-- BEGIN notebook-joycode_star-5custom -->
## notebook-joycode_star-5custom

- **Started**: 2026-06-04 03:10:07
- **Active wall-clock**: 39min 15s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 5 / 5 = **100.0 %** of evaluated, 100.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 8 | 20 | 8min 43s | 65,747 (61,750 + 3,997) | 235 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🟢 PASS | 8 | 16 | 7min 48s | 51,623 (47,968 + 3,655) | 489 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 8 | 13 | 7min 48s | 46,333 (42,625 + 3,708) | 648 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🟢 PASS | 8 | 15 | 7min 56s | 51,385 (47,630 + 3,755) | 572 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 8 | 12 | 7min | 41,820 (38,516 + 3,304) | 698 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 3min 3s | 3min 7s | 15min 15s |
| `reviewer` | 5 | 1min 53s | 1min 52s | 9min 23s |
| `hub` | 20 | 27.9 s | 28.0 s | 9min 17s |
| `locator` | 5 | 41.4 s | 41.0 s | 3min 27s |
| `finalizer` | 5 | 22.6 s | 20.0 s | 1min 53s |

### LLM call totals

- **Total LLM calls**: 116
- **Total tokens**: 256,908 (238,489 + 18,419)

### Resolved instances

- `custom-EvoMas-evomas-instance-easy-fcf59bc`
- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-medium-a406a76`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-joycode_star-5custom -->

<!-- BEGIN notebook-lingxi_star-5custom -->
## notebook-lingxi_star-5custom

- **Started**: 2026-06-04 03:53:07
- **Active wall-clock**: 42min 22s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 5 / 5 = **100.0 %** of evaluated, 100.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 8 | 17 | 9min 8s | 63,046 (58,691 + 4,355) | 262 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🟢 PASS | 8 | 15 | 8min 55s | 62,848 (58,608 + 4,240) | 305 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 6 | 18 | 10min 23s | 81,020 (76,027 + 4,993) | 513 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🟢 PASS | 6 | 11 | 7min 29s | 49,610 (45,998 + 3,612) | 236 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 6 | 13 | 6min 27s | 44,039 (40,958 + 3,081) | 507 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `solver` | 5 | 3min 5s | 2min 32s | 15min 25s |
| `reviewer` | 5 | 2min 18s | 2min 12s | 11min 29s |
| `decoder` | 7 | 1min 14s | 1min 21s | 8min 39s |
| `hub` | 17 | 24.1 s | 24.0 s | 6min 49s |

### LLM call totals

- **Total LLM calls**: 106
- **Total tokens**: 300,563 (280,282 + 20,281)

### Resolved instances

- `custom-EvoMas-evomas-instance-easy-fcf59bc`
- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-medium-a406a76`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-lingxi_star-5custom -->

<!-- BEGIN notebook-openhands_star-5custom -->
## notebook-openhands_star-5custom

- **Started**: 2026-06-04 04:11:19
- **Active wall-clock**: 17min 32s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 5 / 5 = **100.0 %** of evaluated, 100.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 6 | 4 | 3min 27s | 15,469 (13,854 + 1,615) | 235 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🟢 PASS | 6 | 5 | 3min 7s | 16,137 (14,689 + 1,448) | 525 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🟢 PASS | 6 | 5 | 3min 55s | 18,556 (16,667 + 1,889) | 572 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 6 | 4 | 3min 37s | 16,363 (14,621 + 1,742) | 698 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 6 | 4 | 3min 26s | 16,315 (14,692 + 1,623) | 648 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `controller` | 15 | 24.2 s | 25.0 s | 6min 3s |
| `coder` | 5 | 1min 12s | 1min 11s | 6min 1s |
| `locator` | 5 | 43.0 s | 39.0 s | 3min 35s |
| `finalizer` | 5 | 22.6 s | 20.0 s | 1min 53s |

### LLM call totals

- **Total LLM calls**: 52
- **Total tokens**: 82,840 (74,523 + 8,317)

### Resolved instances

- `custom-EvoMas-evomas-instance-easy-fcf59bc`
- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-medium-a406a76`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-openhands_star-5custom -->

<!-- BEGIN notebook-prometheus_tree-5custom -->
## notebook-prometheus_tree-5custom

- **Started**: 2026-06-04 04:45:34
- **Active wall-clock**: 31min 41s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 3 / 5 = **60.0 %** of evaluated, 60.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 3 | 9 | 6min | 33,672 (30,698 + 2,974) | 256 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🟢 PASS | 3 | 8 | 5min 51s | 35,262 (32,409 + 2,853) | 269 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🔴 FAIL | 3 | 9 | 5min 44s | 28,641 (26,254 + 2,387) | 0 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 3 | 9 | 7min 44s | 39,545 (35,642 + 3,903) | 310 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 3 | 10 | 6min 22s | 34,964 (31,753 + 3,211) | 454 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `bug_repro` | 4 | 3min 19s | 3min 35s | 13min 15s |
| `issue_resolver` | 4 | 2min 43s | 2min 38s | 10min 51s |
| `qa_patch` | 1 | 3min 50s | 3min 50s | 3min 50s |
| `classifier` | 5 | 34.0 s | 30.0 s | 2min 50s |
| `context_retrieval` | 1 | 55.0 s | 55.0 s | 55.0 s |

### LLM call totals

- **Total LLM calls**: 56
- **Total tokens**: 172,084 (156,756 + 15,328)

### Resolved instances

- `custom-EvoMas-evomas-instance-easy-fcf59bc`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-prometheus_tree-5custom -->

<!-- BEGIN notebook-openhands_star-23lite -->
## notebook-openhands_star-23lite

- **Started**: 2026-06-04 08:04:11
- **Active wall-clock**: 3h 15min (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 23
- **Evaluated**: 23
- **Resolved**: 0 / 23 = **0.0 %** of evaluated, 0.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `sqlfluff__sqlfluff-1625` | 🔴 FAIL | 6 | 6 | 6min 59s | 35,088 (31,613 + 3,475) | 705 |
| `sqlfluff__sqlfluff-1733` | 🔴 FAIL | 6 | 6 | 10min 20s | 51,158 (46,003 + 5,155) | 0 |
| `sqlfluff__sqlfluff-2419` | 🔴 FAIL | 6 | 11 | 6min 52s | 57,221 (54,040 + 3,181) | 0 |
| `sqlfluff__sqlfluff-1517` | 🔴 FAIL | 8 | 16 | 12min 2s | 95,167 (89,287 + 5,880) | 647 |
| `sqlfluff__sqlfluff-1763` | 🔴 FAIL | 8 | 16 | 11min 23s | 108,638 (103,143 + 5,495) | 0 |
| `marshmallow-code__marshmallow-1343` | 🔴 FAIL | 6 | 10 | 6min 23s | 50,341 (47,364 + 2,977) | 0 |
| `marshmallow-code__marshmallow-1359` | 🔴 FAIL | 6 | 10 | 6min 31s | 59,581 (56,532 + 3,049) | 0 |
| `pvlib__pvlib-python-1072` | 🔴 FAIL | 6 | 7 | 6min 42s | 51,348 (48,162 + 3,186) | 0 |
| `pvlib__pvlib-python-1707` | 🔴 FAIL | 6 | 4 | 6min 39s | 32,580 (29,410 + 3,170) | 0 |
| `pvlib__pvlib-python-1154` | 🔴 FAIL | 12 | 15 | 16min 52s | 99,284 (91,315 + 7,969) | 0 |
| `pvlib__pvlib-python-1606` | 🔴 FAIL | 6 | 5 | 7min 50s | 46,734 (42,789 + 3,945) | 0 |
| `pvlib__pvlib-python-1854` | 🔴 FAIL | 8 | 8 | 9min 19s | 56,585 (52,204 + 4,381) | 0 |
| `pylint-dev__astroid-1333` | 🔴 FAIL | 6 | 5 | 6min 48s | 41,787 (38,620 + 3,167) | 0 |
| `pylint-dev__astroid-1978` | 🔴 FAIL | 6 | 3 | 4min 41s | 34,806 (32,741 + 2,065) | 0 |
| `pylint-dev__astroid-1196` | 🔴 FAIL | 6 | 5 | 6min 28s | 37,213 (34,191 + 3,022) | 0 |
| `pylint-dev__astroid-1866` | 🔴 FAIL | 6 | 8 | 6min 39s | 61,027 (57,961 + 3,066) | 0 |
| `pylint-dev__astroid-1268` | 🔴 FAIL | 6 | 5 | 6min 29s | 35,299 (32,281 + 3,018) | 0 |
| `pyvista__pyvista-4315` | 🔴 FAIL | 6 | 6 | 5min 7s | 38,901 (36,698 + 2,203) | 0 |
| `pydicom__pydicom-1413` | 🔴 FAIL | 8 | 6 | 8min 12s | 59,874 (56,203 + 3,671) | 0 |
| `pydicom__pydicom-1694` | 🔴 FAIL | 6 | 7 | 6min 47s | 53,270 (50,168 + 3,102) | 0 |
| `pydicom__pydicom-1139` | 🔴 FAIL | 12 | 18 | 14min 50s | 106,206 (99,615 + 6,591) | 0 |
| `pydicom__pydicom-901` | 🔴 FAIL | 6 | 7 | 6min 36s | 42,201 (38,897 + 3,304) | 8709 |
| `pydicom__pydicom-1256` | 🔴 FAIL | 10 | 18 | 14min 58s | 94,464 (87,092 + 7,372) | 0 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `coder` | 28 | 2min 53s | 2min 48s | 1h 20min |
| `locator` | 32 | 2min 18s | 2min 12s | 1h 13min |
| `controller` | 81 | 24.2 s | 23.0 s | 32min 43s |
| `finalizer` | 21 | 23.9 s | 24.0 s | 8min 21s |

### LLM call totals

- **Total LLM calls**: 378
- **Total tokens**: 1,348,773 (1,256,329 + 92,444)
<!-- END notebook-openhands_star-23lite -->

<!-- BEGIN notebook-hyperagent_star-23lite -->
## notebook-hyperagent_star-23lite

- **Started**: 2026-06-04 23:26:39
- **Active wall-clock**: 7h 40min (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 23
- **Evaluated**: 23
- **Resolved**: 2 / 23 = **8.7 %** of evaluated, 8.7 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `sqlfluff__sqlfluff-1625` | 🟢 PASS | 8 | 13 | 8min 42s | 96,251 (92,396 + 3,855) | 571 |
| `sqlfluff__sqlfluff-2419` | 🔴 FAIL | 6 | 17 | 14min 21s | 140,325 (134,041 + 6,284) | 562 |
| `sqlfluff__sqlfluff-1517` | 🔴 FAIL | 6 | 17 | 17min 15s | 220,955 (213,690 + 7,265) | 537 |
| `sqlfluff__sqlfluff-1733` | 🔴 FAIL | 6 | 17 | 16min 31s | 132,209 (124,999 + 7,210) | 562 |
| `sqlfluff__sqlfluff-1763` | 🔴 FAIL | 6 | 6 | 13min 20s | 68,959 (62,824 + 6,135) | 562 |
| `marshmallow-code__marshmallow-1359` | 🟢 PASS | 6 | 6 | 11min 9s | 66,709 (61,879 + 4,830) | 491 |
| `marshmallow-code__marshmallow-1343` | 🔴 FAIL | 6 | 7 | 14min 24s | 95,338 (89,177 + 6,161) | 11121 |
| `pvlib__pvlib-python-1707` | 🔴 FAIL | 10 | 30 | 34min 18s | 360,813 (347,639 + 13,174) | 0 |
| `pvlib__pvlib-python-1072` | 🔴 FAIL | 10 | 50 | 51min 59s | 603,229 (580,894 + 22,335) | 0 |
| `pvlib__pvlib-python-1606` | 🔴 FAIL | 10 | 11 | 23min 45s | 118,300 (106,971 + 11,329) | 0 |
| `pvlib__pvlib-python-1854` | 🔴 FAIL | 10 | 11 | 36min 7s | 146,748 (130,297 + 16,451) | 0 |
| `pvlib__pvlib-python-1154` | 🔴 FAIL | 10 | 17 | 35min 9s | 167,061 (151,214 + 15,847) | 0 |
| `pylint-dev__astroid-1978` | 🔴 FAIL | 6 | 15 | 13min 51s | 177,544 (171,819 + 5,725) | 197 |
| `pylint-dev__astroid-1196` | 🔴 FAIL | 6 | 8 | 9min 4s | 71,874 (68,010 + 3,864) | 205 |
| `pylint-dev__astroid-1333` | 🔴 FAIL | 10 | 54 | 43min 6s | 652,537 (635,232 + 17,305) | 0 |
| `pylint-dev__astroid-1268` | 🔴 FAIL | 6 | 15 | 10min 59s | 173,565 (168,991 + 4,574) | 428 |
| `pylint-dev__astroid-1866` | 🔴 FAIL | 6 | 6 | 12min 26s | 71,894 (66,509 + 5,385) | 197 |
| `pyvista__pyvista-4315` | 🔴 FAIL | 6 | 14 | 14min 25s | 187,366 (182,089 + 5,277) | 23067 |
| `pydicom__pydicom-1413` | 🔴 FAIL | 6 | 4 | 11min 1s | 53,347 (48,317 + 5,030) | 1258 |
| `pydicom__pydicom-1694` | 🔴 FAIL | 10 | 11 | 29min 11s | 141,504 (128,782 + 12,722) | 0 |
| `pydicom__pydicom-1139` | 🔴 FAIL | 6 | 8 | 13min 22s | 78,853 (72,873 + 5,980) | 651 |
| `pydicom__pydicom-1256` | 🔴 FAIL | 6 | 17 | 14min 5s | 167,185 (161,322 + 5,863) | 10337 |
| `pydicom__pydicom-901` | 🔴 FAIL | 6 | 15 | 12min 3s | 142,311 (137,172 + 5,139) | 834 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `editor` | 43 | 7min 49s | 7min 25s | 5h 35min |
| `navigator` | 25 | 2min 28s | 2min 29s | 1h 1min |
| `planner` | 84 | 41.3 s | 24.0 s | 57min 46s |
| `finalizer` | 16 | 19.2 s | 19.0 s | 5min 7s |

### LLM call totals

- **Total LLM calls**: 558
- **Total tokens**: 4,134,877 (3,937,137 + 197,740)

### Resolved instances

- `marshmallow-code__marshmallow-1359`
- `sqlfluff__sqlfluff-1625`
<!-- END notebook-hyperagent_star-23lite -->

<!-- BEGIN notebook-chain-coder3b-5custom -->
## notebook-chain-coder3b-5custom

- **Started**: 2026-06-05 00:43:27
- **Active wall-clock**: 1min 9s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 0 / 5 = **0.0 %** of evaluated, 0.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🔴 FAIL | 4 | 0 | 15.0 s | 6,647 (6,365 + 282) | 1087 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 4 | 0 | 15.0 s | 7,411 (7,031 + 380) | 1789 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🔴 FAIL | 4 | 0 | 12.0 s | 6,177 (5,946 + 231) | 511 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🔴 FAIL | 4 | 0 | 14.0 s | 7,110 (6,744 + 366) | 2209 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🔴 FAIL | 4 | 0 | 13.0 s | 6,789 (6,532 + 257) | 1579 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 6.4 s | 6.0 s | 32.0 s |
| `locator` | 5 | 3.4 s | 3.0 s | 17.0 s |
| `reviewer` | 5 | 3.0 s | 3.0 s | 15.0 s |
| `finalizer` | 5 | 1.0 s | 1.0 s | 5.0 s |

### LLM call totals

- **Total LLM calls**: 25
- **Total tokens**: 34,134 (32,618 + 1,516)
<!-- END notebook-chain-coder3b-5custom -->

<!-- BEGIN notebook-chain-coder7b-5custom -->
## notebook-chain-coder7b-5custom

- **Started**: 2026-06-05 00:48:15
- **Active wall-clock**: 4min 12s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 1 / 5 = **20.0 %** of evaluated, 20.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🔴 FAIL | 4 | 0 | 1min 17s | 5,886 (5,636 + 250) | 1087 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🔴 FAIL | 4 | 0 | 33.0 s | 6,192 (5,940 + 252) | 210 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🔴 FAIL | 4 | 0 | 41.0 s | 7,124 (6,737 + 387) | 2209 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🟢 PASS | 4 | 0 | 1min 2s | 7,038 (6,594 + 444) | 266 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🔴 FAIL | 4 | 0 | 39.0 s | 6,881 (6,564 + 317) | 1579 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 31.0 s | 29.0 s | 2min 35s |
| `reviewer` | 5 | 7.6 s | 5.0 s | 38.0 s |
| `finalizer` | 5 | 7.2 s | 2.0 s | 36.0 s |
| `locator` | 5 | 4.6 s | 5.0 s | 23.0 s |

### LLM call totals

- **Total LLM calls**: 24
- **Total tokens**: 33,121 (31,471 + 1,650)

### Resolved instances

- `custom-EvoMas-evomas-instance-medium-a406a76`
<!-- END notebook-chain-coder7b-5custom -->

<!-- BEGIN notebook-chain-9b-temp-hi-seed-random-5custom -->
## notebook-chain-9b-temp-hi-seed-random-5custom

- **Started**: 2026-06-05 02:19:09
- **Active wall-clock**: 29min 25s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 2 / 5 = **40.0 %** of evaluated, 40.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 4 | 12 | 5min | 43,390 (41,088 + 2,302) | 218 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 4 | 14 | 7min 14s | 57,576 (54,059 + 3,517) | 310 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🟢 PASS | 4 | 10 | 5min 32s | 36,826 (34,114 + 2,712) | 269 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🔴 FAIL | 4 | 13 | 5min 14s | 49,359 (46,932 + 2,427) | 514 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🔴 FAIL | 4 | 11 | 6min 25s | 44,560 (41,507 + 3,053) | 436 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 2min 57s | 2min 50s | 14min 44s |
| `reviewer` | 5 | 2min 19s | 2min | 11min 33s |
| `locator` | 5 | 21.2 s | 23.0 s | 1min 46s |
| `finalizer` | 5 | 16.4 s | 16.0 s | 1min 22s |

### LLM call totals

- **Total LLM calls**: 80
- **Total tokens**: 231,711 (217,700 + 14,011)

### Resolved instances

- `custom-EvoMas-evomas-instance-easy-fcf59bc`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-chain-9b-temp-hi-seed-random-5custom -->

<!-- BEGIN notebook-chain-9b-temp-hi-seed-random-rep2-5custom -->
## notebook-chain-9b-temp-hi-seed-random-rep2-5custom

- **Started**: 2026-06-05 02:44:59
- **Active wall-clock**: 25min 19s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 4 / 5 = **80.0 %** of evaluated, 80.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 4 | 11 | 4min 10s | 38,295 (36,406 + 1,889) | 218 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🟢 PASS | 4 | 14 | 7min 14s | 61,625 (58,188 + 3,437) | 305 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 4 | 11 | 5min 2s | 43,855 (41,468 + 2,387) | 310 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 4 | 9 | 4min 13s | 34,811 (32,856 + 1,955) | 517 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 4 | 11 | 4min 40s | 41,674 (39,514 + 2,160) | 474 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 2min 38s | 2min 19s | 13min 9s |
| `reviewer` | 5 | 1min 49s | 1min 50s | 9min 7s |
| `locator` | 5 | 22.2 s | 23.0 s | 1min 51s |
| `finalizer` | 5 | 14.4 s | 14.0 s | 1min 12s |

### LLM call totals

- **Total LLM calls**: 76
- **Total tokens**: 220,260 (208,432 + 11,828)

### Resolved instances

- `custom-EvoMas-evomas-instance-easy-fcf59bc`
- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-chain-9b-temp-hi-seed-random-rep2-5custom -->

<!-- BEGIN notebook-chain-9b-temp-hi-seed-random-rep3-5custom -->
## notebook-chain-9b-temp-hi-seed-random-rep3-5custom

- **Started**: 2026-06-05 03:16:55
- **Active wall-clock**: 31min 28s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 4 / 5 = **80.0 %** of evaluated, 80.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 4 | 12 | 5min 16s | 42,825 (40,349 + 2,476) | 256 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 4 | 12 | 6min 38s | 46,763 (43,545 + 3,218) | 310 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🟢 PASS | 4 | 14 | 7min 45s | 55,282 (51,582 + 3,700) | 305 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 4 | 13 | 7min 22s | 56,201 (52,695 + 3,506) | 513 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 4 | 9 | 4min 27s | 33,335 (31,254 + 2,081) | 507 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 3min 36s | 3min 11s | 18min |
| `reviewer` | 5 | 2min 5s | 1min 54s | 10min 24s |
| `locator` | 5 | 22.6 s | 23.0 s | 1min 53s |
| `finalizer` | 5 | 14.2 s | 11.0 s | 1min 11s |

### LLM call totals

- **Total LLM calls**: 79
- **Total tokens**: 234,406 (219,425 + 14,981)

### Resolved instances

- `custom-EvoMas-evomas-instance-easy-fcf59bc`
- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-chain-9b-temp-hi-seed-random-rep3-5custom -->

<!-- BEGIN notebook-chain-9b-23lite -->
## notebook-chain-9b-23lite

- **Started**: 2026-06-05 08:31:18
- **Active wall-clock**: 4h 37min (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 23
- **Evaluated**: 23
- **Resolved**: 2 / 23 = **8.7 %** of evaluated, 8.7 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `sqlfluff__sqlfluff-1625` | 🟢 PASS | 4 | 7 | 5min 36s | 33,606 (30,914 + 2,692) | 571 |
| `sqlfluff__sqlfluff-1517` | 🔴 FAIL | 4 | 6 | 6min 19s | 36,062 (33,117 + 2,945) | 537 |
| `sqlfluff__sqlfluff-1733` | 🔴 FAIL | 4 | 6 | 15min 10s | 45,711 (38,412 + 7,299) | 562 |
| `sqlfluff__sqlfluff-2419` | 🔴 FAIL | 4 | 7 | 14min 5s | 37,493 (30,604 + 6,889) | 562 |
| `marshmallow-code__marshmallow-1359` | 🟢 PASS | 4 | 11 | 10min 28s | 73,221 (68,600 + 4,621) | 491 |
| `sqlfluff__sqlfluff-1763` | 🔴 FAIL | 4 | 1 | 12min 13s | 33,029 (27,175 + 5,854) | 562 |
| `marshmallow-code__marshmallow-1343` | 🔴 FAIL | 4 | 11 | 8min 54s | 78,096 (74,185 + 3,911) | 11121 |
| `pvlib__pvlib-python-1707` | 🔴 FAIL | 4 | 5 | 15min 49s | 72,296 (65,374 + 6,922) | 11453 |
| `pvlib__pvlib-python-1072` | 🔴 FAIL | 4 | 17 | 11min 47s | 121,167 (116,223 + 4,944) | 710 |
| `pvlib__pvlib-python-1606` | 🔴 FAIL | 4 | 6 | 9min 46s | 54,343 (49,820 + 4,523) | 12445 |
| `pvlib__pvlib-python-1854` | 🔴 FAIL | 4 | 8 | 11min 6s | 61,094 (56,157 + 4,937) | 11453 |
| `pvlib__pvlib-python-1154` | 🔴 FAIL | 4 | 8 | 10min 31s | 60,133 (55,456 + 4,677) | 11701 |
| `pylint-dev__astroid-1978` | 🔴 FAIL | 4 | 18 | 9min 56s | 193,395 (189,325 + 4,070) | 655 |
| `pylint-dev__astroid-1196` | 🔴 FAIL | 4 | 10 | 7min 31s | 71,743 (68,669 + 3,074) | 205 |
| `pylint-dev__astroid-1333` | 🔴 FAIL | 4 | 11 | 20min 49s | 131,176 (121,843 + 9,333) | 6025 |
| `pylint-dev__astroid-1866` | 🔴 FAIL | 4 | 19 | 16min 25s | 158,935 (152,434 + 6,501) | 197 |
| `pylint-dev__astroid-1268` | 🔴 FAIL | 4 | 14 | 8min 27s | 150,184 (146,696 + 3,488) | 482 |
| `pyvista__pyvista-4315` | 🔴 FAIL | 4 | 15 | 17min 37s | 162,178 (154,626 + 7,552) | 23067 |
| `pydicom__pydicom-1413` | 🔴 FAIL | 4 | 2 | 11min 23s | 37,391 (31,989 + 5,402) | 1258 |
| `pydicom__pydicom-1694` | 🔴 FAIL | 4 | 8 | 9min 34s | 58,012 (53,834 + 4,178) | 11319 |
| `pydicom__pydicom-1139` | 🔴 FAIL | 4 | 20 | 13min 55s | 190,498 (184,876 + 5,622) | 651 |
| `pydicom__pydicom-901` | 🔴 FAIL | 4 | 20 | 11min 40s | 141,416 (136,122 + 5,294) | 815 |
| `pydicom__pydicom-1256` | 🔴 FAIL | 4 | 16 | 18min 48s | 177,130 (170,274 + 6,856) | 10337 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 23 | 8min 42s | 7min 35s | 3h 20min |
| `reviewer` | 23 | 1min 53s | 1min 39s | 43min 21s |
| `locator` | 23 | 1min 13s | 1min 19s | 27min 55s |
| `finalizer` | 23 | 16.9 s | 16.0 s | 6min 29s |

### LLM call totals

- **Total LLM calls**: 366
- **Total tokens**: 2,178,309 (2,056,725 + 121,584)

### Resolved instances

- `marshmallow-code__marshmallow-1359`
- `sqlfluff__sqlfluff-1625`
<!-- END notebook-chain-9b-23lite -->

<!-- BEGIN notebook-chain-9b-temp-hi-seed-random-rep4-5custom -->
## notebook-chain-9b-temp-hi-seed-random-rep4-5custom

- **Started**: 2026-06-07 12:16:25
- **Active wall-clock**: 34min 28s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 3 / 5 = **60.0 %** of evaluated, 60.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 4 | 9 | 3min 45s | 30,984 (29,338 + 1,646) | 218 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🟢 PASS | 4 | 13 | 7min 20s | 52,948 (49,377 + 3,571) | 305 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 4 | 11 | 6min 27s | 45,697 (42,577 + 3,120) | 310 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 4 | 13 | 6min 3s | 50,947 (48,113 + 2,834) | 602 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🔴 FAIL | 4 | 19 | 10min 53s | 96,212 (91,156 + 5,056) | 1579 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 3min 52s | 3min 27s | 19min 21s |
| `reviewer` | 5 | 2min 24s | 2min 7s | 12min 2s |
| `locator` | 5 | 21.4 s | 21.0 s | 1min 47s |
| `finalizer` | 5 | 15.6 s | 15.0 s | 1min 18s |

### LLM call totals

- **Total LLM calls**: 85
- **Total tokens**: 276,788 (260,561 + 16,227)

### Resolved instances

- `custom-EvoMas-evomas-instance-easy-fcf59bc`
- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-chain-9b-temp-hi-seed-random-rep4-5custom -->

<!-- BEGIN notebook-chain-9b-temp-hi-seed-random-rep5-5custom -->
## notebook-chain-9b-temp-hi-seed-random-rep5-5custom

- **Started**: 2026-06-07 12:49:55
- **Active wall-clock**: 32min 47s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 4 / 5 = **80.0 %** of evaluated, 80.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 4 | 11 | 5min 16s | 38,387 (35,923 + 2,464) | 256 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🟢 PASS | 4 | 12 | 5min 59s | 45,936 (43,102 + 2,834) | 236 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🟢 PASS | 4 | 10 | 7min 6s | 36,020 (32,537 + 3,483) | 305 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🔴 FAIL | 4 | 9 | 9min 49s | 41,142 (36,405 + 4,737) | 2209 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 4 | 10 | 4min 37s | 37,235 (35,062 + 2,173) | 474 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 3min 39s | 3min 19s | 18min 16s |
| `reviewer` | 5 | 2min 17s | 2min 12s | 11min 24s |
| `locator` | 5 | 22.0 s | 24.0 s | 1min 50s |
| `finalizer` | 5 | 15.4 s | 16.0 s | 1min 17s |

### LLM call totals

- **Total LLM calls**: 73
- **Total tokens**: 198,720 (183,029 + 15,691)

### Resolved instances

- `custom-EvoMas-evomas-instance-easy-fcf59bc`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-medium-a406a76`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-chain-9b-temp-hi-seed-random-rep5-5custom -->

<!-- BEGIN notebook-chain-9b-temp-lo-seed-random-5custom -->
## notebook-chain-9b-temp-lo-seed-random-5custom

- **Started**: 2026-06-07 13:21:33
- **Active wall-clock**: 31min 9s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 3 / 5 = **60.0 %** of evaluated, 60.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 4 | 11 | 4min 25s | 38,310 (36,334 + 1,976) | 256 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 4 | 11 | 5min 55s | 41,620 (38,818 + 2,802) | 310 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🔴 FAIL | 4 | 8 | 9min 55s | 33,486 (28,668 + 4,818) | 225 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 4 | 13 | 5min 56s | 50,335 (47,550 + 2,785) | 517 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 4 | 11 | 4min 58s | 42,331 (40,022 + 2,309) | 507 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 3min 44s | 3min 11s | 18min 39s |
| `reviewer` | 5 | 1min 51s | 1min 53s | 9min 14s |
| `locator` | 5 | 22.0 s | 24.0 s | 1min 50s |
| `finalizer` | 5 | 17.2 s | 18.0 s | 1min 26s |

### LLM call totals

- **Total LLM calls**: 76
- **Total tokens**: 206,082 (191,392 + 14,690)

### Resolved instances

- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-chain-9b-temp-lo-seed-random-5custom -->

<!-- BEGIN notebook-chain-9b-temp-lo-seed-random-rep2-5custom -->
## notebook-chain-9b-temp-lo-seed-random-rep2-5custom

- **Started**: 2026-06-07 13:54:21
- **Active wall-clock**: 31min 48s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 3 / 5 = **60.0 %** of evaluated, 60.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 4 | 11 | 4min 20s | 38,306 (36,334 + 1,972) | 256 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🔴 FAIL | 4 | 8 | 9min 54s | 33,486 (28,668 + 4,818) | 225 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 4 | 13 | 5min 55s | 50,335 (47,550 + 2,785) | 517 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 4 | 11 | 6min 2s | 41,734 (38,865 + 2,869) | 310 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 4 | 11 | 5min 37s | 42,662 (40,007 + 2,655) | 507 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 3min 44s | 3min 11s | 18min 40s |
| `reviewer` | 5 | 1min 57s | 1min 53s | 9min 43s |
| `locator` | 5 | 21.8 s | 23.0 s | 1min 49s |
| `finalizer` | 5 | 19.2 s | 21.0 s | 1min 36s |

### LLM call totals

- **Total LLM calls**: 76
- **Total tokens**: 206,523 (191,424 + 15,099)

### Resolved instances

- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-chain-9b-temp-lo-seed-random-rep2-5custom -->

<!-- BEGIN notebook-chain-9b-temp-lo-seed-random-rep3-5custom -->
## notebook-chain-9b-temp-lo-seed-random-rep3-5custom

- **Started**: 2026-06-07 14:25:49
- **Active wall-clock**: 31min (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 3 / 5 = **60.0 %** of evaluated, 60.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 4 | 11 | 4min 15s | 38,266 (36,333 + 1,933) | 256 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 4 | 11 | 6min 15s | 41,808 (38,812 + 2,996) | 310 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🔴 FAIL | 4 | 8 | 9min 55s | 33,486 (28,668 + 4,818) | 225 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 4 | 13 | 5min 55s | 50,335 (47,550 + 2,785) | 517 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 4 | 11 | 4min 40s | 42,112 (40,007 + 2,105) | 507 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 3min 44s | 3min 11s | 18min 38s |
| `reviewer` | 5 | 1min 45s | 1min 44s | 8min 46s |
| `locator` | 5 | 22.2 s | 23.0 s | 1min 51s |
| `finalizer` | 5 | 21.0 s | 21.0 s | 1min 45s |

### LLM call totals

- **Total LLM calls**: 76
- **Total tokens**: 206,007 (191,370 + 14,637)

### Resolved instances

- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-chain-9b-temp-lo-seed-random-rep3-5custom -->

<!-- BEGIN notebook-chain-9b-temp-lo-seed-random-rep4-5custom -->
## notebook-chain-9b-temp-lo-seed-random-rep4-5custom

- **Started**: 2026-06-07 14:58:02
- **Active wall-clock**: 31min 43s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 3 / 5 = **60.0 %** of evaluated, 60.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 4 | 11 | 4min 12s | 38,251 (36,366 + 1,885) | 256 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🔴 FAIL | 4 | 8 | 10min 1s | 33,486 (28,668 + 4,818) | 225 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 4 | 13 | 5min 54s | 50,335 (47,550 + 2,785) | 517 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 4 | 11 | 6min 13s | 41,761 (38,813 + 2,948) | 310 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 4 | 11 | 5min 23s | 42,586 (40,041 + 2,545) | 507 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 3min 44s | 3min 11s | 18min 42s |
| `reviewer` | 5 | 1min 56s | 1min 53s | 9min 40s |
| `locator` | 5 | 22.0 s | 23.0 s | 1min 50s |
| `finalizer` | 5 | 18.2 s | 17.0 s | 1min 31s |

### LLM call totals

- **Total LLM calls**: 76
- **Total tokens**: 206,419 (191,438 + 14,981)

### Resolved instances

- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-chain-9b-temp-lo-seed-random-rep4-5custom -->

<!-- BEGIN notebook-chain-9b-temp-lo-seed-random-rep5-5custom -->
## notebook-chain-9b-temp-lo-seed-random-rep5-5custom

- **Started**: 2026-06-07 15:29:59
- **Active wall-clock**: 31min 30s (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 5
- **Evaluated**: 5
- **Resolved**: 3 / 5 = **60.0 %** of evaluated, 60.0 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `custom-EvoMas-evomas-instance-trivial-18757fd` | 🟢 PASS | 4 | 11 | 4min 20s | 38,310 (36,334 + 1,976) | 256 |
| `custom-EvoMas-evomas-instance-medium-a406a76` | 🔴 FAIL | 4 | 11 | 6min 4s | 41,755 (38,858 + 2,897) | 310 |
| `custom-EvoMas-evomas-instance-easy-fcf59bc` | 🔴 FAIL | 4 | 8 | 9min 57s | 33,486 (28,668 + 4,818) | 225 |
| `custom-EvoMas-evomas-instance-hard-ad94202` | 🟢 PASS | 4 | 11 | 5min 13s | 42,456 (40,040 + 2,416) | 507 |
| `custom-EvoMas-evomas-instance-expert-a2e3735` | 🟢 PASS | 4 | 13 | 5min 56s | 50,335 (47,550 + 2,785) | 517 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 5 | 3min 44s | 3min 11s | 18min 39s |
| `reviewer` | 5 | 1min 55s | 1min 53s | 9min 36s |
| `locator` | 5 | 22.2 s | 24.0 s | 1min 51s |
| `finalizer` | 5 | 16.8 s | 15.0 s | 1min 24s |

### LLM call totals

- **Total LLM calls**: 76
- **Total tokens**: 206,342 (191,450 + 14,892)

### Resolved instances

- `custom-EvoMas-evomas-instance-expert-a2e3735`
- `custom-EvoMas-evomas-instance-hard-ad94202`
- `custom-EvoMas-evomas-instance-trivial-18757fd`
<!-- END notebook-chain-9b-temp-lo-seed-random-rep5-5custom -->

<!-- BEGIN notebook-chain-9b-77litetest -->
## notebook-chain-9b-77litetest

- **Started**: 2026-06-08 15:00:41
- **Active wall-clock**: 16h 4min (sum of inter-log-line gaps capped at 5 min; skips system-sleep / kernel-paused stretches)
- **Predictions written**: 77
- **Evaluated**: 77
- **Resolved**: 12 / 77 = **15.6 %** of evaluated, 15.6 % of attempted

### Per-cell outcomes

| Instance | Status | Agent calls | Tool calls | Cell duration | Tokens count | Patch (B) |
|---|---|---:|---:|---:|---|---:|
| `astropy__astropy-12907` | 🔴 FAIL | 4 | 4 | 14min 35s | 47,057 (40,423 + 6,634) | 9473 |
| `astropy__astropy-6938` | 🔴 FAIL | 4 | 8 | 6min 3s | 57,088 (54,735 + 2,353) | 5295 |
| `django__django-10914` | 🔴 FAIL | 4 | 12 | 14min 6s | 128,791 (123,123 + 5,668) | 3995 |
| `django__django-10924` | 🔴 FAIL | 4 | 7 | 14min 45s | 79,664 (73,277 + 6,387) | 3995 |
| `django__django-11049` | 🔴 FAIL | 4 | 11 | 13min 54s | 72,765 (66,853 + 5,912) | 3995 |
| `django__django-11133` | 🔴 FAIL | 4 | 17 | 12min 25s | 147,240 (142,065 + 5,175) | 549 |
| `django__django-11179` | 🟢 PASS | 4 | 11 | 9min 3s | 82,792 (79,164 + 3,628) | 614 |
| `django__django-11964` | 🔴 FAIL | 4 | 13 | 8min 57s | 95,594 (92,047 + 3,547) | 453 |
| `django__django-12113` | 🔴 FAIL | 4 | 12 | 22min 32s | 135,946 (126,396 + 9,550) | 715 |
| `django__django-12125` | 🔴 FAIL | 4 | 13 | 18min 48s | 170,862 (163,014 + 7,848) | 4047 |
| `django__django-12856` | 🔴 FAIL | 4 | 15 | 17min 5s | 106,224 (99,353 + 6,871) | 4007 |
| `django__django-12908` | 🔴 FAIL | 4 | 14 | 14min 6s | 81,148 (75,696 + 5,452) | 4007 |
| `django__django-13447` | 🔴 FAIL | 4 | 17 | 19min 48s | 149,923 (142,366 + 7,557) | 4521 |
| `django__django-14411` | 🔴 FAIL | 4 | 15 | 21min 11s | 90,242 (81,702 + 8,540) | 4521 |
| `django__django-14534` | 🔴 FAIL | 4 | 8 | 6min 35s | 56,971 (54,933 + 2,038) | 412 |
| `django__django-14580` | 🟢 PASS | 4 | 8 | 9min 19s | 70,207 (66,727 + 3,480) | 599 |
| `django__django-14672` | 🟢 PASS | 4 | 9 | 10min 58s | 80,435 (76,195 + 4,240) | 512 |
| `django__django-14915` | 🔴 FAIL | 4 | 10 | 13min 8s | 61,070 (56,126 + 4,944) | 4503 |
| `django__django-15061` | 🔴 FAIL | 4 | 11 | 14min 23s | 71,267 (65,670 + 5,597) | 4503 |
| `django__django-15320` | 🔴 FAIL | 4 | 15 | 16min 45s | 90,810 (84,480 + 6,330) | 4503 |
| `django__django-15388` | 🟢 PASS | 4 | 12 | 9min 2s | 71,416 (67,959 + 3,457) | 556 |
| `django__django-15400` | 🔴 FAIL | 4 | 20 | 16min 26s | 167,795 (161,550 + 6,245) | 4503 |
| `django__django-15814` | 🔴 FAIL | 4 | 8 | 11min 58s | 78,827 (74,193 + 4,634) | 4503 |
| `django__django-15851` | 🟢 PASS | 4 | 11 | 9min 14s | 63,363 (59,834 + 3,529) | 576 |
| `django__django-15902` | 🔴 FAIL | 4 | 12 | 18min 32s | 98,463 (91,066 + 7,397) | 4503 |
| `django__django-16046` | 🔴 FAIL | 4 | 14 | 18min 1s | 79,825 (72,315 + 7,510) | 4503 |
| `django__django-16255` | 🔴 FAIL | 4 | 15 | 10min 52s | 96,529 (92,755 + 3,774) | 634 |
| `django__django-16379` | 🟢 PASS | 3 | 11 | 7min 30s | 51,468 (48,902 + 2,566) | 723 |
| `django__django-16527` | 🟢 PASS | 4 | 10 | 7min 43s | 56,643 (53,822 + 2,821) | 549 |
| `django__django-17087` | 🟢 PASS | 3 | 14 | 9min 9s | 74,690 (71,496 + 3,194) | 616 |
| `matplotlib__matplotlib-23314` | 🔴 FAIL | 4 | 11 | 12min 40s | 72,545 (67,284 + 5,261) | 422 |
| `matplotlib__matplotlib-23476` | 🔴 FAIL | 4 | 10 | 16min 55s | 86,562 (79,305 + 7,257) | 422 |
| `matplotlib__matplotlib-23563` | 🔴 FAIL | 4 | 2 | 14min | 50,684 (44,566 + 6,118) | 422 |
| `matplotlib__matplotlib-25433` | 🔴 FAIL | 4 | 17 | 14min 19s | 178,177 (172,602 + 5,575) | 290 |
| `mwaskom__seaborn-3010` | 🟢 PASS | 4 | 14 | 11min 33s | 110,962 (105,710 + 5,252) | 472 |
| `mwaskom__seaborn-3190` | 🔴 FAIL | 4 | 8 | 12min 19s | 71,563 (66,336 + 5,227) | 7433 |
| `mwaskom__seaborn-3407` | 🔴 FAIL | 4 | 8 | 15min 5s | 77,712 (71,100 + 6,612) | 7315 |
| `psf__requests-1963` | 🔴 FAIL | 4 | 10 | 16min 48s | 71,026 (63,402 + 7,624) | 6433 |
| `psf__requests-863` | 🔴 FAIL | 4 | 11 | 11min 14s | 106,257 (101,489 + 4,768) | 559 |
| `pydata__xarray-4094` | 🔴 FAIL | 4 | 14 | 12min 2s | 81,599 (76,309 + 5,290) | 609 |
| `pydata__xarray-4248` | 🔴 FAIL | 4 | 10 | 17min 36s | 101,532 (93,831 + 7,701) | 12391 |
| `pydata__xarray-5131` | 🔴 FAIL | 4 | 2 | 11min 6s | 42,800 (37,790 + 5,010) | 12549 |
| `pylint-dev__pylint-7080` | 🔴 FAIL | 4 | 5 | 13min 4s | 57,837 (51,779 + 6,058) | 14899 |
| `pylint-dev__pylint-7993` | ⚫ ERROR | 4 | 4 | 18min 3s | 52,043 (43,668 + 8,375) | 15517 |
| `pytest-dev__pytest-11143` | ⚫ ERROR | 4 | 1 | 5min 3s | 28,678 (26,426 + 2,252) | 517 |
| `pytest-dev__pytest-11148` | ⚫ ERROR | 4 | 11 | 13min 42s | 90,781 (84,738 + 6,043) | 11741 |
| `pytest-dev__pytest-5227` | ⚫ ERROR | 4 | 10 | 6min 18s | 58,589 (55,849 + 2,740) | 514 |
| `pytest-dev__pytest-5413` | ⚫ ERROR | 4 | 8 | 11min 31s | 75,315 (70,236 + 5,079) | 448 |
| `pytest-dev__pytest-6116` | ⚫ ERROR | 4 | 14 | 9min 32s | 119,192 (115,258 + 3,934) | 424 |
| `scikit-learn__scikit-learn-13439` | 🔴 FAIL | 4 | 19 | 11min 18s | 163,369 (159,174 + 4,195) | 623 |
| `pytest-dev__pytest-7168` | 🔴 FAIL | 4 | 2 | 10min 26s | 36,592 (31,604 + 4,988) | 10831 |
| `pytest-dev__pytest-7432` | 🔴 FAIL | 4 | 7 | 21min 26s | 92,778 (82,697 + 10,081) | 10831 |
| `scikit-learn__scikit-learn-13584` | 🔴 FAIL | 4 | 4 | 16min 20s | 47,791 (40,282 + 7,509) | 12133 |
| `scikit-learn__scikit-learn-13779` | 🔴 FAIL | 4 | 11 | 9min 4s | 77,665 (73,776 + 3,889) | 692 |
| `sphinx-doc__sphinx-7738` | 🔴 FAIL | 4 | 6 | 12min 22s | 67,779 (62,485 + 5,294) | 9111 |
| `sympy__sympy-12171` | 🔴 FAIL | 4 | 17 | 9min 13s | 111,491 (107,561 + 3,930) | 755 |
| `sphinx-doc__sphinx-8721` | 🟢 PASS | 4 | 8 | 5min 7s | 51,815 (49,674 + 2,141) | 586 |
| `sympy__sympy-13177` | ⚫ ERROR | 4 | 4 | 10min 42s | 34,819 (29,989 + 4,830) | 20219 |
| `sympy__sympy-13480` | ⚫ ERROR | 4 | 7 | 8min 53s | 49,582 (45,918 + 3,664) | 20219 |
| `sympy__sympy-13647` | ⚫ ERROR | 4 | 8 | 15min 7s | 62,735 (55,953 + 6,782) | 20219 |
| `sympy__sympy-13971` | ⚫ ERROR | 4 | 8 | 9min 53s | 64,609 (60,581 + 4,028) | 20219 |
| `sympy__sympy-14774` | ⚫ ERROR | 4 | 13 | 12min 9s | 143,429 (138,860 + 4,569) | 20975 |
| `sympy__sympy-14817` | ⚫ ERROR | 4 | 8 | 11min 41s | 62,730 (57,639 + 5,091) | 20975 |
| `sympy__sympy-15346` | ⚫ ERROR | 4 | 4 | 11min 2s | 53,591 (48,841 + 4,750) | 20983 |
| `sympy__sympy-15609` | ⚫ ERROR | 4 | 7 | 12min 29s | 58,041 (52,694 + 5,347) | 20997 |
| `sympy__sympy-16988` | ⚫ ERROR | 4 | 8 | 11min 7s | 69,621 (64,955 + 4,666) | 20983 |
| `sympy__sympy-17139` | ⚫ ERROR | 4 | 4 | 12min 33s | 54,245 (48,849 + 5,396) | 20983 |
| `sympy__sympy-17630` | 🔴 FAIL | 4 | 10 | 16min 7s | 98,536 (91,581 + 6,955) | 20983 |
| `sympy__sympy-17655` | 🔴 FAIL | 4 | 14 | 13min 34s | 78,938 (72,975 + 5,963) | 704 |
| `sympy__sympy-18057` | 🔴 FAIL | 4 | 2 | 8min 37s | 27,401 (23,982 + 3,419) | 21625 |
| `sympy__sympy-18621` | 🟢 PASS | 4 | 10 | 7min 24s | 73,366 (70,280 + 3,086) | 594 |
| `sympy__sympy-19487` | 🔴 FAIL | 4 | 6 | 13min 8s | 73,672 (68,081 + 5,591) | 21703 |
| `sympy__sympy-20212` | 🔴 FAIL | 4 | 5 | 14min 9s | 53,529 (47,335 + 6,194) | 22011 |
| `sympy__sympy-21612` | 🟢 PASS | 4 | 20 | 11min 52s | 162,761 (158,312 + 4,449) | 1127 |
| `sympy__sympy-21614` | 🔴 FAIL | 4 | 8 | 8min 47s | 68,815 (65,281 + 3,534) | 22643 |
| `sympy__sympy-21627` | 🔴 FAIL | 4 | 4 | 12min 12s | 52,815 (47,584 + 5,231) | 22643 |
| `sympy__sympy-22005` | 🔴 FAIL | 4 | 12 | 8min 32s | 103,506 (99,885 + 3,621) | 489 |

### Per-agent timing

| Agent | LLM calls (paired) | Mean | Median | Total |
|---|---:|---:|---:|---:|
| `patcher` | 77 | 8min 38s | 8min 31s | 11h 4min |
| `reviewer` | 77 | 2min 7s | 1min 47s | 2h 42min |
| `locator` | 77 | 1min 29s | 1min 33s | 1h 53min |
| `finalizer` | 75 | 18.9 s | 16.0 s | 23min 38s |

### LLM call totals

- **Total LLM calls**: 1,173
- **Total tokens**: 6,344,990 (5,942,743 + 402,247)

### Resolved instances

- `django__django-11179`
- `django__django-14580`
- `django__django-14672`
- `django__django-15388`
- `django__django-15851`
- `django__django-16379`
- `django__django-16527`
- `django__django-17087`
- `mwaskom__seaborn-3010`
- `sphinx-doc__sphinx-8721`
- `sympy__sympy-18621`
- `sympy__sympy-21612`
<!-- END notebook-chain-9b-77litetest -->
