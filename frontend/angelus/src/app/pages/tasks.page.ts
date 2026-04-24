import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StateService, TaskItem } from '../services/state.service';
import { DataTableColumn, DataTableComponent, EmptyStateComponent, FilterBarComponent, PageHeaderComponent, PanelCardComponent, StatCardGridComponent, StatCardItem } from '../shared';
import { TaskGraphViewerComponent } from '../task-graph-viewer.component';

@Component({
  selector: 'app-tasks-page',
  standalone: true,
  imports: [CommonModule, PageHeaderComponent, StatCardGridComponent, FilterBarComponent, PanelCardComponent, DataTableComponent, EmptyStateComponent, TaskGraphViewerComponent],
  template: `
    <div class="page">
      <!-- Header -->
      <app-page-header title="任务列表" subtitle="管理、监控与调度所有 Agent 任务，并查看依赖关系图">
        <div actions>
          <button class="btn btn-primary" (click)="refreshTasks()">刷新任务</button>
        </div>
      </app-page-header>

      <!-- Stat Cards -->
      <app-stat-card-grid [cards]="taskStatCards()"></app-stat-card-grid>

      <!-- Task Graph -->
      <app-panel-card class="graph-panel" title="任务关系图" [badge]="graphBadge()" [noPadding]="true">
        @if (graphTasks().length) {
          <app-task-graph-viewer [tasks]="graphTasks()"></app-task-graph-viewer>
        } @else {
          <app-empty-state message="当前没有已加载的任务图。请先刷新任务列表，系统会按依赖关系自动展开图结构。"></app-empty-state>
        }
      </app-panel-card>

      <!-- Filter Bar -->
      <app-filter-bar>
        <input
          type="text"
          class="filter-input search"
          placeholder="搜索任务名称..."
          [value]="searchQuery()"
          (input)="searchQuery.set($any($event).target.value)"
        />
        <select class="filter-select" [value]="filterStatus()" (change)="filterStatus.set($any($event).target.value)">
          <option value="">全部状态</option>
          <option value="pending">待处理</option>
          <option value="running">运行中</option>
          <option value="success">成功</option>
          <option value="failed">失败</option>
          <option value="cancelled">已取消</option>
          <option value="timeout">超时</option>
        </select>
        <select class="filter-select" [value]="filterPriority()" (change)="filterPriority.set($any($event).target.value)">
          <option value="">全部优先级</option>
          <option value="urgent">紧急</option>
          <option value="high">高</option>
          <option value="medium">中</option>
          <option value="low">低</option>
        </select>
        <select class="filter-select" [value]="filterDateRange()" (change)="filterDateRange.set($any($event).target.value)">
          <option value="">全部时间</option>
          <option value="today">今天</option>
          <option value="week">本周</option>
          <option value="month">本月</option>
        </select>
        <select class="filter-select" [value]="sortBy()" (change)="sortBy.set($any($event).target.value)">
          <option value="createdDesc">最新创建</option>
          <option value="createdAsc">最早创建</option>
          <option value="priorityDesc">优先级高→低</option>
          <option value="priorityAsc">优先级低→高</option>
        </select>
      </app-filter-bar>

      <!-- Task Table -->
      <app-panel-card [noPadding]="true">
        <div class="table-scroll">
          <app-data-table
            [columns]="taskTableColumns"
            [data]="filteredTasks()"
            trackBy="id"
            emptyText="暂无匹配任务"
            (rowClick)="selectTask($event)"
          ></app-data-table>
        </div>
      </app-panel-card>

      <!-- Right Drawer -->
      @if (selectedTask()) {
        <div class="drawer-overlay" (click)="closeDrawer()"></div>
        <div class="drawer">
          <div class="drawer-header">
            <div>
              <h3>{{ selectedTask()!.name }}</h3>
              <div class="drawer-sub">{{ selectedTask()!.id }}</div>
            </div>
            <button class="icon-btn close" (click)="closeDrawer()">✕</button>
          </div>

          <div class="drawer-body">
            <!-- 基本信息 -->
            <div class="drawer-section">
              <h4>基本信息</h4>
              <div class="info-list">
                <div class="info-row">
                  <span class="info-key">状态</span>
                  <span class="badge" [class]="'badge-' + selectedTask()!.status">{{ statusLabel(selectedTask()!.status) }}</span>
                </div>
                <div class="info-row">
                  <span class="info-key">优先级</span>
                  <span class="badge" [class]="'badge-priority-' + selectedTask()!.priority">{{ priorityLabel(selectedTask()!.priority) }}</span>
                </div>
                <div class="info-row">
                  <span class="info-key">执行者</span>
                  <span class="info-val">{{ selectedTask()!.executor }}</span>
                </div>
                <div class="info-row">
                  <span class="info-key">耗时</span>
                  <span class="info-val">{{ selectedTask()!.duration }}</span>
                </div>
                <div class="info-row">
                  <span class="info-key">创建时间</span>
                  <span class="info-val">{{ selectedTask()!.createdAt }}</span>
                </div>
                <div class="info-row">
                  <span class="info-key">描述</span>
                  <span class="info-val">{{ selectedTask()!.detail.description }}</span>
                </div>
              </div>
            </div>

            <!-- 执行详情 -->
            <div class="drawer-section">
              <h4>执行详情</h4>
              <div class="detail-block">
                <div class="detail-label">输入参数</div>
                <pre class="code-block">{{ selectedTask()!.detail.input | json }}</pre>
              </div>
            </div>

            <!-- 输出结果 -->
            <div class="drawer-section">
              <h4>输出结果</h4>
              @if (selectedTask()!.detail.output) {
                <pre class="code-block">{{ selectedTask()!.detail.output | json }}</pre>
              } @else {
                <app-empty-state message="暂无输出"></app-empty-state>
              }
            </div>

            <!-- 活动日志 -->
            <div class="drawer-section">
              <h4>活动日志</h4>
              <div class="timeline">
                @for (log of selectedTask()!.detail.logs; track $index) {
                  <div class="timeline-item">
                    <div class="timeline-dot" [class]="'dot-' + log.level"></div>
                    <div class="timeline-content">
                      <div class="timeline-time">{{ log.time }}</div>
                      <div class="timeline-msg">{{ log.message }}</div>
                    </div>
                  </div>
                }
              </div>
            </div>
          </div>
        </div>
      }
    </div>
  `,
  styles: [`
    .graph-panel {
      margin-bottom: 18px;
    }
                            .filter-input, .filter-select {
      background: #131827;
      border: 1px solid rgba(148,163,184,0.12);
      border-radius: 8px;
      padding: 8px 12px;
      color: #F1F5F9;
      font-size: 13px;
      outline: none;
      font-family: 'Noto Sans SC', sans-serif;
    }
    .filter-input:focus, .filter-select:focus {
      border-color: #8B5CF6;
    }
    .filter-input.search {
      min-width: 240px;
      flex: 1;
    }
    .filter-select {
      min-width: 130px;
      cursor: pointer;
    }
    .table-scroll {
      overflow-x: auto;
    }
        .badge-pending { background: rgba(245,158,11,0.12); color: #F59E0B; }
    .badge-running { background: rgba(139,92,246,0.12); color: #a78bfa; }
    .badge-success { background: rgba(16,185,129,0.12); color: #10B981; }
    .badge-failed { background: rgba(239,68,68,0.12); color: #EF4444; }
    .badge-cancelled { background: rgba(148,163,184,0.12); color: #94A3B8; }
    .badge-timeout { background: rgba(245,158,11,0.12); color: #F59E0B; }
    .badge-priority-urgent { background: rgba(239,68,68,0.12); color: #EF4444; }
    .badge-priority-high { background: rgba(245,158,11,0.12); color: #F59E0B; }
    .badge-priority-medium { background: rgba(139,92,246,0.12); color: #a78bfa; }
    .badge-priority-low { background: rgba(148,163,184,0.12); color: #94A3B8; }
                .drawer-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.5);
      z-index: 40;
    }
    .drawer {
      position: fixed;
      top: 0;
      right: 0;
      width: 480px;
      max-width: 90vw;
      height: 100vh;
      background: #131827;
      border-left: 1px solid rgba(148,163,184,0.08);
      z-index: 50;
      display: flex;
      flex-direction: column;
      animation: slideIn 0.25s ease;
    }
    @keyframes slideIn {
      from { transform: translateX(100%); }
      to { transform: translateX(0); }
    }
    .drawer-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      padding: 20px 24px;
      border-bottom: 1px solid rgba(148,163,184,0.08);
    }
    .drawer-header h3 {
      margin: 0;
      font-size: 16px;
      font-weight: 600;
      color: #F1F5F9;
    }
    .drawer-sub {
      font-size: 12px;
      color: #64748b;
      font-family: 'JetBrains Mono', monospace;
      margin-top: 4px;
    }
    .drawer-body {
      flex: 1;
      overflow-y: auto;
      padding: 16px 24px;
    }
    .drawer-section {
      margin-bottom: 24px;
    }
    .drawer-section h4 {
      margin: 0 0 12px;
      font-size: 13px;
      font-weight: 600;
      color: #94A3B8;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .info-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .info-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 12px;
      background: #0B0F19;
      border-radius: 8px;
    }
    .info-key {
      font-size: 12px;
      color: #94A3B8;
    }
    .info-val {
      font-size: 13px;
      color: #F1F5F9;
      font-weight: 500;
      max-width: 60%;
      text-align: right;
    }
    .detail-block {
      background: #0B0F19;
      border-radius: 8px;
      padding: 12px;
    }
    .detail-label {
      font-size: 11px;
      color: #94A3B8;
      margin-bottom: 8px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
        .timeline {
      display: flex;
      flex-direction: column;
      gap: 0;
      position: relative;
      padding-left: 16px;
    }
    .timeline::before {
      content: '';
      position: absolute;
      left: 5px;
      top: 6px;
      bottom: 6px;
      width: 2px;
      background: rgba(148,163,184,0.12);
      border-radius: 1px;
    }
    .timeline-item {
      display: flex;
      gap: 12px;
      padding: 10px 0;
      position: relative;
    }
    .timeline-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: #64748b;
      flex-shrink: 0;
      margin-top: 3px;
      position: relative;
      z-index: 1;
    }
    .dot-info { background: #8B5CF6; box-shadow: 0 0 6px rgba(139,92,246,0.35); }
    .dot-success { background: #10B981; box-shadow: 0 0 6px rgba(16,185,129,0.35); }
    .dot-warn { background: #F59E0B; box-shadow: 0 0 6px rgba(245,158,11,0.35); }
    .dot-error { background: #EF4444; box-shadow: 0 0 6px rgba(239,68,68,0.35); }
    .timeline-content {
      flex: 1;
    }
    .timeline-time {
      font-size: 11px;
      color: #64748b;
      font-family: 'JetBrains Mono', monospace;
      margin-bottom: 2px;
    }
    .timeline-msg {
      font-size: 13px;
      color: #cbd5e1;
    }
    @media (max-width: 768px) {
      .filter-input.search { width: 100%; min-width: unset; }
      .drawer { width: 100vw; max-width: 100vw; }
    }
  `]
})
export class TasksPageComponent {
  readonly state = inject(StateService);

