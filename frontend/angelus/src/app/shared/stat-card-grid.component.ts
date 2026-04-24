import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface StatCardItem {
  label: string;
  value: string | number | null;
  subtitle?: string;
  tone?: 'good' | 'warning' | 'bad' | 'neutral' | 'purple' | 'amber' | 'blue' | 'green' | 'red';
  trend?: 'up' | 'down' | 'neutral';
}

@Component({
  selector: 'app-stat-card-grid',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="stat-cards-row">
      @for (card of cards; track card.label) {
        <div class="stat-card">
          <div class="stat-header">
            <span class="stat-label">{{ card.label }}</span>
            @if (card.trend && card.trend !== 'neutral') {
              <span class="trend" [class.up]="card.trend === 'up'" [class.down]="card.trend === 'down'">
                {{ card.trend === 'up' ? '↑' : '↓' }}
              </span>
            }
          </div>
          <div class="stat-value" [class]="'tone-' + (card.tone || 'neutral')">{{ card.value }}</div>
          @if (card.subtitle) {
            <div class="stat-sub">{{ card.subtitle }}</div>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .stat-cards-row {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 16px;
      margin-bottom: 20px;
    }
    .stat-card {
      background: #131827;
      border: 1px solid rgba(148,163,184,.08);
      border-radius: 12px;
      padding: 16px;
    }
    .stat-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: .4rem;
    }
    .stat-label {
      font-size: 12px;
      color: #94A3B8;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 8px;
    }
    .trend { font-size: .85rem; font-weight: 700; }
    .trend.up { color: #10B981; }
    .trend.down { color: #EF4444; }
    .stat-value {
      font-size: 20px;
      font-weight: 700;
      color: #f8fafc;
    }
    .stat-sub {
      font-size: 12px;
      color: #64748b;
      margin-top: .25rem;
    }
    .tone-good, .tone-green { color: #10B981; }
    .tone-warning, .tone-amber { color: #F59E0B; }
    .tone-bad, .tone-red { color: #EF4444; }
    .tone-neutral { color: #f8fafc; }
    .tone-purple { color: #C4B5FD; }
    .tone-blue { color: #60A5FA; }
  `]
})
export class StatCardGridComponent {
  @Input({ required: true }) cards: StatCardItem[] = [];
}
