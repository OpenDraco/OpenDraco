/** Prediction box: metadata KVs, model_patch diff, optional raw NDJSON log
 * toggle, and the action row (download/reveal/View). Pure presentation —
 * parent owns all the async loads and `formatDiff()`. */
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { EvoBoxComponent, EvoButtonComponent, EvoSwitchComponent } from '../../../../components/index';
import { ICON } from '../../../../icons';
import { ResultPrediction, ResultPredictionFile } from '../../../../models/types';

@Component({
  selector: 'app-prediction-panel',
  standalone: true,
  imports: [CommonModule, FormsModule, EvoBoxComponent, EvoButtonComponent, EvoSwitchComponent, NgIcon],
  providers: [provideIcons(ICON)],
  templateUrl: './prediction-panel.component.html',
  styleUrl: './prediction-panel.component.css',
})
export class PredictionPanelComponent {
  @Input() prediction: ResultPrediction | null = null;
  @Input() selectedPredFile: ResultPredictionFile | null = null;
  @Input() predictionLog: string | null = null;
  @Input() predictionLogMissing = false;
  @Input() predictionLogPath: string | null = null;
  @Input() predictionConfigJson = '';
  @Input() predictionTimestamp = '';
  @Input() predictionEndTimestamp = '';
  @Input() predictionDuration = '';
  @Input() predictionConfigUsed = '';
  @Input() showPredictionLog = false;
  @Input() diffLines: { line: string; cls: string }[] = [];

  @Output() downloadPrediction = new EventEmitter<void>();
  @Output() reveal = new EventEmitter<string | null | undefined>();
  @Output() downloadPredictionLog = new EventEmitter<void>();
  @Output() openLogViewer = new EventEmitter<void>();
  @Output() downloadConfig = new EventEmitter<void>();
  @Output() togglePredictionLog = new EventEmitter<boolean>();
}
