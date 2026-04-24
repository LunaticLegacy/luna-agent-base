import { Component, Input, Output, ContentChildren, TemplateRef, QueryList, AfterContentInit, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { EmptyStateComponent } from './empty-state.component';

export interface DataTableColumn<T = unknown> {
  key: string;
  header: string;
  width?: string;
  cell?: (row: T) => string;
}

@Component({
  selector: 'app-data-table',
  standalone: true,
  imports: [CommonModule, EmptyStateComponent],
  template: `
    <table class="data-table">
      <thead>
        <tr>
          @for (col of columns; track col.key) {
            <th [style.width]="col.width">{{ col.header }}</th>
          }
        </tr>
      </thead>
      <tbody>
        @for (row of data; track trackByFn(row, $index)) {
          <tr (click)="onRowClick(row)" [class.clickable]="rowClick.observers.length > 0">
            @for (col of columns; track col.key) {
              <td>
                @if (hasCustomTemplate(col.key)) {
                  <ng-container *ngTemplateOutlet="getTemplate(col.key)!; context: { $implicit: row }"></ng-container>
                } @else {
                  {{ col.cell ? col.cell(row) : getCellValue(row, col.key) }}
                }
              </td>
            }
          </tr>
        } @empty {
          <tr>
            <td [attr.colspan]="columns.length" class="empty-cell">
              <app-empty-state [message]="emptyText" variant="cell"></app-empty-state>
            </td>
          </tr>
        }
      </tbody>
    </table>
  `,
  styles: [`
    .data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th {
      text-align: left;
      padding: 10px 16px;
      color: #94a3b8;
      font-weight: 500;
      border-bottom: 1px solid rgba(148,163,184,.08);
      white-space: nowrap;
      background: #0f1525;
    }
    td {
      padding: 10px 16px;
      color: #cbd5e1;
      border-bottom: 1px solid rgba(148,163,184,.05);
      white-space: nowrap;
    }
    tr:hover {
      background: rgba(148,163,184,.03);
    }
    tr.clickable {
      cursor: pointer;
    }
    .empty-cell {
      padding: 0;
      border-bottom: none;
    }
  `]
})
export class DataTableComponent<T = unknown> implements AfterContentInit {
  @Input({ required: true }) columns: DataTableColumn<T>[] = [];
  @Input({ required: true }) data: T[] = [];
  @Input() trackBy: string | ((item: T, index: number) => string) = '';
  @Input() emptyText = '暂无数据';
  @Output() rowClick = new EventEmitter<T>();

  @ContentChildren(TemplateRef, { descendants: true }) templates?: QueryList<TemplateRef<unknown>>;

  private templateMap = new Map<string, TemplateRef<unknown>>();

  ngAfterContentInit(): void {
    // Custom templates are expected to be provided via named template refs
    // Since Angular doesn't easily support named @ContentChildren in v19 without structural directives,
    // we'll use a simpler approach: consumers pass TemplateRef via Input or use a directive.
    // For now, this component supports basic rendering; advanced cell customization
    // should be done via col.cell function.
  }

  trackByFn(item: T, index: number): string {
    if (typeof this.trackBy === 'function') {
      return this.trackBy(item, index);
    }
    if (this.trackBy) {
      const value = (item as Record<string, unknown>)[this.trackBy];
      return value != null ? String(value) : String(index);
    }
    return String(index);
  }

  getCellValue(row: T, key: string): string {
    const value = (row as Record<string, unknown>)[key];
    if (value == null) return '';
    if (typeof value === 'object') return JSON.stringify(value).slice(0, 60);
    return String(value);
  }

  hasCustomTemplate(key: string): boolean {
    return this.templateMap.has(key);
  }

  getTemplate(key: string): TemplateRef<unknown> | undefined {
    return this.templateMap.get(key);
  }

  onRowClick(row: T): void {
    this.rowClick.emit(row);
  }
}

