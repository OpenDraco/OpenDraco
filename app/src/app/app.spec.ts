import '@angular/compiler';
import { describe, expect, it, vi } from 'vitest';
import { ChangeDetectorRef } from '@angular/core';
import { of, throwError } from 'rxjs';
import { App } from './app';
import { ApiService } from './services/api.service';
import { TopologyStateService } from './services/topology-state.service';
import { DialogService } from './services/dialog.service';
import type { ConfigSummary, UnifiedConfig } from './models/types';

type ApiMock = Record<string, unknown> & { getHealth: ReturnType<typeof vi.fn>; apiHost: string };

function makeApp(
  getHealth = () => of({ status: 'ok' }),
  extras: Record<string, unknown> = {},
): { app: App; api: ApiMock; svc: TopologyStateService } {
  const api: ApiMock = {
    getHealth: vi.fn(getHealth),
    apiHost: 'localhost:8000',
    ...extras,
  };
  const cdr = { markForCheck: vi.fn() } as unknown as ChangeDetectorRef;
  const svc = new TopologyStateService();
  const dialog = new DialogService();
  const app = new App(api as unknown as ApiService, svc, cdr, dialog);
  return { app, api, svc };
}

describe('App health probe', () => {
  it('flips apiOnline to true on a successful probe', () => {
    const { app } = makeApp();
    app.ngOnInit();
    expect(app.apiOnline).toBe(true);
    expect(app.apiHost).toBe('localhost:8000');
    app.ngOnDestroy();
  });

  it('flips apiOnline to false on a failed probe', () => {
    const { app } = makeApp(() => throwError(() => new Error('down')));
    app.ngOnInit();
    expect(app.apiOnline).toBe(false);
    app.ngOnDestroy();
  });
});

describe('App "Create from template" flow', () => {
  function configList(): ConfigSummary[] {
    return [
      { stem: 'chain',  id: 'chain',  description: '', source: 'predefined' },
      { stem: 'hybrid', id: 'hybrid', description: '', source: 'predefined' },
      // Loaded entries are now eligible too — the dropdown groups
      // them under a separate "Loaded" header so the source stays
      // distinguishable. The user can fork either kind.
      { stem: 'my-draft', id: 'my-draft', description: '', source: 'loaded' },
    ];
  }

  it('openCreateFromTemplate exposes every config — predefined + loaded', () => {
    const { app, svc } = makeApp();
    svc.predefinedConfigs = configList();
    app.openCreateFromTemplate();
    expect(app.templateDialogOpen).toBe(true);
    expect(app.templateOptions.map(o => o.stem)).toEqual(['chain', 'hybrid', 'my-draft']);
    // No active config → default to the first PREDEFINED option (the
    // shipped templates are the canonical starting point); loaded
    // entries land second and require an explicit pick.
    expect(app.templateChoice).toBe('chain');
    expect(app.templateNewName).toBe('');
  });

  it('templateSelectGroups groups configs by source for the dropdown', () => {
    const { app, svc } = makeApp();
    svc.predefinedConfigs = configList();
    app.openCreateFromTemplate();
    const groups = app.templateSelectGroups;
    expect(groups.map(g => g.label)).toEqual(['Predefined', 'Loaded']);
    expect((groups[0].items as { value: string }[]).map(i => i.value)).toEqual(['chain', 'hybrid']);
    expect((groups[1].items as { value: string }[]).map(i => i.value)).toEqual(['my-draft']);
  });

  it('openCreateFromTemplate defaults to the currently-loaded config (any source)', () => {
    const { app, svc } = makeApp();
    svc.predefinedConfigs = configList();
    svc.currentConfigName = 'hybrid';
    app.openCreateFromTemplate();
    expect(app.templateChoice).toBe('hybrid');
    // The active loaded config is now a valid template too.
    svc.currentConfigName = 'my-draft';
    app.openCreateFromTemplate();
    expect(app.templateChoice).toBe('my-draft');
  });

  it('confirmCreateFromTemplate fetches the template, rewrites id, and persists', () => {
    const tplFromBackend = {
      id: 'chain', description: 'orig', entry: 'a', end: 'b',
      edges: [{ from: 'a', to: 'b' }], agents: { a: {}, b: {} },
    } as unknown as UnifiedConfig;
    const getConfig = vi.fn(() => of(tplFromBackend));
    // saveLoadedConfig succeeds; refreshConfigsAfterImport then calls
    // getConfigs() which we stub with the new entry appended.
    const saveLoadedConfig = vi.fn(() => of({ ok: true, stem: 'my-clone', path: '/loaded/my-clone.json' }));
    const getConfigs = vi.fn(() => of([
      ...configList(),
      { stem: 'my-clone', id: 'my-clone', description: 'orig', source: 'loaded' },
    ] as ConfigSummary[]));

    const { app, svc } = makeApp(undefined, { getConfig, saveLoadedConfig, getConfigs });
    svc.predefinedConfigs = configList();
    app.openCreateFromTemplate();
    app.templateChoice = 'chain';
    app.templateNewName = 'my-clone';
    app.confirmCreateFromTemplate();

    expect(getConfig).toHaveBeenCalledWith('chain');
    // saveLoadedConfig must be called with the rewritten `id` matching
    // the new name (loader enforces id == filename stem).
    expect(saveLoadedConfig).toHaveBeenCalledWith(
      'my-clone',
      expect.objectContaining({ id: 'my-clone' }),
      false,
    );
    expect(app.templateDialogOpen).toBe(false);
    expect(svc.currentConfigName).toBe('my-clone');
  });

  it('confirmCreateFromTemplate rejects an empty name', () => {
    const getConfig = vi.fn();
    const { app, svc } = makeApp(undefined, { getConfig });
    svc.predefinedConfigs = configList();
    app.openCreateFromTemplate();
    app.templateNewName = '   ';
    app.confirmCreateFromTemplate();
    expect(app.templateError).toContain('empty');
    expect(getConfig).not.toHaveBeenCalled();
  });

  it('confirmCreateFromTemplate rejects names colliding with a predefined config', () => {
    const getConfig = vi.fn();
    const { app, svc } = makeApp(undefined, { getConfig });
    svc.predefinedConfigs = configList();
    app.openCreateFromTemplate();
    app.templateNewName = 'hybrid';  // already a predefined stem
    app.confirmCreateFromTemplate();
    expect(app.templateError).toContain('collides');
    expect(getConfig).not.toHaveBeenCalled();
  });
});
