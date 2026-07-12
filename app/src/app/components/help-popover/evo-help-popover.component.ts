import { Component, ElementRef, HostListener, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

/**
 * Tiny `?` icon that toggles a popover with arbitrary projected content.
 *
 * Usage:
 *   <evo-help-popover>
 *     <p>Anything goes here.</p>
 *   </evo-help-popover>
 */
@Component({
  selector: 'evo-help-popover',
  standalone: true,
  imports: [CommonModule],
  template: `
    <span class="hp-wrap">
      <button class="hp-btn" type="button" (click)="toggle($event)" [title]="title">?</button>
      @if (open) {
        <div class="hp-pop" [class.right]="align === 'right'">
          <ng-content />
        </div>
      }
    </span>
  `,
  styleUrl: './evo-help-popover.component.css',
})
export class EvoHelpPopoverComponent {
  @Input() title = 'Help';
  @Input() align: 'left' | 'right' = 'right';
  open = false;

  constructor(private host: ElementRef<HTMLElement>) {}

  toggle(ev: MouseEvent): void {
    ev.stopPropagation();
    this.open = !this.open;
  }

  @HostListener('document:click', ['$event'])
  onDocClick(ev: MouseEvent): void {
    if (!this.open) return;
    if (!this.host.nativeElement.contains(ev.target as Node)) {
      this.open = false;
    }
  }
}
