import { Component, Input, forwardRef } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'evo-spinbox',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="evo-spinbox-wrap">
      @if (label) { <label class="evo-label">{{ label }}</label> }
      <div class="evo-spinbox" [class.disabled]="isDisabled">
        <button class="evo-spin-btn" (click)="decrement()" [disabled]="isDisabled || value <= min" tabindex="-1">−</button>
        <input
          class="evo-spin-input"
          type="number"
          [min]="min" [max]="max" [step]="step"
          [value]="value"
          [disabled]="isDisabled"
          (change)="onInputChange($any($event.target).value)"
          (input)="onInputChange($any($event.target).value)" />
        <button class="evo-spin-btn" (click)="increment()" [disabled]="isDisabled || value >= max" tabindex="-1">+</button>
      </div>
    </div>
  `,
  styleUrl: './evo-spinbox.component.css',
  providers: [{
    provide: NG_VALUE_ACCESSOR,
    useExisting: forwardRef(() => EvoSpinboxComponent),
    multi: true,
  }],
})
export class EvoSpinboxComponent implements ControlValueAccessor {
  @Input() label = '';
  @Input() min = 0;
  @Input() max = 9999;
  @Input() step = 1;
  @Input() set disabled(v: boolean) { this.isDisabled = !!v; }

  value = 0;
  isDisabled = false;

  private onChange: (v: number) => void = () => {};
  private onTouched: () => void = () => {};

  increment(): void { this.emit(Math.min(this.max, this.value + this.step)); }
  decrement(): void { this.emit(Math.max(this.min, this.value - this.step)); }

  onInputChange(raw: string): void {
    const n = parseFloat(raw);
    if (!isNaN(n)) this.emit(Math.min(this.max, Math.max(this.min, n)));
  }

  private emit(v: number): void {
    this.value = v;
    this.onChange(v);
    this.onTouched();
  }

  writeValue(v: number): void { this.value = v ?? 0; }
  registerOnChange(fn: any): void { this.onChange = fn; }
  registerOnTouched(fn: any): void { this.onTouched = fn; }
  setDisabledState(d: boolean): void { this.isDisabled = d; }
}
