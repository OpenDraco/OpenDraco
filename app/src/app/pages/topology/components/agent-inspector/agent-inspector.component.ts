/** Right-rail editor for the currently-selected agent node. Surfaces three
 * collapsible sections (Parameters, Prompts, Tools) plus a per-section
 * "Reset to defaults" pill.
 *
 * Pure presentation -- all mutation goes through @Output intents and the
 * parent applies it to the shared TopologyStateService. The inspector keeps
 * its own copy of `paramsOpen / toolsOpen / promptsOpen` so toggle UX is
 * snappy without round-tripping every click through the parent. */
import {
  ChangeDetectionStrategy, Component, EventEmitter, Input, Output,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NgIcon, provideIcons } from '@ng-icons/core';

import { ICON } from '../../../../icons';
import {
  AgentBlock, AgentTool, AgentType, ToolDescriptor,
} from '../../../../models/types';
import {
  EvoBoxComponent, EvoSelectComponent, EvoSliderComponent,
  EvoSpinboxComponent, EvoSwitchComponent, EvoHelpPopoverComponent,
} from '../../../../components/index';
import {
  SelectOption, SelectOptionGroup,
} from '../../../../components/select/evo-select.component';

/** Local model-status colors; matches the parent's `currentModelStatus` getter. */
export type ModelStatus = 'pulled' | 'unpulled' | 'custom';

@Component({
  selector: 'app-agent-inspector',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    EvoBoxComponent, EvoSelectComponent, EvoSliderComponent,
    EvoSpinboxComponent, EvoSwitchComponent, EvoHelpPopoverComponent,
    NgIcon,
  ],
  providers: [provideIcons(ICON)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './agent-inspector.component.html',
  styleUrl: './agent-inspector.component.css',
})
export class AgentInspectorComponent {
  // ── Selection / block ───────────────────────────────────────────
  @Input() selectedAgent: string | null = null;
  @Input() agentBlock: AgentBlock | null = null;
  @Input() agentBadgeColor = '#888';
  @Input() agentBadgeLabel = '';

  // ── Catalogues ──────────────────────────────────────────────────
  @Input() availableTools: ToolDescriptor[] = [];
  @Input() currentAgentType: AgentType | null = null;

  // ── Model picker ────────────────────────────────────────────────
  @Input() modelSelectOptions: SelectOption[] = [];
  @Input() modelFilter = '';
  @Input() currentModelStatus: ModelStatus = 'custom';

  // ── Tools editor (pre-computed slices from the parent) ──────────
  @Input() currentTools: AgentTool[] = [];
  @Input() unusedToolOptionGroups: SelectOptionGroup[] = [];
  @Input() unusedToolNamesCount = 0;
  @Input() toolParamsDraft: Record<number, string> = {};
  @Input() toolParamsError: Record<number, string> = {};

  // ── Page-level state ────────────────────────────────────────────
  @Input() isLoadedConfig = false;

  // ── Inspector-local toggles ─────────────────────────────────────
  @Input() paramsOpen = false;
  @Input() toolsOpen = false;
  @Input() promptsOpen = false;
  /** '' = collapsed, otherwise the visible slot key. */
  @Input() promptTab: 'system' | 'user' | 'proxy' | '' = '';

  // ── Outputs ─────────────────────────────────────────────────────
  /** Generic field setter — `key` is one of AgentBlock's keys. */
  @Output() agentFieldChange = new EventEmitter<{ key: keyof AgentBlock; value: unknown }>();
  @Output() modelFilterChange = new EventEmitter<string>();

  @Output() addTool          = new EventEmitter<string>();
  @Output() removeTool       = new EventEmitter<number>();
  @Output() toolParamsInput  = new EventEmitter<{ idx: number; value: string }>();

  @Output() promptChange = new EventEmitter<{ slot: 'system' | 'user' | 'proxy'; value: string }>();
  @Output() togglePromptTabIntent = new EventEmitter<'system' | 'user' | 'proxy'>();

  @Output() resetParams  = new EventEmitter<void>();
  @Output() resetTools   = new EventEmitter<void>();
  @Output() resetPrompts = new EventEmitter<void>();

