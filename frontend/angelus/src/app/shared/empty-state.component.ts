import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-empty-state',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="empty-state" [class.block]="variant === 'block'" [class.cell]="variant === 'cell'">
      {{ message }}
    </div>
  `,
  styles: [`
    .empty-state {
      text-align: center;
      color: #64748b;
    }
    .empty-state.block {
      padding: 20px 24px;
      font-size: 13px;
      background: #0B0F19;
      border-radius: 8px;
    }
    .empty-state.cell {
      padding: 24px 32px;
    }
  `]
})
export class EmptyStateComponent {
  @Input() message = '暂无数据';
  @Input() variant: 'block' | 'cell' = 'block';
}
