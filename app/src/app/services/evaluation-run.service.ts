import { Injectable } from '@angular/core';
import { Subject, Subscription } from 'rxjs';
import { ApiService } from './api.service';
import { EvalEvent } from '../models/types';

export type LogSegment = { t: string; c: string };
export type LogLine = LogSegment[];

export interface ResultStats {
  total: number;
  resolved: number;
  failed: number;
  percent: number;
}

const LEVEL_CLS: Record<string, string> = {
  DEBUG: 'sl-debug', INFO: 'sl-info',
  WARNING: 'sl-warn', WARN: 'sl-warn',
  ERROR: 'sl-err', CRITICAL: 'sl-err', FATAL: 'sl-err',
};

export function parseLogLine(raw: string): LogLine {
  if (!raw.trim()) return [{ t: raw || ' ', c: 'sl-dim' }];
  const segs: LogLine = [];
  let rest = raw;

  // Standard Python log: "YYYY-MM-DD HH:MM:SS,mmm - LEVEL - ..."
  const stdM = rest.match(
    /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d+)?) - (DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL) - /i
  );
  if (stdM) {
    segs.push({ t: stdM[1], c: 'sl-ts' });
    segs.push({ t: ' - ', c: 'sl-dim' });
    segs.push({ t: stdM[2], c: LEVEL_CLS[stdM[2].toUpperCase()] ?? 'sl-dim' });
    segs.push({ t: ' - ', c: 'sl-dim' });
    rest = rest.slice(stdM[0].length);
    const level = stdM[2].toUpperCase();
    const mc = level === 'ERROR' || level === 'CRITICAL' || level === 'FATAL' ? 'sl-err-msg'
             : level === 'WARNING' || level === 'WARN' ? 'sl-warn-msg'
             : level === 'DEBUG' ? 'sl-dim'
             : /resolved|pass|success/i.test(rest) ? 'sl-ok'
             : 'sl-text';
    if (rest) segs.push({ t: rest, c: mc });
    return segs;
  }

  // Short level prefix: "LEVEL - ..." or "LEVEL: ..."
  const shortM = rest.match(/^(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL)(\s*[-:]\s*)/i);
  if (shortM) {
    const level = shortM[1].toUpperCase();
    segs.push({ t: shortM[1], c: LEVEL_CLS[level] ?? 'sl-dim' });
    segs.push({ t: shortM[2], c: 'sl-dim' });
    rest = rest.slice(shortM[0].length);
    const mc = level === 'ERROR' || level === 'CRITICAL' ? 'sl-err-msg'
             : level === 'WARNING' || level === 'WARN' ? 'sl-warn-msg'
             : 'sl-text';
    if (rest) segs.push({ t: rest, c: mc });
    return segs;
  }

  // Traceback / exception lines
  if (/^(Traceback|.*Error:|.*Exception:|\s+File ")/i.test(rest)) {
    return [{ t: rest, c: 'sl-err-msg' }];
  }

  // tqdm progress bar
  if (/^\s*\d+%\|/.test(rest) || /\bit\/s\b/.test(rest)) {
    return [{ t: rest, c: 'sl-dim' }];
  }

  // Resolved / pass lines
  if (/\bresolved\b.*\d+\/\d+/i.test(rest) || /\bpass\b|\bsuccess\b/i.test(rest)) {
    return [{ t: rest, c: 'sl-ok' }];
  }

  return [{ t: rest, c: 'sl-text' }];
}

@Injectable({ providedIn: 'root' })
export class EvaluationRunService {
  // Config (persists across navigation)
  predictionsPath = '';
  split = 'dev';
  maxWorkers = 4;
  runId = '';
  /** Filename stem under scripts/evaluation/ (no .py). Required. */
  evaluator = '';

  // Run state (persists across navigation)
  running = false;
  logs: LogLine[] = [];
  progressTotal = 0;
  progressDone = 0;
  progressPercent = 0;
  stats: ResultStats | null = null;
  errorMsg = '';
  returnCode: number | null = null;

  readonly changed = new Subject<void>();
  private sub?: Subscription;

  constructor(private api: ApiService) {}

  run(): void {
    if (!this.predictionsPath || this.running) return;
    this.running = true;
    this.logs = [];
    this.stats = null;
    this.errorMsg = '';
    this.progressDone = 0;
    this.progressTotal = 0;
    this.progressPercent = 0;
    this.returnCode = null;
    this.notify();

    // Subset, split, run_id auto-derived backend-side; `evaluator` is the script stem.
    this.sub = this.api.streamEvaluation(
      this.predictionsPath, '', this.maxWorkers, '', this.evaluator,
    ).subscribe({
      next: ev => { this.handleEvent(ev); this.notify(); },
      error: err => {
        this.errorMsg = err?.message ?? 'Connection error';
        this.running = false;
        this.notify();
      },
      complete: () => {
        this.running = false;
        this.notify();
      },
    });
  }

  cancel(): void {
    this.sub?.unsubscribe();
    if (this.predictionsPath) {
      this.api.cancelEvaluation(this.predictionsPath).subscribe();
    }
    this.running = false;
    this.notify();
  }

  clearLogs(): void {
    this.logs = [];
    // Reset every transient indicator that the logs panel summarized so the
    // UI fully resets when the user clicks Clear, not just the textual logs.
    this.progressDone = 0;
    this.progressTotal = 0;
    this.progressPercent = 0;
    this.returnCode = null;
    this.stats = null;
    this.errorMsg = '';
    this.notify();
  }

  private notify(): void { this.changed.next(); }

  private handleEvent(ev: EvalEvent): void {
    if (ev.type === 'log' && ev.message) {
      this.logs.push(parseLogLine(ev.message));
      if (this.logs.length > 2000) this.logs.splice(0, 200);
      this.parseProgress(ev.message);
      this.parseStats(ev.message);
    } else if (ev.type === 'group_start') {
      this.logs.push(parseLogLine(
        `── group ${ev.subset}/${ev.split} (${ev.count} instances) → run_id=${ev.run_id}`
      ));
    } else if (ev.type === 'group_done') {
      this.logs.push(parseLogLine(
        `── group ${ev.subset}/${ev.split} done (returncode=${ev.returncode})`
      ));
    } else if (ev.type === 'done') {
      this.returnCode = ev.returncode ?? 0;
      this.running = false;
    } else if (ev.type === 'error') {
      this.errorMsg = ev.message ?? 'Error';
      this.running = false;
    }
  }

  private parseProgress(line: string): void {
    const m1 = line.match(/(\d+)\s*\/\s*(\d+)/);
    if (m1) {
      this.progressDone = +m1[1];
      this.progressTotal = +m1[2];
      if (this.progressTotal > 0)
        this.progressPercent = Math.round((this.progressDone / this.progressTotal) * 100);
    }
    const m2 = line.match(/(\d+)%\|/);
    if (m2) this.progressPercent = +m2[1];
  }

  private parseStats(line: string): void {
    const mRes = line.match(/[Rr]esolved.*?(\d+)\s*\/\s*(\d+)/);
    if (mRes) {
      const resolved = +mRes[1];
      const total = +mRes[2];
      this.stats = {
        total, resolved,
        failed: total - resolved,
        percent: total > 0 ? Math.round((resolved / total) * 100) : 0,
      };
    }
  }
}
