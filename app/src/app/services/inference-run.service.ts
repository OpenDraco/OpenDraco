import { Injectable } from '@angular/core';
import { Subject, Subscription, timer } from 'rxjs';
import { ApiService } from './api.service';
import { AgentType, InferenceEvent, AGENT_COLORS, AGENT_LABELS, HandoffChip, UnifiedConfig } from '../models/types';

/** Per-node colour map from agent config + `/api/agent-types`. Shared
 * by the live Inference page and the Results-page modal so the card
 * palette is identical across renderers. */
export function buildNodeColors(
  cfg: Pick<UnifiedConfig, 'agents'>,
  agentTypes: AgentType[],
): Record<string, string> {
  // Two lookups: the JSON's `class` field can be the AGENT_TYPE label
  // ("Locator") or the Python class name ("LocatorAgent").
  const byClass: Record<string, string> = {};
  const byType:  Record<string, string> = {};
  for (const t of agentTypes) {
    byClass[t.class] = t.color;
    byType[t.type]   = t.color;
  }
  const aliasToType: Record<string, string> = { LLMToolAgent: 'Base agent' };
  const out: Record<string, string> = {};
  for (const [node, block] of Object.entries(cfg.agents ?? {})) {
    const cls = (block as { class?: string })?.class ?? '';
    const color = byClass[cls]
               ?? byType[cls]
               ?? byType[aliasToType[cls] ?? '']
               ?? '';
    if (color) out[node] = color;
  }
  return out;
}

const LOG_POLL_INTERVAL_MS = 1500;

export interface ToolCallEntry {
  tool: string;
  argsPreview: string;
  resultPreview: string;
}

export interface AgentTokenUsage {
  input: number;
  output: number;
  total: number;
}

export interface AgentCard {
  agent: string;
  label: string;
  color: string;
  status: 'running' | 'done' | 'error';
  delta: Record<string, unknown>;
  expanded: boolean;
  thinkingStream: string;
  responseStream: string;
  toolCalls: ToolCallEntry[];
  inputs: Record<string, unknown>;
  tokens: AgentTokenUsage | null;
  /** Chips that triggered THIS card iteration (drained from the
   * run-level pending queue at spawn time). One chip → one card. */
  incomingChips: HandoffChip[];
  startedAt?: number;
  durationMs?: number;
}

/** Per-instance buffer so the user can switch between instances in a
 * multi-instance run without losing each one's execution log. */
export interface RunInstance {
  instance_id: string;
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled';
  cards: AgentCard[];
  finalPatch: string;
  outputPath: string;
  runId: string;
  errorMsg: string;
  errorTraceback: string;
  /** Hand-off chips waiting for their target's next card to spawn.
   * Drained at `_spawnCard` so each chip lands on exactly one card. */
  pendingIncomingByTarget: Record<string, HandoffChip[]>;
}

export type RunStatus = 'idle' | 'running' | 'done' | 'cancelled' | 'error';

function newCard(agent: string, nodeColors: Record<string, string>): AgentCard {
  return {
    agent,
    label: AGENT_LABELS[agent] ?? agent,
    // Per-run config-driven map wins; legacy node-id palette is the fallback.
    color: nodeColors[agent] ?? AGENT_COLORS[agent] ?? '#888',
    status: 'running',
    delta: {},
    expanded: true,
    thinkingStream: '',
    responseStream: '',
    toolCalls: [],
    inputs: {},
    tokens: null,
    incomingChips: [],
    startedAt: Date.now(),
  };
}

/** Fresh RunInstance — shared by the live service and the NDJSON replay. */
export function newRunInstance(
  instanceId: string,
  status: RunInstance['status'] = 'queued',
  runId = '',
): RunInstance {
  return {
    instance_id: instanceId,
    status,
    cards: [],
    finalPatch: '',
    outputPath: '',
    runId,
    errorMsg: '',
    errorTraceback: '',
    pendingIncomingByTarget: {},
  };
}

/** Most-recent still-running card for `agent`. */
function _openCard(inst: RunInstance, agent: string): AgentCard | null {
  for (let i = inst.cards.length - 1; i >= 0; i--) {
    if (inst.cards[i].agent === agent && inst.cards[i].status === 'running') {
      return inst.cards[i];
    }
  }
  return null;
}

