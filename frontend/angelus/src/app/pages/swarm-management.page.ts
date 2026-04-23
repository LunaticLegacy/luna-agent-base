import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StateService } from '../services/state.service';
import { GraphViewerComponent } from '../graph-viewer.component';
import { ThoughtGraphViewerComponent } from '../thought-graph-viewer.component';

@Component({
  selector: 'app-swarm-management-page',
  standalone: true,
  imports: [CommonModule, GraphViewerComponent, ThoughtGraphViewerComponent],
  template: `
    <div class="page">
      <!-- Header -->
      <div class="page-header">
        <div class="header-left">
          <div class="swarm-title-row">
            <h1>{{ state.selectedSwarmName() || '未命名 Swarm' }}</h1>
            <span class="status-badge" [class.online]="state.health()?.status === 'ok'" [class.offline]="state.health()?.status !== 'ok'">
              {{ state.health()?.status === 'ok' ? '运行中' : '离线' }}
            </span>
          </div>
          <p class="subtitle">ID: {{ state.selectedSwarm()?.swarm_name || '—' }} · 最后更新: —</p>
        </div>
        <div class="header-actions">
          <button class="btn btn-secondary" (click)="reloadSwarm()" [disabled]="state.loadingDetails() || state.loading()">
            重新加载
          </button>
          <div class="dropdown">
            <button class="btn btn-secondary" (click)="showOpsDropdown.set(!showOpsDropdown())">
              操作 ▾
            </button>
            @if (showOpsDropdown()) {
              <div class="dropdown-menu">
                <div class="dropdown-item" (click)="loadSwarm(); showOpsDropdown.set(false)">加载 Swarm</div>
                <div class="dropdown-item" (click)="state.refreshGraph(); showOpsDropdown.set(false)">刷新 Graph</div>
                <div class="dropdown-item" (click)="state.refreshAll(); showOpsDropdown.set(false)">刷新全部</div>
                <div class="dropdown-divider"></div>
                <div class="dropdown-item danger" (click)="unloadSwarm(); showOpsDropdown.set(false)">删除 Swarm</div>
              </div>
            }
          </div>
          <button class="btn btn-secondary" (click)="state.activeRun() && state.startSwarmStructure()" [disabled]="!state.activeRun()">
            重新启动结构
          </button>
        </div>
      </div>

      <!-- Stat Cards -->
      <div class="stat-cards-row">
        <div class="stat-card">
          <div class="stat-label">状态</div>
          <div class="stat-value" [class.success]="state.health()?.status === 'ok'">{{ state.health()?.status === 'ok' ? '健康' : '异常' }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Agents</div>
          <div class="stat-value">{{ state.totalAgents() ?? 0 }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">当前任务</div>
          <div class="stat-value">{{ state.activeRunStatusText() }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">成功率</div>
          <div class="stat-value success">{{ state.swarmMgmtStats().successRate }}%</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">任务吞吐量</div>
          <div class="stat-value">{{ state.swarmMgmtStats().throughput }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Token 使用</div>
          <div class="stat-value">{{ state.swarmMgmtStats().tokenUsage }}</div>
        </div>
      </div>

      <!-- Tab Bar -->
      <div class="tab-bar">
        @for (tab of tabs; track tab) {
          <div
            class="tab-item"
            [class.active]="activeTab() === tab"
            (click)="activeTab.set(tab)"
          >
            {{ tab }}
          </div>
        }
      </div>

      @switch (activeTab()) {
        @case ('概览') {

      <!-- Topology Canvas -->
        <div class="panel-card topology-canvas">
        <div class="panel-header">
          <h3>Swarm 拓扑</h3>
          <div class="panel-actions">
            <button class="btn btn-sm" (click)="state.refreshGraph()" [disabled]="state.loading()">刷新</button>
          </div>
        </div>
        <div class="topology-graph">
          @if (state.resolvedGraph()) {
            <app-graph-viewer [graph]="state.resolvedGraph()" [activeNodeId]="state.activeRunNodeId()"></app-graph-viewer>
          } @else {
            <div class="empty-state">暂无拓扑数据</div>
          }
        </div>
      </div>

      <!-- Main Content Grid -->
      <div class="main-grid">
        <!-- Left: Node Type Legend -->
        <div class="panel-card legend-panel">
          <div class="panel-header">
            <h3>节点图例</h3>
          </div>
          <div class="legend-list">
            @for (item of state.topologyLegendItems(); track item.label) {
              <div class="legend-item">
                @if (item.kind === 'dot') {
                  <span class="legend-dot" [style.background]="item.color"></span>
                } @else if (item.kind === 'dashed') {
                  <span class="legend-line dashed" [style.background]="item.color"></span>
                } @else {
                  <span class="legend-line" [style.background]="item.color"></span>
                }
                <span class="legend-name">{{ item.label }}</span>
                <span class="legend-detail">{{ item.detail }}</span>
              </div>
            }
          </div>
        </div>

        <!-- Right: Info + Charts -->
        <div class="right-stack">
          <div class="panel-card info-panel">
            <div class="panel-header">
              <h3>Swarm 信息</h3>
            </div>
            <div class="info-body">
              <div class="info-row">
                <span class="info-key">名称</span>
                <span class="info-val">{{ state.selectedSwarmName() || '—' }}</span>
              </div>
              <div class="info-row">
                <span class="info-key">ID</span>
                <span class="info-val mono">{{ state.selectedSwarm()?.swarm_name || '—' }}</span>
              </div>
              <div class="info-row">
                <span class="info-key">创建时间</span>
                <span class="info-val">—</span>
              </div>
              <div class="info-row">
                <span class="info-key">描述</span>
                <span class="info-val">—</span>
              </div>
              <div class="info-row">
                <span class="info-key">标签</span>
                <div class="tags">
                  @for (tag of []; track tag) {
                    <span class="tag">{{ tag }}</span>
                  } @empty {
                    <span class="tag">默认</span>
                  }
                </div>
              </div>
            </div>
          </div>

          <div class="panel-card chart-panel">
            <div class="panel-header">
              <h3>资源使用趋势</h3>
            </div>
            <div class="chart-body">
              @for (item of state.swarmMgmtResourceTrends(); track item.label) {
                <div class="mini-spark">
                  <div class="mini-label">{{ item.label }}</div>
                  <div class="mini-bar"><div class="mini-fill" [style.width.%]="item.fill" [style.background]="item.color"></div></div>
                  <div class="mini-val">{{ item.value }}</div>
                </div>
              }
            </div>
          </div>

          <div class="panel-card chart-panel">
            <div class="panel-header">
              <h3>任务状态分布</h3>
            </div>
            <div class="donut-body">
              <div class="donut-chart" [style.background]="state.swarmMgmtTaskGradient()">
                <div class="donut-ring"></div>
                <div class="donut-center">{{ state.swarmMgmtStats().taskCount }}</div>
              </div>
              <div class="donut-legend">
                @for (slice of state.swarmMgmtTaskSlices(); track slice.label) {
                  <div class="dl-item">
                    <span class="dl-dot" [style.background]="slice.color"></span>
                    {{ slice.label }} {{ slice.percentage }}%
                  </div>
                }
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Bottom Tables -->
      <div class="bottom-tables">
        <div class="panel-card">
          <div class="panel-header">
            <h3>正在运行的任务</h3>
            <span class="badge">{{ (state.activeRun() ? 1 : 0) }}</span>
          </div>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>任务 ID</th>
                  <th>类型</th>
                  <th>状态</th>
                  <th>进度</th>
                  <th>开始时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                @if (state.activeRun()) {
                  <tr>
                    <td class="mono">{{ state.activeRun()?.run_id || 'RUN-001' }}</td>
                    <td>Swarm 执行</td>
                    <td><span class="pill running">{{ state.activeRunStatusText() }}</span></td>
                    <td>
                      <div class="progress-bar"><div class="progress-fill" [style.width.%]="45"></div></div>
                    </td>
                    <td>{{ state.activeRun()?.started_at || '刚刚' }}</td>
                    <td>
                      <button class="btn btn-sm" (click)="state.startSwarmStructure()">启动结构</button>
                    </td>
                  </tr>
                } @else {
                  <tr>
                    <td colspan="6" class="empty-cell">暂无运行中的任务</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>

      </div>
        }
        @case ('拓扑视图') {
          <div class="panel-card topology-canvas topology-fullscreen">
            <div class="panel-header">
              <h3>Swarm 拓扑</h3>
              <div class="panel-actions">
                <button class="btn btn-sm" (click)="state.refreshGraph()" [disabled]="state.loading()">刷新</button>
              </div>
            </div>
            <div class="topology-graph">
              @if (state.resolvedGraph()) {
                <app-graph-viewer [graph]="state.resolvedGraph()"></app-graph-viewer>
              } @else {
                <div class="empty-state">暂无拓扑数据</div>
              }
            </div>
          </div>
        }
        @case ('思考图') {
          <div class="panel-card topology-canvas topology-fullscreen thought-fullscreen">
            <div class="panel-header">
              <h3>Swarm 思考图</h3>
              <div class="panel-actions">
                <button class="btn btn-sm" (click)="state.refreshGraph()" [disabled]="state.loading()">刷新</button>
              </div>
            </div>
            <div class="topology-graph thought-graph">
              @if (state.resolvedThoughtGraph()) {
                <app-thought-graph-viewer [graph]="state.resolvedThoughtGraph()"></app-thought-graph-viewer>
              } @else {
                <div class="empty-state">暂无思考图数据</div>
              }
            </div>
          </div>
        }
        @case ('Agents') {
          <div class="tab-content">
            <div class="panel-card">
              <div class="panel-header"><h3>Agent 列表</h3><span class="badge">{{ state.derivedAgents().length }}</span></div>
              <div class="table-wrap">
                <table class="data-table">
                  <thead><tr><th>ID</th><th>状态</th><th>类型</th><th>任务执行</th><th>成功率</th><th>响应时间</th><th>最后活动</th></tr></thead>
                  <tbody>
                    @for (agent of state.derivedAgents(); track agent.id) {
                      <tr><td class="mono">{{ agent.id }}</td>
                      <td><span class="pill" [class.online]="agent.status==='online'" [class.running]="agent.status==='running'" [class.error]="agent.status==='error'">{{ agent.status }}</span></td>
                      <td>{{ agent.type }}</td><td>{{ agent.tasksExecuted }}</td><td>{{ agent.successRate }}%</td><td>{{ agent.avgResponseTime }}</td><td>{{ agent.lastActivity }}</td></tr>
                    } @empty { <tr><td colspan="7" class="empty-cell">暂无 Agent</td></tr> }
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        }
        @case ('任务') {
          <div class="tab-content">
            <div class="panel-card">
              <div class="panel-header"><h3>任务列表</h3><span class="badge">{{ state.derivedTasks().length }}</span></div>
              <div class="table-wrap">
                <table class="data-table">
                  <thead><tr><th>ID</th><th>名称</th><th>状态</th><th>优先级</th><th>执行者</th><th>耗时</th></tr></thead>
                  <tbody>
                    @for (task of state.derivedTasks(); track task.id) {
                      <tr><td class="mono">{{ task.id }}</td><td>{{ task.name }}</td>
                      <td><span class="pill" [class.running]="task.status==='running'" [class.success]="task.status==='success'" [class.failed]="task.status==='failed'">{{ task.status }}</span></td>
                      <td>{{ task.priority }}</td><td>{{ task.executor }}</td><td>{{ task.duration }}</td></tr>
                    } @empty { <tr><td colspan="6" class="empty-cell">暂无任务</td></tr> }
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        }
        @case ('知识') {
          <div class="tab-content">
            <div class="panel-card">
              <div class="panel-header"><h3>知识条目</h3><span class="badge">{{ state.derivedKnowledge().length }}</span></div>
              <div class="table-wrap">
                <table class="data-table">
                  <thead><tr><th>ID</th><th>标题</th><th>类型</th><th>来源</th><th>状态</th></tr></thead>
                  <tbody>
                    @for (entry of state.derivedKnowledge(); track entry.id) {
                      <tr><td class="mono">{{ entry.id }}</td><td>{{ entry.title }}</td><td>{{ entry.type }}</td><td>{{ entry.source }}</td><td><span class="pill active">{{ entry.status }}</span></td></tr>
                    } @empty { <tr><td colspan="5" class="empty-cell">暂无知识条目</td></tr> }
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        }
        @case ('记忆') {
          <div class="tab-content">
            <div class="panel-card">
              <div class="panel-header"><h3>记忆列表</h3><span class="badge">{{ state.derivedMemories().length }}</span></div>
              <div class="activity-list">
                @for (mem of state.derivedMemories(); track mem.id) {
                  <div class="activity-item">
                    <div class="activity-body">
                      <div class="activity-title">{{ mem.summary }}</div>
                      <div class="activity-desc">{{ mem.content.slice(0, 120) }}...</div>
                      <div class="activity-time">{{ mem.timestamp }} · {{ mem.type }} · 重要性 {{ mem.importance }}</div>
                    </div>
                  </div>
                } @empty { <div class="empty-state">暂无记忆</div> }
              </div>
            </div>
          </div>
        }
        @case ('设置') {
          <div class="tab-content">
            <div class="panel-card">
              <div class="panel-header"><h3>Swarm 设置</h3></div>
              <div class="info-body">
                <div class="info-row"><span class="info-key">Swarm 名称</span><span class="info-val">{{ state.selectedSwarmName() || '—' }}</span></div>
                <div class="info-row"><span class="info-key">Graph 文件</span><span class="info-val mono">{{ state.selectedSwarm()?.graph_file || '—' }}</span></div>
                <div class="info-row"><span class="info-key">Agent 数量</span><span class="info-val">{{ state.selectedSwarm()?.agent_count ?? 0 }}</span></div>
                <div class="info-row"><span class="info-key">技能数量</span><span class="info-val">{{ state.selectedSwarm()?.skill_count ?? 0 }}</span></div>
                <div class="info-row"><span class="info-key">工具数量</span><span class="info-val">{{ state.selectedSwarm()?.tool_count ?? 0 }}</span></div>
                <div class="info-row"><span class="info-key">Graph 有效</span><span class="info-val">{{ state.selectedSwarm()?.graph_valid ? '是' : '否' }}</span></div>
              </div>
            </div>
          </div>
        }
      }
    </div>
  `,
  styles: [`
    .page {
      padding: 24px;
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    .page-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 24px;
    }
    .swarm-title-row {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 4px;
    }
    .page-header h1 {
      margin: 0;
      font-size: 24px;
      font-weight: 600;
      color: #f8fafc;
    }
    .subtitle {
      margin: 4px 0 0;
      color: #64748b;
      font-size: 13px;
    }
    .status-badge {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 600;
      background: rgba(239,68,68,0.15);
      color: #ef4444;
    }
    .status-badge.online {
      background: rgba(16,185,129,0.15);
      color: #10B981;
    }
    .header-actions {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .btn {
      padding: 8px 16px;
      border-radius: 8px;
      border: 1px solid rgba(148,163,184,0.2);
      background: #1e293b;
      color: #e2e8f0;
      font-size: 14px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn:hover:not(:disabled) { background: #334155; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-primary { background: #8B5CF6; border-color: #8B5CF6; color: #fff; }
    .btn-primary:hover:not(:disabled) { background: #7c3aed; }
    .btn-secondary { background: #1e293b; }
    .btn-danger { background: rgba(239,68,68,0.15); border-color: rgba(239,68,68,0.3); color: #ef4444; }
    .btn-danger:hover:not(:disabled) { background: rgba(239,68,68,0.25); }
    .btn-sm { padding: 4px 10px; font-size: 12px; }
    .dropdown { position: relative; }
    .dropdown-menu {
      position: absolute;
      top: calc(100% + 6px);
      right: 0;
      background: #1e293b;
      border: 1px solid rgba(148,163,184,0.15);
      border-radius: 8px;
      min-width: 160px;
      z-index: 100;
      box-shadow: 0 10px 30px rgba(0,0,0,0.4);
      overflow: hidden;
    }
    .dropdown-item {
      padding: 10px 14px;
      font-size: 13px;
      color: #e2e8f0;
      cursor: pointer;
      transition: background 0.15s;
    }
    .dropdown-item:hover { background: rgba(148,163,184,0.1); }
    .dropdown-item.danger { color: #ef4444; }
    .dropdown-divider { height: 1px; background: rgba(148,163,184,0.1); margin: 4px 0; }
    .stat-cards-row {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
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
      font-size: 20px;
      font-weight: 700;
      color: #f8fafc;
    }
    .stat-value.success { color: #10B981; }
    .tab-bar {
      display: flex;
      gap: 4px;
      margin-bottom: 20px;
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
    .main-grid {
      display: grid;
      grid-template-columns: 240px 1fr;
      gap: 24px;
      margin-bottom: 20px;
    }
    .panel-card {
      background: #131827;
      border: 1px solid rgba(148,163,184,0.08);
      border-radius: 12px;
      overflow: hidden;
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 14px 18px;
      border-bottom: 1px solid rgba(148,163,184,0.08);
    }
    .panel-header h3 {
      margin: 0;
      font-size: 14px;
      font-weight: 600;
      color: #f8fafc;
    }
    .panel-actions { display: flex; gap: 6px; }
    .badge {
      background: rgba(139,92,246,0.15);
      color: #8B5CF6;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 12px;
    }
    .legend-list { padding: 12px 18px; }
    .legend-item {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 0;
      font-size: 13px;
      color: #cbd5e1;
    }
    .legend-name {
      flex: 0 0 auto;
    }
    .legend-detail {
      margin-left: auto;
      color: #94a3b8;
      font-size: 12px;
      white-space: nowrap;
    }
    .legend-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      flex-shrink: 0;
    }
    .legend-line {
      width: 20px;
      height: 2px;
      background: #94a3b8;
      flex-shrink: 0;
    }
    .legend-line.dashed {
      background: repeating-linear-gradient(90deg, #94a3b8, #94a3b8 4px, transparent 4px, transparent 8px);
      height: 2px;
    }
    .topology-canvas {
      display: flex;
      flex-direction: column;
      height: 600px;
      margin-bottom: 18px;
      background: #131827;
      border: 1px solid rgba(148,163,184,0.08);
      border-radius: 12px;
      overflow: hidden;
    }
    .topology-canvas .panel-header {
      padding: 12px 18px;
      border-bottom: 1px solid rgba(148,163,184,0.08);
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
    }
    .topology-graph {
      flex: 1;
      background: #0a0e1a;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      min-height: 0;
      padding: 12px;
    }
    .topology-graph app-graph-viewer {
      width: 100%;
      height: 100%;
      display: block;
      flex: 1 1 auto;
      min-width: 0;
      min-height: 0;
    }
    .right-stack { display: flex; flex-direction: column; gap: 16px; }
    .info-body { padding: 12px 18px; }
    .info-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      padding: 8px 0;
      border-bottom: 1px solid rgba(148,163,184,0.05);
      font-size: 13px;
    }
    .info-key { color: #94a3b8; min-width: 70px; }
    .info-val { color: #e2e8f0; text-align: right; word-break: break-word; }
    .info-val.mono { font-family: monospace; font-size: 12px; }
    .tags { display: flex; flex-wrap: wrap; gap: 4px; justify-content: flex-end; }
    .tag {
      background: rgba(139,92,246,0.12);
      color: #a78bfa;
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 4px;
    }
    .chart-body { padding: 14px 18px; }
    .mini-spark {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
    }
    .mini-label { font-size: 12px; color: #94a3b8; width: 40px; }
    .mini-bar {
      flex: 1;
      height: 6px;
      background: rgba(148,163,184,0.1);
      border-radius: 3px;
      overflow: hidden;
    }
    .mini-fill {
      height: 100%;
      background: #8B5CF6;
      border-radius: 3px;
    }
    .mini-fill.success { background: #10B981; }
    .mini-val { font-size: 12px; color: #cbd5e1; width: 36px; text-align: right; font-family: monospace; }
    .donut-body {
      padding: 14px 18px;
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .donut-chart {
      width: 80px;
      height: 80px;
      border-radius: 50%;
      background: conic-gradient(#10B981 0% 65%, #f59e0b 65% 90%, #ef4444 90% 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      flex-shrink: 0;
    }
    .donut-ring {
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: #131827;
    }
    .donut-center {
      position: absolute;
      font-size: 16px;
      font-weight: 700;
      color: #f8fafc;
    }
    .donut-legend { flex: 1; }
    .dl-item {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: #cbd5e1;
      margin-bottom: 6px;
    }
    .dl-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
    }
    .bottom-tables {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    .table-wrap { overflow-x: auto; }
    .data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .data-table th {
      text-align: left;
      padding: 10px 18px;
      color: #94a3b8;
      font-weight: 500;
      border-bottom: 1px solid rgba(148,163,184,0.08);
      white-space: nowrap;
    }
    .data-table td {
      padding: 10px 18px;
      color: #cbd5e1;
      border-bottom: 1px solid rgba(148,163,184,0.05);
      white-space: nowrap;
    }
    .data-table tr:hover td { background: rgba(148,163,184,0.03); }
    .mono { font-family: monospace; font-size: 12px; }
    .tab-content { padding: 16px 0; }
    .topology-fullscreen { height: calc(100vh - 220px); min-height: 480px; }
    .pill {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 10px;
      font-size: 11px;
      font-weight: 600;
    }
    .pill.running { background: rgba(59,130,246,0.15); color: #60a5fa; }
    .pill.success { background: rgba(16,185,129,0.15); color: #10B981; }
    .pill.online { background: rgba(16,185,129,0.15); color: #10B981; }
    .pill.busy { background: rgba(139,92,246,0.15); color: #a78bfa; }
    .pill.error { background: rgba(239,68,68,0.15); color: #ef4444; }
    .pill.failed { background: rgba(239,68,68,0.15); color: #ef4444; }
    .pill.active { background: rgba(59,130,246,0.15); color: #60a5fa; }
    .progress-bar {
      width: 80px;
      height: 6px;
      background: rgba(148,163,184,0.1);
      border-radius: 3px;
      overflow: hidden;
    }
    .progress-fill {
      height: 100%;
      background: #8B5CF6;
      border-radius: 3px;
      transition: width 0.3s;
    }
    .empty-cell {
      text-align: center;
      color: #64748b;
      padding: 24px;
    }
    .activity-list {
      max-height: 280px;
      overflow-y: auto;
      padding: 8px 18px;
    }
    .activity-item {
      display: flex;
      gap: 12px;
      padding: 10px 0;
      border-bottom: 1px solid rgba(148,163,184,0.05);
    }
    .activity-icon {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      background: rgba(139,92,246,0.12);
      color: #a78bfa;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      font-weight: 700;
      flex-shrink: 0;
    }
    .activity-icon.success { background: rgba(16,185,129,0.12); color: #10B981; }
    .activity-icon.error { background: rgba(239,68,68,0.12); color: #ef4444; }
    .activity-body { flex: 1; min-width: 0; }
    .activity-title { font-size: 13px; font-weight: 600; color: #e2e8f0; margin-bottom: 2px; }
    .activity-desc { font-size: 12px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .activity-time { font-size: 11px; color: #64748b; margin-top: 2px; }
    .empty-state { padding: 24px; text-align: center; color: #64748b; font-size: 13px; }
    @media (max-width: 1200px) {
      .stat-cards-row { grid-template-columns: repeat(3, 1fr); }
      .main-grid { grid-template-columns: 1fr; }
      .bottom-tables { grid-template-columns: 1fr; }
      .right-stack { flex-direction: row; flex-wrap: wrap; }
      .right-stack .panel-card { flex: 1; min-width: 240px; }
    }
    @media (max-width: 768px) {
      .stat-cards-row { grid-template-columns: repeat(2, 1fr); }
      .page-header { flex-direction: column; gap: 12px; }
      .tab-bar { overflow-x: auto; }
    }
  `]
})
export class SwarmManagementPageComponent {
  readonly state = inject(StateService);
  readonly activeTab = signal('概览');
  readonly showOpsDropdown = signal(false);
  readonly tabs = ['概览', '拓扑视图', '思考图', 'Agents', '任务', '知识', '记忆', '设置'];

  async loadSwarm(): Promise<void> {
    const source = window.prompt('输入要加载的 Swarm 路径或名称');
    if (!source) return;
    await this.state.loadSwarmFromSource(source);
  }

  async reloadSwarm(): Promise<void> {
    await this.state.reloadCurrentSwarm();
  }

  async unloadSwarm(): Promise<void> {
    const swarmName = this.state.selectedSwarmName();
    if (!swarmName) return;
    if (!window.confirm(`确认卸载 Swarm "${swarmName}" 吗？`)) return;
    await this.state.unloadCurrentSwarm();
  }

}
