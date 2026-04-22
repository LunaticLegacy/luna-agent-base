import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { StateService } from '../services/state.service';

@Component({
  selector: 'app-logs-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="page-header">
      <div>
        <h1 class="page-title">系统日志</h1>
        <p class="page-subtitle">结构化日志查询与分析</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-sm" (click)="autoScroll.set(!autoScroll())">
          {{ autoScroll() ? '暂停滚动' : '自动滚动' }}
        </button>
        <button class="btn btn-sm btn-primary">导出</button>
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat-card"><div class="stat-label">总日志数</div><div class="stat-value">{{ stats().total }}</div><div class="stat-sub">条记录</div></div>
      <div class="stat-card"><div class="stat-label">ERROR</div><div class="stat-value stat-red">{{ stats().error }}</div><div class="stat-sub">严重</div></div>
      <div class="stat-card"><div class="stat-label">WARN</div><div class="stat-value stat-amber">{{ stats().warn }}</div><div class="stat-sub">警告</div></div>
      <div class="stat-card"><div class="stat-label">INFO</div><div class="stat-value stat-green">{{ stats().info }}</div><div class="stat-sub">信息</div></div>
      <div class="stat-card"><div class="stat-label">DEBUG</div><div class="stat-value stat-blue">{{ stats().debug }}</div><div class="stat-sub">调试</div></div>
    </div>

    <div class="card">
      <div class="card-header">
        <div class="level-filters">
          <button class="level-btn" [class.active]="levelFilter()==='all'" (click)="levelFilter.set('all')">全部</button>
          <button class="level-btn error" [class.active]="levelFilter()==='ERROR'" (click)="levelFilter.set('ERROR')">ERROR</button>
          <button class="level-btn warn" [class.active]="levelFilter()==='WARN'" (click)="levelFilter.set('WARN')">WARN</button>
          <button class="level-btn info" [class.active]="levelFilter()==='INFO'" (click)="levelFilter.set('INFO')">INFO</button>
          <button class="level-btn debug" [class.active]="levelFilter()==='DEBUG'" (click)="levelFilter.set('DEBUG')">DEBUG</button>
        </div>
        <div class="toolbar">
          <input class="input search" placeholder="搜索日志内容..." [(ngModel)]="searchText" />
          <select class="input"><option>所有服务</option><option>backend</option><option>agent</option><option>graph</option></select>
        </div>
      </div>

      <div class="log-container" #logContainer>
        @for (log of filteredLogs(); track log.id) {
          <div class="log-line" [class]="'log-'+log.level.toLowerCase()">
            <span class="log-time">{{ log.time }}</span>
            <span class="log-level">{{ log.level }}</span>
            <span class="log-service">{{ log.service }}</span>
            <span class="log-msg">{{ log.message }}</span>
          </div>
        } @empty {
          <div class="empty">暂无日志记录</div>
        }
      </div>
    </div>
  `,
  styles: [`
    :host { display:block; }
    .page-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:1.25rem; }
    .page-title { font-size:1.35rem; font-weight:700; color:#F1F5F9; margin:0; }
    .page-subtitle { font-size:.82rem; color:#94A3B8; margin:.25rem 0 0; }
    .header-actions { display:flex; gap:.5rem; }
    .btn { display:inline-flex; align-items:center; gap:.4rem; padding:.55rem 1rem; border-radius:8px; border:none; color:#fff; font-size:.82rem; font-weight:600; cursor:pointer; }
    .btn-primary { background:linear-gradient(135deg,#7C3AED,#A78BFA); }
    .btn-sm { padding:.35rem .7rem; font-size:.78rem; background:rgba(255,255,255,.06); color:#94A3B8; }
    .btn-sm:hover { background:rgba(255,255,255,.1); color:#F1F5F9; }
    .stat-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:1rem; margin-bottom:1.25rem; }
    .stat-card { background:#131827; border:1px solid rgba(148,163,184,.08); border-radius:12px; padding:1rem 1.1rem; }
    .stat-label { font-size:.72rem; color:#94A3B8; text-transform:uppercase; letter-spacing:.06em; margin-bottom:.4rem; }
    .stat-value { font-size:1.4rem; font-weight:700; color:#F1F5F9; }
    .stat-green { color:#10B981; } .stat-purple { color:#A78BFA; } .stat-amber { color:#F59E0B; } .stat-red { color:#EF4444; } .stat-blue { color:#60A5FA; }
    .stat-sub { font-size:.72rem; color:#64748B; margin-top:.2rem; }
    .card { background:#131827; border:1px solid rgba(148,163,184,.08); border-radius:12px; overflow:hidden; }
    .card-header { display:flex; align-items:center; justify-content:space-between; padding:1rem 1.25rem; border-bottom:1px solid rgba(148,163,184,.08); flex-wrap:wrap; gap:.75rem; }
    .level-filters { display:flex; gap:.25rem; }
    .level-btn { padding:.4rem .8rem; border-radius:6px; border:none; background:transparent; color:#94A3B8; font-size:.78rem; cursor:pointer; font-family:'JetBrains Mono',monospace; }
    .level-btn.active { background:rgba(255,255,255,.08); color:#F1F5F9; }
    .level-btn.error.active { background:rgba(239,68,68,.12); color:#FCA5A5; }
    .level-btn.warn.active { background:rgba(245,158,11,.12); color:#FCD34D; }
    .level-btn.info.active { background:rgba(59,130,246,.12); color:#93C5FD; }
    .level-btn.debug.active { background:rgba(107,114,128,.12); color:#CBD5E1; }
    .toolbar { display:flex; gap:.5rem; }
    .input { background:#0B0F19; border:1px solid rgba(148,163,184,.12); border-radius:8px; padding:.45rem .7rem; color:#F1F5F9; font-size:.82rem; }
    .input.search { width:240px; }
    .log-container { max-height:600px; overflow-y:auto; padding:.75rem 0; font-family:'JetBrains Mono',monospace; font-size:.78rem; line-height:1.7; }
    .log-line { display:grid; grid-template-columns:100px 60px 100px 1fr; gap:.75rem; padding:.2rem 1.25rem; color:#E2E8F0; }
    .log-line:hover { background:rgba(255,255,255,.02); }
    .log-time { color:#64748B; }
    .log-level { font-weight:600; }
    .log-error .log-level { color:#EF4444; }
    .log-warn .log-level { color:#F59E0B; }
    .log-info .log-level { color:#60A5FA; }
    .log-debug .log-level { color:#94A3B8; }
    .log-service { color:#A78BFA; }
    .log-msg { color:#E2E8F0; }
    .empty { text-align:center; padding:3rem; color:#64748B; }
  `]
})
export class LogsPage {
  readonly state = inject(StateService);
  levelFilter = signal<string>('all');
  searchText = '';
  autoScroll = signal(true);

  stats = signal({ total: 1247, error: 3, warn: 23, info: 892, debug: 329 });

  logs = signal<LogItem[]>([
    { id: '1', time: '12:34:56', level: 'INFO', service: 'backend', message: 'Application startup complete' },
    { id: '2', time: '12:34:57', level: 'INFO', service: 'agent', message: 'Swarm deepseek_demo loaded: 12 agents' },
    { id: '3', time: '12:35:01', level: 'DEBUG', service: 'graph', message: 'Building execution graph from 12 nodes' },
    { id: '4', time: '12:35:02', level: 'INFO', service: 'backend', message: 'Graph built: 12 nodes, 18 edges' },
    { id: '5', time: '12:35:12', level: 'WARN', service: 'agent', message: 'Tool web_search timeout after 30000ms' },
    { id: '6', time: '12:35:13', level: 'DEBUG', service: 'agent', message: 'Retrying with fallback search engine' },
    { id: '7', time: '12:36:45', level: 'INFO', service: 'agent', message: 'Round 3 completed: 4 messages processed' },
    { id: '8', time: '12:37:02', level: 'ERROR', service: 'backend', message: 'Redis connection failed: Connection refused' },
    { id: '9', time: '12:37:03', level: 'WARN', service: 'backend', message: 'Falling back to in-memory cache' },
    { id: '10', time: '12:38:10', level: 'INFO', service: 'system', message: 'Health check passed: all systems operational' },
  ]);

  filteredLogs() {
    let list = this.logs();
    if (this.levelFilter() !== 'all') {
      list = list.filter(l => l.level === this.levelFilter());
    }
    if (this.searchText) {
      list = list.filter(l => l.message.toLowerCase().includes(this.searchText.toLowerCase()));
    }
    return list;
  }
}

interface LogItem {
  id: string; time: string; level: string; service: string; message: string;
}
