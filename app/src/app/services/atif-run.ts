import { AtifObservationResult, AtifStep, AtifTrajectory, InferenceEvent } from '../models/types';
import { RunInstance, applyEventToInstance, newRunInstance } from './inference-run.service';

/** Reading OpenDraco's ATIF run log into the run view.
 *
 * A trajectory is turned into the same event vocabulary the live SSE stream
 * uses (`atifToEvents`), so the one reducer (`applyEventToInstance`) renders
 * both a live run and a stored one. */

const PATH_KEYS = new Set(['path', 'file_path', 'directory', 'repo_path']);
const SKIP_ARGS = new Set(['patch_str', 'with_line_numbers', 'max_chars']);

function text(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    return value
      .map(p => (p && typeof p === 'object' && (p as { type?: string }).type === 'text'
        ? String((p as { text?: string }).text ?? '') : ''))
      .filter(Boolean)
      .join('\n');
  }
  return '';
}

/** Python `str()` of a JSON value, so previews read like the backend's. */
function pyStr(value: unknown): string {
  if (value === true) return 'True';
  if (value === false) return 'False';
  if (value === null || value === undefined) return 'None';
  return typeof value === 'string' ? value : JSON.stringify(value);
}

/** Same rules as `_args_preview` in `api/routers/inference.py`. */
export function argsPreview(args: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(args ?? {})) {
    if (SKIP_ARGS.has(k)) continue;
    let val = typeof v === 'string' ? v : JSON.stringify(v);
    if (PATH_KEYS.has(k) && val.length > 35) {
      const segs = val.replace(/\\/g, '/').replace(/\/+$/, '').split('/');
      val = '…/' + segs.slice(-2).join('/');
    } else {
      val = val.slice(0, 40);
    }
    parts.push(`${k}=${val}`);
  }
  return parts.join(', ');
}

/** Same rules as `_result_preview` in `api/routers/inference.py`, applied
 * to the stored (stringified) result. */
export function resultPreview(content: string): string {
  let parsed: unknown;
  try { parsed = JSON.parse(content); } catch { parsed = undefined; }
  if (Array.isArray(parsed)) return `${parsed.length} items`;
  if (parsed && typeof parsed === 'object') {
    const obj = parsed as Record<string, unknown>;
    if ('ok' in obj || 'applied' in obj) return `ok=${pyStr('ok' in obj ? obj['ok'] : obj['applied'])}`;
  }
  return content.slice(0, 80);
}

function subIndex(doc: AtifTrajectory): Map<string, AtifTrajectory> {
  const out = new Map<string, AtifTrajectory>();
  for (const sub of doc.subagent_trajectories ?? []) {
    if (sub.trajectory_id) out.set(sub.trajectory_id, sub);
  }
  return out;
}

function dispatchResult(step: AtifStep): AtifObservationResult | undefined {
  return step.observation?.results?.find(r => r.subagent_trajectory_ref?.length);
}

function subagentEvents(agent: string, sub: AtifTrajectory): InferenceEvent[] {
  const events: InferenceEvent[] = [];
  for (const step of sub.steps ?? []) {
    if (step.source !== 'agent') continue;
    if (step.reasoning_content) events.push({ type: 'thinking_chunk', agent, chunk: step.reasoning_content });
    const message = text(step.message);
    if (message) events.push({ type: 'response', agent, content: message });
    const results = new Map((step.observation?.results ?? []).map(r => [r.source_call_id ?? '', r]));
    for (const call of step.tool_calls ?? []) {
      events.push({
        type: 'tool_call', agent, tool: call.function_name,
        args_preview: argsPreview(call.arguments),
        result_preview: resultPreview(text(results.get(call.tool_call_id)?.content)),
      });
    }
  }
  return events;
}

