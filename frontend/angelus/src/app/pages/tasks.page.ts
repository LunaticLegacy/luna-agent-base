import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StateService, TaskItem } from '../services/state.service';

@Component({
  selector: 'app-tasks-page',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="page">
      <!-- Header -->
      <div class="section-header">
        <div>
          <h1>任务列表</h1>
          <p class="subtitle">管理、监控与调度所有 Agent 任务</p>
        </div>
        <div class="header-actions">
          <button class="btn btn-primary" (click)="createTask()">+ 创建任务</button>
        </div>
      </div>

      <!-- Stat Cards -->
      <div class="stat-cards-row">
        <div class="stat-card">
          <div class="stat-label">总任务数</div>
          <div class="stat-value">{{ state.derivedTasks().length }}</div>
          <div class="stat-sub">累计创建</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">运行中</div>
          <div class="stat-value" [class.accent-purple]="runningCount() > 0">{{ runningCount() }}</div>
          <div class="stat-sub">活跃执行</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">成功率</div>
          <div class="stat-value" [class.success]="successRate() >= 80">{{ successRate() }}%</div>
          <div class="stat-sub">近 24 小时</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">平均执行时间</div>
          <div class="stat-value">{{ avgDuration() }}</div>
          <div class="stat-sub">已完成的任务</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">待处理</div>
          <div class="stat-value" [class.amber]="pendingCount() > 0">{{ pendingCount() }}</div>
          <div class="stat-sub">队列中等待</div>
        </div>
      </div>

      <!-- Filter Bar -->
      <div class="filter-bar">
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
      </div>

      <!-- Task Table -->
      <div class="panel-card table-panel">
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>任务名称</th>
                <th>状态</th>
                <th>优先级</th>
                <th>执行者</th>
                <th>耗时</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              @for (task of filteredTasks(); track task.id) {
                <tr (click)="selectTask(task)">
                  <td>
                    <div class="task-name">{{ task.name }}</div>
                    <div class="task-id">{{ task.id }}</div>
                  </td>
                  <td>
                    <span class="badge" [class]="'badge-' + task.status">{{ statusLabel(task.status) }}</span>
                  </td>
                  <td>
                    <span class="badge" [class]="'badge-priority-' + task.priority">{{ priorityLabel(task.priority) }}</span>
                  </td>
                  <td>{{ task.executor }}</td>
                  <td>{{ task.duration }}</td>
                  <td>{{ task.createdAt }}</td>
                  <td>
                    <div class="row-actions">
                      <button class="icon-btn" title="查看" (click)="selectTask(task); $event.stopPropagation()">👁</button>
                      <button class="icon-btn" title="重试" (click)="retryTask(task); $event.stopPropagation()">↻</button>
                    </div>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="7" class="empty-cell">暂无匹配任务</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

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
                <div class="empty-state">暂无输出</div>
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
    .page {
      padding: 24px;
      color: #F1F5F9;
      font-family: 'Noto Sans SC', sans-serif;
      background: #0B0F19;
      min-height: 100vh;
    }
    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
    }
    .section-header h1 {
      margin: 0;
      font-size: 24px;
      font-weight: 600;
      color: #F1F5F9;
    }
    .subtitle {
      margin: 4px 0 0;
      color: #94A3B8;
      font-size: 14px;
    }
    .header-actions {
      display: flex;
      gap: 8px;
    }
    .btn {
      padding: 8px 16px;
      border-radius: 8px;
      border: 1px solid rgba(148,163,184,0.2);
      background: #131827;
      color: #F1F5F9;
      font-size: 14px;
      cursor: pointer;
      transition: all 0.2s;
      font-family: 'Noto Sans SC', sans-serif;
    }
    .btn:hover:not(:disabled) {
      background: #1e293b;
    }
    .btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .btn-primary {
      background: #8B5CF6;
      border-color: #8B5CF6;
      color: #fff;
    }
    .btn-primary:hover:not(:disabled) {
      background: #7c3aed;
    }
    .stat-cards-row {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }
    .stat-card {
      background: #131827;
      border: 1px solid rgba(148,163,184,0.08);
      border-radius: 12px;
      padding: 16px;
    }
    .stat-label {
      font-size: 12px;
      color: #94A3B8;
      margin-bottom: 8px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .stat-value {
      font-size: 22px;
      font-weight: 700;
      color: #F1F5F9;
      margin-bottom: 4px;
    }
    .stat-value.success { color: #10B981; }
    .stat-value.accent-purple { color: #8B5CF6; }
    .stat-value.amber { color: #F59E0B; }
    .stat-sub {
      font-size: 12px;
      color: #64748b;
    }
    .filter-bar {
      display: flex;
      gap: 12px;
      margin-bottom: 16px;
      flex-wrap: wrap;
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
    .table-panel {
      overflow: hidden;
    }
    .table-scroll {
      overflow-x: auto;
    }
    .data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .data-table thead th {
      text-align: left;
      padding: 12px 16px;
      color: #94A3B8;
      font-weight: 500;
      border-bottom: 1px solid rgba(148,163,184,0.08);
      background: #131827;
      white-space: nowrap;
    }
    .data-table tbody tr {
      border-bottom: 1px solid rgba(148,163,184,0.05);
      cursor: pointer;
      transition: background 0.15s;
    }
    .data-table tbody tr:hover {
      background: rgba(148,163,184,0.04);
    }
    .data-table tbody td {
      padding: 12px 16px;
      color: #F1F5F9;
      white-space: nowrap;
    }
    .task-name {
      font-weight: 500;
      color: #F1F5F9;
    }
    .task-id {
      font-size: 11px;
      color: #64748b;
      font-family: 'JetBrains Mono', monospace;
      margin-top: 2px;
    }
    .badge {
      display: inline-block;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 12px;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .badge-pending { background: rgba(245,158,11,0.12); color: #F59E0B; }
    .badge-running { background: rgba(139,92,246,0.12); color: #a78bfa; }
    .badge-success { background: rgba(16,185,129,0.12); color: #10B981; }
    .badge-failed { background: rgba(239,68,68,0.12); color: #EF4444; }
    .badge-cancelled { background: rgba(148,163,184,0.12); color: #94A3B8; }
    .badge-priority-urgent { background: rgba(239,68,68,0.12); color: #EF4444; }
    .badge-priority-high { background: rgba(245,158,11,0.12); color: #F59E0B; }
    .badge-priority-medium { background: rgba(139,92,246,0.12); color: #a78bfa; }
    .badge-priority-low { background: rgba(148,163,184,0.12); color: #94A3B8; }
    .row-actions {
      display: flex;
      gap: 6px;
    }
    .icon-btn {
      background: transparent;
      border: 1px solid rgba(148,163,184,0.15);
      border-radius: 6px;
      color: #94A3B8;
      cursor: pointer;
      padding: 4px 8px;
      font-size: 12px;
      transition: all 0.2s;
    }
    .icon-btn:hover {
      background: rgba(148,163,184,0.08);
      color: #F1F5F9;
    }
    .icon-btn.close {
      font-size: 14px;
      padding: 6px 10px;
    }
    .empty-cell {
      text-align: center;
      color: #64748b;
      padding: 32px;
    }
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
    .code-block {
      background: #0B0F19;
      border: 1px solid rgba(148,163,184,0.08);
      border-radius: 8px;
      padding: 12px;
      color: #cbd5e1;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      overflow-x: auto;
      margin: 0;
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
    .empty-state {
      padding: 20px;
      text-align: center;
      color: #64748b;
      font-size: 13px;
      background: #0B0F19;
      border-radius: 8px;
    }
    @media (max-width: 1200px) {
      .stat-cards-row { grid-template-columns: repeat(3, 1fr); }
    }
    @media (max-width: 768px) {
      .stat-cards-row { grid-template-columns: repeat(2, 1fr); }
      .filter-bar { flex-direction: column; }
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
  readonly successRate = computed(() => this.state.taskStats().successRate);
  readonly avgDuration = computed(() => this.state.taskStats().avgDuration);

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

  createTask(): void {
    alert('创建任务功能待实现');
  }

  retryTask(task: TaskItem): void {
    console.log('Retry', task.id);
  }

  statusLabel(status: TaskItem['status']): string {
    const map: Record<string, string> = { pending: '待处理', running: '运行中', success: '成功', failed: '失败', cancelled: '已取消' };
    return map[status] ?? status;
  }

  priorityLabel(priority: TaskItem['priority']): string {
    const map: Record<string, string> = { low: '低', medium: '中', high: '高', urgent: '紧急' };
    return map[priority] ?? priority;
  }
}
