/** `GET /api/models` row. `pulled: false` triggers an `ollama pull`
 * preflight before the Inference run starts. */
export interface OllamaModel {
  name: string;
  pulled: boolean;
}

export interface AgentConfig {
  model: string;
  think: boolean | string;
  num_ctx: number;
  stream: boolean;
  temperature: number;
  top_k: number;
  top_p: number;
  min_p: number;
  repeat_penalty: number;
  repeat_last_n: number;
  seed: number;
  num_predict: number;
  stop: string[];
  [key: string]: unknown;
}

export interface StateField {
  name: string;
  type: string;
  default?: unknown;
}

export interface TopoEdge {
  from: string;
  to: string;
}

export interface PromptBlock {
  system?: string;
  user?: string;
  proxy?: string;
  [key: string]: string | undefined;
}

export interface AgentTool {
  name: string;
  params: Record<string, unknown>;
}

export interface AgentBlock extends AgentConfig {
  class: string;
  /** Palette key (e.g. `"evomas:Locator"`). Traceability only. */
  variant?: string;
  state?: StateField[];
  tools?: AgentTool[];
  prompts?: PromptBlock;
}

/** Repo-relative on-disk paths the backend resolves from BASE_DIR +
 * the current RESULTS_DIR. Surfaced via `/api/paths` so the frontend's
 * user-facing strings (empty hints, tooltips, error messages) reflect
 * the actual values rather than the hardcoded defaults. */
export interface EvomasPaths {
  base_dir: string;
  results_dir: string;
  predictions_dir: string;
  predictions_logs_dir: string;
  evaluations_dir: string;
  inference_logs_dir: string;
}

export interface ToolDescriptor {
  name: string;
  description: string;
  inputSchema: {
    type?: string;
    properties?: Record<string, { type?: string; description?: string; default?: unknown }>;
    required?: string[];
    [k: string]: unknown;
  };
  /** Bundle folder under `evomas/tools/`, or `"evomas"` for top-level. */
  repo?: string;
}

export interface UnifiedConfig {
  id: string;
  description: string;
  entry: string;
  /** Node(s) routing to langgraph END. Legacy configs without it fall
   * back to leaf detection with a deprecation warning. */
  end?: string | string[];
  edges: TopoEdge[];
  agents: Record<string, AgentBlock>;
}

export interface ConfigSummary {
  stem: string;
  id: string;
  description: string;
  source: 'predefined' | 'loaded';
}

export type SwebenchSubset = 'lite' | 'full' | 'verified' | 'custom';
export type SwebenchSplit = 'dev' | 'test' | 'train' | 'custom';

/** Splits actually shipped per subset on HuggingFace.
 * `custom/custom` hosts user-added GitHub repos. */
export const SUBSET_SPLITS: Record<SwebenchSubset, SwebenchSplit[]> = {
  lite:     ['dev', 'test'],
  full:     ['dev', 'test', 'train'],
  verified: ['test'],
  custom:   ['custom'],
};

export interface Instance {
  instance_id: string;
  repo: string;
  problem_statement: string;
  subset: SwebenchSubset;
  split: SwebenchSplit;
}

export interface InferenceEvent {
  type:
    | 'status' | 'start' | 'agent_event' | 'thinking_chunk' | 'response'
    | 'tool_call' | 'agent_input' | 'agent_tokens' | 'run_id'
    | 'instance_start' | 'instance_done' | 'done' | 'error' | 'cancelled'
    | 'handoff'
    // `ollama pull` preflight: per-model start, one stdout line per
    // `preflight_log`, then `preflight_pull_done` with the exit code.
    | 'preflight_pull_start' | 'preflight_log' | 'preflight_pull_done';
  model?: string;
  code?: number;
  line?: string;
  message?: string;
  instance_id?: string;
  instance_ids?: string[];
  index?: number;
  total?: number;
  run_id?: string;
  config?: string;
  agent?: string;
  delta?: Record<string, unknown>;
  patch?: string;
  output_path?: string;
  traceback?: string;
  chunk?: string;
  content?: string;
  tool?: string;
  args_preview?: string;
  result_preview?: string;
  inputs?: Record<string, unknown>;
  input?: number;
  output?: number;
  // handoff payload: one per outgoing edge. `summary` is the chip face;
  // `preview` is the truncated full payload for the click-to-expand modal.
  from?: string;
  to?: string;
  summary?: string;
  preview?: string;
  keys?: string[];
  timestamp?: string;
}

/** Hand-off chip between two agent cards; one per outgoing edge. */
export interface HandoffChip {
  from: string;
  to: string;
  summary: string;
  preview: string;
  keys: string[];
  timestamp: string;
}

export interface EvalEvent {
  type: 'log' | 'group_start' | 'group_done' | 'done' | 'error';
  message?: string;
  returncode?: number;
  subset?: string;
  split?: string;
  run_id?: string;
  count?: number;
}

