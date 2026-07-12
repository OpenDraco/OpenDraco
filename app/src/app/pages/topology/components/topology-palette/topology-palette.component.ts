/** Bottom palette strip: one draggable chip per canonical AGENT_TYPE.
 * The chip + its variant dropdown live in `evo-agent-type-picker`;
 * this component is just the layout shell + the parent-bound variant
 * selection. Drag-start payload is handled inside the chip itself. */
import {
  ChangeDetectionStrategy, Component, EventEmitter, Input, Output,
} from '@angular/core';
import { CommonModule } from '@angular/common';

import { AgentType, AgentVariant } from '../../../../models/types';
import { EvoAgentTypePickerComponent } from '../../../../components/index';

@Component({
  selector: 'app-topology-palette',
  standalone: true,
  imports: [CommonModule, EvoAgentTypePickerComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './topology-palette.component.html',
  styleUrl: './topology-palette.component.css',
})
export class TopologyPaletteComponent {
  @Input() agentTypes: AgentType[] = [];
  @Input() selectedVariantByType: Record<string, string> = {};
  @Input() isLoadedConfig = false;

  @Output() variantChange = new EventEmitter<{ type: string; key: string }>();

  /** Domain agents — the bulk of the palette. */
  get domainTypes(): AgentType[] {
    return this.agentTypes.filter(t => (t.category ?? 'agent') !== 'control');
  }

  /** Control-flow primitives (e.g. Router). Rendered in a separate lane
   * so they read as architectural pieces, not just another domain role. */
  get controlTypes(): AgentType[] {
    return this.agentTypes.filter(t => t.category === 'control');
  }

  variantsFor(type: string): AgentVariant[] {
    return this.agentTypes.find(t => t.type === type)?.variants ?? [];
  }

  selectedVariantKey(type: string): string {
    const stored = this.selectedVariantByType[type];
    if (stored) return stored;
    const vs = this.variantsFor(type);
    return vs.length ? vs[0].key : `evomas:${type}`;
  }

  onVariantChange(type: string, key: string): void {
    this.variantChange.emit({ type, key });
  }
}
