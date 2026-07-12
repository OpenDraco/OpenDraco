import {
  Component, ElementRef, EventEmitter, HostListener, Input, Output, ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { AgentVariant } from '../../models/types';

/**
 * Topology palette chip: one colored, draggable chip per canonical AGENT_TYPE
 * (Locator, Patcher, ...). A small caret opens a dropdown listing every
 * available variant for that type -- the EvoMas built-in (always first) plus
 * every CSV-derived alternative from `evomas/config/agent_types/*.json`.
 *
 * Selecting a variant updates the chip's label and the drag payload so a
 * fresh node lands with that variant's prompts / tools / config instead of
 * the built-in defaults.
 *
 * Payload on `dragstart`:
 *   dataTransfer.setData('agent-type',    <canonical AGENT_TYPE>)
 *   dataTransfer.setData('agent-variant', <variant.key>)
 * The Topology component's `onGraphDrop` reads both. Older drags (legacy
 * `agent-type` only) still work -- they fall back to the EvoMas built-in.
 */
@Component({
  selector: 'evo-agent-type-picker',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './evo-agent-type-picker.component.html',
  styleUrl: './evo-agent-type-picker.component.css',
})
export class EvoAgentTypePickerComponent {
  @Input() agentType = '';
  @Input() color = '#888';
  @Input() variants: AgentVariant[] = [];
  @Input() selectedVariantKey: string | null = null;
  /** When false the chip can't be dragged and the dropdown is suppressed --
   * mirrors the existing `[draggable]` / `[class.disabled]` treatment on the
   * legacy palette chips while a predefined config is open. */
  @Input() draggable = true;

  @Output() variantChange = new EventEmitter<string>();
  /** Emits `(agentType, variantKey)` -- mostly for analytics / future hooks;
   * the parent's `(drop)` handler reads the same data off `dataTransfer`. */
  @Output() dragStartEvent = new EventEmitter<{ agentType: string; variantKey: string }>();

  @ViewChild('host') hostEl?: ElementRef<HTMLDivElement>;

  open = false;
  /** Viewport-anchored position for the dropdown. Computed on toggleOpen()
   * so the menu can use `position: fixed` and escape any clipping ancestor
   * (the palette panel sets `overflow-x: auto`, which would otherwise clip
   * a normally-positioned absolute popup). */
  menuStyle: { left: string; bottom: string } | null = null;

  get selectedVariant(): AgentVariant | null {
    if (!this.variants?.length) return null;
    const k = this.selectedVariantKey;
    return this.variants.find(v => v.key === k) ?? this.variants[0];
  }

  /** Display label inside the chip. Built-in EvoMas variants ("EvoMas ·
   * default") render as just the AGENT_TYPE so the chip stays compact;
   * repo variants show "<repo> · <name>" verbatim. */
  get chipLabel(): string {
    const v = this.selectedVariant;
    if (!v) return this.agentType;
    if (v.repo === 'evomas') return this.agentType;
    return v.label;
  }

  toggleOpen(ev: Event): void {
    ev.stopPropagation();
    if (!this.draggable) return;
    if (!this.open) {
      // Anchor the menu's bottom edge 4 px above the chip's top, left-aligned
      // with the chip. Using viewport coordinates + position:fixed sidesteps
      // any ancestor `overflow: hidden/auto` (the palette panel clips).
      const rect = this.hostEl?.nativeElement.getBoundingClientRect();
      if (rect) {
        this.menuStyle = {
          left:   `${Math.round(rect.left)}px`,
          bottom: `${Math.round(window.innerHeight - rect.top + 4)}px`,
        };
      }
    }
    this.open = !this.open;
  }

  pickVariant(v: AgentVariant, ev: Event): void {
    ev.stopPropagation();
    this.selectedVariantKey = v.key;
    this.variantChange.emit(v.key);
    this.open = false;
  }

  onDragStart(ev: DragEvent): void {
    if (!this.draggable) return;
    const v = this.selectedVariant;
    const variantKey = v?.key ?? `evomas:${this.agentType}`;
    ev.dataTransfer?.setData('agent-type', this.agentType);
    ev.dataTransfer?.setData('agent-variant', variantKey);
    if (ev.dataTransfer) ev.dataTransfer.effectAllowed = 'copy';
    this.dragStartEvent.emit({ agentType: this.agentType, variantKey });
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(ev: MouseEvent): void {
    if (!this.open) return;
    const root = this.hostEl?.nativeElement;
    if (root && !root.contains(ev.target as Node)) {
      this.open = false;
    }
  }
}
