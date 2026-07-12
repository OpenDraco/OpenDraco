import { describe, expect, it } from 'vitest';
import { findAllCycles, isDAG } from './cycles';

describe('findAllCycles', () => {
  it('returns empty list for a DAG', () => {
    const cycles = findAllCycles(
      ['a', 'b', 'c'],
      [['a', 'b'], ['b', 'c']],
    );
    expect(cycles).toEqual([]);
    expect(isDAG(['a', 'b', 'c'], [['a', 'b'], ['b', 'c']])).toBe(true);
  });

  it('detects a single 3-cycle', () => {
    const cycles = findAllCycles(
      ['a', 'b', 'c'],
      [['a', 'b'], ['b', 'c'], ['c', 'a']],
    );
    expect(cycles).toHaveLength(1);
    // Drop the closing repeat for assertion convenience.
    const cycle = cycles[0].slice(0, -1);
    expect(new Set(cycle)).toEqual(new Set(['a', 'b', 'c']));
  });

  it('detects a self-loop as a 1-cycle', () => {
    const cycles = findAllCycles(['a'], [['a', 'a']]);
    expect(cycles).toHaveLength(1);
    expect(cycles[0]).toEqual(['a', 'a']);
  });

  it('detects every elementary cycle in a bidirectional star', () => {
    // hub <-> a, hub <-> b, hub <-> c. Three 2-cycles (one per spoke).
    const nodes = ['hub', 'a', 'b', 'c'];
    const edges: [string, string][] = [
      ['hub', 'a'], ['a', 'hub'],
      ['hub', 'b'], ['b', 'hub'],
      ['hub', 'c'], ['c', 'hub'],
    ];
    const cycles = findAllCycles(nodes, edges);
    expect(cycles).toHaveLength(3);
  });

  it('finds 2 cycles in a figure-8 (two triangles sharing a vertex)', () => {
    // a -> b -> c -> a   and   a -> d -> e -> a   (share `a`).
    const nodes = ['a', 'b', 'c', 'd', 'e'];
    const edges: [string, string][] = [
      ['a', 'b'], ['b', 'c'], ['c', 'a'],
      ['a', 'd'], ['d', 'e'], ['e', 'a'],
    ];
    const cycles = findAllCycles(nodes, edges);
    expect(cycles).toHaveLength(2);
  });

  it('handles isolated nodes without crashing', () => {
    const cycles = findAllCycles(
      ['a', 'b', 'c'],
      [],   // no edges; all three are isolated
    );
    expect(cycles).toEqual([]);
  });

  it('handles empty input', () => {
    expect(findAllCycles([], [])).toEqual([]);
    expect(isDAG([], [])).toBe(true);
  });
});
