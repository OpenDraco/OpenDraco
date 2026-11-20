import { describe, expect, it, vi } from 'vitest';
import { of } from 'rxjs';
import { InferenceRunService } from './inference-run.service';
import type { ApiService } from './api.service';
import type { AtifTrajectory } from '../models/types';

const IDS = ['a__a-1', 'b__b-2'];

function doc(iid: string, status: string): AtifTrajectory {
  return {
    schema_version: 'ATIF-v1.8', session_id: 'chain-1',
    agent: { name: 'opendraco', version: '0.1.0' },
    steps: [{ step_id: 1, source: 'user', message: 'fix' }],
    extra: { instance_id: iid, status },
  };
}

type Answer = { trajectory: AtifTrajectory | null; mtime: number; unchanged: boolean; is_running: boolean };

/** A service whose API reports an active run and answers trajectory polls
 * from `answers` (one queue per instance). Polling is driven by hand. */
function makeService(answers: Record<string, Answer[]>) {
  const getInferenceTrajectory = vi.fn((_runDir: string, iid: string, _since?: number) => {
    const queue = answers[iid];
    return of(queue.length > 1 ? queue.shift()! : queue[0]);
  });
  const api = {
    getActiveInference: vi.fn(() => of({
      active: true, run_id: 'chain-1', config_label: 'chain', instance_ids: IDS,
      run_dir: 'prediction-chain-1', started_at: 1,
    })),
    getInferenceTrajectory,
  } as unknown as ApiService;
  vi.useFakeTimers();
  const svc = new InferenceRunService(api);
  return { svc, getInferenceTrajectory };
}

describe('InferenceRunService reattach', () => {
  it('rebuilds every instance from its trajectory', () => {
    try {
      const { svc, getInferenceTrajectory } = makeService({
        [IDS[0]]: [{ trajectory: doc(IDS[0], 'done'), mtime: 1, unchanged: false, is_running: true }],
        [IDS[1]]: [{ trajectory: doc(IDS[1], 'running'), mtime: 1, unchanged: false, is_running: true }],
      });
      vi.advanceTimersByTime(0);
      expect(getInferenceTrajectory).toHaveBeenCalledWith('prediction-chain-1', IDS[0], undefined);
      expect(svc.instances.map(i => [i.instance_id, i.status, i.runId])).toEqual([
        [IDS[0], 'done', 'chain-1'], [IDS[1], 'running', 'chain-1'],
      ]);
      expect(svc.status).toBe('running');
    } finally {
      vi.useRealTimers();
    }
  });

  it('skips re-parse when mtime is unchanged', () => {
    try {
      const { svc, getInferenceTrajectory } = makeService({
        [IDS[0]]: [
          { trajectory: doc(IDS[0], 'running'), mtime: 5, unchanged: false, is_running: true },
          { trajectory: null, mtime: 5, unchanged: true, is_running: true },
        ],
        [IDS[1]]: [
          { trajectory: doc(IDS[1], 'queued'), mtime: 5, unchanged: false, is_running: true },
          { trajectory: null, mtime: 5, unchanged: true, is_running: true },
        ],
      });
      vi.advanceTimersByTime(0);
      const first = svc.instances[0];
      vi.advanceTimersByTime(1500);
      expect(getInferenceTrajectory).toHaveBeenLastCalledWith('prediction-chain-1', IDS[1], 5);
      expect(svc.instances[0]).toBe(first);  // not rebuilt
      expect(svc.instances[0].status).toBe('running');
    } finally {
      vi.useRealTimers();
    }
  });

  it('ends a reattached run as cancelled when an instance was cancelled', () => {
    try {
      const { svc } = makeService({
        [IDS[0]]: [{ trajectory: doc(IDS[0], 'done'), mtime: 1, unchanged: false, is_running: false }],
        [IDS[1]]: [{ trajectory: doc(IDS[1], 'cancelled'), mtime: 1, unchanged: false, is_running: false }],
      });
      vi.advanceTimersByTime(0);
      expect(svc.status).toBe('cancelled');
      expect(svc.statusMsg).toBe('Cancelled by user');
    } finally {
      vi.useRealTimers();
    }
  });

  it('ends a reattached run as failed when an instance errored', () => {
    try {
      const failed = doc(IDS[1], 'error');
      failed.extra = { ...failed.extra, error: { message: 'boom', traceback: 'tb' } };
      const { svc } = makeService({
        [IDS[0]]: [{ trajectory: doc(IDS[0], 'done'), mtime: 1, unchanged: false, is_running: false }],
        [IDS[1]]: [{ trajectory: failed, mtime: 1, unchanged: false, is_running: false }],
      });
      vi.advanceTimersByTime(0);
      expect(svc.status).toBe('error');
      expect(svc.errorMsg).toBe('boom');
    } finally {
      vi.useRealTimers();
    }
  });

  it('ends a fully finished reattached run as complete', () => {
    try {
      const { svc } = makeService({
        [IDS[0]]: [{ trajectory: doc(IDS[0], 'done'), mtime: 1, unchanged: false, is_running: false }],
        [IDS[1]]: [{ trajectory: doc(IDS[1], 'done'), mtime: 1, unchanged: false, is_running: false }],
      });
      vi.advanceTimersByTime(0);
      expect(svc.statusMsg).toBe('Run complete (2 instances)');
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps cards the user collapsed when the trajectory grows', () => {
    const withAgent = (n: number): AtifTrajectory => ({
      ...doc(IDS[0], 'running'),
      steps: [
        { step_id: 1, source: 'user', message: 'fix' },
        {
          step_id: 2, source: 'agent', llm_call_count: 0, message: 'dispatch locator',
          tool_calls: [{ tool_call_id: 'dispatch-1', function_name: 'run_agent', arguments: { agent: 'locator', inputs: {} } }],
          observation: { results: [{ source_call_id: 'dispatch-1', subagent_trajectory_ref: [{ trajectory_id: 'locator#1' }] }] },
        },
      ],
      subagent_trajectories: [{
        schema_version: 'ATIF-v1.8', trajectory_id: 'locator#1', agent: { name: 'locator', version: '0.1.0' },
        steps: Array.from({ length: n }, (_, k) => ({ step_id: k + 1, source: 'agent' as const, message: `m${k}` })),
      }],
    });
    try {
      const { svc } = makeService({
        [IDS[0]]: [
          { trajectory: withAgent(1), mtime: 1, unchanged: false, is_running: true },
          { trajectory: withAgent(2), mtime: 2, unchanged: false, is_running: true },
        ],
        [IDS[1]]: [{ trajectory: null, mtime: 1, unchanged: true, is_running: true }],
      });
      vi.advanceTimersByTime(0);
      svc.instances[0].cards[0].expanded = false;
      vi.advanceTimersByTime(1500);
      expect(svc.instances[0].cards[0].responseStream).toContain('m1');
      expect(svc.instances[0].cards[0].expanded).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it('stops polling when the run ends', () => {
    try {
      const { svc, getInferenceTrajectory } = makeService({
        [IDS[0]]: [{ trajectory: doc(IDS[0], 'done'), mtime: 1, unchanged: false, is_running: false }],
        [IDS[1]]: [{ trajectory: doc(IDS[1], 'done'), mtime: 1, unchanged: false, is_running: false }],
      });
      vi.advanceTimersByTime(0);
      expect(svc.status).toBe('done');
      const n = getInferenceTrajectory.mock.calls.length;
      vi.advanceTimersByTime(6000);
      expect(getInferenceTrajectory.mock.calls.length).toBe(n);
    } finally {
      vi.useRealTimers();
    }
  });
});
