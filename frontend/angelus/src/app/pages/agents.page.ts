import { Component, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StateService } from '../services/state.service';

interface AgentRow {
  id: string;
  name: string;
  status: 'online' | 'offline' | 'busy' | 'error';
  type: string;
  capabilities: string[];
  tags: string[];
  tasksExecuted: number;
  successRate: number;
  avgResponseTime: string;
  tokenUsage: number;
  lastActivity: string;
}

@Component({
  selector: 'app-agents-page',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="page">
      <!-- Stat Cards -->
      <div class="stat-cards-row">
        <div class="stat-card">
          <div class="stat-label">总 Agents</div>
          <div class="stat-value">{{ state.totalAgents() ?? 0 }}</div>
          <div class="stat-sub">已注册</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">活跃 Agents</div>
          <div class="stat-value success">{{ activeAgentsCount() }}</div>
          <div class="stat-sub">在线运行中</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">总任务执行</div>
          <div class="stat-value">{{ totalTasksExecuted() }}</div>
          <div class="stat-sub">累计</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">平均响应时间</div>
          <div class="stat-value">{{ avgResponseTime() }}</div>
          <div class="stat-sub">毫秒</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">总 Token 消耗</div>
          <div class="stat-value">{{ totalTokenUsage() }}</div>
          <div class="stat-sub">累计</div>
        </div>
      </div>

      <!-- Tabs -->
      <div class="tab-bar">
        @for (tab of tabs; track tab) {
          <div class="tab-item" [class.active]="activeTab() === tab" (click)="activeTab.set(tab)">
            {{ tab }}
          </div>
        }
      </div>

      <!-- Filter Bar -->
      <div class="filter-bar">
        <div class="filter-search">
          <input
            type="text"
            class="filter-input"
            placeholder="搜索 Agent..."
            [value]="searchQuery()"
            (input)="searchQuery.set($any($event).target.value)"
          />
        </div>
        <select class="filter-select" [value]="filterStatus()" (change)="filterStatus.set($any($event).target.value)">
          <option value="">全部状态</option>
          <option value="online">在线</option>
          <option value="offline">离线</option>
          <option value="busy">忙碌</option>
          <option value="error">异常</option>
        </select>
        <select class="filter-select" [value]="filterType()" (change)="filterType.set($any($event).target.value)">
          <option value="">全部类型</option>
          <option value="coordinator">Coordinator</option>
          <option value="worker">Worker</option>
          <option value="specialist">Specialist</option>
          <option value="reviewer">Reviewer</option>
        </select>
        <select class="filter-select" [value]="filterCapability()" (change)="filterCapability.set($any($event).target.value)">
          <option value="">全部能力</option>
          <option value="llm">LLM</option>
          <option value="tool">Tool</option>
          <option value="memory">Memory</option>
          <option value="planning">Planning</option>
        </select>
        <select class="filter-select" [value]="filterTag()" (change)="filterTag.set($any($event).target.value)">
          <option value="">全部标签</option>
          <option value="core">核心</option>
          <option value="experimental">实验性</option>
          <option value="production">生产</option>
        </select>
        <label class="toggle-label">
          <input type="checkbox" [checked]="onlineOnly()" (change)="onlineOnly.set($any($event).target.checked)" />
          <span>仅看在线</span>
        </label>
      </div>

      <!-- Content Area with Drawer -->
      <div class="content-with-drawer" [class.drawer-open]="selectedAgent()">
        <!-- Agent Table -->
        <div class="table-panel">
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>状态</th>
                  <th>类型</th>
                  <th>能力 / 标签</th>
                  <th>任务执行</th>
                  <th>成功率</th>
                  <th>响应时间</th>
                  <th>Token 消耗</th>
                  <th>最后活动</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                @for (agent of paginatedAgents(); track agent.id) {
                  <tr [class.selected]="selectedAgent()?.id === agent.id" (click)="selectAgent(agent)">
                    <td>
                      <div class="agent-cell">
                        <div class="agent-avatar">{{ agent.name.charAt(0).toUpperCase() }}</div>
                        <div class="agent-info">
                          <div class="agent-name">{{ agent.name }}</div>
                          <div class="agent-id">{{ agent.id }}</div>
                        </div>
                      </div>
                    </td>
                    <td><span class="pill" [class.online]="agent.status === 'online'" [class.offline]="agent.status === 'offline'" [class.busy]="agent.status === 'busy'" [class.error]="agent.status === 'error'">{{ statusText(agent.status) }}</span></td>
                    <td>{{ agent.type }}</td>
                    <td>
                      <div class="cap-tags">
                        @for (cap of agent.capabilities.slice(0, 2); track cap) {
                          <span class="mini-cap">{{ cap }}</span>
                        }
                        @for (tag of agent.tags.slice(0, 2); track tag) {
                          <span class="mini-tag">{{ tag }}</span>
                        }
                      </div>
                    </td>
                    <td>{{ agent.tasksExecuted }}</td>
                    <td>
                      <div class="rate-cell">
                        <span>{{ agent.successRate }}%</span>
                        <div class="mini-progress"><div class="mini-progress-fill" [style.width.%]="agent.successRate"></div></div>
                      </div>
                    </td>
                    <td>{{ agent.avgResponseTime }}</td>
                    <td>{{ agent.tokenUsage }}</td>
                    <td class="time-cell">{{ agent.lastActivity }}</td>
                    <td>
                      <button class="btn btn-sm" (click)="$event.stopPropagation(); onAction(agent, 'run')">运行</button>
                    </td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="10" class="empty-cell">没有找到匹配的 Agent</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <!-- Pagination -->
          <div class="pagination">
            <div class="pagination-info">共 {{ filteredAgents().length }} 条</div>
            <div class="pagination-controls">
              <button class="btn btn-sm" [disabled]="currentPage() === 1" (click)="currentPage.set(currentPage() - 1)">上一页</button>
              <span class="page-indicator">{{ currentPage() }} / {{ totalPages() }}</span>
              <button class="btn btn-sm" [disabled]="currentPage() === totalPages()" (click)="currentPage.set(currentPage() + 1)">下一页</button>
            </div>
            <select class="filter-select" [value]="pageSize()" (change)="pageSize.set(+$any($event).target.value); currentPage.set(1)">
              <option [value]="10">10 / 页</option>
              <option [value]="20">20 / 页</option>
              <option [value]="50">50 / 页</option>
            </select>
          </div>
        </div>

        <!-- Right Detail Drawer -->
        @if (selectedAgent(); as agent) {
          <div class="detail-drawer">
            <div class="drawer-header">
              <div class="drawer-title">
                <div class="agent-avatar large">{{ agent.name.charAt(0).toUpperCase() }}</div>
                <div>
                  <div class="drawer-name">{{ agent.name }}</div>
                  <div class="drawer-id">{{ agent.id }}</div>
                </div>
              </div>
              <button class="btn btn-icon" (click)="selectedAgent.set(null)">✕</button>
            </div>

            <div class="drawer-body">
              <!-- Basic Info -->
              <div class="drawer-section">
                <h4>基本信息</h4>
                <div class="drawer-row"><span>状态</span><span class="pill" [class.online]="agent.status === 'online'" [class.offline]="agent.status === 'offline'" [class.busy]="agent.status === 'busy'" [class.error]="agent.status === 'error'">{{ statusText(agent.status) }}</span></div>
                <div class="drawer-row"><span>类型</span><span>{{ agent.type }}</span></div>
                <div class="drawer-row"><span>任务执行</span><span>{{ agent.tasksExecuted }}</span></div>
                <div class="drawer-row"><span>成功率</span><span>{{ agent.successRate }}%</span></div>
                <div class="drawer-row"><span>响应时间</span><span>{{ agent.avgResponseTime }}</span></div>
                <div class="drawer-row"><span>Token 消耗</span><span>{{ agent.tokenUsage }}</span></div>
                <div class="drawer-row"><span>最后活动</span><span>{{ agent.lastActivity }}</span></div>
              </div>

              <!-- Real-time Metrics Sparkline -->
              <div class="drawer-section">
                <h4>实时指标</h4>
                <div class="spark-area">
                  <div class="spark-bars">
                    @for (h of sparkHeights(); track $index) {
                      <div class="spark-bar" [style.height.%]="h"></div>
                    }
                  </div>
                </div>
                <div class="spark-labels">
                  <span>1m</span><span>5m</span><span>15m</span><span>1h</span><span>6h</span><span>24h</span>
                </div>
              </div>

              <!-- Resource Usage -->
              <div class="drawer-section">
                <h4>资源使用</h4>
                <div class="resource-row">
                  <span>CPU</span>
                  <div class="resource-bar"><div class="resource-fill" [style.width.%]="28"></div></div>
                  <span class="resource-val">28%</span>
                </div>
                <div class="resource-row">
                  <span>内存</span>
                  <div class="resource-bar"><div class="resource-fill success" [style.width.%]="45"></div></div>
                  <span class="resource-val">45%</span>
                </div>
                <div class="resource-row">
                  <span>网络</span>
                  <div class="resource-bar"><div class="resource-fill" [style.width.%]="12"></div></div>
                  <span class="resource-val">12%</span>
                </div>
              </div>

              <!-- Tags -->
              <div class="drawer-section">
                <h4>标签</h4>
                <div class="tag-list">
                  @for (tag of agent.tags; track tag) {
                    <span class="tag">{{ tag }}</span>
                  }
                  @for (cap of agent.capabilities; track cap) {
                    <span class="tag cap">{{ cap }}</span>
                  }
                </div>
              </div>
            </div>
          </div>
        }
      </div>
    </div>
  `,
  styles: [`
    .page {
      padding: 24px;
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    .stat-cards-row {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 16px;
      margin-bottom: 20px;
    }
    .stat-card {
      background: #131827;
      border: 1px solid rgba(148,163,184,0.08);
      border-radius: 12px;
      padding: 16px;
    }
    .stat-label {
      font-size: 12px;
      color: #94a3b8;
      margin-bottom: 8px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .stat-value {
      font-size: 22px;
      font-weight: 700;
      color: #f8fafc;
      margin-bottom: 4px;
    }
    .stat-value.success { color: #10B981; }
    .stat-sub {
      font-size: 12px;
      color: #64748b;
    }
    .tab-bar {
      display: flex;
      gap: 4px;
      margin-bottom: 16px;
      border-bottom: 1px solid rgba(148,163,184,0.08);
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
    .tab-item:hover { color: #e2e8f0; }
    .tab-item.active {
      color: #8B5CF6;
      border-bottom-color: #8B5CF6;
      font-weight: 600;
    }
    .filter-bar {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }
    .filter-input, .filter-select {
      background: #131827;
      border: 1px solid rgba(148,163,184,0.12);
      border-radius: 8px;
      padding: 8px 12px;
      color: #e2e8f0;
      font-size: 13px;
      outline: none;
    }
    .filter-input { width: 200px; }
    .filter-input:focus, .filter-select:focus { border-color: #8B5CF6; }
    .filter-select { cursor: pointer; }
    .toggle-label {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      color: #94a3b8;
      cursor: pointer;
      user-select: none;
    }
    .toggle-label input { accent-color: #8B5CF6; }
    .content-with-drawer {
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;
      transition: grid-template-columns 0.3s;
    }
    .content-with-drawer.drawer-open {
      grid-template-columns: 1fr 340px;
    }
    .table-panel {
      background: #131827;
      border: 1px solid rgba(148,163,184,0.08);
      border-radius: 12px;
      overflow: hidden;
    }
    .table-wrap { overflow-x: auto; }
    .data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .data-table th {
      text-align: left;
      padding: 12px 16px;
      color: #94a3b8;
      font-weight: 500;
      border-bottom: 1px solid rgba(148,163,184,0.08);
      white-space: nowrap;
      background: #0f1525;
    }
    .data-table td {
      padding: 12px 16px;
      color: #cbd5e1;
      border-bottom: 1px solid rgba(148,163,184,0.05);
      white-space: nowrap;
    }
    .data-table tr { cursor: pointer; transition: background 0.15s; }
    .data-table tr:hover { background: rgba(148,163,184,0.04); }
    .data-table tr.selected { background: rgba(139,92,246,0.08); }
    .agent-cell { display: flex; align-items: center; gap: 10px; }
    .agent-avatar {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      background: rgba(139,92,246,0.15);
      color: #a78bfa;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      font-weight: 700;
      flex-shrink: 0;
    }
    .agent-avatar.large {
      width: 48px;
      height: 48px;
      font-size: 18px;
      border-radius: 12px;
    }
    .agent-name { font-weight: 600; color: #f8fafc; font-size: 13px; }
    .agent-id { font-size: 11px; color: #64748b; font-family: monospace; }
    .pill {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 10px;
      font-size: 11px;
      font-weight: 600;
    }
    .pill.online { background: rgba(16,185,129,0.15); color: #10B981; }
    .pill.offline { background: rgba(100,116,139,0.15); color: #94a3b8; }
    .pill.busy { background: rgba(245,158,11,0.15); color: #f59e0b; }
    .pill.error { background: rgba(239,68,68,0.15); color: #ef4444; }
    .cap-tags { display: flex; gap: 4px; flex-wrap: wrap; }
    .mini-cap, .mini-tag {
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 4px;
      font-weight: 500;
    }
    .mini-cap { background: rgba(59,130,246,0.12); color: #60a5fa; }
    .mini-tag { background: rgba(139,92,246,0.12); color: #a78bfa; }
    .rate-cell { display: flex; flex-direction: column; gap: 4px; align-items: flex-start; }
    .mini-progress {
      width: 50px;
      height: 4px;
      background: rgba(148,163,184,0.1);
      border-radius: 2px;
      overflow: hidden;
    }
    .mini-progress-fill {
      height: 100%;
      background: #10B981;
      border-radius: 2px;
    }
    .time-cell { color: #64748b; font-size: 12px; }
    .btn {
      padding: 6px 12px;
      border-radius: 6px;
      border: 1px solid rgba(148,163,184,0.2);
      background: #1e293b;
      color: #e2e8f0;
      font-size: 12px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn:hover:not(:disabled) { background: #334155; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-sm { padding: 4px 10px; font-size: 12px; }
    .btn-icon {
      width: 32px;
      height: 32px;
      padding: 0;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .empty-cell {
      text-align: center;
      color: #64748b;
      padding: 32px;
    }
    .pagination {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 16px;
      border-top: 1px solid rgba(148,163,184,0.08);
    }
    .pagination-info { font-size: 12px; color: #64748b; }
    .pagination-controls { display: flex; gap: 8px; align-items: center; }
    .page-indicator { font-size: 13px; color: #94a3b8; padding: 0 8px; }
    .detail-drawer {
      background: #131827;
      border: 1px solid rgba(148,163,184,0.08);
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      max-height: calc(100vh - 200px);
      position: sticky;
      top: 24px;
    }
    .drawer-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px;
      border-bottom: 1px solid rgba(148,163,184,0.08);
    }
    .drawer-title { display: flex; align-items: center; gap: 12px; }
    .drawer-name { font-size: 16px; font-weight: 600; color: #f8fafc; }
    .drawer-id { font-size: 11px; color: #64748b; font-family: monospace; margin-top: 2px; }
    .drawer-body { overflow-y: auto; padding: 8px 0; }
    .drawer-section {
      padding: 12px 16px;
      border-bottom: 1px solid rgba(148,163,184,0.06);
    }
    .drawer-section h4 {
      margin: 0 0 10px;
      font-size: 13px;
      font-weight: 600;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .drawer-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 6px 0;
      font-size: 13px;
    }
    .drawer-row span:first-child { color: #94a3b8; }
    .drawer-row span:last-child { color: #e2e8f0; font-weight: 500; }
    .spark-area {
      height: 60px;
      display: flex;
      align-items: flex-end;
      gap: 4px;
      padding: 8px 0;
    }
    .spark-bars {
      display: flex;
      align-items: flex-end;
      gap: 4px;
      width: 100%;
      height: 100%;
    }
    .spark-bar {
      flex: 1;
      background: rgba(139,92,246,0.4);
      border-radius: 2px 2px 0 0;
      min-height: 4px;
      transition: height 0.3s;
    }
    .spark-labels {
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      color: #64748b;
      margin-top: 4px;
    }
    .resource-row {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 8px;
    }
    .resource-row span:first-child { font-size: 12px; color: #94a3b8; width: 40px; }
    .resource-bar {
      flex: 1;
      height: 6px;
      background: rgba(148,163,184,0.1);
      border-radius: 3px;
      overflow: hidden;
    }
    .resource-fill {
      height: 100%;
      background: #8B5CF6;
      border-radius: 3px;
    }
    .resource-fill.success { background: #10B981; }
    .resource-val { font-size: 12px; color: #cbd5e1; width: 36px; text-align: right; font-family: monospace; }
    .tag-list { display: flex; flex-wrap: wrap; gap: 6px; }
    .tag {
      background: rgba(139,92,246,0.12);
      color: #a78bfa;
      font-size: 11px;
      padding: 3px 10px;
      border-radius: 6px;
    }
    .tag.cap { background: rgba(59,130,246,0.12); color: #60a5fa; }
    @media (max-width: 1200px) {
      .stat-cards-row { grid-template-columns: repeat(3, 1fr); }
      .content-with-drawer.drawer-open { grid-template-columns: 1fr; }
      .detail-drawer { position: static; max-height: none; }
    }
    @media (max-width: 768px) {
      .stat-cards-row { grid-template-columns: repeat(2, 1fr); }
      .filter-bar { flex-direction: column; align-items: stretch; }
      .filter-input { width: 100%; }
      .tab-bar { overflow-x: auto; }
      .pagination { flex-direction: column; gap: 8px; align-items: stretch; }
    }
  `]
})
export class AgentsPageComponent {
  readonly state = inject(StateService);
  readonly activeTab = signal('Agents列表');
  readonly tabs = ['Agents列表', 'Agent市场', '我的收藏', '已禁用'];

  readonly searchQuery = signal('');
  readonly filterStatus = signal('');
  readonly filterType = signal('');
  readonly filterCapability = signal('');
  readonly filterTag = signal('');
  readonly onlineOnly = signal(false);
  readonly currentPage = signal(1);
  readonly pageSize = signal(10);
  readonly selectedAgent = signal<AgentRow | null>(null);

  // Mock agents data based on swarm overview / total agents
  readonly mockAgents = computed<AgentRow[]>(() => {
    const count = this.state.totalAgents() || 5;
    const types = ['coordinator', 'worker', 'specialist', 'reviewer'];
    const statuses: Array<'online' | 'offline' | 'busy' | 'error'> = ['online', 'online', 'online', 'busy', 'offline', 'error'];
    const caps = ['llm', 'tool', 'memory', 'planning'];
    const tags = ['core', 'production', 'experimental'];
    return Array.from({ length: count }, (_, i) => ({
      id: `agent-${String(i + 1).padStart(3, '0')}`,
      name: `Agent ${i + 1}`,
      status: statuses[i % statuses.length],
      type: types[i % types.length],
      capabilities: [caps[i % caps.length], caps[(i + 1) % caps.length]],
      tags: [tags[i % tags.length]],
      tasksExecuted: Math.floor(Math.random() * 500) + 10,
      successRate: Math.floor(Math.random() * 30) + 70,
      avgResponseTime: `${Math.floor(Math.random() * 300) + 50}ms`,
      tokenUsage: Math.floor(Math.random() * 50000) + 1000,
      lastActivity: `${Math.floor(Math.random() * 59) + 1}分钟前`
    }));
  });

  readonly activeAgentsCount = computed(() => this.mockAgents().filter(a => a.status === 'online').length);
  readonly totalTasksExecuted = computed(() => this.mockAgents().reduce((s, a) => s + a.tasksExecuted, 0));
  readonly totalTokenUsage = computed(() => this.mockAgents().reduce((s, a) => s + a.tokenUsage, 0).toLocaleString());
  readonly avgResponseTime = computed(() => {
    const vals = this.mockAgents().map(a => parseInt(a.avgResponseTime));
    if (!vals.length) return '—';
    return `${Math.floor(vals.reduce((s, v) => s + v, 0) / vals.length)}ms`;
  });

  readonly sparkHeights = computed(() => [35, 55, 42, 70, 48, 60, 38, 65, 50, 72, 45, 58]);

  readonly filteredAgents = computed(() => {
    let list = this.mockAgents();
    const q = this.searchQuery().toLowerCase();
    if (q) list = list.filter(a => a.name.toLowerCase().includes(q) || a.id.toLowerCase().includes(q));
    if (this.filterStatus()) list = list.filter(a => a.status === this.filterStatus());
    if (this.filterType()) list = list.filter(a => a.type === this.filterType());
    if (this.filterCapability()) list = list.filter(a => a.capabilities.includes(this.filterCapability()));
    if (this.filterTag()) list = list.filter(a => a.tags.includes(this.filterTag()));
    if (this.onlineOnly()) list = list.filter(a => a.status === 'online');
    return list;
  });

  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.filteredAgents().length / this.pageSize())));
  readonly paginatedAgents = computed(() => {
    const start = (this.currentPage() - 1) * this.pageSize();
    return this.filteredAgents().slice(start, start + this.pageSize());
  });

  statusText(status: string): string {
    const map: Record<string, string> = { online: '在线', offline: '离线', busy: '忙碌', error: '异常' };
    return map[status] || status;
  }

  selectAgent(agent: AgentRow): void {
    this.selectedAgent.set(agent);
  }

  onAction(agent: AgentRow, action: string): void {
    console.log('Action', action, 'on', agent.id);
  }
}
