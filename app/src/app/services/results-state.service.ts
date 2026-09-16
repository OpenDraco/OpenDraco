import { Injectable } from '@angular/core';

type LogName = 'run_instance.log' | 'test_output.txt' | 'eval.sh' | 'patch.diff' | 'report.json';

/**
 * Persists the Results page UI state across navigation. Mirrors
 * `TopologyStateService` and `InferenceStateService` so the user doesn't
 * lose their place when hopping between Topology / Inference / Evaluation /
 * Results.
 *
 * Loaded artefacts (the `prediction` / `evaluation` payloads) live on the
 * component itself and are re-fetched on demand — only selection state needs
 * to survive a navigation.
 */
@Injectable({ providedIn: 'root' })
export class ResultsStateService {
  selectedId: string | null = null;
  selectedRunId: string | null = null;
  showLogs = false;
  activeLog: LogName = 'run_instance.log';
  /** Filter for the left instance panel — matches instance_id substrings OR
   * the run_id of any prediction/evaluation under that instance. */
  filter = '';
  /** Default grouping is by job (run_id) — one row per inference run,
   * expandable to show the instances it produced. Toggling this on flips
   * the left panel to a flat by-instance list. */
  groupByInstance = false;
  /** Open/closed state for the job-group expanders, keyed by `job/<run_id>`.
   * Re-uses the InferenceStateService open-set pattern. */
  openJobs = new Set<string>();

  toggleSubset(s: string): void {
    if (this.openJobs.has(s)) this.openJobs.delete(s);
    else this.openJobs.add(s);
  }
  isSubsetOpen(s: string): boolean { return this.openJobs.has(s); }

  reset(): void {
    this.selectedId = null;
    this.selectedRunId = null;
    this.showLogs = false;
    this.activeLog = 'run_instance.log';
    this.filter = '';
    this.groupByInstance = false;
    this.openJobs.clear();
  }
}
