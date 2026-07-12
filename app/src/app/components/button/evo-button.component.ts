import { Component, Input, Output, EventEmitter, HostBinding } from '@angular/core';
import { CommonModule } from '@angular/common';

export type BtnVariant = 'default' | 'primary' | 'success' | 'danger' | 'warn' | 'ghost' | 'active';
export type BtnSize = 'sm' | 'md';

@Component({
  selector: 'evo-button',
  standalone: true,
  imports: [CommonModule],
  template: `
    <button
      class="evo-btn"
      [class]="'evo-btn--' + variant + ' evo-btn--' + size"
      [disabled]="disabled"
      (click)="!disabled && clicked.emit($event)">
      <ng-content />
    </button>
  `,
  styleUrl: './evo-button.component.css',
})
export class EvoButtonComponent {
  @Input() variant: BtnVariant = 'default';
  @Input() size: BtnSize = 'md';
  @Input() disabled = false;
  @Output() clicked = new EventEmitter<MouseEvent>();
}
