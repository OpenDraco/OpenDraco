import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'draco-box',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="draco-box">
      @if (title || hasActions) {
        <div class="draco-box-header">
          @if (title) { <span class="draco-box-title">{{ title }}</span> }
          <ng-content select="[box-actions]" />
        </div>
      }
      <div class="draco-box-body" [class.no-pad]="noPad">
        <ng-content />
      </div>
    </div>
  `,
  styleUrl: './draco-box.component.css',
})
export class DracoBoxComponent {
  @Input() title = '';
  @Input() noPad = false;

  /** Set to true if you project content into [box-actions] */
  @Input() hasActions = false;
}
