import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-stat-card',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="stat-card">
      <div class="stat-header">
        <span class="stat-title">{{ title }}</span>
        @if (trend !== 'neutral') {
          <span class="trend" [class.up]="trend === 'up'" [class.down]="trend === 'down'">
            {{ trend === 'up' ? '↑' : '↓' }}
          </span>
        }
      </div>
      <div class="stat-value" [class]="'tone-'+tone">{{ value }}</div>
      <div class="stat-subtitle">{{ subtitle }}</div>
    </div>
  `,
  styles: [`
    .stat-card { background:#131827; border:1px solid rgba(148,163,184,.08); border-radius:12px; padding:1rem 1.1rem; }
    .stat-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:.4rem; }
    .stat-title { font-size:.72rem; color:#94A3B8; text-transform:uppercase; letter-spacing:.06em; }
    .trend { font-size:.85rem; font-weight:700; }
    .trend.up { color:#10B981; } .trend.down { color:#EF4444; }
    .stat-value { font-size:1.45rem; font-weight:700; color:#F1F5F9; }
    .tone-good { color:#10B981; } .tone-warning { color:#F59E0B; } .tone-bad { color:#EF4444; } .tone-neutral { color:#F1F5F9; }
    .stat-subtitle { font-size:.72rem; color:#64748B; margin-top:.25rem; }
  `]
})
export class StatCardComponent {
  @Input() title = '';
  @Input() value = '';
  @Input() subtitle = '';
  @Input() trend: 'up' | 'down' | 'neutral' = 'neutral';
  @Input() tone: 'good' | 'warning' | 'bad' | 'neutral' = 'neutral';
}
