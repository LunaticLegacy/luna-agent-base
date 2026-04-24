import { Component, ElementRef, ViewChild, effect, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StateService, LogItem } from '../services/state.service';
import { PageHeaderComponent, StatCardGridComponent, PanelCardComponent, PaginationComponent, EmptyStateComponent, ModalComponent } from '../shared';

@Component({
  selector: 'app-logs-page',
  standalone: true,
  imports: [CommonModule, PageHeaderComponent, StatCardGridComponent, PanelCardComponent, PaginationComponent, EmptyStateComponent, ModalComponent],
  template: `
    <app-page-header title="系统日志" subtitle="结构化日志查询与分析">
      <div actions>
        <button class="btn btn-sm" (click)="autoScroll.set(!autoScroll())">
          {{ autoScroll() ? '暂停滚动' : '自动滚动' }}
        </button>
        <button class="btn btn-sm btn-primary" (click)="exportLogs()">导出</button>
      </div>
    </app-page-header>

    <app-stat-card-grid [cards]="[
      { label: '总日志数', value: state.logStats().total, subtitle: '条记录' },
      { label: 'ERROR', value: state.logStats().error, subtitle: '严重', tone: 'red' },
      { label: 'WARN', value: state.logStats().warn, subtitle: '警告', tone: 'amber' },
      { label: 'INFO', value: state.logStats().info, subtitle: '信息', tone: 'green' },
      { label: 'DEBUG', value: state.logStats().debug, subtitle: '调试', tone: 'blue' }
    ]" />

    <app-panel-card [noPadding]="true">
      <div class="card-header">
        <div class="level-filters">
          <button class="level-btn" [class.active]="levelFilter()==='all'" (click)="onLevelFilterChange('all')">全部</button>
          <button class="level-btn error" [class.active]="levelFilter()==='ERROR'" (click)="onLevelFilterChange('ERROR')">ERROR</button>
          <button class="level-btn warn" [class.active]="levelFilter()==='WARN'" (click)="onLevelFilterChange('WARN')">WARN</button>
          <button class="level-btn info" [class.active]="levelFilter()==='INFO'" (click)="onLevelFilterChange('INFO')">INFO</button>
          <button class="level-btn debug" [class.active]="levelFilter()==='DEBUG'" (click)="onLevelFilterChange('DEBUG')">DEBUG</button>
        </div>
        <div class="toolbar">
          <input class="input search" placeholder="搜索日志内容..." [value]="searchText()" (input)="onSearchChange($any($event).target.value)" />
          <select class="input" [value]="serviceFilter()" (change)="onServiceFilterChange($any($event).target.value)">
            <option value="">所有服务</option>
            <option value="backend">backend</option>
            <option value="agent">agent</option>
            <option value="graph">graph</option>
          </select>
          <select class="input" [value]="pageSize()" (change)="pageSize.set(+$any($event).target.value); goToPage(1)">
            <option [value]="20">20 / 页</option>
            <option [value]="50">50 / 页</option>
            <option [value]="100">100 / 页</option>
            <option [value]="200">200 / 页</option>
            <option [value]="500">500 / 页</option>
          </select>
        </div>
      </div>

      <div class="log-container" #logContainer>
        @for (log of filteredLogs(); track log.id) {
          <div class="log-line" [class]="'log-'+log.level.toLowerCase()" (click)="selectedLog.set(log)">
            <span class="log-time">{{ log.time }}</span>
            <span class="log-level">{{ log.level }}</span>
            <span class="log-service">{{ log.service }}</span>
            <span class="log-msg">{{ log.message }}</span>
          </div>
        } @empty {
          <app-empty-state message="暂无日志记录"></app-empty-state>
        }
      </div>

      <app-pagination
        [currentPage]="currentPage()"
        [totalItems]="totalLogs()"
        [pageSize]="pageSize()"
        [loading]="loading()"
        (pageChange)="goToPage($event)">
        <button class="btn btn-sm" extra (click)="reloadLogs(currentPage())" [disabled]="loading()">
          {{ loading() ? '加载中...' : '刷新当前页' }}
        </button>
      </app-pagination>
    </app-panel-card>

    <app-modal
      [open]="!!selectedLog()"
      [title]="'日志详情'"
      (close)="selectedLog.set(null)">
      @if (selectedLog(); as log) {
        <div class="log-detail">
          <div class="detail-row">
            <span class="detail-label">时间</span>
            <span class="detail-value mono">{{ log.time }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">级别</span>
            <span class="detail-value">
              <span class="level-badge" [class]="'level-'+log.level.toLowerCase()">{{ log.level }}</span>
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-label">服务</span>
            <span class="detail-value mono">{{ log.service }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">消息</span>
          </div>
          <div class="detail-message">{{ log.message }}</div>
          @if (log.raw) {
            <div class="detail-row" style="margin-top:.5rem">
              <span class="detail-label">原始数据</span>
            </div>
            <pre class="detail-raw">{{ log.raw | json }}</pre>
          }
        </div>
      }
    </app-modal>
  `,
  styles: [`
    :host { display:block; }
                .btn-sm:hover { background:rgba(255,255,255,.1); color:#F1F5F9; }
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
    .log-line { cursor:pointer; }
    .log-line:hover { background:rgba(255,255,255,.02); }
    .log-time { color:#64748B; }
    .log-level { font-weight:600; }
    .log-error .log-level { color:#EF4444; }
    .log-warn .log-level { color:#F59E0B; }
    .log-info .log-level { color:#60A5FA; }
    .log-debug .log-level { color:#94A3B8; }
    .log-service { color:#A78BFA; }
    .log-msg { color:#E2E8F0; }
    .log-detail { display:flex; flex-direction:column; gap:.75rem; }
    .detail-row { display:flex; align-items:center; gap:1rem; }
    .detail-label { font-size:.78rem; color:#94A3B8; min-width:3rem; }
    .detail-value { font-size:.85rem; color:#F1F5F9; }
    .detail-value.mono { font-family:'JetBrains Mono',monospace; }
    .level-badge { display:inline-flex; align-items:center; padding:.15rem .5rem; border-radius:4px; font-size:.72rem; font-weight:600; font-family:'JetBrains Mono',monospace; }
    .level-error { background:rgba(239,68,68,.12); color:#FCA5A5; }
    .level-warn { background:rgba(245,158,11,.12); color:#FCD34D; }
    .level-info { background:rgba(59,130,246,.12); color:#93C5FD; }
    .level-debug { background:rgba(107,114,128,.12); color:#CBD5E1; }
    .detail-message { background:#0B0F19; border:1px solid rgba(148,163,184,.08); border-radius:8px; padding:.75rem; font-family:'JetBrains Mono',monospace; font-size:.78rem; color:#E2E8F0; line-height:1.6; white-space:pre-wrap; word-break:break-word; max-height:300px; overflow-y:auto; }
    .detail-raw { background:#0B0F19; border:1px solid rgba(148,163,184,.08); border-radius:8px; padding:.75rem; font-family:'JetBrains Mono',monospace; font-size:.72rem; color:#94A3B8; line-height:1.5; white-space:pre-wrap; word-break:break-word; max-height:260px; overflow-y:auto; margin:0; }
  `]
})
export class LogsPage {
  readonly state = inject(StateService);
  levelFilter = signal<string>('all');
  searchText = signal('');
  serviceFilter = signal('');
  pageSize = signal(100);
  currentPage = signal(1);
  totalLogs = signal(0);
  loading = signal(false);
  autoScroll = signal(true);
  @ViewChild('logContainer') logContainer?: ElementRef<HTMLDivElement>;
  selectedLog = signal<LogItem | null>(null);

