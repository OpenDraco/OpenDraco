import { describe, expect, it } from 'vitest';
import { InferenceStateService } from './inference-state.service';

describe('InferenceStateService', () => {
  it('starts with an empty selection and no config', () => {
    const svc = new InferenceStateService();
    expect(svc.selectedInstanceIds.size).toBe(0);
    expect(svc.config).toBe('');
    expect(svc.selectedList).toEqual([]);
  });

  it('toggleInstance adds and then removes an id', () => {
    const svc = new InferenceStateService();
    svc.toggleInstance('a');
    expect(svc.isSelected('a')).toBe(true);
    svc.toggleInstance('a');
    expect(svc.isSelected('a')).toBe(false);
  });

  it('setSelection replaces the set, dropping previous picks', () => {
    const svc = new InferenceStateService();
    svc.toggleInstance('a');
    svc.setSelection(['x', 'y']);
    expect(svc.selectedList.sort()).toEqual(['x', 'y']);
    expect(svc.isSelected('a')).toBe(false);
  });

  it('clearSelection empties the set', () => {
    const svc = new InferenceStateService();
    svc.setSelection(['a', 'b', 'c']);
    svc.clearSelection();
    expect(svc.selectedInstanceIds.size).toBe(0);
  });
});
