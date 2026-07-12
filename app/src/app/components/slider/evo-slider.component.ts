import { Component, Input, forwardRef } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'evo-slider',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="evo-slider-wrap">
      <div class="evo-slider-header">
        @if (label) { <span class="evo-label">{{ label }}</span> }
        <span class="evo-slider-val">{{ value | number:'1.0-2' }}</span>
      </div>
      <div class="evo-slider-track">
        <div class="evo-slider-fill" [style.width]="fillPct + '%'"></div>
        <input
          class="evo-slider-input"
          type="range"
          [min]="min" [max]="max" [step]="step"
          [value]="value"
          [disabled]="isDisabled"
          (input)="onInput($any($event.target).value)" />
      </div>
    </div>
  `,
  styleUrl: './evo-slider.component.css',
  providers: [{
    provide: NG_VALUE_ACCESSOR,
    useExisting: forwardRef(() => EvoSliderComponent),
    multi: true,
  }],
})
export class EvoSliderComponent implements ControlValueAccessor {
  @Input() label = '';
  @Input() min = 0;
  @Input() max = 1;
  @Input() step = 0.01;
  @Input() set disabled(v: boolean) { this.isDisabled = !!v; }

  value = 0;
  isDisabled = false;

  get fillPct(): number {
    return ((this.value - this.min) / (this.max - this.min)) * 100;
  }

  private onChange: (v: number) => void = () => {};
  private onTouched: () => void = () => {};

  onInput(raw: string): void {
    this.value = parseFloat(raw);
    this.onChange(this.value);
    this.onTouched();
  }

  writeValue(v: number): void { this.value = v ?? 0; }
  registerOnChange(fn: any): void { this.onChange = fn; }
  registerOnTouched(fn: any): void { this.onTouched = fn; }
  setDisabledState(d: boolean): void { this.isDisabled = d; }
}
