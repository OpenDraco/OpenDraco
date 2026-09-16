/** Per-instance chip strip for an active inference run. Each chip is a
 * clickable button that switches the focused instance — but a chip
 * "click" is suppressed when the user actually intended to select text
 * inside it (for copy/paste of the instance / run id). */
import {
  Component, EventEmitter, Input, Output,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { RunInstance } from '../../../../services/inference-run.service';

@Component({
  selector: 'app-batch-progress-strip',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './batch-progress-strip.component.html',
  styleUrl: './batch-progress-strip.component.css',
})
export class BatchProgressStripComponent {
  @Input() runInstances: RunInstance[] = [];
  @Input() currentInstance: RunInstance | null = null;
  @Output() selectInstance = new EventEmitter<string>();
  /** Resolved predictions-logs directory (e.g. `results/predictions/logs` by
   * default, `experiments/foo/predictions/logs` when RESULTS_DIR overrides).
   * Surfaced in the per-chip tooltip so the path tracks the backend. */
  @Input() predictionsLogsDir = 'results/predictions/logs';

  onClick(_ev: MouseEvent, id: string): void {
    // Don't switch instances when the click is a click-to-copy on the
    // selected text inside the chip (see `.bp-id` / `.bp-runid` CSS).
    const sel = window.getSelection?.()?.toString() ?? '';
    if (sel) return;
    this.selectInstance.emit(id);
  }
}
