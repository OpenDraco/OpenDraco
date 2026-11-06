/**
 * Graphectory panel: one rendered state per situation (not configured,
 * idle, uploading, server error, unreachable, ready), and the Viewer
 * link is only ever embedded in an iframe when the Viewer is on another
 * origin than the app — then with `allow-scripts allow-same-origin
 * allow-popups`, through `src`, never in the app's own DOM.
 */
import '@angular/compiler';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { GraphectoryPanelComponent } from './graphectory-panel.component';
import type { ResultPredictionFile } from '../../../../models/types';

const PRED: ResultPredictionFile = {
  path: '/repo/results/predictions/prediction-chain-4f7d9f56.jsonl',
  name: 'prediction-chain-4f7d9f56.jsonl',
  mtime: 0,
};
const VIEWER = 'https://viewer.example:9610';
const LINK = `${VIEWER}/graph/opendraco/chain-4f7d9f56`;
/** `LINK` with the Viewer page's own view options, as embedded and opened. */
const VIEW_QUERY = 'filter_cd=false&filter_repeated=false&thought_quotes=true'
  + '&show_observation=false&unique_think=false';
const VIEWED = `${LINK}?${VIEW_QUERY}`;
const APP_ORIGIN = 'http://localhost:4200';

describe('GraphectoryPanelComponent', () => {
  let fixture: ComponentFixture<GraphectoryPanelComponent>;
  let el: HTMLElement;

  function render(inputs: Partial<Record<keyof GraphectoryPanelComponent, unknown>>): void {
    for (const [k, v] of Object.entries(inputs)) fixture.componentRef.setInput(k, v);
    fixture.detectChanges();
  }
  const stateEl = () => el.querySelector('[data-state]')?.getAttribute('data-state');
  const button = (label: string) => [...el.querySelectorAll('button')]
    .find(b => b.textContent?.includes(label)) as HTMLButtonElement | undefined;
  const ready = (extra: Partial<Record<keyof GraphectoryPanelComponent, unknown>> = {}) => render({
    configured: true, serverUrl: VIEWER, selectedPredFile: PRED,
    state: 'ready', link: LINK, appOrigin: APP_ORIGIN, ...extra,
  });

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [GraphectoryPanelComponent] }).compileComponents();
    fixture = TestBed.createComponent(GraphectoryPanelComponent);
    el = fixture.nativeElement as HTMLElement;
  });

  it('names GRAPHECTORY_URL and its role when it is not configured', () => {
    render({ configured: false, selectedPredFile: PRED, missing: ['GRAPHECTORY_URL'] });
    expect(stateEl()).toBe('not-configured');
    expect(el.textContent).toContain('GRAPHECTORY_URL');
    expect(el.textContent).toContain('http://localhost:9610');
    expect(el.textContent).toContain('opendraco/.env');
    expect(el.textContent).not.toContain('INGEST');
    expect(button('Analyze in Graphectory')!.disabled).toBe(true);
  });

  it('offers the upload once configured and a prediction is selected', () => {
    render({ configured: true, serverUrl: VIEWER, selectedPredFile: PRED });
    expect(stateEl()).toBe('idle');
    expect(button('Analyze in Graphectory')!.disabled).toBe(false);
    expect(button('New tab')!.disabled).toBe(true);
    expect(button('Copy')).toBeUndefined();
    expect(button('Save HTML')).toBeUndefined();
  });

  it('shows a spinner and disables the upload while uploading', () => {
    render({ configured: true, selectedPredFile: PRED, state: 'uploading' });
    expect(stateEl()).toBe('uploading');
    expect(el.querySelector('.spinner')).not.toBeNull();
    expect(button('Analyze in Graphectory')!.disabled).toBe(true);
  });

  it("shows the server's error message", () => {
    render({
      configured: true, selectedPredFile: PRED,
      state: 'error',
      error: 'Graphectory could not convert the run: No OpenDraco event log found',
    });
    expect(stateEl()).toBe('error');
    expect(el.textContent).toContain('No OpenDraco event log found');
    expect(button('Analyze in Graphectory')!.disabled).toBe(false);
  });

  it('tells an unreachable or timed-out server apart', () => {
    render({
      configured: true, serverUrl: VIEWER, selectedPredFile: PRED,
      state: 'unreachable', error: 'Could not reach the Graphectory Viewer at https://viewer.example:9610: refused',
    });
    expect(stateEl()).toBe('unreachable');
    expect(el.textContent).toContain('unreachable or timed out');
    expect(el.textContent).toContain('Could not reach the Graphectory Viewer');
  });

  it('embeds a cross-origin Viewer link in an iframe with the narrowest sandbox that works', () => {
    ready();
    const frame = el.querySelector('iframe') as HTMLIFrameElement;
    expect(frame).not.toBeNull();
    expect(frame.getAttribute('src')).toBe(VIEWED);
    expect(frame.getAttribute('sandbox')).toBe('allow-scripts allow-same-origin allow-popups');
    expect(frame.hasAttribute('srcdoc')).toBe(false);
    expect(el.querySelector('[data-note="same-origin"]')).toBeNull();
    expect(el.querySelector('[data-state="ready"]')?.textContent).toContain(LINK);
    expect(button('New tab')!.disabled).toBe(false);
  });

  it('shows the link only, without embedding, when the Viewer is on the app origin', () => {
    ready({ appOrigin: VIEWER });
    expect(el.querySelector('iframe')).toBeNull();
    expect(el.querySelector('[data-note="same-origin"]')).not.toBeNull();
    expect(el.textContent).toContain(LINK);
    expect(button('Copy')).toBeDefined();
    expect(button('New tab')!.disabled).toBe(false);
  });

  it('never embeds a link that is not http(s)', () => {
    ready({ link: 'javascript:alert(1)' });
    expect(el.querySelector('iframe')).toBeNull();
    expect(el.textContent).toContain('javascript:alert(1)');
    expect(button('New tab')!.disabled).toBe(true);
  });

  it('resolves a relative link against the Viewer URL', () => {
    ready({ link: '/graph/opendraco/chain-4f7d9f56' });
    expect((el.querySelector('iframe') as HTMLIFrameElement).getAttribute('src')).toBe(VIEWED);
  });

  it("asks for the Viewer page's view options, so think steps share one node", () => {
    ready({ link: `${VIEWER}/api/graph?id=openhands_star-eac5450c` });
    const src = new URL((el.querySelector('iframe') as HTMLIFrameElement).getAttribute('src')!);
    expect(src.searchParams.get('id')).toBe('openhands_star-eac5450c');
    expect(src.searchParams.get('unique_think')).toBe('false');
    expect(src.searchParams.get('thought_quotes')).toBe('true');
    expect(el.querySelector('[data-state="ready"] .link-text')?.textContent).toBe(src.href);
  });

  it('keeps a view option the link already sets', () => {
    ready({ link: `${LINK}?unique_think=true` });
    const src = new URL((el.querySelector('iframe') as HTMLIFrameElement).getAttribute('src')!);
    expect(src.searchParams.getAll('unique_think')).toEqual(['true']);
    expect(src.searchParams.get('filter_repeated')).toBe('false');
  });

  it('emits the resolved link when New tab is clicked', () => {
    ready();
    const opened: string[] = [];
    fixture.componentInstance.openInNewTab.subscribe(href => opened.push(href));
    button('New tab')!.click();
    expect(opened).toEqual([VIEWED]);
  });

  it('copies the link to the clipboard', async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    ready();
    button('Copy')!.click();
    expect(writeText).toHaveBeenCalledWith(VIEWED);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(el.querySelector('[data-copy]')?.getAttribute('data-copy')).toBe('copied');
  });

  it('says so when the clipboard is refused', async () => {
    const writeText = vi.fn(() => Promise.reject(new Error('denied')));
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    ready();
    button('Copy')!.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(el.querySelector('[data-copy]')?.getAttribute('data-copy')).toBe('failed');
  });
});
