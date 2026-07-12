import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'evo-box',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="evo-box">
      @if (title || hasActions) {
        <div class="evo-box-header">
          @if (title) { <span class="evo-box-title">{{ title }}</span> }
          <ng-content select="[box-actions]" />
        </div>
      }
      <div class="evo-box-body" [class.no-pad]="noPad">
        <ng-content />
      </div>
    </div>
  `,
  styleUrl: './evo-box.component.css',
})
export class EvoBoxComponent {
  @Input() title = '';
  @Input() noPad = false;

  /** Set to true if you project content into [box-actions] */
  @Input() hasActions = false;
}
