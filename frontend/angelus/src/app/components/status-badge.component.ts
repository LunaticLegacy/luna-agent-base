import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-status-badge',
  standalone: true,
  imports: [CommonModule],
  template: `
    <span class="badge" [class]="'badge-'+tone()">
      <span class="dot"></span>
      {{ label || status }}
    </span>
  `,
  styles: [`
    .badge { display:inline-flex; align-items:center; gap:.35rem; padding:.2rem .55rem; border-radius:999px; font-size:.75rem; font-weight:500; }
    .dot { width:6px; height:6px; border-radius:50%; background:currentColor; }
    .badge-good { background:rgba(16,185,129,.12); color:#10B981; }
    .badge-warning { background:rgba(245,158,11,.12); color:#F59E0B; }
    .badge-bad { background:rgba(239,68,68,.12); color:#EF4444; }
    .badge-neutral { background:rgba(148,163,184,.12); color:#94A3B8; }
    .badge-running { background:rgba(139,92,246,.12); color:#A78BFA; }
    .badge-busy { background:rgba(245,158,11,.12); color:#FCD34D; }
    .badge-idle { background:rgba(59,130,246,.12); color:#93C5FD; }
  `]
})
export class StatusBadgeComponent {
  @Input() status = '';
  @Input() label = '';

  tone(): string {
    const s = (this.status || '').toLowerCase();
    if (['online','healthy','ok','ready','active'].includes(s)) return 'good';
    if (['running','streaming'].includes(s)) return 'running';
    if (['busy','pending'].includes(s)) return 'busy';
    if (['warning','warn'].includes(s)) return 'warning';
    if (['error','offline','failed','dead'].includes(s)) return 'bad';
    if (['idle','standby'].includes(s)) return 'idle';
    return 'neutral';
  }
}
