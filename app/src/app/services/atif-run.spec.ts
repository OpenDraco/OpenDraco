import { describe, expect, it } from 'vitest';
import { AtifStep, AtifTrajectory } from '../models/types';
import { agentTimingsFromAtif, atifToEvents, parseAtifToRunInstance } from './atif-run';

const T = (s: number) => `2026-11-20T10:00:${String(s).padStart(2, '0')}.000Z`;

function dispatch(n: number, agent: string, inputs: Record<string, unknown>, ts: number,
                  end?: { delta: Record<string, unknown>; handoffs?: unknown[] }, activation = 1): AtifStep {
  const result: Record<string, unknown> = {
    source_call_id: `dispatch-${n}`,
    subagent_trajectory_ref: [{ trajectory_id: `${agent}#${activation}` }],
  };
  if (end) {
    result['content'] = 'summary';
    result['extra'] = { delta_keys: Object.keys(end.delta), delta: end.delta, handoffs: end.handoffs ?? [] };
  }
  return {
    step_id: n + 1, timestamp: T(ts), source: 'agent', llm_call_count: 0, message: `dispatch ${agent}`,
    tool_calls: [{ tool_call_id: `dispatch-${n}`, function_name: 'run_agent', arguments: { agent, inputs } }],
    observation: { results: [result as never] },
  };
}

function fixture(status = 'done'): AtifTrajectory {
  return {
    schema_version: 'ATIF-v1.8',
    session_id: 'chain-1',
    trajectory_id: 'chain-1.demo__demo-1',
    agent: { name: 'opendraco', version: '0.1.0' },
    steps: [
      { step_id: 1, timestamp: T(0), source: 'user', message: 'fix it' },
      dispatch(1, 'locator', {}, 1, {
        delta: { locator: 'foo.py' },
        handoffs: [{ to: 'patcher', summary: 'str(6 B)', preview: 'foo.py', timestamp: T(5) }],
      }),
      dispatch(2, 'patcher', { locator: 'foo.py' }, 6, { delta: { patcher: 'diff' } }),
    ],
    subagent_trajectories: [
      {
        schema_version: 'ATIF-v1.8', trajectory_id: 'locator#1', agent: { name: 'locator', version: '0.1.0' },
        steps: [
          { step_id: 1, timestamp: T(1), source: 'system', message: 'sys' },
          { step_id: 2, timestamp: T(1), source: 'user', message: 'usr' },
          {
            step_id: 3, timestamp: T(2), source: 'agent', llm_call_count: 1, message: 'Searching',
            reasoning_content: 'think',
            tool_calls: [{ tool_call_id: 'c1', function_name: 'search_code', arguments: { query: 'foo' } }],
            observation: { results: [{ source_call_id: 'c1', content: '["a.py", "b.py"]' }] },
          },
          { step_id: 4, timestamp: T(4), source: 'agent', llm_call_count: 1, message: 'Found it' },
        ],
      },
      {
        schema_version: 'ATIF-v1.8', trajectory_id: 'patcher#1', agent: { name: 'patcher', version: '0.1.0' },
        steps: [
          {
            step_id: 1, timestamp: T(7), source: 'agent', llm_call_count: 0, message: '',
            tool_calls: [{ tool_call_id: 'tool-1', function_name: 'apply_patch', arguments: { dry_run: false } }],
            observation: { results: [{ source_call_id: 'tool-1', content: '{"ok": true}' }] },
          },
          { step_id: 2, timestamp: T(9), source: 'agent', llm_call_count: 1, message: 'Patched' },
        ],
      },
    ],
    final_metrics: {
      total_prompt_tokens: 150, total_completion_tokens: 30,
      extra: { per_agent: { locator: { input: 100, output: 20, total: 120 }, patcher: { input: 50, output: 10, total: 60 } } },
    },
    extra: {
      instance_id: 'demo__demo-1', status, model_patch: status === 'done' ? 'diff --x' : undefined,
      error: status === 'error' ? { message: 'boom', traceback: 'tb' } : undefined,
    },
  };
}

