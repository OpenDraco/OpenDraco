/** Evaluation box: resolved pill, per-group test table, and the colored
 * log tabs (run_instance.log / test_output.txt / eval.sh / patch.diff /
 * report.json). Pure presentation — parent owns log fetch + colorization. */
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { EvoBoxComponent, EvoButtonComponent, EvoSwitchComponent } from '../../../../components/index';
import { ICON } from '../../../../icons';
import { ResultEvaluation, ResultEvaluationDir, ResultPredictionFile } from '../../../../models/types';
import { LogLine } from '../../../../services/evaluation-run.service';

type LogName = 'run_instance.log' | 'test_output.txt' | 'eval.sh' | 'patch.diff' | 'report.json';

@Component({
  selector: 'app-evaluation-panel',
  standalone: true,
  imports: [CommonModule, FormsModule, EvoBoxComponent, EvoButtonComponent, EvoSwitchComponent, NgIcon],
  providers: [provideIcons(ICON)],
  templateUrl: './evaluation-panel.component.html',
  styleUrl: './evaluation-panel.component.css',
})
export class EvaluationPanelComponent {
  @Input() selectedEvalDir: ResultEvaluationDir | null = null;
  @Input() evaluation: ResultEvaluation | null = null;
  @Input() selectedPredFile: ResultPredictionFile | null = null;
  @Input() resolvedFlag: boolean | null = null;
  @Input() testStatus: { passed: number; failed: number; group: string }[] | null = null;
  @Input() showLogs = false;
  @Input() activeLog: LogName = 'run_instance.log';
  @Input() isCustomInstance = false;
  @Input() loadingLog = false;
  @Input() logContent = '';
  @Input() coloredLog: LogLine[] = [];

  @Output() downloadZip = new EventEmitter<void>();
  @Output() reveal = new EventEmitter<string | null | undefined>();
  @Output() goEvaluate = new EventEmitter<void>();
  @Output() toggleLogs = new EventEmitter<boolean>();
  @Output() setActiveLog = new EventEmitter<LogName>();
  @Output() downloadLog = new EventEmitter<void>();
}
