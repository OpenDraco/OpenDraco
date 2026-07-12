/** Top bar of the Inference page: config picker + selection chip +
 * Show-thinking toggle + Run / Cancel / Clear buttons. */
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { ICON } from '../../../../icons';
import {
  EvoButtonComponent, EvoSelectComponent, EvoSwitchComponent,
} from '../../../../components/index';

@Component({
  selector: 'app-run-controls-bar',
  standalone: true,
  imports: [
    CommonModule, FormsModule,
    EvoButtonComponent, EvoSelectComponent, EvoSwitchComponent,
    NgIcon,
  ],
  providers: [provideIcons(ICON)],
  templateUrl: './run-controls-bar.component.html',
  styleUrl: './run-controls-bar.component.css',
})
export class RunControlsBarComponent {
  @Input() config = '';
  @Input() configs: string[] = [];
  @Input() running = false;
  @Input() runInstancesCount = 0;
  @Input() selectionCount = 0;
  @Input() firstSelected = '';
  @Input() showThinking = true;

  @Output() configChange       = new EventEmitter<string>();
  @Output() showThinkingChange = new EventEmitter<boolean>();
  @Output() run                = new EventEmitter<void>();
  @Output() cancel             = new EventEmitter<void>();
  @Output() clearRun           = new EventEmitter<void>();
  @Output() downloadNotebook   = new EventEmitter<void>();

  onConfigChange(v: string): void       { this.config       = v; this.configChange.emit(v); }
  onShowThinkingChange(v: boolean): void { this.showThinking = v; this.showThinkingChange.emit(v); }
}