/** Append a new card; labels 2nd+ visits with "(retry N)". Drains
 * pending hand-off chips for this agent onto the new card. */
function _spawnCard(
  inst: RunInstance,
  agent: string,
  nodeColors: Record<string, string>,
): AgentCard {
  const previous = inst.cards.filter(c => c.agent === agent).length;
  const card = newCard(agent, nodeColors);
  if (previous > 0) card.label = `${card.label} (retry ${previous + 1})`;
  const pending = inst.pendingIncomingByTarget[agent];
  if (pending && pending.length > 0) {
    card.incomingChips = pending;
    inst.pendingIncomingByTarget[agent] = [];
  }
  inst.cards.push(card);
  return card;
}

/** Pure reducer: SSE/NDJSON event → RunInstance mutation. Per-instance
 * mutations only; run-level status stays in `InferenceRunService`. */
export function applyEventToInstance(
  inst: RunInstance,
  ev: InferenceEvent,
  nodeColors: Record<string, string> = {},
): void {
  switch (ev.type) {
    case 'instance_start':
      inst.status = 'running';
      inst.cards = [];
      inst.pendingIncomingByTarget = {};
      break;

    case 'instance_done':
      inst.status = 'done';
      if (ev.output_path) inst.outputPath = ev.output_path;
      if (ev.run_id) inst.runId = ev.run_id;
      if (ev.patch) inst.finalPatch = ev.patch;
      break;

    case 'agent_event': {
      const agent = ev.agent ?? 'unknown';
      const open = _openCard(inst, agent);
      const card = open ?? _spawnCard(inst, agent, nodeColors);
      card.delta = open ? { ...card.delta, ...(ev.delta ?? {}) } : (ev.delta ?? {});
      card.status = 'done';
      if (card.startedAt != null && card.durationMs == null) {
        card.durationMs = Date.now() - card.startedAt;
      }
      break;
    }

    case 'handoff': {
      const target = ev.to ?? '';
      if (!target) break;
      const chip: HandoffChip = {
        from: ev.from ?? 'unknown',
        to: target,
        summary: ev.summary ?? '',
        preview: ev.preview ?? '',
        keys: ev.keys ?? [],
        timestamp: ev.timestamp ?? '',
      };
      // Queue until the target's next card spawns and drains it.
      (inst.pendingIncomingByTarget[target] ||= []).push(chip);
      break;
    }

    case 'thinking_chunk': {
      const agent = ev.agent ?? 'unknown';
      const open = _openCard(inst, agent);
      const card = open ?? _spawnCard(inst, agent, nodeColors);
      card.thinkingStream += ev.chunk ?? '';
      break;
    }

    case 'response': {
      const agent = ev.agent ?? 'unknown';
      const open = _openCard(inst, agent);
      const card = open ?? _spawnCard(inst, agent, nodeColors);
      const text = ev.content ?? '';
      if (text) {
        card.responseStream = card.responseStream
          ? card.responseStream + '\n\n─────\n\n' + text
          : text;
      }
      break;
    }

    case 'agent_input': {
      const agent = ev.agent ?? 'unknown';
      const open = _openCard(inst, agent);
      const card = open ?? _spawnCard(inst, agent, nodeColors);
      card.inputs = (ev.inputs as Record<string, unknown>) ?? {};
      break;
    }

    case 'agent_tokens': {
      const agent = ev.agent ?? 'unknown';
      for (const card of inst.cards) {
        if (card.agent === agent) {
          card.tokens = {
            input:  Number(ev['input']  ?? 0),
            output: Number(ev['output'] ?? 0),
            total:  Number(ev['total']  ?? 0),
          };
        }
      }
      break;
    }

    case 'tool_call': {
      const agent = ev.agent ?? 'unknown';
      const open = _openCard(inst, agent);
      const card = open ?? _spawnCard(inst, agent, nodeColors);
      card.toolCalls.push({
        tool: ev.tool ?? '',
        argsPreview: ev.args_preview ?? '',
        resultPreview: ev.result_preview ?? '',
      });
      break;
    }

    case 'error':
      inst.errorMsg = ev.message ?? '';
      inst.errorTraceback = ev.traceback ?? '';
      break;

    // status / start / done / cancelled / run_id are service-level only
    // (no per-instance mutation). run_id targets multiple instances at
    // the service layer; the static parser doesn't need it because the
    // NDJSON's `instance_done` carries the final runId.
  }
}

