/** Left rail of the Topology page: lists predefined + loaded configs,
 * with rename / delete affordances on the loaded entries. Pure
 * presentation -- all persistence logic lives on the parent.
 *
 * Collapse state stays on the parent because the center toolbar's
 * `cramped` mode keys on it; the parent owns the signal and feeds the
 * boolean in as an @Input, the child emits a toggle intent. */
import {
  ChangeDetectionStrategy, Component, EventEmitter, Input, Output,
} from '@angular/core';
import { CommonModule } from '@angular/common';

import { ConfigSummary } from '../../../../models/types';
import { EvoBoxComponent } from '../../../../components/index';

@Component({
  selector: 'app-config-list-panel',
  standalone: true,
  imports: [CommonModule, EvoBoxComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './config-list-panel.component.html',
  styleUrl: './config-list-panel.component.css',
})
export class ConfigListPanelComponent {
  @Input() predefinedList: ConfigSummary[] = [];
  @Input() loadedList: ConfigSummary[] = [];
  @Input() currentConfigName: string | null = null;
  @Input() collapsed = false;
  /** Per-config validity from the ngOnInit boot pass. Renders a red dot
   * for errors and an amber dot for warnings-only; tooltip lists the
   * issues. Configs absent from the map (and clean ones) show no dot. */
  @Input() validity: Record<string, { errors: string[]; warnings: string[] }> = {};

  @Output() load            = new EventEmitter<string>();
  @Output() rename          = new EventEmitter<string>();
  @Output() delete          = new EventEmitter<{ stem: string; ev: Event }>();
  @Output() toggleCollapsed = new EventEmitter<void>();

  /** `'error'` when the config has at least one error, `'warn'` if only
   * warnings, `null` if clean / unvalidated (no dot rendered). */
  badge(stem: string): 'error' | 'warn' | null {
    const v = this.validity[stem];
    if (!v) return null;
    if (v.errors.length > 0) return 'error';
    if (v.warnings.length > 0) return 'warn';
    return null;
  }

  /** Tooltip text combining the row's description with the validation
   * issues so hovering surfaces both. */
  badgeTooltip(stem: string, fallback: string): string {
    const v = this.validity[stem];
    const issues: string[] = [];
    if (v?.errors.length) {
      issues.push(`Errors (${v.errors.length}):`);
      for (const e of v.errors) issues.push(`  • ${e}`);
    }
    if (v?.warnings.length) {
      if (issues.length) issues.push('');
      issues.push(`Warnings (${v.warnings.length}):`);
      for (const w of v.warnings) issues.push(`  • ${w}`);
    }
    if (!issues.length) return fallback;
    return `${fallback}\n\n${issues.join('\n')}`;
  }
}