describe('parseAtifToRunInstance', () => {
  it('renders one card per activation with thinking, responses, tools, inputs and hand-offs', () => {
    const inst = parseAtifToRunInstance(fixture());
    expect(inst.instance_id).toBe('demo__demo-1');
    expect(inst.status).toBe('done');
    expect(inst.finalPatch).toBe('diff --x');
    expect(inst.cards.map(c => c.agent)).toEqual(['locator', 'patcher']);
    const [loc, pat] = inst.cards;
    expect(loc.status).toBe('done');
    expect(loc.thinkingStream).toBe('think');
    expect(loc.responseStream).toBe('Searching\n\n─────\n\nFound it');
    expect(loc.toolCalls).toEqual([{ tool: 'search_code', argsPreview: 'query=foo', resultPreview: '2 items' }]);
    expect(loc.delta).toEqual({ locator: 'foo.py' });
    expect(loc.tokens).toEqual({ input: 100, output: 20, total: 120 });
    expect(pat.inputs).toEqual({ locator: 'foo.py' });
    expect(pat.incomingChips.map(c => [c.from, c.to, c.preview])).toEqual([['locator', 'patcher', 'foo.py']]);
    expect(pat.toolCalls).toEqual([{ tool: 'apply_patch', argsPreview: 'dry_run=false', resultPreview: 'ok=True' }]);
    expect(loc.durationMs).toBeUndefined();
  });

  it('keeps a queued instance empty', () => {
    const doc = fixture('queued');
    doc.steps = doc.steps.slice(0, 1);
    doc.subagent_trajectories = [];
    const inst = parseAtifToRunInstance(doc);
    expect(inst.status).toBe('queued');
    expect(inst.cards).toEqual([]);
  });

  it('leaves the open activation of a running instance running', () => {
    const doc = fixture('running');
    doc.steps[2] = dispatch(2, 'patcher', { locator: 'foo.py' }, 6);
    const inst = parseAtifToRunInstance(doc);
    expect(inst.status).toBe('running');
    expect(inst.cards.map(c => c.status)).toEqual(['done', 'running']);
  });

  it('shows the error of a failed instance', () => {
    const inst = parseAtifToRunInstance(fixture('error'));
    expect(inst.status).toBe('error');
    expect(inst.errorMsg).toBe('boom');
    expect(inst.errorTraceback).toBe('tb');
  });

  it('marks a cancelled instance', () => {
    expect(parseAtifToRunInstance(fixture('cancelled')).status).toBe('cancelled');
  });

  it('cuts previews like the backend does', () => {
    const doc = fixture();
    const step = doc.subagent_trajectories![0].steps[2];
    step.tool_calls![0].arguments = { query: 'q'.repeat(100), path: '/very/long/path/that/goes/on/and/on/file.py' };
    step.observation!.results[0].content = 'r'.repeat(200);
    const [tc] = parseAtifToRunInstance(doc).cards[0].toolCalls;
    expect(tc.argsPreview).toBe(`query=${'q'.repeat(40)}, path=…/on/file.py`);
    expect(tc.resultPreview).toBe('r'.repeat(80));
  });

  it('applies the node colours', () => {
    expect(parseAtifToRunInstance(fixture(), { locator: '#123456' }).cards[0].color).toBe('#123456');
  });
});

describe('atifToEvents', () => {
  it('starts with instance_start and ends with instance_done for a finished run', () => {
    const types = atifToEvents(fixture()).map(e => e.type);
    expect(types[0]).toBe('instance_start');
    expect(types[types.length - 1]).toBe('instance_done');
  });
});

describe('agentTimingsFromAtif', () => {
  it('sums each agent activation from its dispatch to its last step', () => {
    const timings = agentTimingsFromAtif(fixture());
    expect(timings.get('locator')).toBe(3000);
    expect(timings.get('patcher')).toBe(3000);
  });

  it('adds up repeated activations of one agent', () => {
    const doc = fixture();
    doc.steps.push(dispatch(3, 'locator', {}, 10, { delta: {} }, 2));
    doc.subagent_trajectories!.push({
      schema_version: 'ATIF-v1.8', trajectory_id: 'locator#2', agent: { name: 'locator', version: '0.1.0' },
      steps: [{ step_id: 1, timestamp: T(12), source: 'agent', llm_call_count: 1, message: 'again' }],
    });
    expect(agentTimingsFromAtif(doc).get('locator')).toBe(5000);
  });
});
