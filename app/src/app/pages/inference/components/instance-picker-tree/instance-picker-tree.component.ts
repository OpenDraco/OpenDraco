/** Left panel of the Inference page: nested subset / split / instance
 * picker with bulk-select chips, per-leaf refresh, search, and the
 * "+ Custom" entrypoint. Owns its own derived state (which subset/split
 * is open, filter results) since the parent service holds expanded
 * sets and selected ids; computed helpers stay here. */
import { Component, EventEmitter, HostBinding, Input, Output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { ICON } from '../../../../icons';
import {
  Instance, SUBSET_SPLITS, SwebenchSplit, SwebenchSubset,
} from '../../../../models/types';
import {
  EvoBoxComponent, EvoButtonComponent,
} from '../../../../components/index';

@Component({
  selector: 'app-instance-picker-tree',
  standalone: true,
  imports: [CommonModule, FormsModule, EvoBoxComponent, EvoButtonComponent, NgIcon],
  providers: [provideIcons(ICON)],
  templateUrl: './instance-picker-tree.component.html',
  styleUrl: './instance-picker-tree.component.css',
})
export class InstancePickerTreeComponent {
  // ─── Data inputs ───────────────────────────────────────────────
  @Input() instances: Instance[] = [];
  @Input() instancesTotal = 0;
  @Input() loadingInstances = false;
  @Input() refreshing = false;
  @Input() refreshError = '';

  // ─── State inputs (owned by InferenceStateService at the page level) ──
  @Input() selectedIds: Set<string> = new Set();
  @Input() selectionCount = 0;
  @Input() openSubsets: Set<string> = new Set();
  @Input() openSplits: Set<string> = new Set();
  @Input() search = '';
  @Input() customFormOpen = false;

  // ─── Outputs ───────────────────────────────────────────────────
  @Output() searchChange         = new EventEmitter<string>();
  @Output() toggleSubset         = new EventEmitter<SwebenchSubset>();
  @Output() toggleSplit          = new EventEmitter<{ subset: SwebenchSubset; split: SwebenchSplit }>();
  @Output() toggleInstance       = new EventEmitter<string>();
  @Output() toggleSubsetSelect   = new EventEmitter<SwebenchSubset>();
  @Output() toggleSplitSelect    = new EventEmitter<{ subset: SwebenchSubset; split: SwebenchSplit }>();
  @Output() refreshLeaf          = new EventEmitter<{ subset: SwebenchSubset; split: SwebenchSplit }>();
  @Output() refreshSubset        = new EventEmitter<SwebenchSubset>();
  @Output() refreshAll           = new EventEmitter<void>();
  @Output() selectAllVisible     = new EventEmitter<void>();
  @Output() clearSelection       = new EventEmitter<void>();
  @Output() toggleCustomForm     = new EventEmitter<void>();

  // ─── Pure helpers over inputs ──────────────────────────────────
  readonly subsets: SwebenchSubset[] = ['lite', 'full', 'verified', 'custom'];
  splitsFor(s: SwebenchSubset): SwebenchSplit[] { return SUBSET_SPLITS[s]; }
  subsetLabel(s: SwebenchSubset): string {
    if (s === 'lite')     return 'Lite';
    if (s === 'full')     return 'Full';
    if (s === 'verified') return 'Verified';
    return 'Custom';
  }
  canRefreshSubset(s: SwebenchSubset): boolean { return s !== 'custom'; }

  instancesIn(subset: SwebenchSubset, split: SwebenchSplit): Instance[] {
    const q = this.search.toLowerCase();
    return this.instances.filter(i =>
      i.subset === subset && i.split === split &&
      (!q || i.instance_id.toLowerCase().includes(q) || i.repo.toLowerCase().includes(q))
    );
  }
  countIn(subset: SwebenchSubset): number {
    const q = this.search.toLowerCase();
    return this.instances.filter(i =>
      i.subset === subset &&
      (!q || i.instance_id.toLowerCase().includes(q) || i.repo.toLowerCase().includes(q))
    ).length;
  }

  isSubsetOpen(s: string): boolean { return this.openSubsets.has(s); }
  isSplitOpen(subset: string, split: string): boolean { return this.openSplits.has(`${subset}/${split}`); }
  isSelected(id: string): boolean { return this.selectedIds.has(id); }

  isSplitAllSelected(subset: SwebenchSubset, split: SwebenchSplit): boolean {
    const leaf = this.instancesIn(subset, split);
    return leaf.length > 0 && leaf.every(i => this.isSelected(i.instance_id));
  }
  isSubsetAllSelected(subset: SwebenchSubset): boolean {
    const ids = this.splitsFor(subset).flatMap(sp => this.instancesIn(subset, sp).map(i => i.instance_id));
    return ids.length > 0 && ids.every(id => this.isSelected(id));
  }

  onSearch(v: string): void { this.search = v; this.searchChange.emit(v); }

  // ─── Collapse toggle ──────────────────────────────────────
  collapsed = signal(false);
  @HostBinding('class.collapsed') get isCollapsed(): boolean { return this.collapsed(); }
  toggleCollapsed(): void { this.collapsed.set(!this.collapsed()); }
}
