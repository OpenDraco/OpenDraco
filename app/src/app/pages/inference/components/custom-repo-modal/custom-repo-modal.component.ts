/** Modal that adds a public GitHub repo as a custom-instance row.
 * Inference-only — the SWE-bench harness can't score these. Parent
 * owns the four form values + open/submitting state; this component
 * is a controlled view. */
import {
  Component, EventEmitter, HostListener, Input, Output,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-custom-repo-modal',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './custom-repo-modal.component.html',
})
export class CustomRepoModalComponent {
  @Input() open = false;
  @Input() submitting = false;
  @Input() repo = '';
  @Input() problem = '';
  @Input() baseCommit = '';
  @Input() error = '';

  @Output() repoChange       = new EventEmitter<string>();
  @Output() problemChange    = new EventEmitter<string>();
  @Output() baseCommitChange = new EventEmitter<string>();
  @Output() submit           = new EventEmitter<void>();
  @Output() close            = new EventEmitter<void>();

  onRepoChange(v: string): void       { this.repo       = v; this.repoChange.emit(v); }
  onProblemChange(v: string): void    { this.problem    = v; this.problemChange.emit(v); }
  onBaseCommitChange(v: string): void { this.baseCommit = v; this.baseCommitChange.emit(v); }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.open && !this.submitting) this.close.emit();
  }
}
