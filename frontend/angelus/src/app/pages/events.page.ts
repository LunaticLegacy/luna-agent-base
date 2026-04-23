import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StateService, EventItem } from '../services/state.service';

@Component({
  selector: 'app-events-page',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="page-header">
      <div>
        <h1 class="page-title">事件中心</h1>
        <p class="page-subtitle">实时系统事件与活动追踪</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-sm" (click)="clearFilters()">清除筛选</button>
        <button class="btn btn-sm btn-primary" (click)="exportEvents()">导出</button>
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat-card"><div class="stat-label">今日事件</div><div class="stat-value">{{ state.eventStats().today }}</div><div class="stat-sub">条记录</div></div>
      <div class="stat-card"><div class="stat-label">错误事件</div><div class="stat-value stat-red">{{ state.eventStats().errors }}</div><div class="stat-sub">需关注</div></div>
      <div class="stat-card"><div class="stat-label">警告事件</div><div class="stat-value stat-amber">{{ state.eventStats().warnings }}</div><div class="stat-sub">提醒</div></div>
      <div class="stat-card"><div class="stat-label">信息事件</div><div class="stat-value stat-green">{{ state.eventStats().infos }}</div><div class="stat-sub">正常</div></div>
      <div class="stat-card"><div class="stat-label">实时流</div><div class="stat-value stat-purple">{{ state.streamState() || '空闲' }}</div><div class="stat-sub">{{ state.liveEvents().length }} 条缓存</div></div>
    </div>

    <div class="card">
      <div class="card-header">
        <div class="tabs">
          <button class="tab" [class.active]="tab()==='all'" (click)="onTabChange('all')">全部</button>
          <button class="tab" [class.active]="tab()==='error'" (click)="onTabChange('error')">错误</button>
          <button class="tab" [class.active]="tab()==='warn'" (click)="onTabChange('warn')">警告</button>
          <button class="tab" [class.active]="tab()==='info'" (click)="onTabChange('info')">信息</button>
          <button class="tab" [class.active]="tab()==='live'" (click)="onTabChange('live')">实时流</button>
        </div>
        <div class="toolbar">
          <input class="input search" placeholder="搜索事件..." [value]="searchText()" (input)="onSearchChange($any($event).target.value)" />
          <select class="input" [value]="sourceFilter()" (change)="onSourceFilterChange($any($event).target.value)">
            <option value="">所有来源</option>
            <option value="System">系统</option>
            <option value="Swarm">Swarm</option>
            <option value="Agent">Agent</option>
          </select>
          <select class="input" [value]="timeFilter()" (change)="onTimeFilterChange($any($event).target.value)">
            <option value="">全部时间</option>
            <option value="hour">最近1小时</option>
            <option value="day">今天</option>
            <option value="week">最近7天</option>
          </select>
          <select class="input" [value]="pageSize()" (change)="onPageSizeChange($any($event).target.value)">
            <option [value]="20">20 / 页</option>
            <option [value]="50">50 / 页</option>
            <option [value]="100">100 / 页</option>
            <option [value]="200">200 / 页</option>
            <option [value]="500">500 / 页</option>
          </select>
        </div>
      </div>

      @if (tab()==='live') {
        <div class="live-panel">
          <div class="live-header">
            <span class="live-badge" [class.pulsing]="state.streamState()==='open'">
              <span class="live-dot"></span>
              {{ state.streamState() === 'open' ? '实时接收中' : '等待数据' }}
            </span>
          </div>
          <div class="live-list">
            @for (ev of filteredLiveEvents(); track $index) {
              <div class="live-item">
                <div class="live-time">{{ ev.timestamp }}</div>
                <div class="live-type" [class]="'type-'+ev.tone">{{ ev.tone }}</div>
                <div class="live-msg">{{ ev.title }}</div>
              </div>
            } @empty {
              <div class="empty">暂无实时事件，启动 Swarm 运行以接收 SSE 流</div>
            }
          </div>
        </div>
      } @else {
        <table class="data-table">
          <thead><tr><th>时间</th><th>级别</th><th>来源</th><th>事件</th><th>详情</th></tr></thead>
          <tbody>
            @for (ev of filteredEvents(); track ev.id) {
              <tr (click)="toggleDetail(ev)" class="clickable">
                <td class="mono">{{ ev.time }}</td>
                <td><span class="level-badge" [class]="'level-'+ev.level">{{ ev.level }}</span></td>
                <td><span class="tag">{{ ev.source }}</span></td>
                <td>{{ ev.event }}</td>
                <td class="muted">{{ ev.detail | slice:0:40 }}...</td>
              </tr>
              @if (expandedEvent()?.id === ev.id) {
                <tr class="detail-row"><td colspan="5">
                  <div class="event-detail">
                    <pre>{{ ev.data | json }}</pre>
                  </div>
                </td></tr>
              }
            }
          </tbody>
        </table>

        <div class="pagination-bar">
          <div class="pagination-summary">
            <span>共 {{ totalEvents() }} 条</span>
            <span>第 {{ currentPage() }} / {{ totalPages() }} 页</span>
            <span>{{ pageItemRange() }}</span>
          </div>
          <div class="pagination-controls">
            <button class="btn btn-sm" (click)="goToPage(currentPage() - 1)" [disabled]="loading() || currentPage() <= 1">上一页</button>
            <button class="btn btn-sm" (click)="goToPage(currentPage() + 1)" [disabled]="loading() || currentPage() >= totalPages()">下一页</button>
            <button class="btn btn-sm" (click)="reloadEvents(currentPage())" [disabled]="loading()">
              {{ loading() ? '加载中...' : '刷新当前页' }}
            </button>
          </div>
        </div>
      }
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
    .stat-green { color:#10B981; } .stat-purple { color:#A78BFA; } .stat-amber { color:#F59E0B; } .stat-red { color:#EF4444; }
    .stat-sub { font-size:.72rem; color:#64748B; margin-top:.2rem; }
    .card { background:#131827; border:1px solid rgba(148,163,184,.08); border-radius:12px; overflow:hidden; }
    .card-header { display:flex; align-items:center; justify-content:space-between; padding:1rem 1.25rem; border-bottom:1px solid rgba(148,163,184,.08); flex-wrap:wrap; gap:.75rem; }
    .tabs { display:flex; gap:.25rem; }
    .tab { padding:.45rem .9rem; border-radius:8px; border:none; background:transparent; color:#94A3B8; font-size:.82rem; cursor:pointer; }
    .tab.active { background:rgba(139,92,246,.12); color:#C4B5FD; }
    .toolbar { display:flex; gap:.5rem; flex-wrap:wrap; }
    .input { background:#0B0F19; border:1px solid rgba(148,163,184,.12); border-radius:8px; padding:.45rem .7rem; color:#F1F5F9; font-size:.82rem; }
    .input.search { width:200px; }
    .live-panel { padding:1rem 1.25rem; }
    .live-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:.75rem; }
    .live-badge { display:inline-flex; align-items:center; gap:.4rem; padding:.35rem .7rem; border-radius:999px; background:rgba(16,185,129,.1); border:1px solid rgba(16,185,129,.2); color:#10B981; font-size:.78rem; font-weight:500; }
    .live-badge.pulsing .live-dot { animation:pulse 1.5s infinite; }
    .live-dot { width:6px; height:6px; border-radius:50%; background:#10B981; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
    .live-list { display:flex; flex-direction:column; gap:.4rem; max-height:500px; overflow-y:auto; }
    .live-item { display:grid; grid-template-columns:120px 80px 1fr; gap:.75rem; padding:.5rem .75rem; border-radius:6px; background:#0B0F19; font-size:.82rem; align-items:center; }
    .live-time { color:#64748B; font-family:'JetBrains Mono',monospace; font-size:.75rem; }
    .live-type { padding:.15rem .4rem; border-radius:4px; font-size:.72rem; font-weight:500; text-transform:uppercase; }
    .type-info { background:rgba(59,130,246,.12); color:#93C5FD; }
    .type-error { background:rgba(239,68,68,.12); color:#FCA5A5; }
    .type-warn { background:rgba(245,158,11,.12); color:#FCD34D; }
    .type-agent { background:rgba(139,92,246,.12); color:#C4B5FD; }
    .live-msg { color:#E2E8F0; }
    .empty { text-align:center; padding:2rem; color:#64748B; font-size:.9rem; }
    .data-table { width:100%; border-collapse:collapse; font-size:.82rem; }
    .data-table th { text-align:left; padding:.7rem 1.25rem; color:#94A3B8; font-weight:500; border-bottom:1px solid rgba(148,163,184,.08); background:#0F131F; }
    .data-table td { padding:.7rem 1.25rem; border-bottom:1px solid rgba(148,163,184,.06); color:#E2E8F0; }
    .data-table tr.clickable { cursor:pointer; }
    .data-table tr.clickable:hover td { background:rgba(255,255,255,.02); }
    .data-table tr.detail-row td { padding:0; background:#0B0F19; }
    .mono { font-family:'JetBrains Mono',monospace; }
    .muted { color:#94A3B8; }
    .level-badge { padding:.2rem .5rem; border-radius:6px; font-size:.72rem; font-weight:500; text-transform:uppercase; }
    .level-error { background:rgba(239,68,68,.12); color:#FCA5A5; }
    .level-warn { background:rgba(245,158,11,.12); color:#FCD34D; }
    .level-info { background:rgba(59,130,246,.12); color:#93C5FD; }
    .tag { padding:.15rem .4rem; border-radius:4px; background:rgba(255,255,255,.06); color:#94A3B8; font-size:.72rem; }
    .event-detail { padding:1rem 1.25rem; }
    .event-detail pre { margin:0; font-size:.78rem; color:#E2E8F0; overflow:auto; max-height:200px; }
    .pagination-bar {
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:1rem;
      padding:1rem 1.25rem 1.1rem;
      border-top:1px solid rgba(148,163,184,.08);
      flex-wrap:wrap;
    }
    .pagination-summary {
      display:flex;
      align-items:center;
      gap:.9rem;
      flex-wrap:wrap;
      color:#94A3B8;
      font-size:.8rem;
    }
    .pagination-controls {
      display:flex;
      align-items:center;
      gap:.5rem;
      flex-wrap:wrap;
    }
    @media (max-width: 768px) {
      .stat-grid { grid-template-columns:repeat(2,1fr); }
      .page-header, .card-header, .pagination-bar { flex-direction:column; align-items:stretch; }
      .toolbar { flex-direction:column; }
      .input.search { width:100%; }
      .live-item { grid-template-columns:1fr; }
    }
  `]
})
export class EventsPage {
  readonly state = inject(StateService);
  tab = signal<'all' | 'error' | 'warn' | 'info' | 'live'>('all');
  searchText = signal('');
  sourceFilter = signal('');
  timeFilter = signal('');
  pageSize = signal(100);
  currentPage = signal(1);
  totalEvents = signal(0);
  loading = signal(false);
  expandedEvent = signal<EventItem | null>(null);

  constructor() {
    void this.reloadEvents(1);
  }

  filteredEvents() {
    return this.state.events();
  }

  filteredLiveEvents() {
    return this.state.liveEvents().slice(0, 50);
  }

  async reloadEvents(page = this.currentPage()): Promise<void> {
    if (this.tab() === 'live') {
      return;
    }
    this.loading.set(true);
    const nextPage = Math.max(1, page);
    this.currentPage.set(nextPage);
    try {
      await this.state.loadEvents(this.buildQuery(nextPage), { gracefulOffline: true });
      this.totalEvents.set(this.state.eventStats().today);
      if (this.currentPage() > this.totalPages()) {
        this.currentPage.set(this.totalPages());
      }
    } finally {
      this.loading.set(false);
    }
  }

  async goToPage(page: number): Promise<void> {
    const nextPage = Math.max(1, Math.min(page, this.totalPages()));
    if (nextPage === this.currentPage() && this.totalEvents() > 0) {
      return;
    }
    await this.reloadEvents(nextPage);
  }

  toggleDetail(ev: EventItem): void {
    this.expandedEvent.set(this.expandedEvent()?.id === ev.id ? null : ev);
  }

  clearFilters(): void {
    this.tab.set('all');
    this.searchText.set('');
    this.sourceFilter.set('');
    this.timeFilter.set('');
    this.expandedEvent.set(null);
    void this.reloadEvents(1);
  }

  exportEvents(): void {
    const data = JSON.stringify(this.filteredEvents(), null, 2);
    const blob = new Blob([data], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `events-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  onTabChange(value: 'all' | 'error' | 'warn' | 'info' | 'live'): void {
    this.tab.set(value);
    this.expandedEvent.set(null);
    if (value === 'live') {
      return;
    }
    void this.reloadEvents(1);
  }

  onSearchChange(value: string): void {
    this.searchText.set(value);
    void this.reloadEvents(1);
  }

  onSourceFilterChange(value: string): void {
    this.sourceFilter.set(value);
    void this.reloadEvents(1);
  }

  onTimeFilterChange(value: string): void {
    this.timeFilter.set(value);
    void this.reloadEvents(1);
  }

  onPageSizeChange(value: string): void {
    const parsed = Number.parseInt(value, 10);
    this.pageSize.set(Number.isFinite(parsed) && parsed > 0 ? parsed : 100);
    void this.reloadEvents(1);
  }

  totalPages(): number {
    return Math.max(1, Math.ceil((this.totalEvents() || this.state.eventStats().today) / Math.max(1, this.pageSize())));
  }

  pageItemRange(): string {
    const total = this.totalEvents() || this.state.eventStats().today;
    if (total === 0) {
      return '暂无记录';
    }
    const start = (this.currentPage() - 1) * this.pageSize() + 1;
    const end = Math.min(total, this.currentPage() * this.pageSize());
    return `显示 ${start}-${end}`;
  }

  private buildQuery(page: number): Record<string, string | number | undefined> {
    const timeWindow = this.timeFilter();
    const from = timeWindow === 'hour'
      ? new Date(Date.now() - 60 * 60 * 1000).toISOString()
      : timeWindow === 'day'
        ? new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()
        : timeWindow === 'week'
          ? new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString()
          : undefined;
    return {
      page,
      limit: this.pageSize(),
      level: this.tab() === 'all' || this.tab() === 'live' ? undefined : this.tab(),
      source: this.sourceFilter() || undefined,
      from,
      q: this.searchText().trim() || undefined,
    };
  }
}
