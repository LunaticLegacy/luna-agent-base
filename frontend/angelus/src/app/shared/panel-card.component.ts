import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-panel-card',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="panel-card" [class.no-padding]="noPadding">
      @if (title || hasActions) {
        <div class="panel-header">
          <div class="panel-header-left">
            <h3>{{ title }}</h3>
            @if (badge !== undefined && badge !== null && badge !== '') {
              <span class="badge">{{ badge }}</span>
            }
          </div>
          <div class="panel-actions">
            <ng-content select="[actions]"></ng-content>
          </div>
        </div>
      }
      <div class="panel-body">
        <ng-content></ng-content>
      </div>
    </div>
  `,
  styles: [`
    .panel-card {
      background: #131827;
      border: 1px solid rgba(148,163,184,.08);
      border-radius: 12px;
      overflow: hidden;
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 14px 18px;
      border-bottom: 1px solid rgba(148,163,184,.08);
    }
    .panel-header-left {
      display: flex;
      align-items: center;
      gap: .6rem;
    }
    .panel-header h3 {
      margin: 0;
      font-size: 14px;
      font-weight: 600;
      color: #f8fafc;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 20px;
      padding: 1px 7px;
      border-radius: 999px;
      background: rgba(139,92,246,.12);
      color: #C4B5FD;
      font-size: 11px;
      font-weight: 600;
    }
    .panel-actions {
      display: flex;
      gap: .5rem;
      align-items: center;
    }
    .panel-body {
      padding: 16px 18px;
    }
    .panel-card.no-padding .panel-body {
      padding: 0;
    }
  `]
})
export class PanelCardComponent {
  @Input() title = '';
  @Input() badge: string | number = '';
  @Input() noPadding = false;
  @Input() hasActions = false;
}
