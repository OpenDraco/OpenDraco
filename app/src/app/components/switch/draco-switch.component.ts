import { Component, Input, forwardRef } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'draco-switch',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="draco-switch-row" [class.disabled]="isDisabled" (click)="toggle()">
      @if (label) { <span class="draco-sw-label">{{ label }}</span> }
      <div class="draco-switch" [class.on]="value">
        <div class="draco-switch-thumb"></div>
      </div>
    </div>
  `,
  styleUrl: './draco-switch.component.css',
  providers: [{
    provide: NG_VALUE_ACCESSOR,
    useExisting: forwardRef(() => DracoSwitchComponent),
    multi: true,
  }],
})
export class DracoSwitchComponent implements ControlValueAccessor {
  @Input() label = '';
  @Input() set disabled(v: boolean) { this.isDisabled = !!v; }

  value = false;
  isDisabled = false;

  private onChange: (v: boolean) => void = () => {};
  private onTouched: () => void = () => {};

  toggle(): void {
    if (this.isDisabled) return;
    this.value = !this.value;
    this.onChange(this.value);
    this.onTouched();
  }

  writeValue(v: boolean): void { this.value = !!v; }
  registerOnChange(fn: (v: boolean) => void): void { this.onChange = fn; }
  registerOnTouched(fn: () => void): void { this.onTouched = fn; }
  setDisabledState(d: boolean): void { this.isDisabled = d; }
}
