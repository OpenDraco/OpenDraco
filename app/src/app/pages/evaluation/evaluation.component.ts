/** Evaluation page shell. Owns the cross-cutting state (predictions
 * listing, file-picker error, inspection cache) and composes two
 * sub-components: `<app-eval-config-panel>` on the left (config + run
 * controls + progress + stats) and `<app-eval-log-panel>` on the right
 * (streaming logs). Sub-components don't touch the
 * `EvaluationRunService` directly — every slice of state crosses via
 * @Input and every intent comes back via @Output. */
import {
  ChangeDetectorRef, Component, OnDestroy, OnInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';

import { ApiService } from '../../services/api.service';
import { EvaluationRunService, LogLine, ResultStats } from '../../services/evaluation-run.service';
import { PredictionInspection } from '../../models/types';
import { EvalConfigPanelComponent, EvalLogPanelComponent } from './components/index';

@Component({
  selector: 'app-evaluation',
  standalone: true,
  imports: [CommonModule, EvalConfigPanelComponent, EvalLogPanelComponent],
  templateUrl: './evaluation.component.html',
  styleUrl: './evaluation.component.css',
})
export class EvaluationComponent implements OnInit, OnDestroy {
  // ─── Transient UI state ────────────────────────────────────────
  availablePredictions: string[] = [];
  predictionOptions: { value: string; label: string }[] = [];
  inspection: PredictionInspection | null = null;
  inspectionError = '';
  inspectionLoading = false;
  filePickerError = '';
  /** Resolved predictions directory from /api/paths, surfaced in
   * user-facing strings. Defaults to the legacy `results/predictions`
   * literal until the first fetch lands. */
  predictionsDir = 'results/predictions';
  private changeSub?: Subscription;
  private lastInspectedPath = '';

  constructor(
    public evalSvc: EvaluationRunService,
    private api: ApiService,
    private cdr: ChangeDetectorRef,
  ) {}

  // ─── Getters delegating to service ─────────────────────────────
  get running(): boolean { return this.evalSvc.running; }
  get logs(): LogLine[] { return this.evalSvc.logs; }
  get progressPercent(): number { return this.evalSvc.progressPercent; }
  get progressDone(): number { return this.evalSvc.progressDone; }
  get progressTotal(): number { return this.evalSvc.progressTotal; }
  get stats(): ResultStats | null { return this.evalSvc.stats; }
  get errorMsg(): string { return this.evalSvc.errorMsg; }
  get returnCode(): number | null { return this.evalSvc.returnCode; }

  get predictionsPath(): string { return this.evalSvc.predictionsPath; }
  setPredictionsPath(v: string): void {
    this.evalSvc.predictionsPath = v;
    this.refreshInspection();
  }

  get maxWorkers(): number { return this.evalSvc.maxWorkers; }
  setMaxWorkers(v: number): void { this.evalSvc.maxWorkers = v; }

  get evaluator(): string { return this.evalSvc.evaluator; }
  setEvaluator(v: string): void { this.evalSvc.evaluator = v; }

  /** `{value, label}` for every `scripts/evaluation/*.py`. Fetched once
   * on init; the inspection card below is informational only. */
  evaluatorOptions: { value: string; label: string }[] = [];

  ngOnInit(): void {
    this.loadPredictions();
    this.api.getEvaluationScripts().subscribe({
      next: opts => {
        this.evaluatorOptions = opts;
        this.cdr.markForCheck();
      },
      error: () => { this.evaluatorOptions = []; },
    });
    // Pull the resolved RESULTS_DIR-derived paths so the empty hint +
    // file-picker tooltip + "isn't under …" error message reflect what
    // the backend actually scans (instead of the hardcoded `results/`).
    this.api.getPaths().subscribe({
      next: paths => {
        this.predictionsDir = paths.predictions_dir;
        this.cdr.markForCheck();
      },
      error: () => { /* keep the literal fallback */ },
    });
    this.changeSub = this.evalSvc.changed.subscribe(() => this.cdr.markForCheck());
  }

  ngOnDestroy(): void {
    this.changeSub?.unsubscribe();
    // Do NOT cancel evalSvc — evaluation keeps running across navigation.
  }

  // ─── True when every group in the picked prediction file is
  //     custom/custom — the SWE-bench harness can't score those.
  get isCustomOnly(): boolean {
    const groups = this.inspection?.groups ?? [];
    return groups.length > 0 && groups.every(g => g.subset === 'custom' && g.split === 'custom');
  }

  // True when the file mixes custom rows with SWE-bench rows.
  get hasCustomMixed(): boolean {
    const groups = this.inspection?.groups ?? [];
    const hasCustom = groups.some(g => g.subset === 'custom' && g.split === 'custom');
    const hasReal   = groups.some(g => !(g.subset === 'custom' && g.split === 'custom'));
    return hasCustom && hasReal;
  }

  // ─── Actions ───────────────────────────────────────────────────
  loadPredictions(): void {
    this.api.getPredictions().subscribe(paths => {
      this.availablePredictions = paths;
      this.predictionOptions = paths.map(p => ({ value: p, label: this.fileName(p) }));
      if (!this.evalSvc.predictionsPath && paths.length > 0)
        this.evalSvc.predictionsPath = paths[0];
      this.refreshInspection();
      this.cdr.markForCheck();
    });
  }

  refreshInspection(): void {
    const path = this.evalSvc.predictionsPath;
    if (!path) {
      this.inspection = null;
      this.inspectionError = '';
      this.lastInspectedPath = '';
      return;
    }
    if (path === this.lastInspectedPath) return;
    this.lastInspectedPath = path;
    this.inspectionLoading = true;
    this.inspectionError = '';
    this.cdr.markForCheck();
    this.api.inspectPrediction(path).subscribe({
      next: res => {
        this.inspection = res;
        this.inspectionLoading = false;
        this.cdr.markForCheck();
      },
      error: err => {
        this.inspection = null;
        this.inspectionError = err?.error?.detail ?? err?.message ?? 'Inspection failed';
        this.inspectionLoading = false;
        this.cdr.markForCheck();
      },
    });
  }

  run(): void { this.evalSvc.run(); }
  cancel(): void { this.evalSvc.cancel(); }
  clearLogs(): void { this.evalSvc.clearLogs(); }

  fileName(path: string): string {
    return path.split(/[/\\]/).pop() ?? path;
  }

  /** OS file-picker handler. Browsers don't expose absolute paths, so we
   * resolve the chosen file against the server's listing of
   * results/predictions/ and pre-select the matching entry. */
  onPredictionFileChosen(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    this.filePickerError = '';

    const resolveFromList = () => {
      const match = this.availablePredictions.find(p => this.fileName(p) === file.name);
      if (match) {
        this.setPredictionsPath(match);
        this.cdr.markForCheck();
        return true;
      }
      return false;
    };

    if (resolveFromList()) return;
    this.api.getPredictions().subscribe({
      next: paths => {
        this.availablePredictions = paths;
        this.predictionOptions = paths.map(p => ({ value: p, label: this.fileName(p) }));
        if (!resolveFromList()) {
          this.filePickerError =
            `"${file.name}" isn't under ${this.predictionsDir}/. ` +
            `Move/copy it there and try again — the harness only reads files under that folder.`;
        }
        this.cdr.markForCheck();
      },
      error: () => {
        this.filePickerError = `"${file.name}" isn't under ${this.predictionsDir}/.`;
        this.cdr.markForCheck();
      },
    });
  }
}