  constructor() {
    void this.reloadLogs(1);
    effect(() => {
      this.state.logs();
      if (this.autoScroll()) {
        queueMicrotask(() => this.scrollToBottom());
      }
    });
  }

  async reloadLogs(page = this.currentPage()): Promise<void> {
    this.loading.set(true);
    const nextPage = Math.max(1, page);
    this.currentPage.set(nextPage);
    try {
      await this.state.loadLogs(this.buildQuery(nextPage));
      this.totalLogs.set(this.state.logStats().total);
      if (this.currentPage() > this.totalPages()) {
        this.currentPage.set(this.totalPages());
      }
      if (this.autoScroll()) {
        queueMicrotask(() => this.scrollToBottom());
      }
    } finally {
      this.loading.set(false);
    }
  }

  async goToPage(page: number): Promise<void> {
    const totalPages = this.totalPages();
    const nextPage = Math.max(1, Math.min(page, totalPages));
    if (nextPage === this.currentPage() && this.totalLogs() > 0) {
      return;
    }
    await this.reloadLogs(nextPage);
  }

  filteredLogs() {
    return this.state.derivedLogs();
  }

  exportLogs(): void {
    const data = JSON.stringify(this.filteredLogs(), null, 2);
    const blob = new Blob([data], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `logs-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  onLevelFilterChange(value: string): void {
    this.levelFilter.set(value);
    void this.reloadLogs(1);
  }

  onSearchChange(value: string): void {
    this.searchText.set(value);
    void this.reloadLogs(1);
  }

  onServiceFilterChange(value: string): void {
    this.serviceFilter.set(value);
    void this.reloadLogs(1);
  }

  totalPages(): number {
    const total = this.state.logStats().total || this.totalLogs();
    return Math.max(1, Math.ceil(total / Math.max(1, this.pageSize())));
  }

  pageItemRange(): string {
    const total = this.state.logStats().total || this.totalLogs();
    if (total === 0) {
      return '暂无记录';
    }
    const start = (this.currentPage() - 1) * this.pageSize() + 1;
    const end = Math.min(total, this.currentPage() * this.pageSize());
    return `显示 ${start}-${end}`;
  }

  private buildQuery(page: number): Record<string, string | number | undefined> {
    return {
      page,
      limit: this.pageSize(),
      level: this.levelFilter() === 'all' ? undefined : this.levelFilter().toLowerCase(),
      service: this.serviceFilter() || undefined,
      q: this.searchText().trim() || undefined,
    };
  }

  private scrollToBottom(): void {
    const element = this.logContainer?.nativeElement;
    if (!element || !this.autoScroll()) return;
    element.scrollTop = element.scrollHeight;
  }
}
