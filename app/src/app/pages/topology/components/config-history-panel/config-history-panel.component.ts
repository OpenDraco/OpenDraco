/** Slide-in version history for a loaded config. Each entry is one
 * Save click; preview as mini graph or diff, then explicitly restore. */
import {
  AfterViewInit, ChangeDetectionStrategy, ChangeDetectorRef, Component,
  ElementRef, EventEmitter, HostListener, Input, OnChanges, OnDestroy,
  Output, SimpleChanges, ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import cytoscape, { Core, ElementDefinition } from 'cytoscape';
import { NgIcon, provideIcons } from '@ng-icons/core';

import { ICON } from '../../../../icons';
import { ApiService } from '../../../../services/api.service';
import { DialogService } from '../../../../services/dialog.service';
import {
  AgentType, ConfigHistoryEntry, ConfigRunMatch, UnifiedConfig,
} from '../../../../models/types';
import { buildNodeColors } from '../../../../services/inference-run.service';

/** One row in the diff view. */
interface DiffLine {
  type: 'add' | 'rm' | 'context';
  line: string;
}

@Component({
  selector: 'app-config-history-panel',
  standalone: true,
  imports: [CommonModule, RouterModule, NgIcon],
  providers: [provideIcons(ICON)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './config-history-panel.component.html',
  styleUrl: './config-history-panel.component.css',
})
export class ConfigHistoryPanelComponent implements OnChanges, AfterViewInit, OnDestroy {
  @Input() open = false;
  @Input() configName: string | null = null;
  /** Working-tree JSON (post in-memory edits) for the diff view's right side. */
  @Input() currentContent: string | null = null;
  /** Agent-type catalogue for the mini-graph palette. */
  @Input() agentTypes: AgentType[] = [];

  /** Carries the parsed config; parent persists + re-commits. */
  @Output() restore = new EventEmitter<UnifiedConfig>();
  @Output() close = new EventEmitter<void>();

  // ─── Timeline state ─────────────────────────────────────────────
  entries: ConfigHistoryEntry[] = [];
  loadingEntries = false;
  loadError = '';

  // ─── Preview pane state ─────────────────────────────────────────
  viewMode: 'graph' | 'diff' = 'graph';
  selectedSha: string | null = null;
  previewContent = '';
  previewLoading = false;
  previewError = '';

  /** Computed lazily on diff-view open to skip the LCS cost. */
  diffLines: DiffLine[] = [];
  diffComputed = false;

  // ─── Runs pill (per-sha cache) ────────────────────────────────────
  runsBySha: Record<string, ConfigRunMatch[]> = {};
  runsLoadingSha: string | null = null;
  expandedRunsSha: string | null = null;

  @ViewChild('graphContainer') graphContainer?: ElementRef<HTMLDivElement>;
  private previewCy: Core | null = null;

  constructor(
    private api: ApiService,
    private cdr: ChangeDetectorRef,
    private dialog: DialogService,
  ) {}

  ngOnChanges(ch: SimpleChanges): void {
    if ((ch['open'] || ch['configName']) && this.open && this.configName) {
      this._loadHistory();
    }
    if (ch['currentContent'] && this.viewMode === 'diff' && this.previewContent) {
      this._computeDiff();
    }
  }

  ngAfterViewInit(): void {}

  ngOnDestroy(): void {
    this.previewCy?.destroy();
    this.previewCy = null;
  }

  @HostListener('document:keydown.escape')
  onEsc(): void { if (this.open) this.close.emit(); }

  // ─── Loaders ────────────────────────────────────────────────────
  private _loadHistory(): void {
    if (!this.configName) return;
    this.loadingEntries = true;
    this.loadError = '';
    this.entries = [];
    this.selectedSha = null;
    this.previewContent = '';
    this.diffLines = [];
    this.diffComputed = false;
    this.expandedRunsSha = null;
    this.previewCy?.destroy();
    this.previewCy = null;
    this.cdr.markForCheck();

    this.api.getConfigHistory(this.configName).subscribe({
      next: res => {
        this.entries = res.entries ?? [];
        this.loadingEntries = false;
        this.cdr.markForCheck();
      },
      error: err => {
        this.loadingEntries = false;
        this.loadError = err?.error?.detail ?? err?.message ?? 'Failed to load history';
        this.cdr.markForCheck();
      },
    });
  }

  selectEntry(entry: ConfigHistoryEntry): void {
    if (!this.configName || this.selectedSha === entry.sha) return;
    this.selectedSha = entry.sha;
    this.previewLoading = true;
    this.previewError = '';
    this.previewContent = '';
    this.diffLines = [];
    this.diffComputed = false;
    this.cdr.markForCheck();

    this.api.getConfigAtSha(this.configName, entry.sha).subscribe({
      next: res => {
        // Pretty-print so externally-committed snapshots match auto-saved layout.
        try {
          this.previewContent = JSON.stringify(JSON.parse(res.content), null, 2);
        } catch {
          this.previewContent = res.content;
        }
        this.previewLoading = false;
        this.cdr.markForCheck();
        this._refreshPreviewView();
      },
      error: err => {
        this.previewLoading = false;
        this.previewError = err?.error?.detail ?? err?.message ?? 'Failed to load version';
        this.cdr.markForCheck();
      },
    });
  }

  /** Drop one commit; confirm warns about descendant-SHA rewrites. */
  async deleteEntry(entry: ConfigHistoryEntry, ev: Event): Promise<void> {
    ev.stopPropagation();
    if (!this.configName) return;
    const short = entry.sha.slice(0, 8);
    const ok = await this.dialog.confirm({
      title: `Delete version ${short}`,
      message:
        `This rewrites the git history of this config — any later ` +
        `versions get new SHAs and stop matching runs that pinned to ` +
        `their old SHA. If this is the latest version, the on-disk ` +
        `file will be reverted to the previous one.`,
      okLabel: 'Delete',
      danger: true,
    });
    if (!ok) return;
    this.api.deleteConfigHistoryEntry(this.configName, entry.sha).subscribe({
      next: () => {
        // Descendants got new SHAs; per-sha caches are now stale.
        this.runsBySha = {};
        this.expandedRunsSha = null;
        if (this.selectedSha === entry.sha) {
          this.selectedSha = null;
          this.previewContent = '';
          this.diffLines = [];
          this.diffComputed = false;
          this.previewCy?.destroy();
          this.previewCy = null;
        }
        this._loadHistory();
      },
      error: err => {
        this.dialog.alert({
          title: 'Delete failed',
          variant: 'danger',
          detail: err?.error?.detail ?? err?.message ?? 'Delete failed',
        });
      },
    });
  }

  /** Wipe history for the currently-open config only. The .json file
   * on disk is preserved; only this config's timeline is reset. */
  async clearAllHistory(): Promise<void> {
    if (!this.configName) return;
    const ok = await this.dialog.confirm({
      title: `Clear history for "${this.configName}"`,
      message:
        `This removes every commit touching ${this.configName}.json. ` +
        `The .json file on disk is preserved; only this config's ` +
        `timeline is reset. Other configs' visible history survives ` +
        `(but their commit SHAs may be rewritten, so run sidecars that ` +
        `pinned to old SHAs will stop matching).`,
      okLabel: 'Clear history',
      danger: true,
    });
    if (!ok) return;
    this.api.clearConfigHistory(this.configName).subscribe({
      next: () => {
        this.runsBySha = {};
        this.selectedSha = null;
        this.previewContent = '';
        this.diffLines = [];
        this.diffComputed = false;
        this.previewCy?.destroy();
        this.previewCy = null;
        this._loadHistory();
      },
      error: err => {
        this.dialog.alert({
          title: 'Reset failed',
          variant: 'danger',
          detail: err?.error?.detail ?? err?.message ?? 'Reset failed',
        });
      },
    });
  }

  toggleRunsExpanded(entry: ConfigHistoryEntry, ev: Event): void {
    ev.stopPropagation();
    if (!this.configName) return;
    if (this.expandedRunsSha === entry.sha) {
      this.expandedRunsSha = null;
      this.cdr.markForCheck();
      return;
    }
    this.expandedRunsSha = entry.sha;
    if (this.runsBySha[entry.sha] === undefined) {
      this.runsLoadingSha = entry.sha;
      this.cdr.markForCheck();
      this.api.getRunsForConfigSha(this.configName, entry.sha).subscribe({
        next: res => {
          this.runsBySha[entry.sha] = res.matches ?? [];
          this.runsLoadingSha = null;
          this.cdr.markForCheck();
        },
        error: () => {
          this.runsBySha[entry.sha] = [];
          this.runsLoadingSha = null;
          this.cdr.markForCheck();
        },
      });
    } else {
      this.cdr.markForCheck();
    }
  }

  // ─── View-mode toggle ───────────────────────────────────────────
  setViewMode(mode: 'graph' | 'diff'): void {
    if (this.viewMode === mode) return;
    this.viewMode = mode;
    this._refreshPreviewView();
  }

  /** setTimeout(0) defers past the `@if` mount; queueMicrotask is too early. */
  private _refreshPreviewView(): void {
    if (!this.previewContent) return;
    let parsed: UnifiedConfig | null = null;
    try {
      parsed = JSON.parse(this.previewContent) as UnifiedConfig;
    } catch {
      parsed = null;
    }
    if (this.viewMode === 'graph') {
      if (parsed) {
        const cfg = parsed;
        setTimeout(() => this._renderGraph(cfg), 0);
      }
    } else {
      this._computeDiff();
    }
    this.cdr.markForCheck();
  }

  // ─── Diff computation ───────────────────────────────────────────
  private _computeDiff(): void {
    if (!this.previewContent || this.currentContent == null) {
      this.diffLines = [];
      this.diffComputed = true;
      return;
    }
    this.diffLines = diffLines(this.previewContent, this.currentContent);
    this.diffComputed = true;
    this.cdr.markForCheck();
  }

  // ─── Mini graph rendering ───────────────────────────────────────
  private _renderGraph(cfg: UnifiedConfig): void {
    const el = this.graphContainer?.nativeElement;
    if (!el) {
      // Container vanished between scheduling and firing — bail silently.
      return;
    }
    this.previewCy?.destroy();

    const elements = buildTopologyElements(cfg, this.agentTypes);
    this.previewCy = cytoscape({
      container: el,
      elements,
      style: TOPOLOGY_PREVIEW_STYLES,
      layout: {
        name: 'breadthfirst', directed: true, padding: 24, spacingFactor: 1.1,
        nodeDimensionsIncludeLabels: true,
        // Horizontal-stretch — matches the main canvas LTR layout.
        transform: (_n: any, pos: any) => ({ x: pos.y * 1.4, y: pos.x * 0.75 }),
      } as any,
      // Read-only thumbnail: no drag/zoom/select.
      userZoomingEnabled: false,
      userPanningEnabled: false,
      boxSelectionEnabled: false,
      autoungrabify: true,
      autounselectify: true,
    });
    // Resize+fit on next tick so cytoscape sees the final flex width.
    setTimeout(() => {
      this.previewCy?.resize();
      this.previewCy?.fit(undefined, 16);
    }, 30);
  }

  // ─── Restore ────────────────────────────────────────────────────
  async doRestore(): Promise<void> {
    if (!this.selectedSha || !this.previewContent) return;
    let parsed: UnifiedConfig;
    try {
      parsed = JSON.parse(this.previewContent) as UnifiedConfig;
    } catch {
      this.previewError = 'Refusing to restore: preview content is not valid JSON.';
      this.cdr.markForCheck();
      return;
    }
    const short = this.selectedSha.slice(0, 8);
    const ok = await this.dialog.confirm({
      title: `Restore version ${short}`,
      message:
        `The current working file will be overwritten and committed as a ` +
        `new history entry on next Save.`,
      okLabel: 'Restore',
    });
    if (!ok) return;
    this.restore.emit(parsed);
  }

  // ─── Helpers used by the template ───────────────────────────────
  shortSha(sha: string | null | undefined): string {
    return (sha || '').slice(0, 8);
  }

  formatTs(iso: string): string {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      const pad = (n: number) => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch {
      return iso;
    }
  }

  runsCountLabel(sha: string): string {
    const arr = this.runsBySha[sha];
    if (arr === undefined) return '… runs';
    if (arr.length === 1) return '1 run';
    return `${arr.length} runs`;
  }

  resultsLink(_run: ConfigRunMatch): string[] {
    return ['/results'];
  }

  resultsQuery(run: ConfigRunMatch): Record<string, string> {
    return {
      runId: run.runId,
      ...(run.instanceIds?.[0] ? { instanceId: run.instanceIds[0] } : {}),
    };
  }
}

// ─── Pure helpers (file-local) ────────────────────────────────────

/** LCS-based line diff. O(n·m), fine for ≤ ~3000-line config JSON. */
export function diffLines(a: string, b: string): DiffLine[] {
  const aL = a.split('\n');
  const bL = b.split('\n');
  const n = aL.length, m = bL.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = aL[i] === bL[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out: DiffLine[] = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (aL[i] === bL[j]) { out.push({ type: 'context', line: aL[i] }); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push({ type: 'rm', line: aL[i] }); i++; }
    else { out.push({ type: 'add', line: bL[j] }); j++; }
  }
  while (i < n) { out.push({ type: 'rm', line: aL[i] }); i++; }
  while (j < m) { out.push({ type: 'add', line: bL[j] }); j++; }
  return out;
}

/** Mirror the main canvas's elements (virtual START/END, conditional
 * + back-edge classes) so the preview reads identical, just static. */
function buildTopologyElements(
  cfg: UnifiedConfig, agentTypes: AgentType[],
): ElementDefinition[] {
  const agents = cfg.agents || {};
  const nodeIds = Object.keys(agents);
  const endIds = new Set<string>(
    Array.isArray(cfg.end) ? cfg.end as string[]
    : typeof cfg.end === 'string' ? [cfg.end]
    : [],
  );
  const colors = buildNodeColors(cfg, agentTypes);

  const outDegree: Record<string, number> = {};
  for (const e of cfg.edges || []) outDegree[e.from] = (outDegree[e.from] ?? 0) + 1;
  const back = findBackEdges(cfg);

  const isConditional = (e: { from: string; to: string }) =>
    (agents[e.from] as { class?: string })?.class === 'Router'
    && (outDegree[e.from] ?? 0) >= 2;

  const elements: ElementDefinition[] = [
    { data: { id: '__START__', label: 'START' }, classes: 'virtual-node start-node', selectable: false },
    ...nodeIds.map(id => ({
      data: {
        id, label: id,
        color: colors[id] ?? '#6e7681',
      },
    })),
    { data: { id: '__END__', label: 'END' }, classes: 'virtual-node end-node', selectable: false },
    // Skip dangling edges (defensive — matches main canvas behaviour).
    ...(cfg.edges || [])
      .filter(e => agents[e.from] && agents[e.to])
      .map(e => {
        const id = `${e.from}-${e.to}`;
        const classes: string[] = [];
        if (back.has(id)) classes.push('edge-loopback');
        else if (isConditional(e)) classes.push('edge-conditional');
        const data: Record<string, unknown> = { id, source: e.from, target: e.to };
        if (back.has(id)) data['cpd'] = [70];
        return { data, ...(classes.length ? { classes: classes.join(' ') } : {}) } as ElementDefinition;
      }),
    ...(cfg.entry && agents[cfg.entry]
      ? [{
          data: { id: `__START__-${cfg.entry}`, source: '__START__', target: cfg.entry },
          classes: 'virtual-edge',
        } as ElementDefinition]
      : []),
    ...nodeIds
      .filter(id => endIds.has(id))
      .map(id => ({
        data: { id: `${id}-__END__`, source: id, target: '__END__' },
        classes: 'virtual-edge',
      } as ElementDefinition)),
  ];
  return elements;
}

/** DFS back-edge detection; visits unreachable subgraphs as new roots. */
function findBackEdges(cfg: UnifiedConfig): Set<string> {
  const adj: Record<string, string[]> = {};
  for (const e of cfg.edges || []) (adj[e.from] = adj[e.from] || []).push(e.to);
  const back = new Set<string>();
  const onStack = new Set<string>();
  const visited = new Set<string>();
  const dfs = (node: string): void => {
    visited.add(node);
    onStack.add(node);
    for (const next of (adj[node] || [])) {
      if (onStack.has(next)) back.add(`${node}-${next}`);
      else if (!visited.has(next)) dfs(next);
    }
    onStack.delete(node);
  };
  if (cfg.entry && cfg.agents?.[cfg.entry]) dfs(cfg.entry);
  for (const id of Object.keys(cfg.agents || {})) {
    if (!visited.has(id)) dfs(id);
  }
  return back;
}

/** Preview stylesheet — same edge-type palette as the main canvas. */
const TOPOLOGY_PREVIEW_STYLES: any[] = [
  {
    selector: 'node',
    style: {
      label: 'data(label)',
      'background-color': 'data(color)',
      color: '#0d1117',
      'text-valign': 'center',
      'text-halign': 'center',
      'font-size': 10,
      'font-weight': 'bold',
      width: 'label',
      'padding-left': '10px',
      'padding-right': '10px',
      'padding-top': '6px',
      'padding-bottom': '6px',
      'min-width': 60,
      shape: 'round-rectangle',
      'border-width': 1,
      'border-color': 'transparent',
    } as any,
  },
  {
    selector: 'edge',
    style: {
      width: 1.6,
      'line-color': '#30363d',
      'target-arrow-color': '#30363d',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      'arrow-scale': 1.2,
    } as any,
  },
  {
    selector: 'edge.edge-conditional',
    style: {
      'line-color': '#a371f7',
      'target-arrow-color': '#a371f7',
      'line-style': 'dashed',
      'line-dash-pattern': [6, 4],
      width: 1.8,
    } as any,
  },
  {
    selector: 'edge.edge-loopback',
    style: {
      'line-color': '#e3b341',
      'target-arrow-color': '#e3b341',
      'curve-style': 'unbundled-bezier',
      'control-point-distances': 'data(cpd)' as any,
      'control-point-weights': [0.5],
      width: 1.8,
    } as any,
  },
  {
    selector: 'node.virtual-node',
    style: {
      'background-color': '#21262d',
      color: '#c9d1d9',
      shape: 'round-rectangle',
      'border-width': 1.5,
      'border-color': '#6e7681',
      'border-style': 'dashed',
      label: 'data(label)',
      width: 'label',
      'min-width': 44,
      'padding-left': '8px',
      'padding-right': '8px',
      'padding-top': '4px',
      'padding-bottom': '4px',
      'font-size': 9,
      'font-weight': 'bold',
      'text-valign': 'center',
      'text-halign': 'center',
    } as any,
  },
  {
    selector: 'edge.virtual-edge',
    style: {
      width: 1.2,
      'line-color': '#6e7681',
      'target-arrow-color': '#6e7681',
      'line-style': 'dashed',
    } as any,
  },
];
