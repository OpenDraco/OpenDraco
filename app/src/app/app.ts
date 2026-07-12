import { Component, ElementRef, HostListener, ViewChild, ChangeDetectorRef, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { ApiService } from './services/api.service';
import { TopologyStateService } from './services/topology-state.service';
import { UnifiedConfig, ConfigSummary } from './models/types';
import { ApragonIconComponent, EvoSelectComponent } from './components/index';
import { DialogHostComponent } from './components/dialog-host/dialog-host.component';
import { DialogService } from './services/dialog.service';
import type { SelectOption, SelectOptionGroup } from './components/select/evo-select.component';

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule, RouterOutlet, RouterLink, RouterLinkActive, ApragonIconComponent, EvoSelectComponent, DialogHostComponent],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements OnInit, OnDestroy {
  @ViewChild('fileInput') fileInput!: ElementRef<HTMLInputElement>;

  menuOpen = false;
  saveDialogOpen = false;
  saveName = '';
  saveError = '';
  /** Stem of the config being exported. The dropdown defaults to the
   * currently-active config; the user can pick any predefined or loaded
   * entry. When the picked stem matches `currentConfigName`, the
   * exporter uses the in-memory `currentConfig` (so unsaved edits are
   * preserved); otherwise it re-fetches the picked file from the API
   * so the export reflects the on-disk version. */
  saveSourceStem = '';
  saveBusy = false;

  // "Create from template" dialog — predefined + loaded both eligible.
  templateDialogOpen = false;
  templateOptions: ConfigSummary[] = [];
  templateChoice = '';
  templateNewName = '';
  templateError = '';
  templateBusy = false;

  /** `templateOptions` shaped for `<evo-select [optgroups]>` — Predefined then Loaded. */
  get templateSelectGroups(): SelectOptionGroup[] {
    const groups: SelectOptionGroup[] = [];
    const predefined = this.templateOptions.filter(c => c.source === 'predefined');
    const loaded = this.templateOptions.filter(c => c.source === 'loaded');
    if (predefined.length > 0) {
      groups.push({
        label: 'Predefined',
        items: predefined.map(t => ({ value: t.stem, label: t.id || t.stem })),
      });
    }
    if (loaded.length > 0) {
      groups.push({
        label: 'Loaded',
        items: loaded.map(t => ({ value: t.stem, label: t.id || t.stem })),
      });
    }
    return groups;
  }

  /** Same shape as `templateSelectGroups` but sourced from the live
   * catalog (`state.predefinedConfigs`) — used by the Export-config
   * dialog's "Which config" dropdown so the user can export any entry,
   * not just the active one. */
  get exportSelectGroups(): SelectOptionGroup[] {
    const groups: SelectOptionGroup[] = [];
    const predefined = this.state.predefinedConfigs.filter(c => c.source === 'predefined');
    const loaded = this.state.predefinedConfigs.filter(c => c.source === 'loaded');
    if (predefined.length > 0) {
      groups.push({
        label: 'Predefined',
        items: predefined.map(t => ({ value: t.stem, label: t.id || t.stem })),
      });
    }
    if (loaded.length > 0) {
      groups.push({
        label: 'Loaded',
        items: loaded.map(t => ({ value: t.stem, label: t.id || t.stem })),
      });
    }
    return groups;
  }

  apiOnline: boolean | null = null;
  apiHost = '';
  private healthTimer?: ReturnType<typeof setInterval>;
  /** True after at least one failed probe — triggers a hard-reload on recovery. */
  private wasOffline = false;

  constructor(
    private api: ApiService,
    private state: TopologyStateService,
    private cdr: ChangeDetectorRef,
    private dialog: DialogService,
  ) {}

  ngOnInit(): void {
    this.apiHost = this.api.apiHost;
    this.checkHealth();
    this.healthTimer = setInterval(() => this.checkHealth(), 5000);
  }

  ngOnDestroy(): void {
    if (this.healthTimer) clearInterval(this.healthTimer);
  }

  private checkHealth(): void {
    this.api.getHealth().subscribe({
      next: () => {
        if (this.wasOffline) {
          // API recovered — reload to pick up any backend changes.
          window.location.reload();
          return;
        }
        if (this.apiOnline !== true) {
          this.apiOnline = true;
          this.cdr.markForCheck();
        }
      },
      error: () => {
        this.wasOffline = true;
        if (this.apiOnline !== false) {
          this.apiOnline = false;
          this.cdr.markForCheck();
        }
      },
    });
  }

  toggleMenu(): void {
    this.menuOpen = !this.menuOpen;
  }

  @HostListener('document:click', ['$event'])
  onDocClick(ev: MouseEvent): void {
    if (!this.menuOpen) return;
    const target = ev.target as HTMLElement;
    if (target.closest('.brand-menu') || target.closest('.brand-trigger')) return;
    this.menuOpen = false;
  }

  openSaveDialog(): void {
    if (this.state.predefinedConfigs.length === 0 && !this.state.currentConfig) {
      this.dialog.alert({
        title: 'Nothing to save',
        message: 'No configurations available to export.',
      });
      return;
    }
    // Default the dropdown to the currently-active config when one is
    // loaded; otherwise fall back to the first catalog entry. The name
    // input starts empty so the user always types it deliberately
    // (avoids accidentally exporting "chain.json" because they didn't
    // notice the default name was pre-filled).
    const active = this.state.currentConfigName;
    const fallback = this.state.predefinedConfigs[0]?.stem ?? '';
    this.saveSourceStem = (active && this.state.predefinedConfigs.some(c => c.stem === active))
      ? active
      : fallback;
    this.saveName = '';
    this.saveError = '';
    this.saveBusy = false;
    this.saveDialogOpen = true;
    this.menuOpen = false;
  }

  cancelSave(): void {
    this.saveDialogOpen = false;
    this.saveName = '';
    this.saveSourceStem = '';
    this.saveError = '';
    this.saveBusy = false;
  }

  /** Download the picked config under the chosen filename. When the
   * picked stem is the currently-active config we use the in-memory
   * `currentConfig` so unsaved edits flow into the export; otherwise
   * we fetch the on-disk version via the API. */
  confirmSave(): void {
    if (this.saveBusy) return;
    const name = this.saveName.trim();
    if (!name) { this.saveError = 'Name cannot be empty.'; return; }
    if (/[\\/:*?"<>|]/.test(name)) {
      this.saveError = 'Name contains invalid characters.';
      return;
    }
    if (!this.saveSourceStem) {
      this.saveError = 'Pick a config to export.';
      return;
    }

    const finalize = (cfg: UnifiedConfig) => {
      // Sync `id` to the chosen filename — the loader treats `id` as
      // the routing key and enforces `id == stem` on re-import.
      const cloned = { ...cfg, id: name } as UnifiedConfig;
      const json = JSON.stringify(cloned, null, 2);
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${name}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      this.saveDialogOpen = false;
      this.saveName = '';
      this.saveSourceStem = '';
      this.saveError = '';
      this.saveBusy = false;
      this.cdr.markForCheck();
    };

    // Active config → in-memory (carries unsaved edits). Otherwise →
    // re-fetch so the export reflects the on-disk version.
    if (this.saveSourceStem === this.state.currentConfigName && this.state.currentConfig) {
      finalize(this.state.currentConfig);
      return;
    }
    this.saveBusy = true;
    this.api.getConfig(this.saveSourceStem).subscribe({
      next: cfg => finalize(cfg),
      error: err => {
        this.saveBusy = false;
        this.saveError = `Could not fetch "${this.saveSourceStem}": ${err?.error?.detail ?? err?.message ?? 'unknown error'}`;
        this.cdr.markForCheck();
      },
    });
  }

  openFilePicker(): void {
    this.menuOpen = false;
    this.fileInput?.nativeElement.click();
  }

  /** Open the "Create from template" modal. Snapshots the config list
   * to avoid mid-flight reactivity. */
  openCreateFromTemplate(): void {
    this.templateOptions = this.state.predefinedConfigs.slice();
    if (this.templateOptions.length === 0) {
      this.dialog.alert({
        title: 'No templates',
        message: 'No templates available.',
      });
      this.menuOpen = false;
      return;
    }
    // Default to the active config (fork-current is the common intent).
    const active = this.state.currentConfigName;
    const matchingTemplate = active
      ? this.templateOptions.find(t => t.stem === active)
      : undefined;
    const firstPredefined = this.templateOptions.find(c => c.source === 'predefined');
    this.templateChoice = (matchingTemplate ?? firstPredefined ?? this.templateOptions[0]).stem;
    this.templateNewName = '';
    this.templateError = '';
    this.templateBusy = false;
    this.templateDialogOpen = true;
    this.menuOpen = false;
  }

  cancelCreateFromTemplate(): void {
    this.templateDialogOpen = false;
    this.templateChoice = '';
    this.templateNewName = '';
    this.templateError = '';
    this.templateBusy = false;
  }

  /** Fetch the template, rewrite `id` to the new stem, persist. */
  confirmCreateFromTemplate(): void {
    const name = this.templateNewName.trim();
    if (!name) { this.templateError = 'Name cannot be empty.'; return; }
    if (/[\\/:*?"<>|]/.test(name)) {
      this.templateError = 'Name contains invalid characters.';
      return;
    }
    if (this.state.predefinedConfigs.some(c => (c.stem === name || c.id === name) && c.source === 'predefined')) {
      this.templateError = `"${name}" collides with a predefined config. Pick a different name.`;
      return;
    }
    if (!this.templateChoice) {
      this.templateError = 'Pick a template first.';
      return;
    }

    this.templateBusy = true;
    this.api.getConfig(this.templateChoice).subscribe({
      next: tpl => {
        const cloned = { ...tpl, id: name } as unknown as Record<string, unknown>;
        this.persistLoadedConfig(name, cloned);
        this.templateDialogOpen = false;
        this.templateChoice = '';
        this.templateNewName = '';
        this.templateError = '';
        this.templateBusy = false;
      },
      error: err => {
        this.templateError = `Failed to fetch template: ${err?.error?.detail ?? err?.message ?? 'unknown error'}`;
        this.templateBusy = false;
        this.cdr.markForCheck();
      },
    });
  }

  onFileChosen(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(reader.result as string) as Record<string, unknown>;
      } catch (err) {
        this.dialog.alert({
          title: 'Import failed',
          variant: 'danger',
          message: 'The file could not be parsed as JSON.',
          detail: (err as Error).message,
        });
        return;
      }
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        this.dialog.alert({
          title: 'Import failed',
          variant: 'danger',
          message: 'The file does not contain a JSON object.',
        });
        return;
      }
      const stem = file.name.replace(/\.json$/i, '');
      // Permissive import: no required-key / id-stem checks. The
      // topology page's Validate button surfaces structural problems
      // against the in-memory config; the file imports as-is.
      this.persistLoadedConfig(stem, parsed);
    };
    reader.onerror = () => this.dialog.alert({
      title: 'Read failed',
      variant: 'danger',
      message: 'Could not read the selected file.',
    });
    reader.readAsText(file);
  }

  /** POST the config; on 409 prompt for replacement and retry. */
  private persistLoadedConfig(stem: string, data: Record<string, unknown>, replace = false): void {
    this.api.saveLoadedConfig(stem, data, replace).subscribe({
      next: () => this.refreshConfigsAfterImport(stem, data as unknown as UnifiedConfig),
      error: async err => {
        if (err?.status === 409 && !replace) {
          const ok = await this.dialog.confirm({
            title: 'Config already exists',
            message: `A loaded config named "${stem}" already exists. Replace it?`,
            okLabel: 'Replace',
            danger: true,
          });
          if (ok) this.persistLoadedConfig(stem, data, true);
          return;
        }
        this.dialog.alert({
          title: 'Load failed',
          variant: 'danger',
          detail: err?.error?.detail ?? err?.message ?? 'unknown error',
        });
      },
    });
  }

  private refreshConfigsAfterImport(stem: string, data: UnifiedConfig): void {
    this.api.getConfigs().subscribe({
      next: list => {
        this.state.predefinedConfigs = list;
        this.state.setCurrentConfig(data, stem);
        this.cdr.markForCheck();
      },
      error: () => { this.state.setCurrentConfig(data, stem); this.cdr.markForCheck(); },
    });
  }
}
