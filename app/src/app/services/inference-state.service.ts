import { Injectable } from '@angular/core';

/**
 * Persists Inference page selections across navigations. Mirrors
 * `TopologyStateService`: page components delegate selection state through
 * here so the user doesn't lose work when hopping between Topology / Inference
 * / Evaluation / Results.
 */
@Injectable({ providedIn: 'root' })
export class InferenceStateService {
  selectedInstanceIds = new Set<string>();
  config = '';
  instanceSearch = '';
  instancesPage = 0;

  /** Open subset expanders. Default: only lite is open since that's the only
   * subset most users have pulled. */
  openSubsets = new Set<string>(['lite']);
  /** Open subset+split expanders. Key shape: `${subset}/${split}`. */
  openSplits = new Set<string>(['lite/dev']);

  toggleSubset(s: string): void {
    if (this.openSubsets.has(s)) this.openSubsets.delete(s);
    else this.openSubsets.add(s);
  }
  isSubsetOpen(s: string): boolean { return this.openSubsets.has(s); }

  toggleSplit(subset: string, split: string): void {
    const k = `${subset}/${split}`;
    if (this.openSplits.has(k)) this.openSplits.delete(k);
    else this.openSplits.add(k);
  }
  isSplitOpen(subset: string, split: string): boolean {
    return this.openSplits.has(`${subset}/${split}`);
  }

  toggleInstance(id: string): void {
    if (this.selectedInstanceIds.has(id)) this.selectedInstanceIds.delete(id);
    else this.selectedInstanceIds.add(id);
  }

  isSelected(id: string): boolean {
    return this.selectedInstanceIds.has(id);
  }

  setSelection(ids: string[]): void {
    this.selectedInstanceIds = new Set(ids);
  }

  clearSelection(): void {
    this.selectedInstanceIds.clear();
  }

  get selectedList(): string[] {
    return Array.from(this.selectedInstanceIds);
  }
}
