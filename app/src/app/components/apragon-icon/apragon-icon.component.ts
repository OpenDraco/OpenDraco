import { Component, Input } from '@angular/core';

/**
 * Apragon brand mark — the Draco constellation, using its real star
 * positions: head quad (γ Eltanin · β Rastaban · ν Kuma · ξ Grumium) at the
 * bottom-left, vertical neck up through δ Altais and ε Tyl, body wave across
 * the top down through ζ Aldhibah → η Aldibain → ι Edasich (the valley) →
 * α Thuban → λ Giausar (tail tip) at upper-right.
 *
 * Eltanin (γ) is the brightest star in Draco — it carries the accent color.
 *
 * Inherits its non-accent color from the surrounding CSS `color` property
 * (uses `currentColor` for stars & edges) so it themes naturally.
 *
 * Usage:
 *   <apragon-icon />
 *   <apragon-icon [size]="32" />
 *   <apragon-icon [size]="64" accent="#d97706" [glow]="false" />
 */
@Component({
  selector: 'apragon-icon',
  standalone: true,
  template: `
    <svg
      [attr.width]="size"
      [attr.height]="size"
      viewBox="0 0 100 100"
      xmlns="http://www.w3.org/2000/svg"
      [attr.aria-label]="ariaLabel"
      [attr.role]="ariaLabel ? 'img' : null"
      style="display: block; overflow: visible;"
    >
      <!-- edges (head quad + neck + body wave) -->
      <g
        stroke="currentColor"
        [attr.stroke-width]="strokeWidth"
        [attr.stroke-opacity]="lineOpacity"
        stroke-linecap="round"
        fill="none"
      >
        <!-- head quadrilateral -->
        <line x1="8" y1="92" x2="22" y2="88" />
        <line x1="22" y1="88" x2="22" y2="72" />
        <line x1="22" y1="72" x2="10" y2="70" />
        <line x1="10" y1="70" x2="8" y2="92" />
        <!-- vertical neck up: ξ Grumium → δ Altais → ε Tyl -->
        <line x1="10" y1="70" x2="11" y2="40" />
        <line x1="11" y1="40" x2="13" y2="22" />
        <!-- body wave: ε Tyl → ζ → η → ι → α → λ Giausar -->
        <line x1="13" y1="22" x2="34" y2="50" />
        <line x1="34" y1="50" x2="44" y2="74" />
        <line x1="44" y1="74" x2="60" y2="78" />
        <line x1="60" y1="78" x2="80" y2="44" />
        <line x1="80" y1="44" x2="92" y2="12" />
      </g>

      <!-- non-bright stars (β, ν, ξ, δ, ε, ζ, η, ι, α, λ) -->
      <g fill="currentColor">
        <circle cx="22" cy="88" r="2.4" />
        <circle cx="22" cy="72" r="2.4" />
        <circle cx="10" cy="70" r="2.4" />
        <circle cx="11" cy="40" r="2.4" />
        <circle cx="13" cy="22" r="2.4" />
        <circle cx="34" cy="50" r="2.4" />
        <circle cx="44" cy="74" r="2.4" />
        <circle cx="60" cy="78" r="2.4" />
        <circle cx="80" cy="44" r="2.4" />
        <circle cx="92" cy="12" r="2.4" />
      </g>

      <!-- γ Eltanin — brightest, accent halo -->
      @if (glow) {
        <circle cx="8" cy="92" r="10.92" [attr.fill]="accent" fill-opacity="0.12" />
        <circle cx="8" cy="92" r="6.51" [attr.fill]="accent" fill-opacity="0.24" />
      }
      <circle cx="8" cy="92" r="4.2" [attr.fill]="accent" />
    </svg>
  `,
  styles: [
    `
      :host {
        display: inline-flex;
        line-height: 0;
        color: currentColor;
      }
    `,
  ],
})
export class ApragonIconComponent {
  /** Rendered pixel dimension (square). */
  @Input() size: number | string = 48;

  /** Color of the bright Eltanin (γ) accent star + its halo. */
  @Input() accent: string = '#f8c468';

  /** Render the soft halo around Eltanin. Drop to `false` for ≤24px / favicons. */
  @Input() glow: boolean = true;

  /** Stroke width of the constellation edges (viewBox units). */
  @Input() strokeWidth: number = 1.4;

  /** Opacity of the constellation edges (0–1). */
  @Input() lineOpacity: number = 0.42;

  /** Accessible label. Omit for purely decorative use. */
  @Input() ariaLabel: string | null = null;
}
