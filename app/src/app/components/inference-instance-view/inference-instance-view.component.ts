/** Per-instance renderer for a single inference run — the vertical agent
 * cards + hand-off chips + final-patch viewer that's the central column of
 * the Inference page. Lifted into its own component so the Results page's
 * "View" modal can show a completed run with full fidelity, reusing the
 * exact rendering pipeline the live page uses. */
import {
  Component, Input, ChangeDetectionStrategy,
} from '@angular/core';
import { CommonModule } from '@angular/common';

import { NgIcon, provideIcons } from '@ng-icons/core';
import { ICON } from '../../icons';
import { AgentCard, RunInstance, formatDurationMs } from '../../services/inference-run.service';
import { HandoffChip } from '../../models/types';
import { EvoBadgeComponent } from '../badge/evo-badge.component';

@Component({
  selector: 'app-inference-instance-view',
  standalone: true,
  imports: [CommonModule, EvoBadgeComponent, NgIcon],
  providers: [provideIcons(ICON)],
  changeDetection: ChangeDetectionStrategy.Default,
  templateUrl: './inference-instance-view.component.html',
  styleUrl: './inference-instance-view.component.css',
})
export class InferenceInstanceViewComponent {
  /** The instance snapshot to render. `null` is treated as "nothing to show". */
  @Input() instance: RunInstance | null = null;
  /** Optional status line shown above the cards. Driven by the live page;
   * empty string in the replay modal. */
  @Input() statusMsg = '';
  /** True while the run is actively streaming. Toggles the spinner +
   * "Running…" prefix on the status line, and the running tail row at the
   * bottom of the card list. */
  @Input() running = false;
  /** True when the user cancelled. Shows the "Cancelled" footer row. */
  @Input() cancelled = false;
  /** Whether to render the thinking trace inside each card. Inherited from
   * the live page's toggle; default true so the Results modal shows it. */
  @Input() showThinking = true;

  // ─── Computed getters ───────────────────────────────────────────
  get cards(): AgentCard[] { return this.instance?.cards ?? []; }
  get finalPatch(): string { return this.instance?.finalPatch ?? ''; }
  get outputPath(): string { return this.instance?.outputPath ?? ''; }
  get errorMsg(): string { return this.instance?.errorMsg ?? ''; }
  get errorTraceback(): string { return this.instance?.errorTraceback ?? ''; }

  /** Hand-off chips that triggered THIS specific card's iteration —
   * pulled directly off the card now that the service drains the
   * pending-incoming queue at spawn time. A previous version of this
   * method indexed a globally-keyed map by agent name, which made
   * every retry card of a cyclic agent re-render every chip ever
   * sent to that agent. */
  handoffsFor(card: AgentCard): HandoffChip[] {
    return card.incomingChips ?? [];
  }

  // ─── Card expand / collapse ─────────────────────────────────────
  toggleCard(card: AgentCard): void { card.expanded = !card.expanded; }

  /** Human-friendly duration for a card. Empty when the card has no
   * timing — happens for in-flight live cards (status still 'running')
   * or for replays whose `.log` file is missing. */
  cardDuration(card: AgentCard): string {
    if (card.durationMs == null) return '';
    return formatDurationMs(card.durationMs);
  }

  // ─── Hand-off preview modal ─────────────────────────────────────
  handoffPreview: HandoffChip | null = null;
  openHandoffPreview(chip: HandoffChip): void { this.handoffPreview = chip; }
  closeHandoffPreview(): void { this.handoffPreview = null; }

  /** What the target agent receives from the source for this hand-off.
   *
   * Earlier versions of this lookup waited for the target's
   * `agent_input` SSE event (which fires when the target's first
   * iteration starts) and pulled `card.inputs[chip.from]`. That made
   * the modal sit on "(target hasn't run yet)" for the entire gap
   * between the source finishing and the target's first LLM call —
   * which on a slow Ollama is minutes.
   *
   * State in LangGraph is shared: whatever value the source wrote into
   * `state[chip.from]` IS what the target reads from
   * `state[self.predecessor_name]` when it starts. The chip event
   * already carries that value as `chip.preview`. So we use it
   * directly — same data, available the instant the source emits its
   * hand-off event. The earlier `card.inputs` path is now dead code.
   *
   * Returns `null` only when the chip preview was genuinely empty
   * (the source produced nothing — e.g. an agent that hit num_predict
   * mid-thinking before the summary-fallback ran). */
  targetReceived(chip: HandoffChip): string | null {
    return chip.preview && chip.preview.trim() ? chip.preview : null;
  }

  // ─── Card body helpers ──────────────────────────────────────────
  inputKeys(inputs: Record<string, unknown>): string[] {
    return Object.keys(inputs ?? {});
  }

  /** Single-line preview of a predecessor's output. Lists / objects get
   * stringified and truncated. */
  inputPreview(value: unknown): string {
    if (value == null) return '<empty>';
    if (typeof value === 'string') {
      return value.length > 600 ? value.slice(0, 600) + '…(truncated)' : value;
    }
    if (Array.isArray(value)) {
      return `[${value.length} items]`;
    }
    if (typeof value === 'object') {
      try { return JSON.stringify(value).slice(0, 600); } catch { return String(value); }
    }
    return String(value);
  }

  /** Render the per-agent delta as a list of fields. Drops system keys
   * AND the agent's own producer-slot key (= `agentName`) so the producer
   * payload only appears on the hand-off chip's modal — not duplicated as
   * a delta-field on the originating card. */
  formatDelta(
    delta: Record<string, unknown>,
    agentName = '',
  ): { key: string; value: string; type: string }[] {
    const reserved = new Set(['workspace_path', 'issue_text', 'instance', 'thinking']);
    if (agentName) reserved.add(agentName);
    return Object.entries(delta ?? {})
      .filter(([k]) => !reserved.has(k))
      .map(([key, value]) => {
        let type = 'text';
        let str = '';
        if (key === 'final_patch' || key === 'candidate_patches') {
          type = 'code';
          str = Array.isArray(value) ? value.join('\n\n─────\n\n') : String(value ?? '');
        } else if (key === 'validation_results' && Array.isArray(value)) {
          type = 'json';
          str = JSON.stringify(value, null, 2);
        } else if (Array.isArray(value)) {
          str = (value as unknown[]).join('\n');
        } else {
          str = String(value ?? '');
        }
        return { key, value: str, type };
      });
  }

  /** Line-by-line diff styling for the final patch block. */
  formatDiff(patch: string): { line: string; cls: string }[] {
    return patch.split('\n').map(line => {
      let cls = '';
      if (line.startsWith('+') && !line.startsWith('+++')) cls = 'diff-add';
      else if (line.startsWith('-') && !line.startsWith('---')) cls = 'diff-rm';
      else if (line.startsWith('@@') || line.startsWith('diff ')) cls = 'diff-hdr';
      return { line, cls };
    });
  }
}