export interface ResultPredictionFile {
  path: string;
  name: string;
  mtime: number;
}

export interface ResultEvaluationDir {
  run_id: string;
  model: string;
  dir: string;
  mtime: number;
}

export interface PredictionGroup {
  subset: SwebenchSubset;
  split: SwebenchSplit;
  instance_ids: string[];
}

export interface PredictionInspection {
  path: string;
  name: string;
  run_id_base: string;
  total: number;
  groups: PredictionGroup[];
}

export interface ResultRun {
  run_id: string;
  timestamp: string | null;
  prediction: ResultPredictionFile | null;
  evaluation: ResultEvaluationDir | null;
  mtime: number;
}

export interface ResultInstance {
  instance_id: string;
  /** Canonical (first) subset/split, falling back to lite/dev. */
  subset: SwebenchSubset;
  split: SwebenchSplit;
  /** Every (subset, split) the instance belongs to, expanded through
   * the SWE-bench dataset hierarchy. */
  memberships: { subset: SwebenchSubset; split: SwebenchSplit }[];
  predictions: ResultPredictionFile[];
  evaluations: ResultEvaluationDir[];
  runs: ResultRun[];
}

/** LLM token usage. `input` = prompt+context, `output` = generated. */
export interface PredictionTokens {
  input: number;
  output: number;
  total: number;
}

export interface ResultPrediction {
  path: string;
  name: string;
  raw: string;
  data: {
    instance_id?: string;
    model_patch?: string;
    model_name_or_path?: string;
    tokens?: PredictionTokens;
    [k: string]: unknown;
  };
}

export interface ResultEvaluation {
  dir: string;
  report: Record<string, unknown>;
  patch: string;
  files: string[];
  /** Parent of the per-instance evaluation dir; reveal-in-explorer target. */
  run_dir: string;
  /** Cross-model summary file; empty until written. */
  summary_path: string;
}

// ─── Agent types (live catalog from /api/agent-types) ──────────────
export interface AgentType {
  type: string;
  color: string;
  description: string;
  class: string;
  /** `"agent"` = domain role; `"control"` = graph control-flow primitive
   * (e.g. Router). The palette renders control types in a separate lane.
   * Older backends omit this — treat as `"agent"`. */
  category?: 'agent' | 'control';
  default_system: string;
  default_user: string;
  default_tools: string[];
  default_config: Record<string, unknown>;
  /** EvoMas built-in first, then CSV-derived alternatives. */
  variants?: AgentVariant[];
}

/** One variant of an AGENT_TYPE — EvoMas built-in or CSV-derived. */
export interface AgentVariant {
  /** Drag payload (e.g. `"evomas:Locator"`). */
  key: string;
  label: string;
  /** `"evomas"` for built-ins; CSV stem otherwise. */
  repo: string;
  /** Upstream agent name. Equals AGENT_TYPE for built-ins. */
  name: string;
  agent_type: string;
  source_url: string;
  description: string;
  default_system: string;
  default_user: string;
  default_proxy: string;
  default_tools: string[];
  default_config: Record<string, unknown>;
}

/** Lower-snake-case a free-form label into a safe node id base. */
export function normalizeNodeBase(label: string): string {
  return label
    .toLowerCase()
    .replace(/[\/\s]+/g, '_')
    .replace(/[^a-z0-9_]+/g, '')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '');
}

export function suggestNodeId(typeLabel: string, takenIds: Set<string>): string {
  const base = normalizeNodeBase(typeLabel) || 'agent';
  let i = 1;
  while (takenIds.has(`${base}_${i}`)) i += 1;
  return `${base}_${i}`;
}

// Legacy per-node-id palette; fallback for configs without type-driven colors.
export const AGENT_COLORS: Record<string, string> = {
  manager_agent:   '#e3b341',
  localize_agent:  '#388bfd',
  patch_agent:     '#56d364',
  validate_agent:  '#db61a2',
  ensembler_agent: '#a371f7',
};

export const AGENT_LABELS: Record<string, string> = {
  manager_agent:   'Manager',
  localize_agent:  'Localize',
  patch_agent:     'Patch',
  validate_agent:  'Validate',
  ensembler_agent: 'Ensembler',
};

export const ALL_AGENTS = Object.keys(AGENT_COLORS);

/** One commit in the loaded-config history. */
export interface ConfigHistoryEntry {
  sha: string;
  /** ISO-8601 UTC. */
  ts: string;
  message: string;
  /** First-parent SHA, or null for the root. */
  parent_sha: string | null;
}

/** Run pinned to a historical `config_sha` — drives the "N runs" pill. */
export interface ConfigRunMatch {
  runId: string;
  instanceIds: string[];
  /** ISO-8601 from inference start. */
  ts: string;
}
