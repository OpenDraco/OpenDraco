/** Left-panel browser: search input, group-by-instance toggle, and the
 * two list shapes (flat instance list / job-grouped tree). Controlled —
 * parent owns selection state and supplies the filtered groupings. */
import { Component, ElementRef, EventEmitter, HostBinding, Input, Output, ViewChild, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { EvoBoxComponent, EvoButtonComponent, EvoSwitchComponent } from '../../../../components/index';
import { ICON } from '../../../../icons';
import { ResultInstance, ResultRun } from '../../../../models/types';

export interface JobGroup {
  runId: string;
  mtime: number;
  entries: { instance: ResultInstance; run: ResultRun }[];
}

@Component({
  selector: 'app-instance-tree-picker',
  standalone: true,
  imports: [CommonModule, FormsModule, EvoBoxComponent, EvoButtonComponent, EvoSwitchComponent, NgIcon],
  providers: [provideIcons(ICON)],
  templateUrl: './instance-tree-picker.component.html',
  styleUrl: './instance-tree-picker.component.css',
})
export class InstanceTreePickerComponent {
  @ViewChild('instanceList') instanceListEl?: ElementRef<HTMLDivElement>;

  @Input() instances: ResultInstance[] = [];
  @Input() filteredInstances: ResultInstance[] = [];
  @Input() jobGroups: JobGroup[] = [];
  @Input() loading = false;
  @Input() selectedId: string | null = null;
  @Input() selectedRunId: string | null = null;
  @Input() filter = '';
  @Input() groupByInstance = false;
  @Input() openJobs = new Set<string>();

  @Output() filterChange = new EventEmitter<string>();
  @Output() groupByInstanceChange = new EventEmitter<boolean>();
  @Output() refresh = new EventEmitter<void>();
  @Output() selectInstance = new EventEmitter<string>();
  @Output() selectInstanceInJob = new EventEmitter<{ instance: ResultInstance; run: ResultRun }>();
  @Output() toggleJob = new EventEmitter<string>();

  isJobOpen(runId: string): boolean { return this.openJobs.has(`job/${runId}`); }

  // ─── Collapse toggle ──────────────────────────────────────
  collapsed = signal(false);
  @HostBinding('class.collapsed') get isCollapsed(): boolean { return this.collapsed(); }
  toggleCollapsed(): void { this.collapsed.set(!this.collapsed()); }

  /** Scroll the currently-selected row into view inside the list
   * container. Called by the parent after a deep-link selection
   * (history-panel "N runs" link) so the user lands on the right row
   * visually, not just in state. Defers scrolling to a microtask so
   * the picker's template has re-rendered with the new `.active`
   * class before we query for it. If the user collapsed the panel,
   * expand it first so the scroll has a non-zero box to operate in. */
  revealSelected(): void {
    if (this.collapsed()) this.collapsed.set(false);
    queueMicrotask(() => {
      const list = this.instanceListEl?.nativeElement;
      if (!list) return;
      const active = list.querySelector<HTMLElement>('.inst-item.active');
      if (active) {
        active.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
    });
  }
}
