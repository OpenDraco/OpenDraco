/**
 * Promise-based replacement for `window.alert / .confirm / .prompt`.
 *
 * The browser dialogs are intrusive, can't be styled, and block the
 * whole tab — this service swaps them out for the same `modal-card`
 * shell the topology page already uses for Save-failed / Save-config /
 * Create-from-template. A single `<app-dialog-host>` is mounted at the
 * root of `app.html`; every page just injects this service and awaits.
 */

import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

export interface AlertOptions {
  title: string;
  /** Plain-text body. Long backend reasons render inside a monospace
   * `<pre>` block — pass them via `detail` instead so they wrap and
   * scroll without pushing the OK button off-screen. */
  message?: string;
  /** Pre-formatted error / detail text. Rendered in a monospace block. */
  detail?: string;
  /** Optional OK button label; defaults to "OK". */
  okLabel?: string;
  /** Visual variant — `'danger'` paints the icon + title red. */
  variant?: 'info' | 'danger';
}

export interface ConfirmOptions {
  title: string;
  message?: string;
  detail?: string;
  /** Defaults to "OK". */
  okLabel?: string;
  /** Defaults to "Cancel". */
  cancelLabel?: string;
  /** When true the confirm button uses the danger styling (deletes, etc). */
  danger?: boolean;
}

export interface PromptOptions {
  title: string;
  message?: string;
  /** Pre-filled value for the input. */
  defaultValue?: string;
  /** Placeholder when the input is empty. */
  placeholder?: string;
  okLabel?: string;
  cancelLabel?: string;
  /** Synchronous client-side check. Return a string to render as an
   * inline error and keep the dialog open; return null to accept. */
  validate?: (value: string) => string | null;
  /** When provided, the prompt renders a `<select>` over these options
   * instead of a free-text `<input>`. `defaultValue` should match one
   * of them. */
  selectOptions?: { value: string; label: string }[];
}

export type DialogKind = 'alert' | 'confirm' | 'prompt';

export interface DialogState {
  kind: DialogKind;
  title: string;
  message?: string;
  detail?: string;
  okLabel: string;
  cancelLabel?: string;
  danger?: boolean;
  variant?: 'info' | 'danger';
  placeholder?: string;
  defaultValue?: string;
  validate?: (value: string) => string | null;
  selectOptions?: { value: string; label: string }[];
  resolve: (value: unknown) => void;
}

@Injectable({ providedIn: 'root' })
export class DialogService {
  private readonly subject = new BehaviorSubject<DialogState | null>(null);
  /** Current dialog state — the host subscribes; null hides the modal. */
  readonly state$ = this.subject.asObservable();

  /** Quick "OK" message. Resolves when the user dismisses. */
  alert(opts: AlertOptions): Promise<void> {
    return new Promise(resolve => {
      this.subject.next({
        kind: 'alert',
        title: opts.title,
        message: opts.message,
        detail: opts.detail,
        okLabel: opts.okLabel ?? 'OK',
        variant: opts.variant,
        resolve: () => resolve(),
      });
    });
  }

  /** Yes / No prompt. Resolves to `true` for OK, `false` for Cancel /
   * backdrop click / Escape. */
  confirm(opts: ConfirmOptions): Promise<boolean> {
    return new Promise(resolve => {
      this.subject.next({
        kind: 'confirm',
        title: opts.title,
        message: opts.message,
        detail: opts.detail,
        okLabel: opts.okLabel ?? 'OK',
        cancelLabel: opts.cancelLabel ?? 'Cancel',
        danger: opts.danger,
        resolve: (v: unknown) => resolve(v === true),
      });
    });
  }

  /** Text input. Resolves with the entered string, or `null` on Cancel /
   * dismissal — matches the legacy `window.prompt` contract. */
  prompt(opts: PromptOptions): Promise<string | null> {
    return new Promise(resolve => {
      this.subject.next({
        kind: 'prompt',
        title: opts.title,
        message: opts.message,
        defaultValue: opts.defaultValue ?? '',
        placeholder: opts.placeholder,
        validate: opts.validate,
        selectOptions: opts.selectOptions,
        okLabel: opts.okLabel ?? 'OK',
        cancelLabel: opts.cancelLabel ?? 'Cancel',
        resolve: (v: unknown) => resolve(typeof v === 'string' ? v : null),
      });
    });
  }

  /** Internal — called by the host on confirm / cancel / dismiss. */
  resolveCurrent(value: unknown): void {
    const cur = this.subject.value;
    if (!cur) return;
    this.subject.next(null);
    cur.resolve(value);
  }
}
