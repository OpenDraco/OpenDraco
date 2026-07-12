/**
 * Johnson's algorithm for enumerating all elementary (simple) cycles in
 * a directed graph. Pure TypeScript, zero dependencies.
 *
 * Why Johnson's instead of just counting back-edges from a DFS?
 *   - A back-edge tells you "this graph has at least one cycle", but
 *     not how MANY distinct cycles there are. The topology stats panel
 *     wants the count, so it needs the proper enumeration.
 *   - For typical EvoMas topology configs (<= ~20 nodes) Johnson runs
 *     in microseconds; the O(V * E * C) complexity (C = number of
 *     cycles) is fine at this scale. We don't need to ship a more
 *     optimized algorithm.
 *
 * The implementation follows the original 1975 paper:
 *   "Finding all the elementary circuits of a directed graph",
 *   Donald B. Johnson, SIAM J. Comput. 4(1), 77-84.
 *
 * Tarjan's strongly-connected-components decomposition prunes the
 * search space: cycles only exist within SCCs of size > 1 (or a
 * self-loop), so we enumerate SCCs first and run the circuit-finding
 * routine on the smallest-vertex SCC at a time.
 */

/** Cycle as a list of node ids in traversal order. The first and last
 * entries are the same vertex (closed walk). Callers that want simple
 * cycles without the closing repeat should drop the last element. */
export type Cycle = string[];

/**
 * Find every elementary cycle in a directed graph.
 *
 * @param nodes  All node ids in the graph (including isolated ones).
 *               Isolated nodes contribute zero cycles but must be in
 *               this list so the algorithm doesn't index-out-of-range.
 * @param edges  Directed edges as `[from, to]` pairs. Self-loops are
 *               valid (and produce a 1-cycle).
 * @returns      Every elementary cycle, deduplicated. Order of cycles
 *               in the output isn't guaranteed.
 */
export function findAllCycles(nodes: string[], edges: [string, string][]): Cycle[] {
  if (nodes.length === 0) return [];

  // Adjacency list keyed by node id. We mutate this during the
  // algorithm (removing the smallest vertex after each SCC pass) so
  // start from a fresh deep-ish copy of the input.
  const allAdj = new Map<string, string[]>();
  for (const n of nodes) allAdj.set(n, []);
  for (const [u, v] of edges) {
    if (!allAdj.has(u) || !allAdj.has(v)) continue;
    allAdj.get(u)!.push(v);
  }

  const result: Cycle[] = [];
  // Fixed traversal order so output is deterministic when given the
  // same input; mirrors networkx's behavior.
  const order = [...nodes].sort();

  // Johnson processes one SCC at a time, restricting to vertices with
  // index >= currentStart. After each iteration we drop the smallest
  // index, find SCCs in the remaining subgraph, and recurse.
  for (let startIdx = 0; startIdx < order.length; startIdx++) {
    const startNode = order[startIdx];
    const subset = new Set(order.slice(startIdx));
    const sccVertices = _smallestSccContaining(startNode, subset, allAdj);
    if (!sccVertices) continue;  // start vertex isn't in any non-trivial SCC

    // Build the subgraph restricted to this SCC's vertices, plus only
    // edges leading to vertices >= startIdx. This is what Johnson's
    // "Bk" set represents.
    const adj = new Map<string, string[]>();
    for (const v of sccVertices) adj.set(v, []);
    for (const v of sccVertices) {
      for (const w of allAdj.get(v) ?? []) {
        if (sccVertices.has(w)) adj.get(v)!.push(w);
      }
    }

    _johnsonCircuit(startNode, adj, result);
  }

  return result;
}

/** Returns true when the graph is acyclic (has a topological order). */
export function isDAG(nodes: string[], edges: [string, string][]): boolean {
  return findAllCycles(nodes, edges).length === 0;
}

// ─── Internal helpers ────────────────────────────────────────────────

/** Tarjan-style: find the SCC containing `start` within the subgraph
 * restricted to `subset` vertices. Returns the SCC's vertex set if it
 * has > 1 member OR a self-loop on `start`; null otherwise. */
function _smallestSccContaining(
  start: string,
  subset: Set<string>,
  adj: Map<string, string[]>,
): Set<string> | null {
  const index = new Map<string, number>();
  const lowlink = new Map<string, number>();
  const onStack = new Set<string>();
  const stack: string[] = [];
  let counter = 0;
  let result: Set<string> | null = null;

  function strongconnect(v: string): void {
    index.set(v, counter);
    lowlink.set(v, counter);
    counter++;
    stack.push(v);
    onStack.add(v);

    for (const w of adj.get(v) ?? []) {
      if (!subset.has(w)) continue;
      if (!index.has(w)) {
        strongconnect(w);
        lowlink.set(v, Math.min(lowlink.get(v)!, lowlink.get(w)!));
      } else if (onStack.has(w)) {
        lowlink.set(v, Math.min(lowlink.get(v)!, index.get(w)!));
      }
    }

    if (lowlink.get(v) === index.get(v)) {
      // Pop the SCC off the stack.
      const scc = new Set<string>();
      let w: string;
      do {
        w = stack.pop()!;
        onStack.delete(w);
        scc.add(w);
      } while (w !== v);
      // Only keep SCCs that contain `start` AND are interesting
      // (size > 1, or a self-loop on the single member).
      if (scc.has(start)) {
        if (scc.size > 1 || (adj.get(start) ?? []).includes(start)) {
          result = scc;
        }
      }
    }
  }

  if (!index.has(start)) strongconnect(start);
  return result;
}

/** Johnson's circuit-finding routine on a subgraph rooted at `start`.
 * Pushes every elementary cycle starting AND ending at `start` into
 * `out`. Uses the blocked-set + B-set mechanism from the original
 * paper. */
function _johnsonCircuit(
  start: string,
  adj: Map<string, string[]>,
  out: Cycle[],
): void {
  const blocked = new Set<string>();
  const blockedMap = new Map<string, Set<string>>();
  const stack: string[] = [];

  function unblock(v: string): void {
    blocked.delete(v);
    const blockedOnV = blockedMap.get(v);
    if (blockedOnV) {
      for (const w of blockedOnV) {
        blockedMap.get(v)!.delete(w);
        if (blocked.has(w)) unblock(w);
      }
    }
  }

  function circuit(v: string): boolean {
    let foundCycle = false;
    stack.push(v);
    blocked.add(v);

    for (const w of adj.get(v) ?? []) {
      if (w === start) {
        out.push([...stack, start]);
        foundCycle = true;
      } else if (!blocked.has(w)) {
        if (circuit(w)) foundCycle = true;
      }
    }

    if (foundCycle) {
      unblock(v);
    } else {
      for (const w of adj.get(v) ?? []) {
        if (!blockedMap.has(w)) blockedMap.set(w, new Set());
        blockedMap.get(w)!.add(v);
      }
    }

    stack.pop();
    return foundCycle;
  }

  circuit(start);
}
