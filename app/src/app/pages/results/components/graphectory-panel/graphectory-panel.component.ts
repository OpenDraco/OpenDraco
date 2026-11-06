/** Graphectory box: the upload button, the run's Viewer link (with a copy
 * button) and, when it is safe, the Viewer page in an iframe. Pure
 * presentation — the Results page owns the API calls and the state.
 *
 * The Viewer is another server's web app. Its page is embedded only when
 * the link is http(s) and its origin differs from the app's: the iframe
 * is sandboxed with `allow-same-origin` (the Viewer needs its own origin
 * for its fetches and storage), and that is safe only because a frame
 * with the app's origin plus `allow-scripts` could remove its own sandbox
 * and reach the app. Otherwise only the link is shown. */
import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { DracoBoxComponent, DracoButtonComponent } from '../../../../components/index';
import { ICON } from '../../../../icons';
import { ResultPredictionFile } from '../../../../models/types';

export type GraphectoryViewState = 'idle' | 'uploading' | 'ready' | 'error' | 'unreachable';

/** What each setting is for, shown when it is missing. */
const SETTING_ROLES: Record<string, string> = {
  GRAPHECTORY_URL: 'the local Graphectory Viewer container, e.g. "http://localhost:9610"',
};

/** The view options the Graphectory Viewer's own page sends with every
 * graph request (its toggles' defaults, `graphRequestParams()` in its
 * `browser.js`). The graph route's own defaults differ — without
 * `unique_think=false` every `think` step becomes its own node instead of
 * one shared node — so the link is given these to draw the same graph as
 * the Viewer. Options the link already sets are kept. */
export const VIEWER_GRAPH_DEFAULTS: Readonly<Record<string, string>> = {
  filter_cd: 'false',
  filter_repeated: 'false',
  thought_quotes: 'true',
  show_observation: 'false',
  unique_think: 'false',
};

@Component({
  selector: 'app-graphectory-panel',
  standalone: true,
  imports: [CommonModule, DracoBoxComponent, DracoButtonComponent, NgIcon],
  providers: [provideIcons(ICON)],
  templateUrl: './graphectory-panel.component.html',
  styleUrl: './graphectory-panel.component.css',
})
export class GraphectoryPanelComponent implements OnChanges {
  /** `null` while the API has not said yet which settings are set. */
  @Input() configured: boolean | null = null;
  /** Names of the settings that are empty. */
  @Input() missing: string[] = [];
  /** `GRAPHECTORY_URL`, the Viewer. */
  @Input() serverUrl = '';
  @Input() selectedPredFile: ResultPredictionFile | null = null;
  @Input() state: GraphectoryViewState = 'idle';
  /** The run's Viewer link, as the API returned it. */
  @Input() link = '';
  @Input() error = '';
  /** The app's own origin; an input so it can be tested. */
  @Input() appOrigin = window.location.origin;

  @Output() analyze = new EventEmitter<void>();
  /** The resolved http(s) link to open. */
  @Output() openInNewTab = new EventEmitter<string>();

  /** `link` as an absolute http(s) URL with `VIEWER_GRAPH_DEFAULTS` added,
   * or '' when it is not one. A relative link is resolved against the
   * Viewer's URL. */
  href = '';
  /** `href` marked as a trusted frame URL; set only when the Viewer's
   * origin differs from the app's. */
  frameSrc: SafeResourceUrl | null = null;
  copyState: 'idle' | 'copied' | 'failed' = 'idle';

  constructor(private sanitizer: DomSanitizer) {}

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['link'] || changes['serverUrl'] || changes['appOrigin']) {
      this.href = this.resolveHref();
      this.frameSrc = this.href && new URL(this.href).origin !== this.appOrigin
        ? this.sanitizer.bypassSecurityTrustResourceUrl(this.href)
        : null;
    }
    if (changes['link']) this.copyState = 'idle';
  }

  private resolveHref(): string {
    if (!this.link) return '';
    try {
      const url = new URL(this.link, this.serverUrl || undefined);
      if (url.protocol !== 'http:' && url.protocol !== 'https:') return '';
      for (const [name, value] of Object.entries(VIEWER_GRAPH_DEFAULTS)) {
        if (!url.searchParams.has(name)) url.searchParams.set(name, value);
      }
      return url.href;
    } catch {
      return '';
    }
  }

  /** The link shown and copied: the embedded one (`href`) when the link is
   * usable, so opening it elsewhere draws the same graph; else as given. */
  get shownLink(): string {
    return this.href || this.link;
  }

  get canUpload(): boolean {
    return this.configured === true && !!this.selectedPredFile && this.state !== 'uploading';
  }

  get missingSettings(): { name: string; role: string }[] {
    return this.missing.map(name => ({ name, role: SETTING_ROLES[name] ?? '' }));
  }

  async copyLink(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.shownLink);
      this.copyState = 'copied';
    } catch {
      this.copyState = 'failed';
    }
  }
}
