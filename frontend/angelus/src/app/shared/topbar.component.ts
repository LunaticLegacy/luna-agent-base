import { Component, Input, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StateService } from '../services/state.service';

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [CommonModule],
  template: `
    <header class="topbar">
      <div class="breadcrumb">
        <span>Angelus</span>
        <span class="breadcrumb-sep">/</span>
        <span class="breadcrumb-current">{{ pageTitle }}</span>
      </div>
      <div class="topbar-actions">
        <span class="topbar-chip">
          <span class="status-dot"></span>
          {{ state.health()?.status === 'ok' ? 'System Online' : 'Offline' }}
        </span>
        <button class="topbar-btn" title="刷新" (click)="state.refreshAll()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
        </button>
        <button class="topbar-btn" title="通知">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
          </svg>
        </button>
        <button class="topbar-user">
          <div class="user-avatar">A</div>
          <span>Admin</span>
        </button>
      </div>
    </header>
  `,
  styles: [`
    .topbar {
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 1.5rem;
      border-bottom: 1px solid rgba(148, 163, 184, 0.08);
      background: #0B0F19;
      position: sticky;
      top: 0;
      z-index: 50;
    }
    .breadcrumb {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.88rem;
      color: #94A3B8;
    }
    .breadcrumb-sep {
      color: #64748B;
    }
    .breadcrumb-current {
      color: #F1F5F9;
      font-weight: 600;
    }
    .topbar-actions {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .topbar-chip {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.35rem 0.7rem;
      border-radius: 999px;
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.2);
      color: #10B981;
      font-size: 0.78rem;
      font-weight: 500;
    }
    .status-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #10B981;
      box-shadow: 0 0 6px #10B981;
      display: inline-block;
    }
    .topbar-btn {
      width: 2rem;
      height: 2rem;
      border-radius: 8px;
      border: 1px solid rgba(148, 163, 184, 0.08);
      background: transparent;
      color: #94A3B8;
      display: grid;
      place-items: center;
      cursor: pointer;
      transition: all 0.2s;
    }
    .topbar-btn:hover {
      background: rgba(255, 255, 255, 0.04);
      color: #F1F5F9;
    }
    .topbar-user {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.25rem 0.6rem 0.25rem 0.25rem;
      border-radius: 999px;
      border: 1px solid rgba(148, 163, 184, 0.08);
      background: transparent;
      color: #94A3B8;
      font-size: 0.82rem;
      cursor: pointer;
    }
    .user-avatar {
      width: 1.6rem;
      height: 1.6rem;
      border-radius: 50%;
      background: linear-gradient(135deg, #7C3AED, #3B82F6);
      display: grid;
      place-items: center;
      font-size: 0.65rem;
      font-weight: 700;
      color: white;
    }
  `]
})
export class TopbarComponent {
  readonly state = inject(StateService);
  @Input({ required: true }) pageTitle = '';
}