/** Replay a completed run's NDJSON event log into a snapshot RunInstance.
 *
 * Multi-instance batches: if `instanceId` is non-empty, only events that
 * are scoped to that instance (`ev.instance_id === instanceId`) OR that
 * are instance-unscoped (`thinking_chunk` / `tool_call` etc., which the
 * worker emits between `instance_start`/`instance_done` for the active
 * one) are applied.
 *
 * Falls back to `status='done'` if the file never emitted an
 * `instance_start` — older runs predating that event still produce a
 * usable card view. */
export function parseNdjsonToRunInstance(
  raw: string,
  instanceId: string,
  nodeColors: Record<string, string> = {},
): RunInstance {
  const inst = newRunInstance(instanceId);
  let activeInstanceId = '';
  let sawInstanceStart = false;

  for (const line of raw.split('\n')) {
    const t = line.trim();
    if (!t) continue;
    let ev: InferenceEvent;
    try { ev = JSON.parse(t) as InferenceEvent; } catch { continue; }

    // `instance_start`/`instance_done` scope unscoped events between them.
    if (ev.type === 'instance_start' && ev.instance_id) {
      activeInstanceId = ev.instance_id;
      sawInstanceStart = true;
    }

    if (instanceId) {
      if (ev.instance_id && ev.instance_id !== instanceId) {
        if (ev.type === 'instance_done' && ev.instance_id === activeInstanceId) {
          activeInstanceId = '';
        }
        continue;
      }
      // Unscoped event: apply only if the active scope is our target.
      if (!ev.instance_id && activeInstanceId && activeInstanceId !== instanceId) {
        continue;
      }
    }

    applyEventToInstance(inst, ev, nodeColors);

    if (ev.type === 'instance_done' && ev.instance_id) {
      activeInstanceId = '';
    }
  }

  // Completed runs without an instance_start still belong on 'done'.
  if (!sawInstanceStart && inst.status === 'queued') {
    inst.status = 'done';
  }
  // Strip the live-path `durationMs` that the reducer wrote using
  // parse-time wall clock — those numbers reflect the millis between
  // spawn and event-reduce, NOT the original run. Callers overlay
  // log-derived timings via `applyAgentTimingsToInstance` instead.
  for (const card of inst.cards) {
    card.durationMs = undefined;
    card.startedAt = undefined;
  }
  return inst;
}

/** Extract per-agent execution time (ms) from a prediction's `.log` text.
 *
 * The runner writes lines shaped like
 *   `YYYY-MM-DD HH:MM:SS,mmm - INFO - [agent] ...`
 * and sub-tag variants like `[agent|think]` or `[agent|tool]`. The
 * agent's TOTAL time is taken as (last timestamp − first timestamp) of
 * every line whose `[agent...]` prefix matches that agent — sub-tags
 * are folded into the parent agent so `[locator|think]` counts toward
 * `locator`.
 *
 * Returns `agent → durationMs`. Agents that only emit one line get 0.
 */
export function parseAgentTimingsFromLog(raw: string): Map<string, number> {
  // ISO-ish line head: `2026-05-14 22:24:01,881 - INFO - [agent...]`.
  // Capture group 1 = timestamp; group 2 = agent identifier (before any
  // `|` sub-tag or `]`).
  const RE = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - \w+ - \[([^\]|]+)/;
  const first = new Map<string, number>();
  const last  = new Map<string, number>();
  for (const line of raw.split('\n')) {
    const m = line.match(RE);
    if (!m) continue;
    const t = parseLogTimestamp(m[1]);
    if (t == null) continue;
    const agent = m[2].trim();
    if (!agent) continue;
    if (!first.has(agent) || t < (first.get(agent) ?? Infinity)) first.set(agent, t);
    if (!last.has(agent)  || t > (last.get(agent)  ?? -Infinity)) last.set(agent, t);
  }
  const out = new Map<string, number>();
  for (const [a, start] of first) {
    out.set(a, Math.max(0, (last.get(a) ?? start) - start));
  }
  return out;
}

