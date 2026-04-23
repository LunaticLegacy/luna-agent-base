import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-pagination',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="pagination-bar">
      <div class="pagination-summary">
        <span>共 {{ totalItems }} 条</span>
        <span>第 {{ currentPage }} / {{ totalPages }} 页</span>
        <span>{{ itemRange }}</span>
      </div>
      <div class="pagination-controls">
        <button class="btn btn-sm" (click)="prevPage()" [disabled]="currentPage <= 1 || loading">上一页</button>
        <button class="btn btn-sm" (click)="nextPage()" [disabled]="currentPage >= totalPages || loading">下一页</button>
        <ng-content select="[extra]"></ng-content>
      </div>
    </div>
  `,
  styles: [`
    .pagination-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 16px;
      border-top: 1px solid rgba(148,163,184,.08);
      font-size: 13px;
      color: #94A3B8;
    }
    .pagination-summary {
      display: flex;
      gap: 12px;
    }
    .pagination-controls {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: .4rem;
      padding: .55rem 1rem;
      border-radius: 8px;
      border: none;
      color: #fff;
      font-size: .82rem;
      font-weight: 600;
      cursor: pointer;
      background: rgba(255,255,255,.06);
      color: #94A3B8;
    }
    .btn:hover:not(:disabled) {
      background: rgba(255,255,255,.1);
      color: #F1F5F9;
    }
    .btn:disabled {
      opacity: .4;
      cursor: not-allowed;
    }
    .btn-sm { padding: .35rem .7rem; font-size: .78rem; }
  `]
})
export class PaginationComponent {
  @Input({ required: true }) currentPage = 1;
  @Input({ required: true }) totalItems = 0;
  @Input() pageSize = 20;
  @Input() loading = false;

  @Output() pageChange = new EventEmitter<number>();

  get totalPages(): number {
    return Math.max(1, Math.ceil(this.totalItems / this.pageSize));
  }

  get itemRange(): string {
    const start = (this.currentPage - 1) * this.pageSize + 1;
    const end = Math.min(this.currentPage * this.pageSize, this.totalItems);
    if (this.totalItems === 0) return '0 条';
    return `${start} - ${end} 条`;
  }

  prevPage(): void {
    if (this.currentPage > 1) {
      this.pageChange.emit(this.currentPage - 1);
    }
  }

  nextPage(): void {
    if (this.currentPage < this.totalPages) {
      this.pageChange.emit(this.currentPage + 1);
    }
  }
}