  readonly selectedTask = signal<TaskItem | null>(null);
  readonly searchQuery = signal('');
  readonly filterStatus = signal('');
  readonly filterPriority = signal('');
  readonly filterDateRange = signal('');
  readonly sortBy = signal('createdDesc');

  readonly runningCount = computed(() => this.state.derivedTasks().filter(t => t.status === 'running').length);
  readonly pendingCount = computed(() => this.state.derivedTasks().filter(t => t.status === 'pending').length);
  readonly timeoutCount = computed(() => this.state.derivedTasks().filter(t => t.status === 'timeout').length);
  readonly successRate = computed(() => this.state.taskStats().successRate);
  readonly avgDuration = computed(() => this.state.taskStats().avgDuration);
  readonly graphTasks = computed(() => (this.state.tasksLoaded() ? this.state.tasks() : []));
  readonly graphBadge = computed(() => (this.state.tasksLoaded() ? `${this.state.tasks().length} 项` : '未加载'));

  readonly taskStatCards = computed<StatCardItem[]>(() => [
    { label: '总任务数', value: this.state.derivedTasks().length, subtitle: '累计创建' },
    { label: '运行中', value: this.runningCount(), subtitle: '活跃执行', tone: this.runningCount() > 0 ? 'purple' : undefined },
    { label: '成功率', value: this.successRate() + '%', subtitle: '近 24 小时', tone: this.successRate() >= 80 ? 'good' : undefined },
    { label: '超时', value: this.timeoutCount(), subtitle: '请求超时任务', tone: this.timeoutCount() > 0 ? 'amber' : undefined },
    { label: '待处理', value: this.pendingCount(), subtitle: '队列中等待', tone: this.pendingCount() > 0 ? 'amber' : undefined },
  ]);

