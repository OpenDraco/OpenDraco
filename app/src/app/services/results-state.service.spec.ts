import { describe, expect, it } from 'vitest';
import { ResultsStateService } from './results-state.service';

describe('ResultsStateService', () => {
  it('starts with no selection and the default log tab', () => {
    const svc = new ResultsStateService();
    expect(svc.selectedId).toBeNull();
    expect(svc.selectedRunId).toBeNull();
    expect(svc.showLogs).toBe(false);
    expect(svc.activeLog).toBe('run_instance.log');
  });

  it('reset() returns the service to its initial state', () => {
    const svc = new ResultsStateService();
    svc.selectedId = 'sqlfluff__sqlfluff-1625';
    svc.selectedRunId = 'evo-star-abcd1234';
    svc.showLogs = true;
    svc.activeLog = 'test_output.txt';

    svc.reset();

    expect(svc.selectedId).toBeNull();
    expect(svc.selectedRunId).toBeNull();
    expect(svc.showLogs).toBe(false);
    expect(svc.activeLog).toBe('run_instance.log');
  });
});
