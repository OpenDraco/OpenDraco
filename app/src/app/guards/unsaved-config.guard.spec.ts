import '@angular/compiler';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { unsavedConfigGuard } from './unsaved-config.guard';
import { TopologyStateService } from '../services/topology-state.service';
import { DialogService } from '../services/dialog.service';
import type { TopologyComponent } from '../pages/topology/topology.component';

function fakeComponent(isLoadedConfig: boolean): TopologyComponent {
  return { isLoadedConfig } as unknown as TopologyComponent;
}

describe('unsavedConfigGuard', () => {
  let confirmSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [TopologyStateService, DialogService],
    });
    // Spy on the DialogService that the guard injects.
    confirmSpy = vi.spyOn(TestBed.inject(DialogService), 'confirm')
      .mockResolvedValue(true);
  });

  afterEach(() => {
    confirmSpy.mockRestore();
  });

  async function runGuard(
    component: TopologyComponent,
    nextUrl = '/inference',
  ): Promise<boolean> {
    // The guard's body now returns `Promise<boolean>` (it awaits the
    // DialogService prompt). The cast is still safe — no UrlTree /
    // Observable branches in this code path.
    const nextState = { url: nextUrl } as never;
    return (await TestBed.runInInjectionContext(() =>
      unsavedConfigGuard(
        component,
        null as never, null as never, nextState,
      ),
    )) as boolean;
  }

  it('returns true (no warning) when there are no unsaved edits', async () => {
    const svc = TestBed.inject(TopologyStateService);
    svc.dirty = false;
    const allowed = await runGuard(fakeComponent(true));
    expect(allowed).toBe(true);
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('returns true (no warning) when the active config is read-only', async () => {
    const svc = TestBed.inject(TopologyStateService);
    svc.dirty = true;
    svc.currentConfigName = 'chain';
    const allowed = await runGuard(fakeComponent(false));
    expect(allowed).toBe(true);
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('prompts the user when dirty + loaded config; "Stay" cancels navigation', async () => {
    const svc = TestBed.inject(TopologyStateService);
    svc.dirty = true;
    svc.currentConfigName = 'my-draft';
    confirmSpy.mockResolvedValueOnce(false);
    expect(await runGuard(fakeComponent(true))).toBe(false);
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    // The dialog payload includes the config name in its message.
    const arg = confirmSpy.mock.calls[0][0] as { message?: string };
    expect(arg.message).toContain('my-draft');
  });

  it('"Leave" returns false (Angular nav cancelled — browser does the real one)', async () => {
    const svc = TestBed.inject(TopologyStateService);
    svc.dirty = true;
    svc.currentConfigName = 'my-draft';
    confirmSpy.mockResolvedValueOnce(true);
    // The guard's contract on accept is: cancel Angular's pending
    // navigation (return false) and kick off a full-page reload to the
    // destination URL via `window.location.assign`. We can't stub
    // `window.location.assign` in jsdom — the property is read-only —
    // so we only verify the contract surface that's testable: the
    // returned boolean. The `assign()` call itself is exercised by
    // the manual smoke-test in the plan's verification section.
    expect(await runGuard(fakeComponent(true), '/inference')).toBe(false);
    expect(confirmSpy).toHaveBeenCalledTimes(1);
  });
});
