import { Component, Input } from '@angular/core';

export type BadgeVariant = 'ok' | 'run' | 'err' | 'warn' | 'info';

@Component({
  selector: 'evo-badge',
  standalone: true,
  template: `<span class="evo-badge" [class]="'evo-badge--' + variant"><ng-content /></span>`,
  styleUrl: './evo-badge.component.css',
})
export class EvoBadgeComponent {
  @Input() variant: BadgeVariant = 'info';
}
