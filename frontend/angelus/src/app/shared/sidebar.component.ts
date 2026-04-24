import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { StateService } from '../services/state.service';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive],
  template: `
    <aside class="sidebar">
      <div class="sidebar-brand">
        <div class="brand-icon">A</div>
        <div class="brand-text">
          <div class="brand-title">Angelus</div>
          <div class="brand-sub">Lunae</div>
        </div>
      </div>

      <nav class="sidebar-nav">
        @for (item of navItems; track item.path) {
          <a class="nav-item" [routerLink]="item.path" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: item.path === '/' }">
            <span class="nav-icon" [innerHTML]="item.icon"></span>
            <span>{{ item.label }}</span>
          </a>
        }
      </nav>

      <div class="sidebar-footer">
        @if (state.selectedSwarm(); as swarm) {
          <div class="sidebar-swarm-info">
            <div class="sidebar-swarm-icon">S</div>
            <div>
              <div class="sidebar-swarm-name">{{ swarm.swarm_name }}</div>
              <div class="sidebar-swarm-id">{{ swarm.swarm_name }}</div>
            </div>
          </div>
        }
        <div class="sidebar-status">
          <span class="status-dot"></span>
          <span>{{ state.health()?.status === 'ok' ? '系统在线' : '系统离线' }}</span>
        </div>
      </div>
    </aside>
  `,
  styles: [`
    .sidebar {
      width: 240px;
      flex-shrink: 0;
      background: #0F131F;
      border-right: 1px solid rgba(148, 163, 184, 0.08);
      display: flex;
      flex-direction: column;
      position: fixed;
      top: 0;
      left: 0;
      bottom: 0;
      z-index: 100;
    }
    .sidebar-brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 1.25rem 1.5rem;
      border-bottom: 1px solid rgba(148, 163, 184, 0.08);
    }
    .brand-icon {
      width: 2.2rem;
      height: 2.2rem;
      border-radius: 10px;
      background: linear-gradient(135deg, #7C3AED, #A78BFA);
      display: grid;
      place-items: center;
      font-size: 1.1rem;
      color: white;
      font-weight: 700;
    }
    .brand-text {
      display: flex;
      flex-direction: column;
      gap: 0.1rem;
    }
    .brand-title {
      font-size: 0.95rem;
      font-weight: 700;
      color: #F1F5F9;
      letter-spacing: 0.04em;
    }
    .brand-sub {
      font-size: 0.68rem;
      color: #64748B;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .sidebar-nav {
      flex: 1;
      padding: 1rem 0.75rem;
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      overflow-y: auto;
    }
    .nav-item {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.65rem 1rem;
      border-radius: 10px;
      color: #94A3B8;
      font-size: 0.88rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
      border: none;
      background: transparent;
      text-align: left;
      width: 100%;
      text-decoration: none;
    }
    .nav-item:hover {
      background: rgba(255, 255, 255, 0.04);
      color: #F1F5F9;
    }
    .nav-item.active {
      background: linear-gradient(90deg, rgba(139, 92, 246, 0.18), rgba(139, 92, 246, 0.05));
      color: #C4B5FD;
      border-left: 3px solid #8B5CF6;
      margin-left: -3px;
    }
    .nav-icon {
      width: 1.25rem;
      height: 1.25rem;
      opacity: 0.7;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    .nav-item.active .nav-icon {
      opacity: 1;
      color: #8B5CF6;
    }
    .nav-icon svg {
      width: 100%;
      height: 100%;
    }
    .sidebar-footer {
      padding: 1rem 1.25rem;
      border-top: 1px solid rgba(148, 163, 184, 0.08);
    }
    .sidebar-swarm-info {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      margin-bottom: 0.6rem;
    }
    .sidebar-swarm-icon {
      width: 1.5rem;
      height: 1.5rem;
      border-radius: 6px;
      background: rgba(139, 92, 246, 0.15);
      display: grid;
      place-items: center;
      color: #8B5CF6;
      font-size: 0.75rem;
    }
    .sidebar-swarm-name {
      font-size: 0.82rem;
      font-weight: 600;
      color: #F1F5F9;
    }
    .sidebar-swarm-id {
      font-size: 0.7rem;
      color: #64748B;
      font-family: 'JetBrains Mono', ui-monospace, monospace;
      margin-top: 0.15rem;
    }
    .sidebar-status {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.75rem;
      color: #10B981;
    }
    .status-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #10B981;
      box-shadow: 0 0 6px #10B981;
      display: inline-block;
    }
  `]
})
export class SidebarComponent {
  readonly state = inject(StateService);

  readonly navItems = [
    { path: '/', label: '概览', icon: this.overviewIcon() },
    { path: '/swarm', label: 'Swarm', icon: this.swarmIcon() },
    { path: '/agents', label: '智能体', icon: this.agentIcon() },
    { path: '/tasks', label: '任务', icon: this.taskIcon() },
    { path: '/knowledge', label: '知识库', icon: this.knowledgeIcon() },
    { path: '/tools', label: '工具', icon: this.toolIcon() },
    { path: '/memory', label: '记忆', icon: this.memoryIcon() },
    { path: '/logs', label: '日志', icon: this.logIcon() },
    { path: '/settings', label: '设置', icon: this.settingsIcon() },
  ];

  private overviewIcon() {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>`;
  }
  private swarmIcon() {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`;
  }
  private agentIcon() {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`;
  }
  private taskIcon() {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>`;
  }
  private knowledgeIcon() {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`;
  }
  private toolIcon() {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>`;
  }
  private memoryIcon() {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 1 0 10 10H12V2z"/><path d="M12 2a10 10 0 0 1 10 10"/><path d="M12 12L2.5 12"/></svg>`;
  }
  private logIcon() {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`;
  }
  private settingsIcon() {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`;
  }
}