/** `2026-05-14 22:24:01,881` → epoch ms. Parses as **local time** since
 * the runner uses the host clock. Returns `null` on malformed input. */
function parseLogTimestamp(s: string): number | null {
  // `Date.parse` accepts `YYYY-MM-DDTHH:MM:SS.mmm` reliably across
  // browsers; the runner writes `YYYY-MM-DD HH:MM:SS,mmm`.
  const iso = s.replace(' ', 'T').replace(',', '.');
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : null;
}

/** Overwrite each `AgentCard.durationMs` with the matching entry from
 * `timings`. Cards for the same agent across retries get the same
 * aggregate value — the `.log` file doesn't split iteration boundaries
 * reliably, so showing the total on every card is the accurate read. */
export function applyAgentTimingsToInstance(
  inst: RunInstance,
  timings: Map<string, number>,
): void {
  for (const card of inst.cards) {
    const d = timings.get(card.agent);
    if (d != null) card.durationMs = d;
  }
}

/** Human-friendly duration: `420ms` / `5.4s` / `1m 12s` / `1h 03m`. */
export function formatDurationMs(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)}s`;
  const totalSec = Math.round(s);
  const m = Math.floor(totalSec / 60);
  const r = totalSec % 60;
  if (m < 60) return `${m}m ${String(r).padStart(2, '0')}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${String(m % 60).padStart(2, '0')}m`;
}

/** Single-run inference. One run at a time; overlapping `run()` calls
 * are ignored until cancel or completion. */
@Injectable({ providedIn: 'root' })
export class InferenceRunService {
  status: RunStatus = 'idle';
  config: string | UnifiedConfig = '';
  configLabel = '';
  startedAt = 0;
  instances: RunInstance[] = [];
  selectedInstanceId: string | null = null;
  errorMsg = '';
  statusMsg = '';

  /** Preflight `ollama pull` progress per model — drives the inference
   * page's preflight panel. `code === 0` is success. */
  pullingModels: Array<{
    model: string;
    lastLine: string;
    done: boolean;
    code?: number;
  }> = [];

  /** Per-run node → hex colour map (built by `buildNodeColors`). */
  nodeColors: Record<string, string> = {};

  readonly changed = new Subject<void>();
  private sub?: Subscription;

  // Resume-from-log state for mid-run page reloads.
  private logPath: string | null = null;
  private logOffset = 0;
  private pollSub?: Subscription;
  private logBuffer = '';

  constructor(private api: ApiService) {
    this.attach();
  }

  // ─── Selection / convenience getters ──────────────────────────
  get running(): boolean { return this.status === 'running'; }
  get cancelled(): boolean { return this.status === 'cancelled'; }

  get currentInstance(): RunInstance | null {
    return this.instances.find(i => i.instance_id === this.selectedInstanceId)
        ?? this.instances.find(i => i.status === 'running')
        ?? this.instances[0]
        ?? null;
  }

  get cards(): AgentCard[] { return this.currentInstance?.cards ?? []; }
  get finalPatch(): string { return this.currentInstance?.finalPatch ?? ''; }
  get outputPath(): string { return this.currentInstance?.outputPath ?? ''; }
  get errorTraceback(): string { return this.currentInstance?.errorTraceback ?? ''; }
  get progress(): RunInstance[] { return this.instances; }

  selectInstance(id: string): void {
    this.selectedInstanceId = id;
    this.notify();
  }

  clear(): void {
    if (this.status === 'running') return;
    this.status = 'idle';
    this.instances = [];
    this.selectedInstanceId = null;
    this.errorMsg = '';
    this.statusMsg = '';
    this.pullingModels = [];
    this.notify();
  }

  // ─── Live-stream lifecycle (attach on inference page enter, ──
  //                              detach on leave) ──────────────────
  /** Sync to the backend's `_active_run` and start log-polling. No-op
   * when an SSE stream for the same run is already attached. */
  attach(): void {
    if (this.sub && this.status === 'running') return;
    this.api.getActiveInference().subscribe({
      next: snap => {
        if (!snap.active || !snap.log_path || !snap.instance_ids) return;
        const sameRun =
          !!snap.run_id &&
          this.instances.length > 0 &&
          this.instances[0]?.runId === snap.run_id;
        if (!sameRun) {
          this.config = snap.config_label ?? '';
          this.configLabel = snap.config_label ?? '(active)';
          this.startedAt = snap.started_at ?? Date.now();
          this.errorMsg = '';
          this.status = 'running';
          this.instances = snap.instance_ids.map(id =>
            newRunInstance(id, 'queued', snap.run_id ?? ''),
          );
          this.selectedInstanceId = snap.instance_ids[0] ?? null;
          this.statusMsg = `Reattaching to run ${snap.run_id ?? ''}…`;
          this.logOffset = 0;
          this.logBuffer = '';
        }
        this.logPath = snap.log_path;
        this.notify();
        this.startLogPolling();
      },
      error: () => { /* server unreachable; nothing to resume */ },
    });
  }

  /** Stop SSE + polling without dropping instance state. */
  detach(): void {
    this.sub?.unsubscribe();
    this.sub = undefined;
    this.stopLogPolling();
  }

  private startLogPolling(): void {
    this.stopLogPolling();
    if (!this.logPath) return;
    this.pollSub = timer(0, LOG_POLL_INTERVAL_MS).subscribe(() => this.pollLog());
  }

  private stopLogPolling(): void {
    this.pollSub?.unsubscribe();
    this.pollSub = undefined;
  }

  private pollLog(): void {
    if (!this.logPath) { this.stopLogPolling(); return; }
    this.api.getInferenceLogTail(this.logPath, this.logOffset).subscribe({
      next: chunk => {
        this.logOffset = chunk.offset;
        // Buffer + newline split so partial-line tails don't break JSON.parse.
        this.logBuffer += chunk.raw;
        const lines = this.logBuffer.split('\n');
        this.logBuffer = lines.pop() ?? '';
        for (const line of lines) {
          const t = line.trim();
          if (!t) continue;
          try { this.handleEvent(JSON.parse(t) as InferenceEvent); } catch { /* skip malformed */ }
        }
        if (!chunk.is_running) {
          if (this.logBuffer.trim()) {
            try { this.handleEvent(JSON.parse(this.logBuffer.trim()) as InferenceEvent); } catch {}
            this.logBuffer = '';
          }
          if (this.status === 'running') this.status = 'done';
          this.logPath = null;
          this.stopLogPolling();
        }
        this.notify();
      },
      error: () => { /* transient — keep polling */ },
    });
  }

  // ─── Run / cancel ─────────────────────────────────────────────
  run(instanceIds: string | string[], config: string | UnifiedConfig): void {
    if (this.status === 'running') return;
    const ids = Array.isArray(instanceIds) ? instanceIds : [instanceIds];
    if (ids.length === 0) return;

    this.config = config;
    this.configLabel = typeof config === 'string'
      ? (config || '(unsaved)')
      : (config.id || '(session)');
    this.status = 'running';
    this.startedAt = Date.now();
    this.errorMsg = '';
    this.instances = ids.map(id => newRunInstance(id));
    this.selectedInstanceId = ids[0] ?? null;
    this.pullingModels = [];
    this.statusMsg = `Running ${this.configLabel} (${ids.length} instance${ids.length > 1 ? 's' : ''})`;
    this.notify();

    this.sub = this.api.streamInference(ids, config).subscribe({
      next: ev => { this.handleEvent(ev); this.notify(); },
      error: err => {
        this.status = 'error';
        this.errorMsg = err?.message ?? 'Connection error';
        this.notify();
      },
      complete: () => {
        if (this.status === 'running') this.status = 'done';
        this.notify();
      },
    });
  }

  cancel(): void {
    if (this.status !== 'running') return;
    this.sub?.unsubscribe();
    for (const inst of this.instances) {
      if (inst.status === 'queued' || inst.status === 'running') {
        inst.status = 'cancelled';
        this.api.cancelInference(inst.instance_id).subscribe();
      }
    }
    this.status = 'cancelled';
    this.statusMsg = 'Cancelled by user';
    this.notify();
  }

  // ─── Stream handler ───────────────────────────────────────────
  private getInstance(id: string | undefined | null): RunInstance | null {
    if (!id) return null;
    return this.instances.find(i => i.instance_id === id) ?? null;
  }

  private runningInst(): RunInstance | null {
    return this.instances.find(i => i.status === 'running') ?? null;
  }

  /** Service-level mutations stay here; per-instance mutations delegate. */
  private handleEvent(ev: InferenceEvent): void {
    switch (ev.type) {
      case 'status':
        this.statusMsg = ev.message ?? '';
        break;

      // Preflight `ollama pull` → preflight panel + status-bar line.
      case 'preflight_pull_start': {
        if (ev.model) {
          const existing = this.pullingModels.find(p => p.model === ev.model);
          if (existing) {
            existing.lastLine = '';
            existing.done = false;
            existing.code = undefined;
          } else {
            this.pullingModels = [
              ...this.pullingModels,
              { model: ev.model, lastLine: '', done: false },
            ];
          }
          this.statusMsg = `Pulling ${ev.model}…`;
        }
        break;
      }
      case 'preflight_log': {
        if (ev.model && ev.line) {
          // Strip ANSI cursor controls that Ollama embeds in progress lines.
          const clean = ev.line.replace(/\x1B\[[0-9;?]*[A-Za-z]/g, '').trim();
          if (clean) {
            const entry = this.pullingModels.find(p => p.model === ev.model);
            if (entry) entry.lastLine = clean;
            this.statusMsg = `${ev.model}: ${clean}`;
          }
        }
        break;
      }
      case 'preflight_pull_done': {
        if (ev.model) {
          const entry = this.pullingModels.find(p => p.model === ev.model);
          if (entry) {
            entry.done = true;
            entry.code = ev.code ?? 0;
          }
          this.statusMsg = (ev.code ?? 0) === 0
            ? `Pulled ${ev.model}.`
            : `Failed to pull ${ev.model} (exit ${ev.code}).`;
        }
        break;
      }

      case 'instance_start': {
        const inst = this.getInstance(ev.instance_id);
        if (inst) {
          applyEventToInstance(inst, ev, this.nodeColors);
          // Auto-focus unless the user has already clicked into another instance.
          if (!this.selectedInstanceId || this.selectedInstanceId === inst.instance_id) {
            this.selectedInstanceId = inst.instance_id;
          }
        }
        this.statusMsg = `Starting ${ev.instance_id} (${(ev.index ?? 0) + 1}/${ev.total ?? 1})`;
        break;
      }

      case 'instance_done': {
        const inst = this.getInstance(ev.instance_id);
        if (inst) applyEventToInstance(inst, ev, this.nodeColors);
        this.statusMsg = `Finished ${ev.instance_id} (${(ev.index ?? 0) + 1}/${ev.total ?? 1})`;
        break;
      }

      case 'start':
        this.statusMsg = `Running ${ev.config} on ${ev.instance_id}…`;
        break;

      case 'agent_event':
      case 'handoff':
      case 'thinking_chunk':
      case 'response':
      case 'agent_input':
      case 'agent_tokens':
      case 'tool_call': {
        const inst = this.runningInst();
        if (!inst) return;
        applyEventToInstance(inst, ev, this.nodeColors);
        break;
      }

      case 'run_id': {
        if (!ev.run_id) break;
        // Cross-instance fan-out — sets run_id on every queued/running card.
        for (const inst of this.instances) {
          if (inst.status === 'queued' || inst.status === 'running') {
            inst.runId = String(ev.run_id);
            if (ev.output_path) inst.outputPath = String(ev.output_path);
          }
        }
        break;
      }

      case 'done':
        this.status = 'done';
        this.statusMsg = `Run complete (${this.instances.length} instance${this.instances.length > 1 ? 's' : ''})`;
        break;

      case 'error': {
        this.status = 'error';
        this.errorMsg = ev.message ?? 'Unknown error';
        const inst = this.runningInst() ?? this.getInstance(this.selectedInstanceId);
        if (inst) applyEventToInstance(inst, ev, this.nodeColors);
        break;
      }

      case 'cancelled':
        this.status = 'cancelled';
        this.statusMsg = 'Cancelled by user';
        break;
    }
  }

  private notify(): void { this.changed.next(); }
}
