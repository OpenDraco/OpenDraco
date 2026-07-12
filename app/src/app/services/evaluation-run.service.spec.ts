import { describe, expect, it } from 'vitest';
import { parseLogLine } from './evaluation-run.service';

describe('parseLogLine', () => {
  it('returns a single dim segment for blank input', () => {
    const segs = parseLogLine('');
    expect(segs).toHaveLength(1);
    expect(segs[0].c).toBe('sl-dim');
  });

  it('colors a standard Python INFO log line', () => {
    const segs = parseLogLine(
      '2026-05-08 12:34:56,123 - INFO - patch applied cleanly',
    );
    // ts, ' - ', LEVEL, ' - ', msg
    expect(segs.map(s => s.c)).toEqual([
      'sl-ts', 'sl-dim', 'sl-info', 'sl-dim', 'sl-text',
    ]);
    expect(segs[0].t).toContain('2026-05-08');
    expect(segs[2].t).toBe('INFO');
  });

  it('uses the success class when an INFO line says "resolved"', () => {
    const segs = parseLogLine(
      '2026-05-08 12:34:56 - INFO - resolved 1/1',
    );
    expect(segs.at(-1)!.c).toBe('sl-ok');
  });

  it('classifies ERROR lines with the error message class', () => {
    const segs = parseLogLine(
      '2026-05-08 12:34:56 - ERROR - boom',
    );
    // Segments: [ts, ' - ', LEVEL, ' - ', msg]
    expect(segs[2].t).toBe('ERROR');
    expect(segs[2].c).toBe('sl-err');
    expect(segs.at(-1)!.c).toBe('sl-err-msg');
  });

  it('handles short-prefix lines like "WARNING: …"', () => {
    const segs = parseLogLine('WARNING: deprecated');
    expect(segs[0].t).toBe('WARNING');
    expect(segs[0].c).toBe('sl-warn');
    expect(segs.at(-1)!.c).toBe('sl-warn-msg');
  });

  it('marks tracebacks red without level parsing', () => {
    const segs = parseLogLine('Traceback (most recent call last):');
    expect(segs).toHaveLength(1);
    expect(segs[0].c).toBe('sl-err-msg');
  });

  it('marks tqdm-style progress lines as dim', () => {
    const segs = parseLogLine('  10%|##        | 1/10 [00:01<00:09]');
    expect(segs[0].c).toBe('sl-dim');
  });
});
