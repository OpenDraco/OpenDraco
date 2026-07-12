import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  UnifiedConfig, ConfigSummary, Instance, InferenceEvent, EvalEvent,
  ResultInstance, ResultPrediction, ResultEvaluation, ToolDescriptor,
  AgentType, AgentVariant, PredictionInspection, OllamaModel,
  ConfigHistoryEntry, ConfigRunMatch, EvomasPaths,
} from '../models/types';

const BASE = 'http://localhost:8000/api';

@Injectable({ providedIn: 'root' })
export class ApiService {
  constructor(private http: HttpClient) {}

  // ─── Health ───────────────────────────────────────────────────────
  getHealth(): Observable<{ status: string }> {
    return this.http.get<{ status: string }>(`${BASE}/health`);
  }

  /** Resolved on-disk paths the backend uses for the current RESULTS_DIR.
   * Used by user-facing strings (Evaluation page empty hint, file-picker
   * tooltips, "log lives under …" hints) so the displayed path tracks
   * whatever the user set in `evomas/.env` / `api/.env` instead of the
   * legacy `results/` literal. Returned as repo-relative POSIX strings. */
  getPaths(): Observable<EvomasPaths> {
    return this.http.get<EvomasPaths>(`${BASE}/paths`);
  }

  /** `host:port` portion of BASE. */
  get apiHost(): string {
    return BASE.replace(/\/?api\/?$/, '').replace(/^https?:\/\//, '');
  }

  // ─── Models ───────────────────────────────────────────────────────
  getModels(): Observable<OllamaModel[]> {
    return this.http.get<OllamaModel[]>(`${BASE}/models`);
  }

  // ─── MCP tools ────────────────────────────────────────────────────
  getTools(): Observable<ToolDescriptor[]> {
    return this.http.get<ToolDescriptor[]>(`${BASE}/tools`);
  }

  // ─── Agent types ──────────────────────────────────────────────────
  getAgentTypes(): Observable<AgentType[]> {
    return this.http.get<AgentType[]>(`${BASE}/agent-types`);
  }

  /** Variants flat-keyed by AGENT_TYPE. First entry per bucket is the
   * EvoMas built-in (Topology dropdown default). */
  getAgentVariants(): Observable<Record<string, AgentVariant[]>> {
    return this.http.get<Record<string, AgentVariant[]>>(`${BASE}/agent-variants`);
  }

  // ─── Unified Configs ──────────────────────────────────────────────
  getConfigs(): Observable<ConfigSummary[]> {
    return this.http.get<ConfigSummary[]>(`${BASE}/configs`);
  }

  getConfig(name: string): Observable<UnifiedConfig> {
    return this.http.get<UnifiedConfig>(`${BASE}/configs/${name}`);
  }

  /** 409 on name collision — retry with `replace: true` to overwrite.
   * Predefined-stem collisions always fail. */
  saveLoadedConfig(name: string, data: unknown, replace = false): Observable<{ ok: boolean; stem: string; path: string }> {
    return this.http.post<{ ok: boolean; stem: string; path: string }>(
      `${BASE}/configs/loaded`, { name, data, replace },
    );
  }

  renameLoadedConfig(name: string, newName: string): Observable<{ ok: boolean; stem: string }> {
    return this.http.patch<{ ok: boolean; stem: string }>(
      `${BASE}/configs/loaded/${encodeURIComponent(name)}`, { new_name: newName },
    );
  }

  deleteLoadedConfig(name: string): Observable<{ ok: boolean; stem: string }> {
    return this.http.delete<{ ok: boolean; stem: string }>(
      `${BASE}/configs/loaded/${encodeURIComponent(name)}`,
    );
  }

  /** Newest-first commit log for a loaded config. */
  getConfigHistory(name: string): Observable<{ entries: ConfigHistoryEntry[] }> {
    return this.http.get<{ entries: ConfigHistoryEntry[] }>(
      `${BASE}/configs/loaded/${encodeURIComponent(name)}/history`,
    );
  }

  /** Raw `<name>.json` contents at `sha`. */
  getConfigAtSha(name: string, sha: string): Observable<{ sha: string; content: string }> {
    return this.http.get<{ sha: string; content: string }>(
      `${BASE}/configs/loaded/${encodeURIComponent(name)}/history/${encodeURIComponent(sha)}`,
    );
  }

  /** Runs whose recorded `config_sha` matches — drives the "N runs" pill. */
  getRunsForConfigSha(name: string, sha: string): Observable<{ matches: ConfigRunMatch[] }> {
    return this.http.get<{ matches: ConfigRunMatch[] }>(
      `${BASE}/configs/loaded/${encodeURIComponent(name)}/history/${encodeURIComponent(sha)}/runs`,
    );
  }

  /** Drop one commit; descendants get rewritten SHAs. */
  deleteConfigHistoryEntry(name: string, sha: string): Observable<{ ok: boolean; new_head: string }> {
    return this.http.delete<{ ok: boolean; new_head: string }>(
      `${BASE}/configs/loaded/${encodeURIComponent(name)}/history/${encodeURIComponent(sha)}`,
    );
  }

  /** Drop every commit touching `<name>.json`. Other configs' history is
   * preserved (SHAs may be rewritten but their content + timeline survive).
   * The working-tree JSON for `name` is kept so the loader still finds it. */
  clearConfigHistory(name: string): Observable<{ ok: boolean; stem: string }> {
    return this.http.delete<{ ok: boolean; stem: string }>(
      `${BASE}/configs/loaded/${encodeURIComponent(name)}/history`,
    );
  }

  /** Config snapshot saved alongside the run. `exists: false` for legacy runs. */
  getResultPredictionConfig(path: string): Observable<{ path: string; name: string; exists: boolean; raw: string }> {
    return this.http.get<{ path: string; name: string; exists: boolean; raw: string }>(
      `${BASE}/results/prediction/config?path=${encodeURIComponent(path)}`,
    );
  }

  /** Reproduce-this-run notebook as a Blob (attachment-headered).
   * `evaluator` is the filename stem under `scripts/evaluation/` baked
   * into the notebook's section 5 — required. */
  getResultPredictionNotebook(path: string, evaluator: string): Observable<Blob> {
    return this.http.get(
      `${BASE}/results/prediction/notebook?path=${encodeURIComponent(path)}&evaluator=${encodeURIComponent(evaluator)}`,
      { responseType: 'blob' },
    );
  }

  // ─── Instances ────────────────────────────────────────────────────
  getInstances(skip = 0, limit = 100): Observable<Instance[]> {
    return this.http.get<Instance[]>(`${BASE}/instances?skip=${skip}&limit=${limit}`);
  }

  countInstances(): Observable<{ count: number }> {
    return this.http.get<{ count: number }>(`${BASE}/instances/count`);
  }

  // ─── Predictions ──────────────────────────────────────────────────
  getPredictions(): Observable<string[]> {
    return this.http.get<string[]>(`${BASE}/predictions`);
  }

  inspectPrediction(path: string): Observable<PredictionInspection> {
    return this.http.get<PredictionInspection>(
      `${BASE}/predictions/inspect?path=${encodeURIComponent(path)}`,
    );
  }

  /** Every `scripts/evaluation/*.py` exposed by the backend. */
  getEvaluationScripts(): Observable<{ value: string; label: string }[]> {
    return this.http.get<{ value: string; label: string }[]>(`${BASE}/evaluation/scripts`);
  }

  // ─── Results browser ──────────────────────────────────────────────
  getResultInstances(): Observable<ResultInstance[]> {
    return this.http.get<ResultInstance[]>(`${BASE}/results/instances`);
  }

  getResultPrediction(path: string, instanceId?: string): Observable<ResultPrediction> {
    let url = `${BASE}/results/prediction?path=${encodeURIComponent(path)}`;
    if (instanceId) url += `&instance_id=${encodeURIComponent(instanceId)}`;
    return this.http.get<ResultPrediction>(url);
  }

  /** Text-format `.log` for a run. `exists: false` for legacy runs. */
  getResultPredictionLog(path: string): Observable<{ path: string; name: string; exists: boolean; raw: string }> {
    return this.http.get<{ path: string; name: string; exists: boolean; raw: string }>(
      `${BASE}/results/prediction/log?path=${encodeURIComponent(path)}`,
    );
  }

  /** Internal NDJSON SSE log — same stream the Inference page consumes
   * live, replayed for completed runs in the Results modal. */
  getResultPredictionNdjson(path: string): Observable<{ path: string; name: string; exists: boolean; raw: string }> {
    return this.http.get<{ path: string; name: string; exists: boolean; raw: string }>(
      `${BASE}/results/prediction/ndjson?path=${encodeURIComponent(path)}`,
    );
  }

  getResultEvaluation(dir: string): Observable<ResultEvaluation> {
    return this.http.get<ResultEvaluation>(`${BASE}/results/evaluation?dir=${encodeURIComponent(dir)}`);
  }

  getResultEvaluationLog(dir: string, name: string): Observable<{ name: string; content: string }> {
    return this.http.get<{ name: string; content: string }>(
      `${BASE}/results/evaluation/log?dir=${encodeURIComponent(dir)}&name=${encodeURIComponent(name)}`
    );
  }

  getResultEvaluationZipUrl(dir: string): string {
    return `${BASE}/results/evaluation/zip?dir=${encodeURIComponent(dir)}`;
  }

  revealInExplorer(path: string): Observable<{ ok: boolean; path: string }> {
    return this.http.post<{ ok: boolean; path: string }>(`${BASE}/results/reveal`, { path });
  }

  // ─── Refresh SWE-bench instances ──────────────────────────────────
  refreshInstances(
    subset: 'lite' | 'full' | 'verified' = 'lite',
    split: 'dev' | 'test' | 'train' = 'dev',
    limit?: number,
  ): Observable<{ count: number; subset: string; split: string; path: string }> {
    const params = new URLSearchParams({ subset, split, append: 'true' });
    if (limit !== undefined) params.set('limit', String(limit));
    return this.http.post<{ count: number; subset: string; split: string; path: string }>(
      `${BASE}/instances/refresh?${params.toString()}`, {},
    );
  }

  /** Append a user-provided GitHub repo as a custom-subset row. */
  addCustomInstance(repo: string, problem_statement: string, base_commit?: string): Observable<{
    instance_id: string; repo: string; base_commit: string; duplicate: boolean;
  }> {
    return this.http.post<{ instance_id: string; repo: string; base_commit: string; duplicate: boolean }>(
      `${BASE}/instances/custom`,
      { repo, problem_statement, base_commit: base_commit || null },
    );
  }

  /** Pull every (subset, split) pair from HuggingFace. Slow. */
  refreshAllInstances(limit?: number): Observable<{
    total: number;
    results: Record<string, { count?: number; error?: string }>;
  }> {
    const params = new URLSearchParams();
    if (limit !== undefined) params.set('limit', String(limit));
    const qs = params.toString();
    return this.http.post<{ total: number; results: Record<string, { count?: number; error?: string }> }>(
      `${BASE}/instances/refresh-all${qs ? '?' + qs : ''}`, {},
    );
  }

  /** Reproduce-this-run notebook for (instance_ids, config) — built
   * BEFORE any prediction exists, so the comparative section is omitted.
   * Mirror of `getResultPredictionNotebook` for the Inference page. */
  buildInferenceNotebook(
    instanceIds: string[], config: string | UnifiedConfig, evaluator: string,
  ): Observable<Blob> {
    return this.http.post(
      `${BASE}/inference/notebook`,
      { instance_ids: instanceIds, config, evaluator },
      { responseType: 'blob' },
    );
  }

  // ─── Inference SSE (POST + ReadableStream) ────────────────────────
  streamInference(
    instanceIds: string | string[],
    config: string | UnifiedConfig,
  ): Observable<InferenceEvent> {
    const ids = Array.isArray(instanceIds) ? instanceIds : [instanceIds];
    return new Observable<InferenceEvent>(observer => {
      const controller = new AbortController();
      fetch(`${BASE}/inference/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instance_ids: ids, config }),
        signal: controller.signal,
      }).then(async res => {
        const reader = res.body!.getReader();
        const dec = new TextDecoder();
        let buf = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) { observer.complete(); break; }
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() ?? '';
          for (const line of lines) {
            const t = line.trim();
            if (t.startsWith('data: ')) {
              try { observer.next(JSON.parse(t.slice(6))); } catch {}
            }
          }
        }
      }).catch(err => {
        if (err.name !== 'AbortError') observer.error(err);
        else observer.complete();
      });
      return () => controller.abort();
    });
  }

  cancelInference(instanceId: string): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${BASE}/inference/cancel/${instanceId}`, {});
  }

  /** Stream `ollama pull <model>` as SSE: `{type:'log',line}` per stdout
   * line, then a terminal `{type:'done',code}` (0 = success). */
  streamModelPull(model: string): Observable<{ type: 'log'; line: string } | { type: 'done'; code: number }> {
    return new Observable(observer => {
      const controller = new AbortController();
      fetch(`${BASE}/models/pull`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model }),
        signal: controller.signal,
      }).then(async res => {
        if (!res.body) { observer.error(new Error('no response body')); return; }
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) { observer.complete(); break; }
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() ?? '';
          for (const line of lines) {
            const t = line.trim();
            if (t.startsWith('data: ')) {
              try { observer.next(JSON.parse(t.slice(6))); } catch {}
            }
          }
        }
      }).catch(err => {
        if (err.name !== 'AbortError') observer.error(err);
        else observer.complete();
      });
      return () => controller.abort();
    });
  }

  getActiveInference(): Observable<{
    active: boolean;
    run_id?: string;
    config_label?: string;
    instance_ids?: string[];
    log_path?: string;
    started_at?: number;
  }> {
    return this.http.get<{
      active: boolean;
      run_id?: string;
      config_label?: string;
      instance_ids?: string[];
      log_path?: string;
      started_at?: number;
    }>(`${BASE}/inference/active`);
  }

  /** Tail bytes of the internal NDJSON log past `offset`. */
  getInferenceLogTail(path: string, offset: number): Observable<{ raw: string; offset: number; is_running: boolean }> {
    return this.http.get<{ raw: string; offset: number; is_running: boolean }>(
      `${BASE}/inference/log-tail?path=${encodeURIComponent(path)}&offset=${offset}`,
    );
  }

  cancelEvaluation(predictionsPath: string): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${BASE}/evaluation/cancel?predictions_path=${encodeURIComponent(predictionsPath)}`, {});
  }

  // ─── Evaluation SSE ───────────────────────────────────────────────
  streamEvaluation(predictionsPath: string, split: string, maxWorkers: number, runId: string, script: string = ''): Observable<EvalEvent> {
    return new Observable<EvalEvent>(observer => {
      const controller = new AbortController();
      // Omit blanks so the backend auto-detects from the prediction file.
      const body: Record<string, unknown> = {
        predictions_path: predictionsPath,
        max_workers: maxWorkers,
      };
      if (split) body['split'] = split;
      if (runId) body['run_id'] = runId;
      if (script) body['script'] = script;
      fetch(`${BASE}/evaluation/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      }).then(async res => {
        const reader = res.body!.getReader();
        const dec = new TextDecoder();
        let buf = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) { observer.complete(); break; }
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() ?? '';
          for (const line of lines) {
            const t = line.trim();
            if (t.startsWith('data: ')) {
              try { observer.next(JSON.parse(t.slice(6))); } catch {}
            }
          }
        }
      }).catch(err => {
        if (err.name !== 'AbortError') observer.error(err);
        else observer.complete();
      });
      return () => controller.abort();
    });
  }
}