  @Output() paramsOpenChange  = new EventEmitter<boolean>();
  @Output() toolsOpenChange   = new EventEmitter<boolean>();
  @Output() promptsOpenChange = new EventEmitter<boolean>();

  // ── Empty-sentinel option for the Add-a-tool dropdown ──────────
  readonly emptyToolOption: SelectOption[] = [{ value: '', label: '(empty)' }];

  // ── Section toggle helpers ─────────────────────────────────────
  toggleParams(): void  { this.paramsOpen  = !this.paramsOpen;  this.paramsOpenChange.emit(this.paramsOpen); }
  toggleTools(): void   { this.toolsOpen   = !this.toolsOpen;   this.toolsOpenChange.emit(this.toolsOpen); }
  togglePrompts(): void { this.promptsOpen = !this.promptsOpen; this.promptsOpenChange.emit(this.promptsOpen); }

  // ── Field setters (typed in HTML via $any) ─────────────────────
  onAgentField<K extends keyof AgentBlock>(key: K, value: AgentBlock[K]): void {
    this.agentFieldChange.emit({ key, value });
  }
  onModelFilterChange(value: string): void {
    this.modelFilter = value;
    this.modelFilterChange.emit(value);
  }

  onPromptChange(slot: 'system' | 'user' | 'proxy', value: string): void {
    this.promptChange.emit({ slot, value });
  }
  togglePromptTab(slot: 'system' | 'user' | 'proxy'): void {
    this.togglePromptTabIntent.emit(slot);
  }

  onParamsInput(idx: number, value: string): void {
    this.toolParamsInput.emit({ idx, value });
  }

  // ── Provider-aware knob support (mirrors parent) ───────────────
  /** Unprefixed legacy values default to `ollama` (matches `parse_provider`). */
  private providerOf(model: string | undefined | null): 'ollama' | 'gemini' | 'openai' {
    const m = (model ?? '').trim().toLowerCase();
    if (m.startsWith('gemini/')) return 'gemini';
    if (m.startsWith('openai/')) return 'openai';
    return 'ollama';
  }

  /** Prompt slots that carry content, for the general-info box. */
  get activePromptSlots(): string {
    const slots = (['system', 'user', 'proxy'] as const)
      .filter(slot => !!this.getPrompt(slot));
    return slots.length ? slots.join(', ') : '—';
  }

  supportsKnob(knob: string): boolean {
    const p = this.providerOf(this.agentBlock?.model);
    if (p === 'ollama') return true;
    if (p === 'gemini') {
      return ['temperature', 'top_p', 'top_k', 'num_predict', 'stream', 'model'].includes(knob);
    }
    // openai
    return ['temperature', 'top_p', 'num_predict', 'seed', 'stream', 'model'].includes(knob);
  }

  // ── Prompt + tool param helpers (pure on inputs) ───────────────
  /** True when the active node was seeded from a non-EvoMas variant. */
  private get blockHasRepoVariant(): boolean {
    const v = this.agentBlock?.variant;
    return !!v && !v.startsWith('evomas:');
  }

  getPrompt(slot: 'system' | 'user' | 'proxy'): string {
    const explicit = this.agentBlock?.prompts?.[slot];
    if (typeof explicit === 'string' && explicit.length > 0) return explicit;
    if (this.blockHasRepoVariant) return '';
    const t = this.currentAgentType;
    if (slot === 'system') return t?.default_system ?? '';
    if (slot === 'user')   return t?.default_user ?? '';
    return '';
  }

  /** Pretty-printed JSON the tool-params textarea binds to. */
  paramsJson(idx: number): string {
    if (this.toolParamsDraft[idx] !== undefined) return this.toolParamsDraft[idx];
    const params = this.currentTools[idx]?.params ?? {};
    return Object.keys(params).length === 0 ? '{}' : JSON.stringify(params, null, 2);
  }

  toolDescription(name: string): string {
    return this.availableTools.find(t => t.name === name)?.description ?? '';
  }
}
