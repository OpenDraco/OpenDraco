import '@angular/compiler';
import { describe, expect, it, vi } from 'vitest';
import { ChangeDetectorRef } from '@angular/core';
import { of } from 'rxjs';
import { convertToParamMap } from '@angular/router';

import { ResultsComponent } from './results.component';
import { ResultsStateService } from '../../services/results-state.service';
import { ApiService } from '../../services/api.service';
import { EvaluationRunService } from '../../services/evaluation-run.service';
import { DialogService } from '../../services/dialog.service';
import type { ResultInstance, ResultRun } from '../../models/types';

/** Build a ResultsComponent against in-memory stubs. The real
 * ResultsStateService is used (it's a thin POJO) so the test can read
 * the same `openJobs` / `groupByInstance` flags the picker would
 * receive via @Input. The api stub returns a small but representative
 * instances list; the route stub fires the deep-link query params
 * synchronously through `of(...)`. */
function makeResults(
  queryParams: Record<string, string> | undefined,
  instances: ResultInstance[],
): { app: ResultsComponent; state: ResultsStateService; revealSpy: ReturnType<typeof vi.fn> } {
  const api = {
    getResultInstances: vi.fn(() => of(instances)),
    getResultPrediction: vi.fn(() => of(null)),
    getResultPredictionLog: vi.fn(() => of({ exists: false, raw: '' })),
    getResultPredictionConfig: vi.fn(() => of({ exists: false, raw: '', path: '' })),
    getResultEvaluation: vi.fn(() => of(null)),
    getPaths: vi.fn(() => of({
      base_dir: '.',
      results_dir: 'results',
      predictions_dir: 'results/predictions',
      predictions_logs_dir: 'results/predictions/logs',
      evaluations_dir: 'results/evaluations',
      inference_logs_dir: 'evomas/logs/inference_logs',
    })),
  } as unknown as ApiService;
  const state = new ResultsStateService();
  // ChangeDetectorRef stub — `detectChanges` is what the reveal flow
  // calls to force a synchronous CD pass before the scroll fires.
  const cdr = { markForCheck: vi.fn(), detectChanges: vi.fn() } as unknown as ChangeDetectorRef;
  const router = { navigate: vi.fn() } as any;
  const route = { queryParamMap: of(convertToParamMap(queryParams ?? {})) } as any;
  const evalSvc = {} as EvaluationRunService;
  const dialog = {
    alert: vi.fn(),
    confirm: vi.fn(),
    prompt: vi.fn(),
  } as unknown as DialogService;

  const app = new ResultsComponent(api, state, cdr, router, route, evalSvc, dialog);

  // The picker is normally resolved via @ViewChild — in unit-test mode
  // it never instantiates, so we set it manually so the scroll-call
  // branch is exercised + observable.
  const revealSpy = vi.fn();
  (app as any).treePicker = { revealSelected: revealSpy };

  return { app, state, revealSpy };
}

function mkInstance(id: string, runs: { run_id: string }[]): ResultInstance {
  return {
    instance_id: id,
    subset: 'lite',
    split: 'dev',
    subsets: [['lite', 'dev']],
    predictions: [],
    evaluations: [],
    runs: runs.map(r => ({
      run_id: r.run_id,
      timestamp: null,
      prediction: null,
      evaluation: null,
      mtime: 0,
    } as ResultRun)),
  } as unknown as ResultInstance;
}

