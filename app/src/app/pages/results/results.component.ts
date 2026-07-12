/** Results page shell — owns selection / fetch pipeline / log-viewer
 * modal and composes the four sub-panels. Sub-components are pure
 * presentation; intents bubble back here via @Output. */
import { Component, ChangeDetectorRef, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { forkJoin } from 'rxjs';

import { ApiService } from '../../services/api.service';
import { ResultsStateService } from '../../services/results-state.service';
import { EvaluationRunService, LogLine, parseLogLine } from '../../services/evaluation-run.service';
import { DialogService } from '../../services/dialog.service';
import {
  AgentType,
  ResultInstance, ResultPrediction, ResultEvaluation,
  ResultPredictionFile, ResultEvaluationDir, ResultRun,
  UnifiedConfig,
} from '../../models/types';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { EvoBoxComponent, EvoButtonComponent, EvoSelectComponent } from '../../components/index';
import { ICON } from '../../icons';
import {
  RunInstance, buildNodeColors, parseNdjsonToRunInstance,
  parseAgentTimingsFromLog, applyAgentTimingsToInstance,
} from '../../services/inference-run.service';

import {
  InstanceTreePickerComponent, PredictionPanelComponent,
  EvaluationPanelComponent, LogViewerModalComponent, JobGroup,
} from './components/index';

type LogName = 'run_instance.log' | 'test_output.txt' | 'eval.sh' | 'patch.diff' | 'report.json';

@Component({
  selector: 'app-results',
  standalone: true,
  imports: [
    CommonModule, FormsModule, EvoBoxComponent, EvoButtonComponent, EvoSelectComponent,
    InstanceTreePickerComponent, PredictionPanelComponent,
    EvaluationPanelComponent, LogViewerModalComponent, NgIcon,
  ],
  providers: [provideIcons(ICON)],
  templateUrl: './results.component.html',
  styleUrl: './results.component.css',
})
export class ResultsComponent implements OnInit {
  /** Used to scroll the deep-linked row into view. */
  @ViewChild(InstanceTreePickerComponent) treePicker?: InstanceTreePickerComponent;

  instances: ResultInstance[] = [];

  // ─── Selection (persisted across navigation) ───────────────────
  get selectedId(): string | null { return this.state.selectedId; }
  set selectedId(v: string | null) { this.state.selectedId = v; }
  get selectedRunId(): string | null { return this.state.selectedRunId; }
  set selectedRunId(v: string | null) { this.state.selectedRunId = v; }

  // ─── Loaded artefacts ─────────────────────────────────────────
  prediction: ResultPrediction | null = null;
  evaluation: ResultEvaluation | null = null;
  predictionLog: string | null = null;
  predictionLogMissing = false;
  predictionLogPath: string | null = null;
  showPredictionLog = false;
  predictionConfigJson = '';
  predictionConfigPath = '';
  logContent = '';
  loadingLog = false;

  // ─── Log-viewer modal state ──────────────────────────────────
  logViewOpen = false;
  logViewInstance: RunInstance | null = null;
  logViewLoading = false;
  logViewError = '';
  logViewTitle = '';
  /** Text-log filename shown in the modal title. */
  logViewFileName = '';
  /** Resolved predictions-logs directory from /api/paths; used in the
   * modal's filename-pill tooltip. Defaults to the legacy literal until
   * the first fetch lands. */
  predictionsLogsDir = 'results/predictions/logs';
  private agentTypesCache: AgentType[] | null = null;

  loading = false;
  error = '';

  constructor(
    private api: ApiService,
    private state: ResultsStateService,
    private cdr: ChangeDetectorRef,
    private router: Router,
    private route: ActivatedRoute,
    private evalSvc: EvaluationRunService,
    private dialog: DialogService,
  ) {}

  /** Deep-link from `?runId=…&instanceId=…`; applied after `refresh()`. */
  private pendingDeepLink: { runId?: string; instanceId?: string } | null = null;

  // ─── State proxies ─────────────────────────────────────────────
  get filter(): string { return this.state.filter; }
  set filter(v: string) { this.state.filter = v; }
  get groupByInstance(): boolean { return this.state.groupByInstance; }
  set groupByInstance(v: boolean) { this.state.groupByInstance = v; }
  get showLogs(): boolean { return this.state.showLogs; }
  set showLogs(v: boolean) { this.state.showLogs = v; }
  get activeLog(): LogName { return this.state.activeLog; }
  set activeLog(v: LogName) { this.state.activeLog = v; }

  get current(): ResultInstance | null {
    return this.instances.find(i => i.instance_id === this.selectedId) ?? null;
  }
  get selectedRun(): ResultRun | null {
    return this.current?.runs.find(r => r.run_id === this.selectedRunId) ?? null;
  }
  get selectedPredFile(): ResultPredictionFile | null { return this.selectedRun?.prediction ?? null; }
  get selectedEvalDir(): ResultEvaluationDir | null { return this.selectedRun?.evaluation ?? null; }
  get isCustomInstance(): boolean { return (this.selectedId ?? '').startsWith('custom-'); }

  get runOptions(): { value: string; label: string }[] {
    const runs = this.current?.runs ?? [];
    return runs.map(r => {
      const ts = this.formatTs(r.mtime);
      const tag = (r.prediction && r.evaluation) ? 'pred + eval'
                : (r.prediction)                  ? 'pred only — no eval yet'
                :                                   'eval only — prediction missing';
      return { value: r.run_id, label: `${r.run_id} — ${ts} · ${tag}` };
    });
  }

  get openJobs(): Set<string> { return this.state.openJobs; }

  get filteredInstances(): ResultInstance[] {
    const q = this.filter.trim().toLowerCase();
    if (!q) return this.instances;
    return this.instances.filter(inst =>
      inst.instance_id.toLowerCase().includes(q) ||
      inst.runs.some(r => (r.run_id || '').toLowerCase().includes(q))
    );
  }

  get jobGroups(): JobGroup[] {
    const map = new Map<string, JobGroup>();
    for (const inst of this.filteredInstances) {
      for (const run of inst.runs) {
        const key = run.run_id || '(unknown)';
        let g = map.get(key);
        if (!g) { g = { runId: key, mtime: 0, entries: [] }; map.set(key, g); }
        g.entries.push({ instance: inst, run });
        if (run.mtime > g.mtime) g.mtime = run.mtime;
      }
    }
    return [...map.values()].sort((a, b) => b.mtime - a.mtime);
  }

  isJobOpen(runId: string): boolean { return this.state.isSubsetOpen(`job/${runId}`); }
  toggleJob(runId: string): void { this.state.toggleSubset(`job/${runId}`); }

  // ─── Timing / config display ──────────────────────────────────
  get predictionTimestamp(): string {
    const fromLog = this.firstLogTimestamp(this.predictionLog ?? '');
    if (fromLog) return fromLog.toLocaleString();
    const startedAt = this.prediction?.data?.['started_at'];
    if (typeof startedAt === 'number') return new Date(startedAt).toLocaleString();
    return '—';
  }

  private firstLogTimestamp(raw: string): Date | null {
    if (!raw) return null;
    const re = /^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})[,.](\d{1,6})/;
    const lines = raw.split('\n', 25);
    for (const line of lines) {
      const m = re.exec(line);
      if (!m) continue;
      const ms = m[3].padEnd(3, '0').slice(0, 3);
      const d = new Date(`${m[1]}T${m[2]}.${ms}`);
      if (!Number.isNaN(d.getTime())) return d;
    }
    return null;
  }

  get predictionEndTimestamp(): string {
    const endedAt = this.prediction?.data?.['ended_at'];
    if (typeof endedAt === 'number') return new Date(endedAt).toLocaleString();
    const p = this.selectedPredFile;
    return p ? new Date(p.mtime * 1000).toLocaleString() : '—';
  }

  get predictionDuration(): string {
    const startDate = this.firstLogTimestamp(this.predictionLog ?? '');
    const startMs = startDate
      ? startDate.getTime()
      : (typeof this.prediction?.data?.['started_at'] === 'number'
          ? (this.prediction!.data!['started_at'] as number)
          : NaN);
    const endRaw = this.prediction?.data?.['ended_at'];
    const endMs = typeof endRaw === 'number'
      ? endRaw
      : (this.selectedPredFile ? this.selectedPredFile.mtime * 1000 : NaN);
    if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) return '';
    const total = Math.round((endMs - startMs) / 1000);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    const pad = (n: number) => n.toString().padStart(2, '0');
    return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
  }

  get predictionConfigUsed(): string {
    const runId = this.selectedRunId ?? '';
    if (!runId) return '—';
    const m = runId.match(/^(.+)-[0-9a-f]{6,}$/);
    return m ? m[1] : runId;
  }

  // ─── Lifecycle ────────────────────────────────────────────────
  ngOnInit(): void {
    // Pull the resolved RESULTS_DIR-derived paths so the log-viewer
    // modal's filename-pill tooltip surfaces the actual on-disk path
    // instead of the legacy `results/predictions/logs` literal.
    this.api.getPaths().subscribe({
      next: paths => {
        this.predictionsLogsDir = paths.predictions_logs_dir;
        this.cdr.markForCheck();
      },
      error: () => { /* keep the literal fallback */ },
    });
    // Subscribe (not snapshot) so deep-links land when the user is
    // already on this page — query-only nav keeps the component mounted.
    this.route.queryParamMap.subscribe(q => {
      const runId = q.get('runId') ?? '';
      const instanceId = q.get('instanceId') ?? '';
      this.pendingDeepLink = (runId || instanceId)
        ? {
            ...(runId ? { runId } : {}),
            ...(instanceId ? { instanceId } : {}),
          }
        : null;
      this.refresh();
    });
  }

  /** Apply the queued deep-link. Precise (instance+run) pairs require
   * both to exist; partial matches clear selection instead of latching
   * onto a different run on the same instance. */
  private applyPendingDeepLink(): void {
    const link = this.pendingDeepLink;
    if (!link) return;
    this.pendingDeepLink = null;
    if (link.instanceId && link.runId) {
      const inst = this.instances.find(i => i.instance_id === link.instanceId);
      const run = inst?.runs.find(r => r.run_id === link.runId);
      if (inst && run) {
        this.selectInstance(inst.instance_id);
        this.selectRun(run.run_id);
      } else {
        this.clearSelection();
      }
      return;
    }
    if (link.instanceId) {
      const inst = this.instances.find(i => i.instance_id === link.instanceId);
      if (inst) {
        this.selectInstance(inst.instance_id);
      } else {
        this.clearSelection();
      }
      return;
    }
    if (link.runId) {
      for (const inst of this.instances) {
        const run = inst.runs.find(r => r.run_id === link.runId);
        if (run) {
          this.selectInstance(inst.instance_id);
          this.selectRun(run.run_id);
          return;
        }
      }
      this.clearSelection();
    }
  }

  /** Force grouped-by-run mode, open the run's group, scroll into view.
   * The new Set is required so `[openJobs]` re-checks (Object.is). */
  private _revealRunInLeftPanel(runId: string): void {
    this.state.groupByInstance = false;
    this.state.openJobs = new Set<string>([...this.state.openJobs, `job/${runId}`]);
    this.cdr.markForCheck();
    setTimeout(() => this.treePicker?.revealSelected(), 0);
  }

  private restoreSelection(): void {
    if (!this.selectedRunId) return;
    const run = this.selectedRun;
    if (!run) return;
    if (run.prediction) this.loadPrediction(run.prediction);
    if (run.evaluation) this.loadEvaluation(run.evaluation);
  }

  refresh(): void {
    this.loading = true;
    this.error = '';
    this.api.getResultInstances().subscribe({
      next: (list) => {
        this.instances = list;
        // Deep-link wins over the last-viewed selection.
        if (this.pendingDeepLink) {
          this.applyPendingDeepLink();
        } else if (this.selectedId && !list.find(i => i.instance_id === this.selectedId)) {
          this.clearSelection();
        } else {
          this.restoreSelection();
        }
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: (err) => {
        this.error = `Failed to load results: ${err.message ?? err}`;
        this.loading = false;
        this.cdr.markForCheck();
      },
    });
  }

  selectInstance(id: string): void {
    if (this.selectedId === id) return;
    this.selectedId = id;
    this.resetArtefacts();
    const firstRun = this.current?.runs[0] ?? null;
    this.selectRun(firstRun?.run_id ?? null);
  }

  selectInstanceInJob(payload: { instance: ResultInstance; run: ResultRun }): void {
    const idChanged = this.selectedId !== payload.instance.instance_id;
    if (idChanged) {
      this.selectedId = payload.instance.instance_id;
      this.resetArtefacts();
    }
    this.selectRun(payload.run.run_id ?? null);
  }

  private resetArtefacts(): void {
    this.prediction = null;
    this.evaluation = null;
    this.predictionLog = null;
    this.predictionLogMissing = false;
    this.showPredictionLog = false;
    this.logContent = '';
    this.showLogs = false;
  }

  clearSelection(): void {
    this.selectedId = null;
    this.selectedRunId = null;
    this.resetArtefacts();
  }

  selectRun(runId: string | null): void {
    this.selectedRunId = runId;
    this.prediction = null;
    this.evaluation = null;
    this.predictionLog = null;
    this.predictionLogMissing = false;
    this.predictionConfigJson = '';
    this.predictionConfigPath = '';
    this.logContent = '';
    if (this.selectedPredFile) {
      this.loadPrediction(this.selectedPredFile);
      this.loadPredictionLog(this.selectedPredFile);
      this.loadPredictionConfig(this.selectedPredFile);
    }
    if (this.selectedEvalDir) this.loadEvaluation(this.selectedEvalDir);
    if (runId) this._revealRunInLeftPanel(runId);
    this.cdr.markForCheck();
  }

  // ─── Async loads ──────────────────────────────────────────────
  private loadPredictionConfig(p: ResultPredictionFile): void {
    this.api.getResultPredictionConfig(p.path).subscribe({
      next: res => {
        this.predictionConfigJson = res.exists ? res.raw : '';
        this.predictionConfigPath = res.exists ? res.path : '';
        this.cdr.markForCheck();
      },
      error: () => { this.predictionConfigJson = ''; this.predictionConfigPath = ''; this.cdr.markForCheck(); },
    });
  }

  private loadPredictionLog(p: ResultPredictionFile): void {
    this.api.getResultPredictionLog(p.path).subscribe({
      next: (res) => {
        this.predictionLog = res.raw;
        this.predictionLogMissing = !res.exists;
        this.predictionLogPath = res.exists ? res.path : null;
        this.cdr.markForCheck();
      },
      error: () => {
        this.predictionLog = '';
        this.predictionLogMissing = true;
        this.predictionLogPath = null;
        this.cdr.markForCheck();
      },
    });
  }

  private loadPrediction(p: ResultPredictionFile): void {
    this.api.getResultPrediction(p.path, this.selectedId ?? undefined).subscribe({
      next: (res) => { this.prediction = res; this.cdr.markForCheck(); },
      error: (err) => { this.error = `Prediction load failed: ${err.message ?? err}`; this.cdr.markForCheck(); },
    });
  }

  private loadEvaluation(e: ResultEvaluationDir): void {
    this.api.getResultEvaluation(e.dir).subscribe({
      next: (res) => {
        this.evaluation = res;
        this.cdr.markForCheck();
        if (this.showLogs) this.fetchLog();
      },
      error: (err) => { this.error = `Evaluation load failed: ${err.message ?? err}`; this.cdr.markForCheck(); },
    });
  }

  toggleLogs(on: boolean): void {
    this.showLogs = on;
    if (on && !this.logContent) this.fetchLog();
  }

  setActiveLog(name: LogName): void {
    if (this.activeLog === name) return;
    this.activeLog = name;
    this.fetchLog();
  }

  private fetchLog(): void {
    if (!this.selectedEvalDir) return;
    this.loadingLog = true;
    this.logContent = '';
    this.api.getResultEvaluationLog(this.selectedEvalDir.dir, this.activeLog).subscribe({
      next: (res) => { this.logContent = res.content; this.loadingLog = false; this.cdr.markForCheck(); },
      error: (err) => {
        this.logContent = `(failed to load log: ${err?.error?.detail ?? err?.message ?? err})`;
        this.loadingLog = false;
        this.cdr.markForCheck();
      },
    });
  }

  togglePredictionLog(on: boolean): void { this.showPredictionLog = on; }

  // ─── Downloads ────────────────────────────────────────────────
  downloadPrediction(): void {
    if (!this.prediction) return;
    this.downloadText(this.prediction.raw, this.prediction.name, 'application/jsonl');
  }

  downloadPredictionLogFile(): void {
    if (!this.prediction || !this.predictionLog) return;
    const stem = this.prediction.name.replace(/\.jsonl$/i, '');
    this.downloadText(this.predictionLog, `${stem}.log`, 'application/x-ndjson');
  }

  downloadPredictionConfig(): void {
    if (!this.prediction || !this.predictionConfigJson) return;
    const stem = this.prediction.name.replace(/^prediction-/, '').replace(/\.jsonl$/i, '');
    this.downloadText(this.predictionConfigJson, `${stem}.json`, 'application/json');
  }

  /** Reproduce-this-run notebook (built server-side, streamed as blob).
   * Prompts for the evaluator stem to bake into section 5 — required
   * because grading is task-specific. */
  downloadNotebook(): void {
    if (!this.selectedPredFile) return;
    const predFile = this.selectedPredFile;
    this.api.getEvaluationScripts().subscribe({
      next: async scripts => {
        if (scripts.length === 0) {
          this.dialog.alert({
            title: 'No evaluators registered',
            variant: 'danger',
            detail: 'Add a script under scripts/evaluation/ before downloading a reproducer notebook.',
          });
          return;
        }
        const defaultStem = scripts.some(s => s.value === 'apply_and_test')
          ? 'apply_and_test'
          : scripts[0].value;
        const chosen = await this.dialog.prompt({
          title: 'Pick evaluator',
          message: 'Baked into the notebook\'s section 5. Pick the grader that matches this task.',
          defaultValue: defaultStem,
          selectOptions: scripts,
          okLabel: 'Download',
        });
        if (!chosen) return;
        this.api.getResultPredictionNotebook(predFile.path, chosen).subscribe({
          next: blob => {
            const stem = predFile.name?.replace(/\.jsonl$/i, '') || 'prediction';
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${stem}.ipynb`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
          },
          error: err => {
            this.error = err?.error?.detail ?? err?.message ?? 'Failed to generate notebook';
            this.cdr.markForCheck();
          },
        });
      },
      error: err => {
        this.error = err?.error?.detail ?? err?.message ?? 'Could not list evaluators';
        this.cdr.markForCheck();
      },
    });
  }

  reveal(path: string | null | undefined): void {
    if (!path) return;
    this.api.revealInExplorer(path).subscribe({ error: () => { /* swallow */ } });
  }

  downloadZip(): void {
    if (!this.selectedEvalDir) return;
    const url = this.api.getResultEvaluationZipUrl(this.selectedEvalDir.dir);
    const a = document.createElement('a');
    a.href = url; a.rel = 'noopener';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }

  downloadLog(): void {
    if (!this.logContent) return;
    const id = this.selectedId ?? 'log';
    this.downloadText(this.logContent, `${id}.${this.activeLog}`, 'text/plain');
  }

  private downloadText(text: string, filename: string, mime: string): void {
    const blob = new Blob([text], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  goEvaluate(): void {
    const path = this.selectedPredFile?.path;
    if (!path) return;
    this.evalSvc.predictionsPath = path;
    this.router.navigate(['/evaluation']);
  }

  // ─── Log-viewer modal ─────────────────────────────────────────
  openLogViewer(): void {
    const file = this.selectedPredFile;
    if (!file) return;
    this.logViewOpen = true;
    this.logViewLoading = true;
    this.logViewError = '';
    this.logViewInstance = null;
    this.logViewTitle = this.prediction?.data?.instance_id ?? this.selectedId ?? '';
    this.logViewFileName = this.selectedRunId
      ? `prediction-${this.selectedRunId}.log` : '';
    this.cdr.markForCheck();

    const agentTypes$ = this.agentTypesCache
      ? new Promise<AgentType[]>(res => res(this.agentTypesCache!))
      : this.api.getAgentTypes().toPromise().then(v => v ?? []);

    forkJoin({
      ndjson: this.api.getResultPredictionNdjson(file.path),
      cfg:    this.api.getResultPredictionConfig(file.path),
      // The .log file is the source of truth for per-agent execution
      // time. NDJSON events don't carry per-event timestamps, so the
      // replay path overlays log-derived `durationMs` onto the cards
      // after the NDJSON reduce. Missing log → cards render without
      // timings (the renderer just omits the badge).
      log:    this.api.getResultPredictionLog(file.path),
      types:  agentTypes$,
    }).subscribe({
      next: ({ ndjson, cfg, log, types }) => {
        this.logViewLoading = false;
        if (types && !this.agentTypesCache) this.agentTypesCache = types;
        if (!ndjson.exists) {
          this.logViewError = 'NDJSON event log not found for this run — re-run inference to capture one.';
          this.cdr.markForCheck();
          return;
        }
        let nodeColors: Record<string, string> = {};
        if (cfg.exists && cfg.raw && types?.length) {
          try {
            const parsed = JSON.parse(cfg.raw) as UnifiedConfig;
            nodeColors = buildNodeColors(parsed, types);
          } catch { /* leave nodeColors empty */ }
        }
        this.logViewInstance = parseNdjsonToRunInstance(
          ndjson.raw, this.logViewTitle, nodeColors,
        );
        // Overlay log-derived per-agent durations. The NDJSON reduce
        // path also writes `durationMs` (using parse-time wall clock,
        // not the original run's clock), so this overwrite is what
        // makes the replay timing meaningful.
        if (log.exists && log.raw) {
          applyAgentTimingsToInstance(
            this.logViewInstance,
            parseAgentTimingsFromLog(log.raw),
          );
        }
        this.cdr.markForCheck();
      },
      error: err => {
        this.logViewLoading = false;
        this.logViewError = err?.error?.detail ?? err?.message ?? 'Failed to load log';
        this.cdr.markForCheck();
      },
    });
  }

  closeLogViewer(): void {
    this.logViewOpen = false;
    this.logViewInstance = null;
    this.logViewError = '';
    this.logViewTitle = '';
    this.logViewFileName = '';
    this.cdr.markForCheck();
  }

  // ─── View helpers ─────────────────────────────────────────────
  formatTs(mtime: number): string {
    return new Date(mtime * 1000).toLocaleString();
  }

  diffLines(): { line: string; cls: string }[] {
    const patch = this.prediction?.data?.model_patch ?? '';
    return patch.split('\n').map((line: string) => {
      let cls = '';
      if (line.startsWith('+') && !line.startsWith('+++')) cls = 'diff-add';
      else if (line.startsWith('-') && !line.startsWith('---')) cls = 'diff-rm';
      else if (line.startsWith('@@') || line.startsWith('diff ')) cls = 'diff-hdr';
      return { line, cls };
    });
  }

  coloredLog(): LogLine[] {
    if (!this.logContent) return [];
    const lines = this.logContent.split('\n');
    switch (this.activeLog) {
      case 'test_output.txt': return lines.map(l => this.parseTestLine(l));
      case 'eval.sh':         return lines.map(l => this.parseShellLine(l));
      case 'patch.diff':      return lines.map(l => this.parseDiffLine(l));
      case 'report.json':     return this.parseJsonLines();
      case 'run_instance.log':
      default:                return lines.map(parseLogLine);
    }
  }

  private parseTestLine(line: string): LogLine {
    if (!line.trim()) return [{ t: line || ' ', c: 'sl-dim' }];
    const kw = line.match(/\b(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b/);
    if (kw) {
      const idx = kw.index!;
      const cls =
        kw[1] === 'PASSED' || kw[1] === 'XPASS' ? 'sl-ok' :
        kw[1] === 'SKIPPED' || kw[1] === 'XFAIL' ? 'sl-warn-msg' : 'sl-err-msg';
      return [
        { t: line.slice(0, idx), c: 'sl-text' },
        { t: kw[1], c: cls },
        { t: line.slice(idx + kw[1].length), c: 'sl-text' },
      ];
    }
    if (/^=+\s.*\s=+$/.test(line)) return [{ t: line, c: 'sl-info' }];
    if (/^_{3,}\s/.test(line))      return [{ t: line, c: 'sl-warn' }];
    if (/^(Traceback|.*Error:|.*Exception:|\s+File ")/.test(line)) {
      return [{ t: line, c: 'sl-err-msg' }];
    }
    if (/^collected \d+ item/.test(line)) return [{ t: line, c: 'sl-info' }];
    return [{ t: line, c: 'sl-text' }];
  }

  private parseShellLine(line: string): LogLine {
    if (line.startsWith('#!')) return [{ t: line, c: 'sl-info' }];
    if (line.trimStart().startsWith('#')) return [{ t: line, c: 'sl-dim' }];
    return [{ t: line || ' ', c: 'sl-text' }];
  }

  private parseDiffLine(line: string): LogLine {
    if (line.startsWith('+') && !line.startsWith('+++')) return [{ t: line, c: 'diff-add' }];
    if (line.startsWith('-') && !line.startsWith('---')) return [{ t: line, c: 'diff-rm' }];
    if (line.startsWith('@@') || line.startsWith('diff ')
        || line.startsWith('+++') || line.startsWith('---'))
      return [{ t: line, c: 'diff-hdr' }];
    return [{ t: line, c: 'sl-text' }];
  }

  private parseJsonLines(): LogLine[] {
    let pretty = this.logContent;
    try { pretty = JSON.stringify(JSON.parse(this.logContent), null, 2); } catch { /* fall through */ }
    return pretty.split('\n').map(line => {
      const out: LogLine = [];
      const re = /("(?:\\.|[^"\\])*")|(\b(?:true|false|null)\b)|(-?\d+(?:\.\d+)?)/g;
      let last = 0;
      let m: RegExpExecArray | null;
      while ((m = re.exec(line)) !== null) {
        if (m.index > last) out.push({ t: line.slice(last, m.index), c: 'sl-text' });
        const cls = m[1] ? 'sl-ok'
                  : m[2] ? 'sl-warn'
                  :        'sl-info';
        out.push({ t: m[0], c: cls });
        last = m.index + m[0].length;
      }
      if (last < line.length) out.push({ t: line.slice(last), c: 'sl-text' });
      return out.length ? out : [{ t: line || ' ', c: 'sl-dim' }];
    });
  }

  resolvedFlag(): boolean | null {
    const r = this.evaluation?.report;
    if (!r) return null;
    const inner = r[this.selectedId ?? ''] as Record<string, unknown> | undefined;
    if (inner && typeof inner['resolved'] === 'boolean') return inner['resolved'] as boolean;
    return null;
  }

  testStatus(): { passed: number; failed: number; group: string }[] | null {
    const inner = this.evaluation?.report?.[this.selectedId ?? ''] as Record<string, unknown> | undefined;
    const status = inner?.['tests_status'] as Record<string, { success?: string[]; failure?: string[] }> | undefined;
    if (!status) return null;
    return Object.entries(status).map(([group, g]) => ({
      group,
      passed: g.success?.length ?? 0,
      failed: g.failure?.length ?? 0,
    }));
  }
}
