import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';
import { AgentBlock, ConfigSummary, OllamaModel, UnifiedConfig } from '../models/types';
import type { SelectOption } from '../components/select/evo-select.component';

/** Single in-RAM history entry: the canonical config plus per-node positions. */
export interface TopologySnapshot {
  config: UnifiedConfig;
  positions: Record<string, { x: number; y: number }>;
}

/** Max snapshots retained per config; older entries fall off the bottom. */
const UNDO_LIMIT = 50;
/** Same-key text edits within this window collapse into one undo step. */
const COALESCE_MS = 800;

/** Recursive JSON serializer with sorted object keys. Used to detect
 * "current matches the on-disk saved state" reliably even when undo /
 * rename rebuilds the `agents` map and shuffles its insertion order;
 * plain JSON.stringify would diverge purely from key reordering. Arrays
 * keep their order — `edges` is order-sensitive in the runtime. */
function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonicalJson).join(',') + ']';
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  return '{' + keys.map(
    k => JSON.stringify(k) + ':' + canonicalJson(obj[k]),
  ).join(',') + '}';
}

/**
 * Single source of truth for the in-memory unified config currently being viewed
 * and edited. Edits to a *loaded* config are persisted through the topology
 * page's Save button (POST /api/configs/loaded with replace=true). Predefined
 * configs are read-only — to keep an edited variant, export it via the brand
 * menu's Export config… and re-import it as a loaded config.
 */
@Injectable({ providedIn: 'root' })
export class TopologyStateService {
  // List of predefined configs available from the backend.
  // Each entry carries both the file `stem` (routing key) and the human `id`
  // (display label, sourced from the JSON's top-level `id` field).
  predefinedConfigs: ConfigSummary[] = [];

  // Currently loaded config (may have unsaved in-memory edits — only writable
  // when the active config came from evomas/config/loaded/).
  currentConfig: UnifiedConfig | null = null;
  // Display name (from currentConfig.name, or filename when opened from disk)
  currentConfigName: string | null = null;

  // Selection state
  selectedAgent: string | null = null;
  selectedEdgeId: string | null = null;

  // Available LLM models (populated from /api/models). Each entry
  // carries a `pulled` flag — pulled-locally entries are listed first
  // by the backend, then unpulled catalog entries. The Inference page
  // runs `ollama pull` for unpulled entries before a run starts.
  availableModels: OllamaModel[] = [];
  // Dropdown options for the inspector's model picker. `value` is the
  // clean `<provider>/<model>` identifier (so `ngModel` round-trips
  // cleanly), `label` may carry a `· pull` suffix to flag unpulled
  // catalog entries. Built by `syncModelOptions()` so the list reflects
  // both the locally-pulled set AND any model the active block already
  // references (even if it's been removed from the registry catalog
  // mid-session).
  modelSelectOptions: SelectOption[] = [];

  // UI flags
  addEdgeMode = false;

  /** True when the active config has in-memory edits that haven't been
   * written to disk. Derived: `recomputeDirty()` compares the current
   * canonical-serialized config against `savedConfigSerialized` (the
   * baseline captured on load / save). So undoing back to disk state
   * clears this automatically and the "unsaved" toolbar chip goes away.
   * Drives the "unsaved" toolbar chip. */
  dirty = false;

  /** Canonical serialization of the last `setCurrentConfig` / `markSaved`
   * baseline. `null` when no config is loaded. Used by `recomputeDirty`
   * to decide whether the current in-memory config has diverged from disk. */
  private savedConfigSerialized: string | null = null;

  /** True when the active config has been validated since the last edit.
   * Fresh-loaded configs default to `validated: true` (the user hasn't
   * touched anything yet). Every site that calls `markDirty()` also
   * flips this to `false`; the Validate toolbar button flips it back to
   * `true` whether or not findings were surfaced — the user has at
   * least acknowledged the diagnostics. Save is disabled while this is
   * `false` so the user can't ship un-inspected edits. */
  validated = true;

  // Persisted node positions per config name
  nodePositions: Record<string, Record<string, { x: number; y: number }>> = {};

  // Persisted dropdown selection for each palette chip (one entry per
  // canonical AGENT_TYPE). Survives navigation away from the page. Empty
  // map = every chip defaults to the EvoMas built-in (first variant).
  selectedVariantByType: Record<string, string> = {};

  // ─── Undo / redo history (in-RAM, per-config) ─────────────────
  // Keyed by config name so switching between configs preserves each
  // graph's edit timeline. Cleared explicitly on reloadGraph and
  // onHistoryRestore (those replace the canvas wholesale); ordinary
  // navigation between configs leaves the stacks untouched.
  private undoStacks: Record<string, TopologySnapshot[]> = {};
  private redoStacks: Record<string, TopologySnapshot[]> = {};
  // Coalesce tracker for streaming edits (text inputs, sliders): consecutive
  // pushes with the same key inside COALESCE_MS collapse into one snapshot
  // so a single field's typing doesn't fill the undo stack.
  private lastCoalesce: Record<string, { key: string; time: number }> = {};

