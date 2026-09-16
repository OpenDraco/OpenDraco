/** Pure structural validation for a `UnifiedConfig`.
 *
 * Originally lived as an instance method on TopologyComponent; pulled
 * out into a helper so the boot pass (ngOnInit) can validate every
 * predefined + loaded config without coupling to component state. The
 * Validate toolbar button and the per-row config-list badge share the
 * same logic. */

import { UnifiedConfig } from '../models/types';

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

/** Cross-config context for catalog-level checks. Optional — when
 * unset, only the in-config structural rules run. The Topology page's
 * boot pass + Validate button supply both fields. */
export interface ValidationContext {
  /** Filename stem of the config under validation. Used to enforce that
   * `cfg.id` matches the on-disk filename — a runtime requirement since
   * `id` is the routing key for `/api/configs/<id>`. */
  stem?: string;
  /** Every config the catalog knows about (predefined + loaded), keyed
   * by stem. Used to flag duplicate `id` values across configs — two
   * files sharing an `id` would shadow each other at runtime. */
  catalog?: ReadonlyArray<{ stem: string; id: string }>;
}

/** Normalize `cfg.end` (string | string[] | undefined) into a flat id array. */
function endNodeIds(cfg: UnifiedConfig): string[] {
  if (typeof cfg.end === 'string') return cfg.end ? [cfg.end] : [];
  if (Array.isArray(cfg.end)) return cfg.end.filter(Boolean);
  return [];
}

export function validateConfig(
  cfg: UnifiedConfig | null,
  context: ValidationContext = {},
): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (!cfg) return { valid: false, errors: ['No configuration loaded.'], warnings };

  // ── Catalog-level checks (run before the structural ones so the
  //    panel surfaces the bigger-picture issues first) ──────────────
  // 0a. `cfg.id` must match the on-disk filename. The runtime resolves
  //     configs by stem, but referrers (history, exports) use `id` — a
  //     mismatch silently swaps which one wins depending on path.
  const cfgId = typeof cfg.id === 'string' ? cfg.id : '';
  if (context.stem != null && cfgId !== '' && cfgId !== context.stem) {
    errors.push(
      `Config \`id\` "${cfgId}" does not match the filename "${context.stem}". ` +
      `Rename the file or update the JSON's \`id\` so they agree.`,
    );
  }
  if (context.stem != null && cfgId === '') {
    errors.push(
      `Config has no \`id\` field — it must equal the filename ` +
      `"${context.stem}".`,
    );
  }
  // 0b. `id` must be unique across the catalog. Two files sharing an
  //     `id` shadow each other depending on which root resolves first.
  if (context.catalog && cfgId !== '') {
    const ownStem = context.stem ?? '';
    const collisions = context.catalog
      .filter(c => c.id === cfgId && c.stem !== ownStem)
      .map(c => c.stem);
    if (collisions.length > 0) {
      errors.push(
        `Config \`id\` "${cfgId}" is also used by: ` +
        `${collisions.map(s => `"${s}"`).join(', ')}. ` +
        `Each config must have a unique \`id\`.`,
      );
    }
  }

  const agents = cfg.agents ?? {};
  const edges = cfg.edges ?? [];
  const agentIds = Object.keys(agents);
  if (agentIds.length === 0) {
    errors.push('Configuration has no agents.');
    return { valid: false, errors, warnings };
  }

  // 1. entry must be set and refer to an existing agent.
  if (!cfg.entry || !cfg.entry.trim()) {
    errors.push('`entry` is empty — no node will be the START successor.');
  } else if (!agents[cfg.entry]) {
    errors.push(`\`entry\` points at "${cfg.entry}" but no agent with that id exists.`);
  }

  // 2. end must be non-empty and every entry must refer to an existing agent.
  const ends = endNodeIds(cfg);
  if (ends.length === 0) {
    errors.push('`end` is empty — no node is allowed to route to END.');
  }
  for (const id of ends) {
    if (!agents[id]) {
      errors.push(`\`end\` lists "${id}" but no agent with that id exists.`);
    }
  }

  // 3. every edge endpoint must refer to an existing agent.
  for (const e of edges) {
    if (!agents[e.from]) {
      errors.push(`Edge "${e.from} → ${e.to}" has unknown source "${e.from}".`);
    }
    if (!agents[e.to]) {
      errors.push(`Edge "${e.from} → ${e.to}" has unknown target "${e.to}".`);
    }
  }

  // 4+5. Shape diagnostics (warnings): orphan dead-ends and fully
  //      disconnected nodes. Dedupe to the more specific case.
  const hasOutgoing = new Set<string>(edges.map(e => e.from));
  const hasIncoming = new Set<string>(edges.map(e => e.to));
  const endSet = new Set(ends);
  for (const id of agentIds) {
    const incoming = hasIncoming.has(id);
    const outgoing = hasOutgoing.has(id);
    const isEntry  = cfg.entry === id;
    const inEnd    = endSet.has(id);
    if (!incoming && !outgoing && !isEntry) {
      warnings.push(
        `Node "${id}" is disconnected — no incoming or outgoing edges and not the entry. ` +
        `It will never execute at runtime.`,
      );
    } else if (!outgoing && !inEnd) {
      warnings.push(
        `Node "${id}" has no outgoing edges and is not in \`end\` — it's an orphan ` +
        `dead-end. The branch that reaches it will stall until the runtime ` +
        `recursion-limit aborts the run.`,
      );
    }
  }

  // 6. BFS from `entry` must reach at least one degree-0 end-set node.
  //    Only degree-0 `end` nodes get the static `→ END` wire at runtime.
  if (cfg.entry && agents[cfg.entry] && ends.length > 0) {
    const outBySource: Record<string, string[]> = {};
    for (const e of edges) (outBySource[e.from] ||= []).push(e.to);
    const reachable = new Set<string>();
    const frontier: string[] = [cfg.entry];
    while (frontier.length) {
      const node = frontier.shift()!;
      if (reachable.has(node)) continue;
      reachable.add(node);
      for (const t of (outBySource[node] || [])) frontier.push(t);
    }
    const endZeroDegree = ends.filter(id => !outBySource[id]);
    if (endZeroDegree.length === 0) {
      errors.push(
        `\`end\` has no degree-0 nodes — every end-set node has outgoing edges. ` +
        `At runtime only degree-0 end-set nodes get the static \`→ END\` wire, ` +
        `so START can never reach END.`,
      );
    } else if (!endZeroDegree.some(id => reachable.has(id))) {
      errors.push(
        `START cannot reach END: BFS from entry "${cfg.entry}" never reaches a ` +
        `degree-0 end-set node (candidates: ${endZeroDegree.map(s => `"${s}"`).join(', ')}). ` +
        `Add an edge path from "${cfg.entry}" to one of them.`,
      );
    }
    const unreachable = agentIds.filter(
      id => id !== cfg.entry && !reachable.has(id),
    );
    if (unreachable.length > 0) {
      warnings.push(
        `${unreachable.length} node(s) unreachable from entry "${cfg.entry}": ` +
        `${unreachable.map(s => `"${s}"`).join(', ')}. These will never execute ` +
        `at runtime — connect them with edges or remove them from \`agents\`.`,
      );
    }
  }

  return { valid: errors.length === 0, errors, warnings };
}
