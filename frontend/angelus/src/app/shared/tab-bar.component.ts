import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-tab-bar',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="tab-bar">
      @for (tab of tabs; track tab) {
        <div
          class="tab-item"
          [class.active]="activeTab === tab"
          (click)="onTabClick(tab)"
        >
          {{ tab }}
        </div>
      }
    </div>
  `,
  styles: [`
    .tab-bar {
      display: flex;
      gap: 4px;
      margin-bottom: 16px;
      border-bottom: 1px solid rgba(148,163,184,.08);
      padding-bottom: 1px;
    }
    .tab-item {
      padding: 10px 18px;
      font-size: 14px;
      color: #94a3b8;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
      transition: all 0.2s;
      white-space: nowrap;
    }
    .tab-item:hover {
      color: #cbd5e1;
    }
    .tab-item.active {
      color: #8B5CF6;
      border-bottom-color: #8B5CF6;
      font-weight: 600;
    }
  `]
})
export class TabBarComponent {
  @Input({ required: true }) tabs: string[] = [];
  @Input({ required: true }) activeTab = '';
  @Output() tabChange = new EventEmitter<string>();

  onTabClick(tab: string): void {
    this.tabChange.emit(tab);
  }
}
