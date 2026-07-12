/** Inference page shell — owns instance list, refresh status, and the
 * custom-repo form. Sub-components project slices via @Input and
 * bubble intents via @Output into `InferenceRunService`. */
import {
  AfterViewChecked, ChangeDetectorRef, Component, ElementRef,
  OnDestroy, OnInit, ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';

import { ApiService } from '../../services/api.service';
import { DialogService } from '../../services/dialog.service';
import {
  InferenceRunService, RunInstance, buildNodeColors,
} from '../../services/inference-run.service';
import { InferenceStateService } from '../../services/inference-state.service';
import {
  AgentType, Instance, SwebenchSubset, SwebenchSplit,
} from '../../models/types';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { ICON } from '../../icons';
import { InferenceInstanceViewComponent } from '../../components/index';
import {
  InstancePickerTreeComponent, RunControlsBarComponent,
  BatchProgressStripComponent, CustomRepoModalComponent,
} from './components/index';

@Component({
  selector: 'app-inference',
  standalone: true,
  imports: [
    CommonModule, InferenceInstanceViewComponent,
    InstancePickerTreeComponent, RunControlsBarComponent,
    BatchProgressStripComponent, CustomRepoModalComponent,
    NgIcon,
  ],
  providers: [provideIcons(ICON)],
  templateUrl: './inference.component.html',
  styleUrl: './inference.component.css',
})
export class InferenceComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('scrollEl') scrollEl!: ElementRef<HTMLDivElement>;

  // ─── Instances ─────────────────────────────────────────────────
  instances: Instance[] = [];
  instancesTotal = 0;
  /** 0 = unlimited. The picker collapses subsets so scale isn't an issue. */
  instancesPageSize = 0;
  loadingInstances = false;
  refreshing = false;
  refreshError = '';

  configs: string[] = [];
  showThinking = true;
  /** `/api/agent-types` catalog; feeds the per-node colour map. */
  private agentTypes: AgentType[] = [];
  private changeSub?: Subscription;
  shouldScroll = false;
  /** True when the log panel is pinned to the bottom edge. */
  stickToBottom = true;

  customFormOpen = false;
  customRepo = '';
  customProblem = '';
  customBaseCommit = '';
  /** Resolved predictions-logs directory from /api/paths; used in the
   * per-instance chip tooltip. Defaults to the legacy literal until the
   * first fetch lands. */
  predictionsLogsDir = 'results/predictions/logs';
  customSubmitting = false;
  customError = '';

  constructor(
    private api: ApiService,
    public inferSvc: InferenceRunService,
    public state: InferenceStateService,
    private cdr: ChangeDetectorRef,
    private dialog: DialogService,
  ) {}

  // ─── Getters delegating to the run service ─────────────────────
  get running(): boolean { return this.inferSvc.running; }
  get cancelled(): boolean { return this.inferSvc.cancelled; }
  get statusMsg(): string { return this.inferSvc.statusMsg; }
  get pullingModels(): InferenceRunService['pullingModels'] { return this.inferSvc.pullingModels; }
  get hasActivePulls(): boolean { return this.pullingModels.length > 0; }
  get runInstances(): RunInstance[] { return this.inferSvc.instances; }
  get currentInstance(): RunInstance | null { return this.inferSvc.currentInstance; }

  selectInstanceInRun(id: string): void { this.inferSvc.selectInstance(id); }
  clearRun(): void { this.inferSvc.clear(); }

  // ─── State service proxies ─────────────────────────────────────
  get selectionCount(): number { return this.state.selectedInstanceIds.size; }
  get firstSelected(): string { return this.state.selectedList[0] ?? ''; }
  get instanceSearch(): string { return this.state.instanceSearch; }
  set instanceSearch(v: string) { this.state.instanceSearch = v; }
  get config(): string { return this.state.config; }
  setConfig(v: string): void {
    const changed = this.state.config !== v;
    this.state.config = v;
    if (changed) this.refreshNodeColors();
  }

  // ─── Lifecycle ─────────────────────────────────────────────────
  ngOnInit(): void {
    this.inferSvc.attach();
    this.loadInstances();
    // Pick up the resolved RESULTS_DIR-derived paths so the per-chip
    // tooltip surfaces the actual logs directory (not the legacy
    // `results/predictions/logs` literal).
    this.api.getPaths().subscribe({
      next: paths => {
        this.predictionsLogsDir = paths.predictions_logs_dir;
        this.cdr.markForCheck();
      },
      error: () => { /* keep the literal fallback */ },
    });
    this.api.getConfigs().subscribe(summaries => {
      this.configs = summaries.map(s => s.stem);
      if (!this.config && this.configs.length) {
        this.setConfig(this.configs.includes('chain') ? 'chain' : this.configs[0]);
      }
      this.refreshNodeColors();
      this.cdr.markForCheck();
    });
    this.api.getAgentTypes().subscribe(types => {
      this.agentTypes = types;
      this.refreshNodeColors();
    });
    this.changeSub = this.inferSvc.changed.subscribe(() => {
      this.shouldScroll = this.inferSvc.running && this.stickToBottom;
      this.cdr.markForCheck();
    });
  }

  private refreshNodeColors(): void {
    const stem = this.config;
    if (!stem || this.agentTypes.length === 0) return;
    this.api.getConfig(stem).subscribe({
      next: cfg => this.inferSvc.nodeColors = buildNodeColors(cfg, this.agentTypes),
      error: () => this.inferSvc.nodeColors = {},
    });
  }

  ngOnDestroy(): void {
    this.changeSub?.unsubscribe();
    this.inferSvc.detach();
  }

  onLogScroll(): void {
    if (!this.scrollEl) return;
    const el = this.scrollEl.nativeElement;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    this.stickToBottom = distanceFromBottom < 16;
  }

  ngAfterViewChecked(): void {
    if (this.shouldScroll && this.scrollEl) {
      const el = this.scrollEl.nativeElement;
      el.scrollTop = el.scrollHeight;
      this.shouldScroll = false;
    }
  }

  // ─── Instance picker outputs ───────────────────────────────────
  loadInstances(): void {
    this.loadingInstances = true;
    const skip = this.state.instancesPage * this.instancesPageSize;
    this.api.getInstances(skip, this.instancesPageSize).subscribe(list => {
      this.instances = list;
      this.loadingInstances = false;
      this.cdr.markForCheck();
      this.api.countInstances().subscribe(r => {
        this.instancesTotal = r.count;
        this.cdr.markForCheck();
      });
    });
  }

  refreshAll(): void {
    if (this.refreshing) return;
    this.refreshing = true;
    this.refreshError = '';
    this.cdr.markForCheck();
    this.api.refreshAllInstances().subscribe({
      next: res => {
        this.refreshing = false;
        const failures = Object.entries(res.results)
          .filter(([, v]) => 'error' in v)
          .map(([k, v]) => `${k}: ${v.error}`);
        if (failures.length) this.refreshError = failures.join(' | ');
        this.loadInstances();
      },
      error: err => {
        this.refreshing = false;
        this.refreshError = err?.error?.detail ?? err?.message ?? 'Refresh failed';
        this.cdr.markForCheck();
      },
    });
  }

  refreshLeaf(payload: { subset: SwebenchSubset; split: SwebenchSplit }): void {
    if (this.refreshing) return;
    if (payload.subset === 'custom') return;
    this.refreshing = true;
    this.refreshError = '';
    this.cdr.markForCheck();
    this.api.refreshInstances(payload.subset, payload.split as 'dev' | 'test' | 'train').subscribe({
      next: () => { this.refreshing = false; this.loadInstances(); },
      error: err => {
        this.refreshing = false;
        this.refreshError = err?.error?.detail ?? err?.message ?? 'Refresh failed';
        this.cdr.markForCheck();
      },
    });
  }

  refreshSubset(subset: SwebenchSubset): void {
    if (this.refreshing || subset === 'custom') return;
    const splits: SwebenchSplit[] = ['dev', 'test', 'train'] as SwebenchSplit[];
    this.refreshing = true;
    this.refreshError = '';
    this.cdr.markForCheck();
    const failures: string[] = [];
    const next = (idx: number) => {
      if (idx >= splits.length) {
        this.refreshing = false;
        this.refreshError = failures.join(' | ');
        this.loadInstances();
        return;
      }
      const split = splits[idx];
      this.api.refreshInstances(subset, split as 'dev' | 'test' | 'train').subscribe({
        next: () => next(idx + 1),
        error: err => {
          failures.push(`${subset}/${split}: ${err?.error?.detail ?? err?.message ?? 'failed'}`);
          next(idx + 1);
        },
      });
    };
    next(0);
  }

  toggleSplitSelection(payload: { subset: SwebenchSubset; split: SwebenchSplit }): void {
    // Honour the picker's filter — operate on visible ids only.
    const q = this.state.instanceSearch.toLowerCase();
    const ids = this.instances
      .filter(i => i.subset === payload.subset && i.split === payload.split &&
                   (!q || i.instance_id.toLowerCase().includes(q) || i.repo.toLowerCase().includes(q)))
      .map(i => i.instance_id);
    if (ids.length === 0) return;
    const allOn = ids.every(id => this.state.isSelected(id));
    for (const id of ids) {
      const on = this.state.isSelected(id);
      if (allOn && on) this.state.toggleInstance(id);
      if (!allOn && !on) this.state.toggleInstance(id);
    }
  }

  toggleSubsetSelection(subset: SwebenchSubset): void {
    const q = this.state.instanceSearch.toLowerCase();
    const ids = this.instances
      .filter(i => i.subset === subset &&
                   (!q || i.instance_id.toLowerCase().includes(q) || i.repo.toLowerCase().includes(q)))
      .map(i => i.instance_id);
    if (ids.length === 0) return;
    const allOn = ids.every(id => this.state.isSelected(id));
    for (const id of ids) {
      const on = this.state.isSelected(id);
      if (allOn && on) this.state.toggleInstance(id);
      if (!allOn && !on) this.state.toggleInstance(id);
    }
  }

  selectAllVisible(): void {
    const q = this.state.instanceSearch.toLowerCase();
    const visible: string[] = [];
    for (const inst of this.instances) {
      if (q && !inst.instance_id.toLowerCase().includes(q) && !inst.repo.toLowerCase().includes(q)) continue;
      if (this.state.isSubsetOpen(inst.subset) && this.state.isSplitOpen(inst.subset, inst.split)) {
        visible.push(inst.instance_id);
      }
    }
    this.state.setSelection([...this.state.selectedList, ...visible]);
  }

  // ─── Run / cancel ──────────────────────────────────────────────
  run(): void {
    const ids = this.state.selectedList;
    if (ids.length === 0 || this.running) return;
    this.inferSvc.run(ids, this.config);
    this.state.clearSelection();
  }
  cancel(): void { this.inferSvc.cancel(); }

  /** POST /api/inference/notebook with the current (instance_ids, config)
   * and hand the returned `.ipynb` to a download anchor. Lets the user
   * generate a reproduce-this-run notebook BEFORE running anything, so
   * they can take it to a different machine and run it there. */
  downloadNotebook(): void {
    const ids = this.state.selectedList;
    if (ids.length === 0 || !this.config) return;
    // Ask which evaluator to bake into section 5 — required at gen
    // time because inference is task-agnostic but grading isn't.
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
        this.api.buildInferenceNotebook(ids, this.config!, chosen).subscribe({
          next: blob => {
            const stem = `notebook-${this.config}-${Date.now()}`;
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
            const msg = err?.error?.detail ?? err?.message ?? 'Failed to build notebook';
            this.dialog.alert({
              title: 'Notebook download failed',
              variant: 'danger',
              detail: msg,
            });
          },
        });
      },
      error: err => {
        this.dialog.alert({
          title: 'Could not list evaluators',
          variant: 'danger',
          detail: err?.error?.detail ?? err?.message ?? String(err),
        });
      },
    });
  }

  // ─── Custom-repo modal handlers ────────────────────────────────
  toggleCustomForm(): void {
    this.customFormOpen = !this.customFormOpen;
    if (!this.customFormOpen) this.customError = '';
  }

  submitCustomInstance(): void {
    const repo = this.customRepo.trim();
    const problem = this.customProblem.trim();
    if (!repo || !problem || this.customSubmitting) return;
    this.customSubmitting = true;
    this.customError = '';
    this.cdr.markForCheck();
    this.api.addCustomInstance(repo, problem, this.customBaseCommit.trim() || undefined).subscribe({
      next: res => {
        this.customSubmitting = false;
        this.api.getInstances(0, this.instancesPageSize).subscribe(list => {
          this.instances = list;
          this.api.countInstances().subscribe(r => {
            this.instancesTotal = r.count;
            this.cdr.markForCheck();
          });
          if (!this.state.isSelected(res.instance_id)) this.state.toggleInstance(res.instance_id);
          if (!this.state.isSubsetOpen('custom')) this.state.toggleSubset('custom');
          if (!this.state.isSplitOpen('custom', 'custom')) this.state.toggleSplit('custom', 'custom');
          this.cdr.markForCheck();
        });
        this.customRepo = '';
        this.customProblem = '';
        this.customBaseCommit = '';
        this.customFormOpen = false;
        this.cdr.markForCheck();
      },
      error: err => {
        this.customSubmitting = false;
        this.customError = err?.error?.detail ?? err?.message ?? 'Failed to add custom instance';
        this.cdr.markForCheck();
      },
    });
  }
}