  readonly taskTableColumns: DataTableColumn<TaskItem>[] = [
    { key: 'name', header: '任务名称', cell: t => t.name + ' / ' + t.id },
    { key: 'status', header: '状态', cell: t => this.statusLabel(t.status) },
    { key: 'priority', header: '优先级', cell: t => this.priorityLabel(t.priority) },
    { key: 'executor', header: '执行者' },
    { key: 'duration', header: '耗时' },
    { key: 'createdAt', header: '创建时间' },
  ];

  readonly filteredTasks = computed(() => {
    let list = [...this.state.derivedTasks()];
    const q = this.searchQuery().trim().toLowerCase();
    if (q) list = list.filter(t => t.name.toLowerCase().includes(q) || t.id.toLowerCase().includes(q));
    if (this.filterStatus()) list = list.filter(t => t.status === this.filterStatus());
    if (this.filterPriority()) list = list.filter(t => t.priority === this.filterPriority());
    const s = this.sortBy();
    if (s === 'priorityDesc') {
      const order = { urgent: 4, high: 3, medium: 2, low: 1 };
      list.sort((a, b) => order[b.priority] - order[a.priority]);
    } else if (s === 'priorityAsc') {
      const order = { urgent: 4, high: 3, medium: 2, low: 1 };
      list.sort((a, b) => order[a.priority] - order[b.priority]);
    }
    return list;
  });

  selectTask(task: TaskItem): void {
    this.selectedTask.set(task);
  }

  closeDrawer(): void {
    this.selectedTask.set(null);
  }

  async refreshTasks(): Promise<void> {
    await this.state.loadTasks();
  }

  statusLabel(status: TaskItem['status']): string {
    const map: Record<string, string> = { pending: '待处理', running: '运行中', success: '成功', failed: '失败', cancelled: '已取消', timeout: '超时' };
    return map[status] ?? status;
  }

  priorityLabel(priority: TaskItem['priority']): string {
    const map: Record<string, string> = { low: '低', medium: '中', high: '高', urgent: '紧急' };
    return map[priority] ?? priority;
  }
}
