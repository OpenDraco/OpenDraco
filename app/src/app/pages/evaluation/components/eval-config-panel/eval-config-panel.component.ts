/** Left pane of the Evaluation page: prediction-file picker, run knobs,
 * inspection card, run button + progress + stats + error surfaces.
 *
 * State stays in the parent (`EvaluationComponent` + `EvaluationRunService`)
 * and is projected here via @Inputs. Two-way fields (`predictionsPath`,
 * `maxWorkers`) use the standard `xChange` output convention so the
 * parent can mirror them back into the service.
 */
import { Component, EventEmitter, HostBinding, Input, Output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { NgIcon, provideIcons } from '@ng-icons/core';
import { ICON } from '../../../../icons';
import { PredictionInspection } from '../../../../models/types';
import { ResultStats } from '../../../../services/evaluation-run.service';
import {
  EvoBoxComponent, EvoButtonComponent, EvoSelectComponent, EvoSpinboxComponent,
} from '../../../../components/index';

@Component({
  selector: 'app-eval-config-panel',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    EvoBoxComponent, EvoButtonComponent, EvoSelectComponent, EvoSpinboxComponent,
    NgIcon,
  ],
  providers: [provideIcons(ICON)],
  templateUrl: './eval-config-panel.component.html',
  styleUrl: './eval-config-panel.component.css',
})
export class EvalConfigPanelComponent {
  // ─── Predictions file ─────────────────────────────────────
  @Input() predictionOptions: { value: string; label: string }[] = [];
  @Input() predictionsPath = '';
  @Output() predictionsPathChange = new EventEmitter<string>();
  @Input() filePickerError = '';
  @Output() predictionFileChosen = new EventEmitter<Event>();
  @Output() refreshPredictions = new EventEmitter<void>();
  /** Resolved predictions directory (e.g. `results/predictions` by default,
   * `experiments/foo/predictions` when RESULTS_DIR is overridden). Surfaced
   * in the empty-state hint + file-picker tooltip so they show the real
   * path the backend is scanning. Falls back to the legacy literal when
   * the parent hasn't fetched `/api/paths` yet. */
  @Input() predictionsDir = 'results/predictions';

  // ─── Workers + inspection ─────────────────────────────────
  @Input() maxWorkers = 1;
  @Output() maxWorkersChange = new EventEmitter<number>();
  @Input() inspection: PredictionInspection | null = null;
  @Input() inspectionLoading = false;
  @Input() inspectionError = '';
  @Input() isCustomOnly = false;
  @Input() hasCustomMixed = false;

  // ─── Evaluator script picker ──────────────────────────────
  /** Options the parent derives from the prediction-file inspection.
   * The `<empty>` sentinel is included whenever nothing is detected so
   * the dropdown still has a visible item; the parent disables Run
   * while that's the active value. */
  @Input() evaluatorOptions: { value: string; label: string }[] = [];
  @Input() evaluator = '';
  @Output() evaluatorChange = new EventEmitter<string>();
  onEvaluatorChange(v: string): void {
    this.evaluator = v;
    this.evaluatorChange.emit(v);
  }

  // ─── Run / progress / stats ───────────────────────────────
  @Input() running = false;
  @Input() progressPercent = 0;
  @Input() progressDone = 0;
  @Input() progressTotal = 0;
  @Input() stats: ResultStats | null = null;
  @Input() returnCode: number | null = null;
  @Input() errorMsg = '';
  @Output() run = new EventEmitter<void>();
  @Output() cancel = new EventEmitter<void>();

  // ─── Two-way passthroughs ─────────────────────────────────
  onPredictionsPathChange(v: string): void {
    this.predictionsPath = v;
    this.predictionsPathChange.emit(v);
  }
  onMaxWorkersChange(v: number): void {
    this.maxWorkers = v;
    this.maxWorkersChange.emit(v);
  }

  // ─── Collapse toggle (rail-style) ─────────────────────────
  /** When true the host shrinks to a narrow rail showing only the
   * expand chevron; the body + title are hidden. State is local — a
   * page navigation resets it to expanded, which is the sensible
   * default. */
  collapsed = signal(false);
  @HostBinding('class.collapsed') get isCollapsed(): boolean { return this.collapsed(); }
  toggleCollapsed(): void { this.collapsed.set(!this.collapsed()); }
}
