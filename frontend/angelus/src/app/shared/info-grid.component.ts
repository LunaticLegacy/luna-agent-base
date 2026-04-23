import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface InfoGridItem {
  label: string;
  value: string | number;
  mono?: boolean;
  tone?: 'good' | 'warning' | 'bad' | 'neutral' | 'purple' | 'amber';
}

@Component({
  selector: 'app-info-grid',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="info-grid" [class.two-col]="columns === 2" [class.three-col]="columns === 3">
      @for (item of items; track item.label) {
        <div class="info-item">
          <span class="info-key">{{ item.label }}</span>
          <span class="info-val" [class.mono]="item.mono" [class]="'tone-' + (item.tone || 'neutral')">{{ item.value }}</span>
        </div>
      }
    </div>
  `,
  styles: [`
    .info-grid {
      display: grid;
      gap: .6rem 1.2rem;
    }
    .info-grid.two-col {
      grid-template-columns: repeat(2, 1fr);
    }
    .info-grid.three-col {
      grid-template-columns: repeat(3, 1fr);
    }
    .info-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: .35rem 0;
      border-bottom: 1px solid rgba(148,163,184,.05);
    }
    .info-key {
      font-size: .78rem;
      color: #94A3B8;
    }
    .info-val {
      font-size: .82rem;
      color: #E2E8F0;
      font-weight: 500;
    }
    .info-val.mono {
      font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
      font-size: .78rem;
    }
    .tone-good { color: #10B981; }
    .tone-warning { color: #F59E0B; }
    .tone-bad { color: #EF4444; }
    .tone-neutral { color: #E2E8F0; }
    .tone-purple { color: #C4B5FD; }
    .tone-amber { color: #F59E0B; }
  `]
})
export class InfoGridComponent {
  @Input({ required: true }) items: InfoGridItem[] = [];
  @Input() columns: 2 | 3 = 3;
}
