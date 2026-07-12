/** Center-top toolbar of the Topology page: title + state chips (read-only,
 * unsaved, unvalidated), topology stats, then four grouped button clusters
 * (Edit / Validate / Save / View) and a Help popover.
 *
 * Pure presentation -- everything the buttons do lives on the parent and
 * comes back through one @Output per intent. The component also renders the
 * inline validation banners since they sit just below the toolbar row. */
import {
  ChangeDetectionStrategy, Component, EventEmitter, Input, Output,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { NgIcon, provideIcons } from '@ng-icons/core';

import { ICON } from '../../../../icons';
import { UnifiedConfig } from '../../../../models/types';
import {
  EvoButtonComponent, EvoHelpPopoverComponent,
} from '../../../../components/index';

@Component({
  selector: 'app-topology-toolbar',
  standalone: true,
  imports: [
    CommonModule,
    EvoButtonComponent, EvoHelpPopoverComponent,
    NgIcon,
  ],
  providers: [provideIcons(ICON)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './topology-toolbar.component.html',
  styleUrl: './topology-toolbar.component.css',
})
export class TopologyToolbarComponent {
  // ── Header / state chips ────────────────────────────────────────
  @Input() currentConfig: UnifiedConfig | null = null;
  @Input() currentConfigName: string | null = null;
  @Input() isLoadedConfig = false;
  @Input() dirty = false;
  @Input() validated = true;

  // ── Edit-group state ────────────────────────────────────────────
  @Input() addEdgeMode = false;
  @Input() edgeSource: string | null = null;
  @Input() selectedAgent: string | null = null;
  @Input() selectedEdgeId: string | null = null;
  @Input() canUndo = false;
  @Input() canRedo = false;

  // ── Transient flashes ───────────────────────────────────────────
  @Input() saveFlash = false;
  @Input() validateFlash = false;

  // ── Topology stats ──────────────────────────────────────────────
  @Input() agentCount = 0;
  @Input() edgeCount = 0;
  @Input() cycleCount = 0;
  @Input() topoStatsTooltip = '';

  // ── Cramped-mode trigger ────────────────────────────────────────
  /** True when BOTH side rails are open at once; toggles icon-only labels. */
  @Input() cramped = false;

  // ── Validation banner state ─────────────────────────────────────
  @Input() validationErrors: string[] = [];
  @Input() validationWarnings: string[] = [];

  // ── Outputs ─────────────────────────────────────────────────────
  @Output() toggleAddEdge              = new EventEmitter<void>();
  @Output() deleteSelected             = new EventEmitter<void>();
  @Output() renameSelected             = new EventEmitter<void>();
  @Output() undo                       = new EventEmitter<void>();
  @Output() redo                       = new EventEmitter<void>();
  @Output() relayout                   = new EventEmitter<void>();
  @Output() reloadGraph                = new EventEmitter<void>();
  @Output() validate                   = new EventEmitter<void>();
  @Output() saveToDisk                 = new EventEmitter<void>();
  @Output() openHistoryPanel           = new EventEmitter<void>();
  @Output() dismissValidationErrors    = new EventEmitter<void>();
  @Output() dismissValidationWarnings  = new EventEmitter<void>();
}