  /** Push a snapshot onto the undo stack. When `coalesceKey` is set and
   * matches the previous push within COALESCE_MS, the new push is dropped
   * (the older snapshot remains the undo target for the whole burst). Any
   * push — coalesced or not — clears the redo stack. */
  pushUndo(name: string, snap: TopologySnapshot, coalesceKey?: string): void {
    if (!name) return;
    const stack = (this.undoStacks[name] ??= []);
    if (coalesceKey != null) {
      const now = Date.now();
      const last = this.lastCoalesce[name];
      if (last && last.key === coalesceKey && now - last.time < COALESCE_MS) {
        // Refresh the timestamp so the run keeps coalescing while typing.
        last.time = now;
        // Still clear redo — the user has diverged from the redo path.
        this.redoStacks[name] = [];
        return;
      }
      this.lastCoalesce[name] = { key: coalesceKey, time: now };
    } else {
      delete this.lastCoalesce[name];
    }
    stack.push(snap);
    if (stack.length > UNDO_LIMIT) stack.shift();
    this.redoStacks[name] = [];
  }

  popUndo(name: string): TopologySnapshot | undefined {
    delete this.lastCoalesce[name];
    return this.undoStacks[name]?.pop();
  }

  /** Push onto undo WITHOUT clearing the redo stack. Used by `redo()`
   * to record the pre-redo state so a follow-up undo can roll back —
   * the regular `pushUndo` invalidates redo (correct for fresh user
   * mutations, wrong here because we're navigating, not branching). */
  pushUndoPreserveRedo(name: string, snap: TopologySnapshot): void {
    if (!name) return;
    const stack = (this.undoStacks[name] ??= []);
    delete this.lastCoalesce[name];
    stack.push(snap);
    if (stack.length > UNDO_LIMIT) stack.shift();
  }

  pushRedo(name: string, snap: TopologySnapshot): void {
    if (!name) return;
    (this.redoStacks[name] ??= []).push(snap);
  }

  popRedo(name: string): TopologySnapshot | undefined {
    delete this.lastCoalesce[name];
    return this.redoStacks[name]?.pop();
  }

  canUndo(name: string | null): boolean {
    return !!name && (this.undoStacks[name]?.length ?? 0) > 0;
  }

  canRedo(name: string | null): boolean {
    return !!name && (this.redoStacks[name]?.length ?? 0) > 0;
  }

  /** Drop both stacks for a config — called when the canvas is replaced
   * wholesale (reloadGraph, onHistoryRestore) so undo can't roll back to
   * a state that no longer matches what's on screen. */
  clearHistory(name: string | null): void {
    if (!name) return;
    delete this.undoStacks[name];
    delete this.redoStacks[name];
    delete this.lastCoalesce[name];
  }

  // Notifies subscribers when currentConfig is replaced (e.g. by Open file).
  readonly configChanged = new Subject<UnifiedConfig | null>();

  setCurrentConfig(config: UnifiedConfig | null, displayName: string | null): void {
    // Defensive normalization: load is now permissive (no required-key
    // gate), so any of these may be missing. Defaulting here lets
    // renderConfig walk the shape without needing per-field guards.
    if (config) {
      if (config.agents == null) config.agents = {};
      if (config.edges == null) config.edges = [];
      if (config.entry == null) config.entry = '';
      if (config.end == null) config.end = [];
    }
    this.currentConfig = config;
    this.currentConfigName = displayName;
    this.selectedAgent = null;
    this.selectedEdgeId = null;
    // Fresh load IS the saved baseline — anchor the dirty check here so
    // undoing back to this state clears the chip.
    this.savedConfigSerialized = config ? canonicalJson(config) : null;
    this.dirty = false;
    // Fresh-loaded config starts validated — Save is enabled until the
    // user touches anything, mirroring the "no unsaved edits" baseline.
    this.validated = true;
    this.configChanged.next(config);
  }

  /** Re-anchor the dirty baseline to the current in-memory config. Called
   * by the topology page after a successful Save so subsequent edits
   * compare against the freshly-written file. */
  markSaved(): void {
    this.savedConfigSerialized = this.currentConfig
      ? canonicalJson(this.currentConfig)
      : null;
    this.dirty = false;
    this.validated = true;
  }

  /** Compare the current config against the saved baseline and flip
   * `dirty` / `validated` to match. Called from every mutation site
   * (including undo / redo) so the chip reflects the actual delta. */
  recomputeDirty(): void {
    if (!this.currentConfig) {
      this.dirty = false;
      return;
    }
    const wasDirty = this.dirty;
    const cur = canonicalJson(this.currentConfig);
    this.dirty = cur !== this.savedConfigSerialized;
    if (this.dirty) {
      // Diverged — the user owes us a Validate click before Save.
      this.validated = false;
    } else if (wasDirty) {
      // Just returned to the saved baseline (likely via undo). The file
      // on disk was implicitly validated when it was written, so reset
      // the flag too — otherwise the toolbar would still flag the
      // "unvalidated" chip after a clean undo.
      this.validated = true;
    }
  }

  /** Block for the currently selected agent, or null. */
  selectedAgentBlock(): AgentBlock | null {
    if (!this.currentConfig || !this.selectedAgent) return null;
    return this.currentConfig.agents[this.selectedAgent] ?? null;
  }
}
