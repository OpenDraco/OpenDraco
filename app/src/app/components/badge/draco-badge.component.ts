import { Component, Input } from '@angular/core';

export type BadgeVariant = 'ok' | 'run' | 'err' | 'warn' | 'info';

@Component({
  selector: 'draco-badge',
  standalone: true,
  template: `<span class="draco-badge" [class]="'draco-badge--' + variant"><ng-content /></span>`,
  styleUrl: './draco-badge.component.css',
})
export class DracoBadgeComponent {
  @Input() variant: BadgeVariant = 'info';
}