/** The live-event sequence that renders this trajectory. */
export function atifToEvents(doc: AtifTrajectory): InferenceEvent[] {
  const extra = (doc.extra ?? {}) as Record<string, unknown>;
  const status = String(extra['status'] ?? 'done');
  const iid = String(extra['instance_id'] ?? '');
  if (status === 'queued') return [];
  const events: InferenceEvent[] = [{ type: 'instance_start', instance_id: iid }];
  const subs = subIndex(doc);
  for (const step of doc.steps ?? []) {
    const call = step.tool_calls?.[0];
    if (step.source !== 'agent' || call?.function_name !== 'run_agent') continue;
    const agent = String(call.arguments?.['agent'] ?? 'unknown');
    events.push({ type: 'agent_input', agent, inputs: (call.arguments?.['inputs'] as Record<string, unknown>) ?? {} });
    const result = dispatchResult(step);
    const sub = subs.get(result?.subagent_trajectory_ref?.[0]?.trajectory_id ?? '');
    if (sub) events.push(...subagentEvents(agent, sub));
    const end = result?.extra as Record<string, unknown> | undefined;
    if (!end) continue; // still running
    events.push({ type: 'agent_event', agent, delta: (end['delta'] as Record<string, unknown>) ?? {} });
    for (const h of (end['handoffs'] as Array<Record<string, unknown>>) ?? []) {
      events.push({
        type: 'handoff', from: agent, to: String(h['to'] ?? ''),
        summary: String(h['summary'] ?? ''), preview: String(h['preview'] ?? ''),
        keys: (end['delta_keys'] as string[]) ?? [], timestamp: String(h['timestamp'] ?? ''),
      });
    }
  }
  const perAgent = (doc.final_metrics?.extra?.['per_agent'] ?? {}) as Record<string, Record<string, number>>;
  for (const [agent, t] of Object.entries(perAgent)) {
    events.push({ type: 'agent_tokens', agent, input: t['input'] ?? 0, output: t['output'] ?? 0, total: t['total'] ?? 0 } as InferenceEvent);
  }
  if (status === 'done') {
    events.push({ type: 'instance_done', instance_id: iid, patch: String(extra['model_patch'] ?? ''), run_id: doc.session_id });
  } else if (status === 'error') {
    const err = (extra['error'] ?? {}) as Record<string, unknown>;
    events.push({ type: 'error', message: String(err['message'] ?? ''), traceback: String(err['traceback'] ?? '') });
  }
  return events;
}

/** One instance's stored trajectory as the run view's `RunInstance`. */
export function parseAtifToRunInstance(
  doc: AtifTrajectory,
  nodeColors: Record<string, string> = {},
): RunInstance {
  const extra = (doc.extra ?? {}) as Record<string, unknown>;
  const inst = newRunInstance(String(extra['instance_id'] ?? ''), 'queued', doc.session_id ?? '');
  for (const ev of atifToEvents(doc)) applyEventToInstance(inst, ev, nodeColors);
  const status = String(extra['status'] ?? 'done');
  if (['queued', 'running', 'done', 'error', 'cancelled'].includes(status)) {
    inst.status = status as RunInstance['status'];
  }
  // The reducer timed cards with the parse-time clock; real timings come
  // from `agentTimingsFromAtif` via `applyAgentTimingsToInstance`.
  for (const card of inst.cards) {
    card.durationMs = undefined;
    card.startedAt = undefined;
  }
  return inst;
}

function ms(ts: string | undefined): number | null {
  if (!ts) return null;
  const t = Date.parse(ts);
  return Number.isFinite(t) ? t : null;
}

/** Per agent, the summed time of its activations: from the dispatch step to
 * the activation's last recorded step. */
export function agentTimingsFromAtif(doc: AtifTrajectory): Map<string, number> {
  const out = new Map<string, number>();
  const subs = subIndex(doc);
  for (const step of doc.steps ?? []) {
    const call = step.tool_calls?.[0];
    if (call?.function_name !== 'run_agent') continue;
    const agent = String(call.arguments?.['agent'] ?? 'unknown');
    const sub = subs.get(dispatchResult(step)?.subagent_trajectory_ref?.[0]?.trajectory_id ?? '');
    const start = ms(step.timestamp);
    const stamps = (sub?.steps ?? []).map(s => ms(s.timestamp)).filter((t): t is number => t != null);
    if (start == null || stamps.length === 0) continue;
    out.set(agent, (out.get(agent) ?? 0) + Math.max(0, Math.max(...stamps) - start));
  }
  return out;
}
