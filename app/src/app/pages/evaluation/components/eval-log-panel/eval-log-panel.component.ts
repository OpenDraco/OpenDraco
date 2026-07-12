/** Right pane of the Evaluation page: streaming log output + clear button.
 *
 * Owns the scroll container and auto-scrolls to the bottom whenever a new
 * line arrives. The parent page passes the latest `logs` and `running`
 * flag via inputs; this component handles its own DOM-level scroll
 * choreography via `ngOnChanges` + `AfterViewChecked` so the page shell
 * doesn't have to know which element holds the log.
 */
import {
  AfterViewChecked, Component, ElementRef, EventEmitter,
  Input, OnChanges, Output, SimpleChanges, ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';

import { LogLine } from '../../../../services/evaluation-run.service';
import { EvoButtonComponent, EvoBoxComponent } from '../../../../components/index';

@Component({
  selector: 'app-eval-log-panel',
  standalone: true,
  imports: [CommonModule, EvoButtonComponent, EvoBoxComponent],
  templateUrl: './eval-log-panel.component.html',
  styleUrl: './eval-log-panel.component.css',
})
export class EvalLogPanelComponent implements AfterViewChecked, OnChanges {
  @Input() logs: LogLine[] = [];
  @Input() running = false;
  @Output() clearLogs = new EventEmitter<void>();

  @ViewChild('logEl') logEl?: ElementRef<HTMLDivElement>;
  private shouldScroll = false;

  ngOnChanges(changes: SimpleChanges): void {
    // Whenever the `logs` array reference flips (new line appended), queue a
    // scroll-to-bottom. Object identity is the trigger — the parent service
    // emits an immutable snapshot per change so this fires on every line.
    if (changes['logs']) this.shouldScroll = true;
  }

  ngAfterViewChecked(): void {
    if (this.shouldScroll && this.logEl) {
      const el = this.logEl.nativeElement;
      el.scrollTop = el.scrollHeight;
      this.shouldScroll = false;
    }
  }

  onClear(): void { this.clearLogs.emit(); }
}
