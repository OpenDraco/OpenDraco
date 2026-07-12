/** Full-screen modal that mounts the shared `<app-inference-instance-view>`
 * with a RunInstance snapshot parsed from a prediction's NDJSON event log.
 * Controlled component: parent owns load/parse and passes the instance in. */
import { Component, EventEmitter, HostListener, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { InferenceInstanceViewComponent } from '../../../../components/index';
import { RunInstance } from '../../../../services/inference-run.service';

@Component({
  selector: 'app-log-viewer-modal',
  standalone: true,
  imports: [CommonModule, InferenceInstanceViewComponent],
  templateUrl: './log-viewer-modal.component.html',
  styles: [`
    .log-filename-pill {
      font-family: monospace;
      font-size: 11px;
      color: var(--text-muted);
      background: var(--bg-0);
      border: 1px solid var(--border);
      border-radius: 3px;
      padding: 1px 6px;
      margin-left: 8px;
      opacity: 0.75;
      -webkit-user-select: text;
      -moz-user-select: text;
      user-select: text;
      cursor: text;
    }
  `],
})
export class LogViewerModalComponent {
  @Input() open = false;
  @Input() loading = false;
  @Input() error = '';
  @Input() title = '';
  @Input() instance: RunInstance | null = null;
  /** Filename of the user-facing text log that mirrors this NDJSON
   * event log (e.g. `prediction-<runId>.log`). Rendered as a pill next
   * to the modal title so users can locate it on disk. */
  @Input() logFileName = '';
  /** Resolved predictions-logs directory (e.g. `results/predictions/logs`
   * by default, `experiments/foo/predictions/logs` when RESULTS_DIR
   * overrides). Surfaced in the pill tooltip so the path is accurate. */
  @Input() predictionsLogsDir = 'results/predictions/logs';

  @Output() close = new EventEmitter<void>();

  @HostListener('document:keydown.escape')
  onEsc(): void { if (this.open) this.close.emit(); }
}
