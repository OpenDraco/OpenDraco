import { inject } from '@angular/core';
import { CanDeactivateFn } from '@angular/router';
import { TopologyStateService } from '../services/topology-state.service';
import { DialogService } from '../services/dialog.service';
import type { TopologyComponent } from '../pages/topology/topology.component';

/**
 * Navigation guard that warns the user before leaving the Topology
 * page when there are in-memory edits to a writable (`loaded`) config
 * that haven't been saved to disk yet.
 *
 * Why guard navigation and NOT also block? Predefined configs are
 * read-only — there's nothing to lose; we only intervene when the
 * config could actually be persisted. The guard short-circuits to
 * `true` in every other case so the user never sees a useless confirm.
 *
 * When the user confirms losing changes, the guard does a full
 * browser navigation (`window.location.assign(nextState.url)`) rather
 * than letting Angular's router proceed. The full reload wipes the
 * in-memory `TopologyStateService` state (dirty flag + mutated
 * `currentConfig`) so the chips on the topology page reflect the
 * persisted-on-disk version when the user returns — without that,
 * the same dirty/unvalidated chips would still show because the
 * mutations live on a singleton service that survives route changes.
 *
 * Pair this with the `beforeunload` listener `TopologyComponent`
 * installs in `ngOnInit` for the browser-tab-close case (the router
 * guard only catches in-app navigation).
 */
export const unsavedConfigGuard: CanDeactivateFn<TopologyComponent> = async (
  component, _currentRoute, _currentState, nextState,
) => {
  const svc = inject(TopologyStateService);
  if (!svc.dirty) return true;
  if (!component.isLoadedConfig) return true;
  const dialog = inject(DialogService);
  const accepted = await dialog.confirm({
    title: 'Discard unsaved changes?',
    message:
      `You have unsaved changes in "${svc.currentConfigName}". ` +
      `Leave the page and lose them?`,
    okLabel: 'Discard',
    danger: true,
  });
  if (!accepted) return false;
  // User opted to discard their edits. Clear `dirty` FIRST so the
  // `beforeunload` listener `TopologyComponent` installed doesn't
  // double-prompt the user with the browser's native "leave site?"
  // dialog as the page unloads. Then hard-reload to the destination:
  // the singleton `TopologyStateService` is wiped on reload, so the
  // topology chips reflect the persisted-on-disk version when the
  // user returns. Returning `false` cancels Angular's pending nav —
  // the browser does the real one via `window.location.assign`.
  svc.dirty = false;
  window.location.assign(nextState.url);
  return false;
};
