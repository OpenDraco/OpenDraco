import { describe, expect, it, vi } from 'vitest';
import { TopologyStateService } from './topology-state.service';
import { UnifiedConfig } from '../models/types';

function makeConfig(id: string): UnifiedConfig {
  return {
    id,
    description: '',
    entry: 'orchestrator',
    edges: [],
    agents: { orchestrator: { class: 'Router' } as any },
  };
}

describe('TopologyStateService', () => {
  it('setCurrentConfig stores the config and emits configChanged', () => {
    const svc = new TopologyStateService();
    const cfg = makeConfig('a');
    const sub = vi.fn();
    svc.configChanged.subscribe(sub);

    svc.setCurrentConfig(cfg, 'evo-a');

    expect(svc.currentConfig).toBe(cfg);
    expect(svc.currentConfigName).toBe('evo-a');
    expect(sub).toHaveBeenCalledWith(cfg);
  });

  it('selectedAgentBlock returns the chosen agent or null', () => {
    const svc = new TopologyStateService();
    svc.setCurrentConfig(makeConfig('a'), 'a');
    expect(svc.selectedAgentBlock()).toBeNull();      // no selectedAgent yet

    svc.selectedAgent = 'orchestrator';
    expect(svc.selectedAgentBlock()?.class).toBe('Router');

    svc.selectedAgent = 'does_not_exist';
    expect(svc.selectedAgentBlock()).toBeNull();
  });
});