describe('ResultsComponent deep-link reveal', () => {
  it('opens the job-group for a runId-only deep-link and asks the picker to scroll', () => {
    vi.useFakeTimers();
    try {
      const instances = [
        mkInstance('sqlfluff__sqlfluff-1625', [
          { run_id: 'chain-4f7d9f56' },
          { run_id: 'star-deadbeef' },
        ]),
      ];
      const { app, state, revealSpy } = makeResults({ runId: 'chain-4f7d9f56' }, instances);

      app.ngOnInit();

      // selectInstance + selectRun resolved against the matching run.
      expect(state.selectedId).toBe('sqlfluff__sqlfluff-1625');
      expect(state.selectedRunId).toBe('chain-4f7d9f56');
      // `_revealRunInLeftPanel` opens the run's job group AND forces
      // grouped-by-run mode (so the expander is the one rendered).
      expect(state.groupByInstance).toBe(false);
      expect(state.openJobs.has('job/chain-4f7d9f56')).toBe(true);
      // The picker scroll-into-view is deferred via setTimeout(0);
      // run any pending timers and confirm the call landed.
      vi.runAllTimers();
      // selectInstance internally calls selectRun(firstRun.run_id),
      // then the deep-link's explicit selectRun(targetRun) fires too —
      // each path reveals via `_revealRunInLeftPanel`. We don't care
      // about the call count, only that the FINAL reveal landed.
      expect(revealSpy).toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('honours instanceId+runId together when both query params are present', () => {
    vi.useFakeTimers();
    try {
      const instances = [
        mkInstance('inst-a', [{ run_id: 'run-a-1' }, { run_id: 'run-a-2' }]),
        mkInstance('inst-b', [{ run_id: 'run-b-1' }]),
      ];
      const { app, state, revealSpy } = makeResults(
        { runId: 'run-a-2', instanceId: 'inst-a' },
        instances,
      );

      app.ngOnInit();

      expect(state.selectedId).toBe('inst-a');
      expect(state.selectedRunId).toBe('run-a-2');
      expect(state.openJobs.has('job/run-a-2')).toBe(true);
      vi.runAllTimers();
      // selectInstance internally calls selectRun(firstRun.run_id),
      // then the deep-link's explicit selectRun(targetRun) fires too —
      // each path reveals via `_revealRunInLeftPanel`. We don't care
      // about the call count, only that the FINAL reveal landed.
      expect(revealSpy).toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('uses a fresh Set reference for openJobs (so the picker @Input change-detects)', () => {
    vi.useFakeTimers();
    try {
      const instances = [mkInstance('inst-a', [{ run_id: 'run-a-1' }])];
      const { app, state } = makeResults({ runId: 'run-a-1' }, instances);
      const beforeRef = state.openJobs;

      app.ngOnInit();

      // The pre-existing Set reference is replaced, not mutated in
      // place. Mutation alone wouldn't dirty `[openJobs]` on the
      // tree picker — Angular's @Input check uses Object.is.
      expect(state.openJobs).not.toBe(beforeRef);
      vi.runAllTimers();
    } finally {
      vi.useRealTimers();
    }
  });

  it('reveals the new run_id when the header dropdown changes via selectRun', () => {
    vi.useFakeTimers();
    try {
      const instances = [
        mkInstance('inst-a', [{ run_id: 'run-a-1' }, { run_id: 'run-a-2' }]),
      ];
      // No deep-link this time — user is already on the page, picks
      // a different run from the top-panel dropdown. The reveal logic
      // hangs off `selectRun` so the left panel auto-expands the new
      // run's job-group without the user having to click into it.
      const { app, state, revealSpy } = makeResults({}, instances);
      app.ngOnInit();
      // Simulate the dropdown emitting a new value.
      app.selectRun('run-a-2');

      expect(state.selectedRunId).toBe('run-a-2');
      expect(state.openJobs.has('job/run-a-2')).toBe(true);
      expect(state.groupByInstance).toBe(false);
      vi.runAllTimers();
      expect(revealSpy).toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('clears the selection when only the runId is given and nothing matches', () => {
    vi.useFakeTimers();
    try {
      const instances = [mkInstance('inst-a', [{ run_id: 'run-a-1' }])];
      const { app, state, revealSpy } = makeResults({ runId: 'nope' }, instances);

      app.ngOnInit();

      // No selection happens, no group is opened, no scroll fires —
      // the page shows its empty state rather than silently picking
      // an unrelated row.
      expect(state.selectedId).toBeNull();
      expect(state.selectedRunId).toBeNull();
      expect(state.openJobs.size).toBe(0);
      vi.runAllTimers();
      expect(revealSpy).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('clears the selection when runId+instanceId are BOTH supplied but the pair does not exist', () => {
    vi.useFakeTimers();
    try {
      // The instance exists; the run does not. Without the precise-
      // pair guard the previous logic would have latched onto the
      // instance + its first run, which is the wrong result for a
      // stale deep-link.
      const instances = [
        mkInstance('custom-xiangfengyepan-evomas-test-instance-fcf59bc', [
          { run_id: 'star-deadbeef' },
        ]),
      ];
      const { app, state, revealSpy } = makeResults(
        {
          runId: 'chain2-d7fd42ff',
          instanceId: 'custom-xiangfengyepan-evomas-test-instance-fcf59bc',
        },
        instances,
      );

      app.ngOnInit();

      expect(state.selectedId).toBeNull();
      expect(state.selectedRunId).toBeNull();
      vi.runAllTimers();
      expect(revealSpy).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it('clears the selection when an instanceId-only deep-link does not match', () => {
    vi.useFakeTimers();
    try {
      const instances = [mkInstance('inst-a', [{ run_id: 'run-a-1' }])];
      const { app, state } = makeResults({ instanceId: 'inst-missing' }, instances);

      app.ngOnInit();

      expect(state.selectedId).toBeNull();
      expect(state.selectedRunId).toBeNull();
      vi.runAllTimers();
    } finally {
      vi.useRealTimers();
    }
  });
});
