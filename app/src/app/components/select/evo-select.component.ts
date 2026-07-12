import { Component, ElementRef, HostListener, Input, ViewChild, forwardRef } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR, FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';

export interface SelectOption { value: string; label: string; }
export interface SelectOptionGroup { label: string; items: string[] | SelectOption[]; }

@Component({
  selector: 'evo-select',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="evo-select-wrap">
      @if (label) { <label class="evo-label">{{ label }}</label> }

      @if (useGroupedPanel) {
        <!-- Custom grouped panel: stronger visual section separation than
             native <optgroup> can deliver. Click-outside + ESC dismiss. -->
        <div class="evo-select-box grouped" [class.disabled]="isDisabled">
          <button #trigger type="button" class="evo-select grouped-trigger"
                  [disabled]="isDisabled"
                  [class.open]="open"
                  (click)="toggle($event)">
            <span class="grouped-trigger-label">{{ displaySelectedLabel() || placeholder }}</span>
          </button>
          <span class="evo-select-arrow" [class.open]="open">▾</span>

          @if (open) {
            <div class="grouped-panel" role="listbox"
                 [class.up]="panelOpenUp"
                 [style.top.px]="panelTop"
                 [style.left.px]="panelLeft"
                 [style.width.px]="panelWidth"
                 [style.max-height.px]="panelMaxHeight">
              <!-- Flat options (from the [options] input) render at the
                   top of the panel as an ungrouped list, before any
                   section headers. Used by callers that want a leading
                   empty / none sentinel that clears the current pick. -->
              @if (normalizedOptions.length > 0) {
                <ul class="grouped-section-items grouped-flat-items">
                  @for (opt of normalizedOptions; track opt.value) {
                    <li class="grouped-item grouped-item-flat"
                        [class.active]="opt.value === value"
                        role="option"
                        (click)="pick(opt.value)">{{ opt.label || '(empty)' }}</li>
                  }
                </ul>
              }
              @for (g of normalizedGroups; track g.label) {
                <div class="grouped-section">
                  <div class="grouped-section-head" [attr.data-group]="g.label">
                    <span class="grouped-section-label">{{ g.label }}</span>
                    <span class="grouped-section-count">{{ g.items.length }}</span>
                  </div>
                  <ul class="grouped-section-items">
                    @for (opt of g.items; track opt.value) {
                      <li class="grouped-item"
                          [class.active]="opt.value === value"
                          role="option"
                          (click)="pick(opt.value)">{{ opt.label }}</li>
                    }
                  </ul>
                </div>
              }
            </div>
          }
        </div>
      } @else {
        <!-- Flat / native path: unchanged behaviour for every other call
             site in the app. -->
        <div class="evo-select-box" [class.disabled]="isDisabled">
          <select
            class="evo-select"
            [disabled]="isDisabled"
            [ngModel]="value"
            (ngModelChange)="onValueChange($event)">
            @for (opt of normalizedOptions; track opt.value) {
              <option [value]="opt.value">{{ opt.label }}</option>
            }
          </select>
          <span class="evo-select-arrow">▾</span>
        </div>
      }
    </div>
  `,
  styleUrl: './evo-select.component.css',
  providers: [{
    provide: NG_VALUE_ACCESSOR,
    useExisting: forwardRef(() => EvoSelectComponent),
    multi: true,
  }],
})
export class EvoSelectComponent implements ControlValueAccessor {
  @Input() label = '';
  /** Placeholder text shown on the grouped-panel trigger when no value
   * is selected (or value is the blank-sentinel). Ignored on the native
   * flat path because `<select>` already shows the first option. */
  @Input() placeholder = '+ Add…';
  /** When true, the trigger reverts to its placeholder state immediately
   * after the user picks an option. Use this for "action" pickers
   * (e.g. the inspector's Add-a-tool dropdown) where the parent emits
   * the picked value but doesn't store it — without this flag Angular
   * one-way `[ngModel]="''"` would NOT re-call writeValue after the
   * pick, and the trigger would keep showing the just-picked item.
   * Default false preserves the stateful behaviour every other
   * caller relies on. */
  @Input() clearOnPick = false;
  @Input() set options(v: string[] | SelectOption[]) {
    this.normalizedOptions = (v as any[]).map(o =>
      typeof o === 'string' ? { value: o, label: o } : o
    );
  }
  /**
   * Optional `<optgroup>`-rendered shape. When provided AND non-empty,
   * the component renders a CUSTOM grouped panel instead of the native
   * `<select>` — gives proper visual section separation (color-tagged
   * headers, hover/active states, per-group counts) that native
   * `<optgroup>` can't deliver in modern browsers.
   */
  @Input() set optgroups(v: SelectOptionGroup[]) {
    this.normalizedGroups = (v ?? [])
      .filter(g => g && (g.items?.length ?? 0) > 0)
      .map(g => ({
        label: g.label,
        items: (g.items as any[]).map(o => typeof o === 'string' ? { value: o, label: o } : o),
      }));
  }
  @Input() set disabled(v: boolean) { this.isDisabled = !!v; }

  /** Minimum width the grouped popover panel snaps to. Independent of
   * the trigger's width — the panel is `position: fixed` to escape the
   * inspector's `overflow:hidden`/`overflow-y:auto` chain, so it can
   * grow wider than its host. Bump this to give the dropdown more
   * breathing room. */
  private static readonly PANEL_MIN_WIDTH = 380;
  /** Viewport-edge gutter so the panel never butts directly against
   * the right side of the window. */
  private static readonly PANEL_RIGHT_GUTTER = 12;
  /** Cap on panel height. Matches the CSS `max-height` so the inline
   * computed value never gets larger than what the stylesheet allows;
   * the runtime value shrinks below this when the chosen direction
   * doesn't have enough room. */
  private static readonly PANEL_MAX_HEIGHT = 320;
  /** Minimum usable panel height — below this the picker becomes a
   * single-row stub. Floor for the auto-shrink path so we never
   * collapse to <120px even when both above/below are cramped. */
  private static readonly PANEL_MIN_HEIGHT = 120;
  /** Vertical gutter between the trigger and the panel; also used as
   * the safety margin against viewport edges. */
  private static readonly PANEL_VERTICAL_GUTTER = 8;

  @ViewChild('trigger') triggerRef?: ElementRef<HTMLButtonElement>;

  value = '';
  isDisabled = false;
  open = false;
  normalizedOptions: SelectOption[] = [];
  normalizedGroups: { label: string; items: SelectOption[] }[] = [];

  // Panel positioning (viewport-relative, used by `position: fixed`).
  panelTop = 0;
  panelLeft = 0;
  panelWidth = 0;
  panelMaxHeight = EvoSelectComponent.PANEL_MAX_HEIGHT;
  /** True when the panel should expand UP from the trigger because
   * there's more room above than below. Toggled by `positionPanel()`. */
  panelOpenUp = false;

  private onChange: (v: string) => void = () => {};
  private onTouched: () => void = () => {};

  constructor(private host: ElementRef<HTMLElement>) {}

  /** True iff at least one group has items — drives the template
   * branch between the custom panel and the native select. */
  get useGroupedPanel(): boolean { return this.normalizedGroups.length > 0; }

  onValueChange(v: string): void {
    this.value = v;
    this.onChange(v);
    this.onTouched();
  }

  toggle(ev: MouseEvent): void {
    ev.stopPropagation();
    if (this.isDisabled) return;
    if (this.open) { this.open = false; return; }
    this.positionPanel();
    this.open = true;
  }

  private positionPanel(): void {
    const btn = this.triggerRef?.nativeElement;
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    const minW = EvoSelectComponent.PANEL_MIN_WIDTH;
    const rightGutter = EvoSelectComponent.PANEL_RIGHT_GUTTER;
    const vGutter = EvoSelectComponent.PANEL_VERTICAL_GUTTER;
    const maxH = EvoSelectComponent.PANEL_MAX_HEIGHT;
    const minH = EvoSelectComponent.PANEL_MIN_HEIGHT;
    // Width: at least PANEL_MIN_WIDTH and at least as wide as the trigger;
    // capped so the right edge stays inside the viewport.
    const maxFitting = Math.max(160, window.innerWidth - r.left - rightGutter);
    this.panelWidth = Math.min(Math.max(minW, r.width), maxFitting);
    this.panelLeft = r.left;

    // Choose the side with more room. Prefer DOWN when both fit; flip UP
    // only when down can't hold the desired height AND up can hold more.
    // This keeps the long-standing "appears below" behaviour for triggers
    // anywhere in the upper viewport and only inverts near the bottom
    // edge (e.g. the inspector's Add-tool picker on a bottom-anchored
    // node card).
    const spaceBelow = Math.max(0, window.innerHeight - r.bottom - vGutter);
    const spaceAbove = Math.max(0, r.top - vGutter);
    const fitsBelow = spaceBelow >= maxH;
    const flipUp = !fitsBelow && spaceAbove > spaceBelow;
    if (flipUp) {
      this.panelMaxHeight = Math.max(minH, Math.min(maxH, spaceAbove));
      this.panelTop = Math.max(vGutter, r.top - 4 - this.panelMaxHeight);
      this.panelOpenUp = true;
    } else {
      this.panelMaxHeight = Math.max(minH, Math.min(maxH, spaceBelow));
      this.panelTop = r.bottom + 4;
      this.panelOpenUp = false;
    }
  }

  pick(v: string): void {
    this.open = false;
    this.onValueChange(v);
    // Action-style pickers (e.g. Add-a-tool): the parent emits the
    // picked value but doesn't store it, so its `[ngModel]="''"` stays
    // structurally equal across CD cycles and Angular won't re-call
    // writeValue() to clear our internal state. Reset locally so the
    // trigger reverts to its placeholder for the next pick.
    if (this.clearOnPick && v) {
      this.value = '';
      this.onChange('');
    }
  }

  /** Resolve the currently-selected option's label across both
   * `normalizedOptions` and the grouped items, so the trigger button
   * can display it. Returns `''` when the value is blank/unknown so
   * the placeholder text takes over. */
  displaySelectedLabel(): string {
    if (!this.value) return '';
    for (const opt of this.normalizedOptions) {
      if (opt.value === this.value) return opt.label;
    }
    for (const g of this.normalizedGroups) {
      for (const opt of g.items) if (opt.value === this.value) return opt.label;
    }
    return this.value;
  }

  @HostListener('document:click', ['$event'])
  onDocClick(ev: MouseEvent): void {
    if (!this.open) return;
    if (!this.host.nativeElement.contains(ev.target as Node)) this.open = false;
  }

  @HostListener('document:keydown.escape')
  onEsc(): void { if (this.open) this.open = false; }

  writeValue(v: string): void { this.value = v ?? ''; }
  registerOnChange(fn: any): void { this.onChange = fn; }
  registerOnTouched(fn: any): void { this.onTouched = fn; }
  setDisabledState(d: boolean): void { this.isDisabled = d; }
}
