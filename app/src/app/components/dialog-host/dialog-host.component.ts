/**
 * Renders the active `DialogService` dialog. One instance is mounted
 * at the root of `app.html` so any page / service / guard can call
 * `dialog.confirm(...)` and get a Promise back — the host takes care of
 * the modal lifecycle (focus, backdrop dismiss, Escape, the trailing
 * `resolveCurrent`).
 *
 * Three kinds:
 *   - `alert`: message + OK button (+ optional pre-formatted detail).
 *   - `confirm`: message + Cancel / OK (optional danger styling on OK).
 *   - `prompt`: message + text input + Cancel / OK (with optional
 *     synchronous validator that gates the OK click).
 *
 * Styling reuses the global `modal-*` classes from `styles.css` so the
 * shell matches the Save-failed / Save-config / Create-from-template
 * modals that are already in the app.
 */

import {
  ChangeDetectionStrategy, Component, ChangeDetectorRef, OnInit, OnDestroy,
  ViewChild, ElementRef,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import { DialogService, DialogState } from '../../services/dialog.service';

@Component({
  selector: 'app-dialog-host',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dialog-host.component.html',
  styleUrl: './dialog-host.component.css',
})
export class DialogHostComponent implements OnInit, OnDestroy {
  @ViewChild('promptInput') promptInput?: ElementRef<HTMLInputElement | HTMLSelectElement>;

  state: DialogState | null = null;
  /** Local copy of the prompt input value — bound via `[(ngModel)]`. */
  promptValue = '';
  /** Inline error from a failed `validate(value)` — shown under the input. */
  promptError = '';

  private sub?: Subscription;

  constructor(private dialog: DialogService, private cdr: ChangeDetectorRef) {}

  ngOnInit(): void {
    this.sub = this.dialog.state$.subscribe(next => {
      this.state = next;
      this.promptValue = next?.defaultValue ?? '';
      this.promptError = '';
      this.cdr.markForCheck();
      // Focus the input on the next tick — the @if branch needs to
      // render before the ViewChild ref is populated.
      if (next?.kind === 'prompt') {
        queueMicrotask(() => this.promptInput?.nativeElement.focus());
        queueMicrotask(() => {
          const el = this.promptInput?.nativeElement;
          // `.select()` is input-only; the select-options variant uses
          // a <select> element which doesn't have it.
          if (el instanceof HTMLInputElement) el.select();
        });
      }
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  /** OK click. For prompt, runs the optional validator and bails on a
   * failure so the user can correct the input without losing context. */
  confirm(): void {
    const s = this.state;
    if (!s) return;
    if (s.kind === 'prompt') {
      if (s.validate) {
        const err = s.validate(this.promptValue);
        if (err) {
          this.promptError = err;
          this.cdr.markForCheck();
          return;
        }
      }
      this.dialog.resolveCurrent(this.promptValue);
      return;
    }
    this.dialog.resolveCurrent(s.kind === 'confirm' ? true : undefined);
  }

  /** Cancel / backdrop click / Escape. `confirm` → `false`,
   * `prompt` → `null`, `alert` → `undefined` (matches the OK contract
   * since alerts only have one outcome). */
  cancel(): void {
    const s = this.state;
    if (!s) return;
    if (s.kind === 'confirm') this.dialog.resolveCurrent(false);
    else if (s.kind === 'prompt') this.dialog.resolveCurrent(null);
    else this.dialog.resolveCurrent(undefined);
  }

  /** Browser-wide Escape key handler. Cheaper than a per-modal listener
   * and matches the native `window.confirm/prompt/alert` UX. */
  onKeydown(ev: KeyboardEvent): void {
    if (!this.state) return;
    if (ev.key === 'Escape') {
      ev.preventDefault();
      this.cancel();
    } else if (ev.key === 'Enter' && this.state.kind !== 'prompt') {
      // Prompt handles Enter via the input's own (keyup.enter) binding
      // so submitting from the input field also runs the validator.
      ev.preventDefault();
      this.confirm();
    }
  }
}
