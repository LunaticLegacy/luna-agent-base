import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StateService } from '../services/state.service';
import { GraphViewerComponent } from '../graph-viewer.component';
import { ThoughtGraphViewerComponent } from '../thought-graph-viewer.component';
import { THOUGHT_NODE_LEGEND_ENTRIES, THOUGHT_RELATION_LEGEND_ENTRIES } from '../thought-graph.taxonomy';
import { EmptyStateComponent, PanelCardComponent, StatCardGridComponent, TabBarComponent } from '../shared';

@Component({
  selector: 'app-swarm-management-page',
  standalone: true,
  imports: [CommonModule, GraphViewerComponent, ThoughtGraphViewerComponent, StatCardGridComponent, TabBarComponent, PanelCardComponent, EmptyStateComponent],
  template: `
    <div class="page">
      <!-- Header (kept inline due to custom status badge inline with title) -->
      <div class="page-header">
        <div class="header-left">
          <div class="swarm-title-row">
            <h1>{{ state.selectedSwarmName() || '未命名 Swarm' }}</h1>
            <span class="status-badge" [class.online]="state.health()?.status === 'ok'" [class.offline]="state.health()?.status !== 'ok'">
              {{ state.health()?.status === 'ok' ? '运行中' : '离线' }}
            </span>
          </div>
          <p class="subtitle">{{ state.swarmSummaryText() }}</p>
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
          <button class="btn btn-secondary" (click)="state.activeRun() && state.startRun()" [disabled]="!state.activeRun()">
            重新启动结构
          </button>
        </div>
      </div>

      <!-- Stat Cards -->
      <app-stat-card-grid [cards]="[
        { label: '状态', value: state.health()?.status === 'ok' ? '健康' : '异常', tone: state.health()?.status === 'ok' ? 'good' : 'bad' },
        { label: 'Agents', value: state.totalAgents() },
        { label: '当前任务', value: state.activeRunStatusText() },
        { label: '成功率', value: state.swarmMgmtStats().successRate + '%', tone: 'good' },
        { label: '任务吞吐量', value: state.swarmMgmtStats().throughput },
        { label: 'Token 使用', value: state.swarmMgmtStats().tokenUsage },
        { label: 'API 数量', value: state.swarmMgmtStats().apiCount ?? (state.selectedSwarm()?.api_count ?? 0) }
      ]"></app-stat-card-grid>

      <!-- Tab Bar -->
      <app-tab-bar [tabs]="tabs" [activeTab]="activeTab()" (tabChange)="activeTab.set($event)"></app-tab-bar>

      @switch (activeTab()) {
        @case ('概览') {

      <!-- Agent Graph Canvas -->
      <div class="topology-canvas">
        <div class="panel-header">
          <h3>Agent 图</h3>
          <div class="panel-actions">
            <button class="btn btn-sm" (click)="state.refreshGraph()" [disabled]="state.loading()">刷新</button>
          </div>
        </div>
        <div class="topology-graph">
          @if (state.resolvedGraph()) {
            <app-graph-viewer [graph]="state.resolvedGraph()" [activeNodeId]="state.activeRunNodeId()"></app-graph-viewer>
          } @else {
            <app-empty-state message="暂无 Agent 图数据"></app-empty-state>
          }
        </div>
      </div>

      <!-- Main Content Grid -->
      <div class="main-grid">
        <!-- Left: Node Type Legend -->
        <app-panel-card title="Agent 图例" [noPadding]="true">
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
        </app-panel-card>

        <!-- Right: Info + Charts -->
        <div class="right-stack">
        <app-panel-card title="Swarm 信息" [noPadding]="true">
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
          </app-panel-card>

          <app-panel-card title="资源使用趋势" [noPadding]="true">
            <div class="chart-body">
              @for (item of state.swarmMgmtResourceTrends(); track item.label) {
                <div class="mini-spark">
                  <div class="mini-label">{{ item.label }}</div>
                  <div class="mini-bar"><div class="mini-fill" [style.width.%]="item.fill" [style.background]="item.color"></div></div>
                  <div class="mini-val">{{ item.value }}</div>
                </div>
              }
            </div>
          </app-panel-card>

          <app-panel-card title="任务状态分布" [noPadding]="true">
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
          </app-panel-card>
        </div>
      </div>

      <!-- Bottom Tables -->
      <div class="bottom-tables">
        <app-panel-card title="正在运行的任务" [badge]="state.activeRun() ? 1 : 0" [noPadding]="true">
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
                      <button class="btn btn-sm" (click)="state.startRun()">启动结构</button>
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
        </app-panel-card>

      </div>
        }
        @case ('Agent 图') {
          <div class="topology-shell topology-fullscreen">
            <div class="panel-header topology-header">
              <div>
                <h3>Agent 图</h3>
                <p class="panel-subtitle">展示当前 swarm 的 Agent 节点、路由关系和活跃路径。</p>
              </div>
              <div class="panel-actions">
                <button class="btn btn-sm" (click)="state.refreshGraph()" [disabled]="state.loading()">刷新</button>
              </div>
            </div>
            <div class="topology-layout">
              <div class="topology-stage">
                <div class="topology-stage-frame">
                  @if (state.resolvedGraph()) {
                    <app-graph-viewer [graph]="state.resolvedGraph()" [activeNodeId]="state.activeRunNodeId()"></app-graph-viewer>
                  } @else {
                    <app-empty-state message="暂无 Agent 图数据"></app-empty-state>
                  }
                </div>
                <div class="topology-summary-strip">
                  <div class="summary-item">
                    <span class="summary-label">Agent 节点</span>
                    <span class="summary-value">{{ state.resolvedGraph()?.nodes?.length ?? 0 }}</span>
                  </div>
                  <div class="summary-item">
                    <span class="summary-label">关系边</span>
                    <span class="summary-value">{{ state.resolvedGraph()?.edges?.length ?? 0 }}</span>
                  </div>
                  <div class="summary-item">
                    <span class="summary-label">入口 / 退出</span>
                    <span class="summary-value">{{ state.resolvedGraph()?.entry_node_id ?? '—' }} / {{ state.resolvedGraph()?.exit_node_id ?? '—' }}</span>
                  </div>
                  <div class="summary-item">
                    <span class="summary-label">版本</span>
                    <span class="summary-value">
                      {{ state.resolvedGraph()?.revision !== undefined && state.resolvedGraph()?.revision !== null ? '#' + state.resolvedGraph()?.revision : '—' }}
                    </span>
                  </div>
                </div>
              </div>
              <div class="topology-rail">
                <app-panel-card title="图例" [noPadding]="true">
                  <div class="legend-list topology-legend">
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
                </app-panel-card>
                <app-panel-card title="Agent 节点" [badge]="state.resolvedGraph()?.nodes?.length ?? 0" [noPadding]="true">
                  <div class="topology-instance-list">
                    @for (node of state.resolvedGraph()?.nodes ?? []; track node.node_id) {
                      <div class="topology-instance-item">
                        <div class="topology-instance-head">
                          <div class="topology-instance-name">{{ node.node_name }}</div>
                          <span class="pill active">{{ node.node_type }}</span>
                        </div>
                        <div class="topology-instance-meta mono">ID {{ node.node_id }}</div>
                        <div class="topology-instance-detail">next: {{ node.next_node_ids.length ? node.next_node_ids.join(', ') : 'none' }}</div>
                      </div>
                    } @empty {
                      <app-empty-state message="暂无 Agent 节点"></app-empty-state>
                    }
                  </div>
                </app-panel-card>
              </div>
            </div>
          </div>
        }
        @case ('执行轨迹') {
          <div class="trace-shell trace-fullscreen">
            <div class="panel-header trace-header">
              <div>
                <h3>执行轨迹图</h3>
                <p class="panel-subtitle">展示运行中的 run、事件序列和分支执行信息。</p>
              </div>
              <div class="panel-actions">
                <button class="btn btn-sm" (click)="state.refreshGraph()" [disabled]="state.loading()">刷新</button>
              </div>
            </div>
            <div class="trace-layout">
              <app-panel-card title="当前 Run" [noPadding]="true">
                @if (state.selectedExecutionTrace()?.run; as run) {
                  <div class="info-body">
                    <div class="info-row"><span class="info-key">Run ID</span><span class="info-val mono">{{ run.run_id }}</span></div>
                    <div class="info-row"><span class="info-key">状态</span><span class="info-val">{{ run.status }}</span></div>
                    <div class="info-row"><span class="info-key">Swarm</span><span class="info-val">{{ run.swarm }}</span></div>
                    <div class="info-row"><span class="info-key">轮次</span><span class="info-val">{{ run.rounds }}</span></div>
                    <div class="info-row"><span class="info-key">当前节点</span><span class="info-val">{{ run.current_node_name || '—' }}</span></div>
                    <div class="info-row"><span class="info-key">事件数</span><span class="info-val">{{ run.event_count }}</span></div>
                  </div>
                } @else {
                  <app-empty-state message="当前没有可展示的运行轨迹。"></app-empty-state>
                }
              </app-panel-card>
              <app-panel-card title="事件列表" [badge]="state.selectedExecutionTrace()?.events?.length ?? 0" [noPadding]="true">
                <div class="trace-event-list">
                  @for (event of state.selectedExecutionTrace()?.events ?? []; track $index) {
                    <div class="trace-event-item">
                      <div class="trace-event-head">
                        <span class="trace-event-index mono">#{{ $index + 1 }}</span>
                        <span class="trace-event-title">{{ traceEventLabel(event) }}</span>
                      </div>
                      <pre class="trace-event-body">{{ event | json }}</pre>
                    </div>
                  } @empty {
                    <app-empty-state message="当前没有事件可展示。"></app-empty-state>
                  }
                </div>
              </app-panel-card>
            </div>
          </div>
        }
        @case ('思维图谱') {
          <div class="thought-shell thought-fullscreen">
            <div class="panel-header thought-header">
              <div>
                <h3>思维图谱</h3>
                <p class="panel-subtitle">展示认知节点、关系边和活跃子图。</p>
              </div>
              <div class="panel-actions">
                <button class="btn btn-sm" (click)="state.refreshGraph()" [disabled]="state.loading()">刷新</button>
              </div>
            </div>
            <div class="thought-layout">
              <div class="thought-stage">
                <div class="thought-stage-frame">
                  @if (state.resolvedThoughtGraph()) {
                    <app-thought-graph-viewer [graph]="state.resolvedThoughtGraph()"></app-thought-graph-viewer>
                  } @else {
                    <app-empty-state message="暂无思维图谱数据"></app-empty-state>
                  }
                </div>
                <div class="thought-summary-strip">
                  <div class="summary-item">
                    <span class="summary-label">节点</span>
                    <span class="summary-value">{{ state.resolvedThoughtGraph()?.nodes?.length ?? 0 }}</span>
                  </div>
                  <div class="summary-item">
                    <span class="summary-label">边</span>
                    <span class="summary-value">{{ state.resolvedThoughtGraph()?.edges?.length ?? 0 }}</span>
                  </div>
                  <div class="summary-item">
                    <span class="summary-label">活跃子图</span>
                    <span class="summary-value">{{ state.resolvedThoughtGraph()?.active_subgraphs?.length ?? 0 }}</span>
                  </div>
                </div>
              </div>
              <div class="thought-rail">
                <app-panel-card title="图例" [noPadding]="true">
                  <div class="thought-legend">
                    <div class="thought-legend-group">
                      <div class="legend-group-title">节点类型</div>
                      <div class="legend-grid legend-grid-nodes">
                        @for (item of thoughtNodeLegendItems; track item.key) {
                          <div class="legend-item">
                            <span class="legend-dot" [style.background]="item.color"></span>
                            <span class="legend-name">{{ item.label }}</span>
                            <span class="legend-detail">{{ item.detail }}</span>
                          </div>
                        }
                      </div>
                    </div>
                    <div class="thought-legend-group">
                      <div class="legend-group-title">关系类型</div>
                      <div class="legend-grid legend-grid-relations">
                        @for (item of thoughtRelationLegendItems; track item.key) {
                          <div class="legend-item">
                            <span class="legend-line" [class.dashed]="!!item.dash" [style.background]="item.color"></span>
                            <span class="legend-name">{{ item.label }}</span>
                            <span class="legend-detail">{{ item.detail }}</span>
                          </div>
                        }
                      </div>
                    </div>
                  </div>
                </app-panel-card>
                <app-panel-card title="活跃子图" [noPadding]="true">
                  <div class="thought-subgraph-list">
                    @for (subgraph of state.resolvedThoughtGraph()?.active_subgraphs ?? []; track subgraph.subgraph_id) {
                      <div class="thought-subgraph-item">
                        <div class="thought-subgraph-title">{{ subgraph.purpose || subgraph.subgraph_id }}</div>
                        <div class="thought-subgraph-meta mono">{{ subgraph.subgraph_id }}</div>
                        <div class="thought-subgraph-detail">owner: {{ subgraph.owner_agent }} · status: {{ subgraph.status }}</div>
                      </div>
                    } @empty {
                      <app-empty-state message="暂无活跃子图"></app-empty-state>
                    }
                  </div>
                </app-panel-card>
              </div>
            </div>
          </div>
        }
        @case ('Agents') {
          <div class="tab-content">
            <app-panel-card title="Agent 列表" [badge]="state.derivedAgents().length" [noPadding]="true">
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
            </app-panel-card>
          </div>
        }
        @case ('任务') {
          <div class="tab-content">
            <app-panel-card title="任务列表" [badge]="state.derivedTasks().length" [noPadding]="true">
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
            </app-panel-card>
          </div>
        }
        @case ('知识') {
          <div class="tab-content">
            <app-panel-card title="知识条目" [badge]="state.derivedKnowledge().length" [noPadding]="true">
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
            </app-panel-card>
          </div>
        }
        @case ('记忆') {
          <div class="tab-content">
            <app-panel-card title="记忆列表" [badge]="state.derivedMemories().length" [noPadding]="true">
              <div class="activity-list">
                @for (mem of state.derivedMemories(); track mem.id) {
                  <div class="activity-item">
                    <div class="activity-body">
                      <div class="activity-title">{{ mem.summary }}</div>
                      <div class="activity-desc">{{ mem.content.slice(0, 120) }}...</div>
                      <div class="activity-time">{{ mem.timestamp }} · {{ mem.type }} · 重要性 {{ mem.importance }}</div>
                    </div>
                  </div>
                } @empty { <app-empty-state message="暂无记忆"></app-empty-state> }
              </div>
            </app-panel-card>
          </div>
        }
        @case ('设置') {
          <div class="tab-content">
            <app-panel-card title="Swarm 设置" [noPadding]="true">
              <div class="info-body">
                <div class="info-row"><span class="info-key">Swarm 名称</span><span class="info-val">{{ state.selectedSwarmName() || '—' }}</span></div>
                <div class="info-row"><span class="info-key">Graph 文件</span><span class="info-val mono">{{ state.selectedSwarm()?.graph_file || '—' }}</span></div>
                <div class="info-row"><span class="info-key">Agent 数量</span><span class="info-val">{{ state.selectedSwarm()?.agent_count ?? 0 }}</span></div>
                <div class="info-row"><span class="info-key">技能数量</span><span class="info-val">{{ state.selectedSwarm()?.skill_count ?? 0 }}</span></div>
                <div class="info-row"><span class="info-key">工具数量</span><span class="info-val">{{ state.selectedSwarm()?.tool_count ?? 0 }}</span></div>
                <div class="info-row"><span class="info-key">API 数量</span><span class="info-val">{{ state.selectedSwarm()?.api_count ?? 0 }}</span></div>
                <div class="info-row"><span class="info-key">Graph 有效</span><span class="info-val">{{ state.selectedSwarm()?.graph_valid ? '是' : '否' }}</span></div>
              </div>
            </app-panel-card>
            <app-panel-card title="API 列表" [badge]="state.apis().length" [noPadding]="true">
              @if (state.apisLoaded() && state.apis().length > 0) {
                <div class="table-wrap">
                  <table class="data-table">
                    <thead><tr><th>名称</th><th>来源</th><th>类型</th><th>路径</th></tr></thead>
                    <tbody>
                      @for (api of state.apis(); track api.name) {
                        <tr>
                          <td class="mono">{{ api.name }}</td>
                          <td><span class="pill active">{{ api.origin }}</span></td>
                          <td>{{ api.type }}</td>
                          <td class="mono">{{ api.source || '—' }}</td>
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              } @else {
                <app-empty-state message="暂无已注册 API"></app-empty-state>
              }
            </app-panel-card>
          </div>
        }
      }
    </div>
  `,
  styles: [`
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
                                .btn-danger:hover:not(:disabled) { background: rgba(239,68,68,0.25); }
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
    .main-grid {
      display: grid;
      grid-template-columns: 240px 1fr;
      gap: 24px;
      margin-bottom: 20px;
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
    .legend-list { padding: 12px 18px; }
    .thought-legend {
      display: grid;
      gap: 14px;
      padding: 12px 14px 14px;
      max-height: 520px;
      overflow: auto;
    }
    .thought-legend-group {
      display: grid;
      gap: 8px;
    }
    .legend-group-title {
      color: #e2e8f0;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .legend-grid {
      display: grid;
      gap: 2px;
    }
    .legend-grid-nodes {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .legend-grid-relations {
      grid-template-columns: repeat(1, minmax(0, 1fr));
    }
    .legend-item {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 0;
      font-size: 13px;
      color: #cbd5e1;
      min-width: 0;
    }
    .legend-name {
      flex: 0 0 auto;
      white-space: nowrap;
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
      box-shadow: 0 0 0 1px rgba(8, 12, 22, 0.55), 0 0 8px rgba(148,163,184,0.16);
    }
    .legend-line {
      width: 20px;
      height: 2px;
      background: #94a3b8;
      flex-shrink: 0;
      border-radius: 999px;
      box-shadow: 0 0 0 1px rgba(8, 12, 22, 0.4);
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
    .info-val    .tags { display: flex; flex-wrap: wrap; gap: 4px; justify-content: flex-end; }
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
                .data-table tr:hover td { background: rgba(148,163,184,0.03); }
        .tab-content { padding: 16px 0; }
    .topology-fullscreen { height: calc(100vh - 220px); min-height: 480px; }
    .topology-shell,
    .thought-shell {
      display: flex;
      flex-direction: column;
      gap: 14px;
      height: calc(100vh - 220px);
      min-height: 560px;
      margin-bottom: 18px;
      padding: 14px;
      background:
        radial-gradient(circle at top left, rgba(94, 234, 212, 0.12), transparent 28%),
        radial-gradient(circle at bottom right, rgba(139, 92, 246, 0.10), transparent 24%),
        linear-gradient(180deg, #0c1220, #090d17);
      border: 1px solid rgba(148,163,184,0.1);
      border-radius: 16px;
      overflow: hidden;
    }
    .topology-shell {
      background:
        radial-gradient(circle at top left, rgba(96, 165, 250, 0.12), transparent 28%),
        radial-gradient(circle at bottom right, rgba(34, 197, 94, 0.10), transparent 24%),
        linear-gradient(180deg, #0c1220, #090d17);
    }
    .topology-header {
      padding: 0 4px;
      border-bottom: none;
    }
    .thought-header {
      padding: 0 4px;
      border-bottom: none;
    }
    .panel-subtitle {
      margin: 4px 0 0;
      color: #94a3b8;
      font-size: 12px;
    }
    .thought-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 312px;
      gap: 14px;
      min-height: 0;
      flex: 1 1 auto;
    }
    .topology-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 312px;
      gap: 14px;
      min-height: 0;
      flex: 1 1 auto;
    }
    .thought-stage {
      display: flex;
      flex-direction: column;
      min-width: 0;
      min-height: 0;
      gap: 10px;
    }
    .topology-stage {
      display: flex;
      flex-direction: column;
      min-width: 0;
      min-height: 0;
      gap: 10px;
    }
    .thought-stage-frame {
      flex: 1 1 auto;
      min-height: 0;
      min-width: 0;
      overflow: hidden;
      border-radius: 14px;
      border: 1px solid rgba(148,163,184,0.10);
      background: rgba(2, 6, 23, 0.45);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
    }
    .topology-stage-frame {
      flex: 1 1 auto;
      min-height: 0;
      min-width: 0;
      overflow: hidden;
      border-radius: 14px;
      border: 1px solid rgba(148,163,184,0.10);
      background: rgba(2, 6, 23, 0.45);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
    }
    .thought-stage-frame app-thought-graph-viewer {
      display: block;
      width: 100%;
      height: 100%;
      min-width: 0;
      min-height: 0;
    }
    .topology-stage-frame app-graph-viewer {
      display: block;
      width: 100%;
      height: 100%;
      min-width: 0;
      min-height: 0;
    }
    .thought-summary-strip {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .topology-summary-strip {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .summary-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 12px;
      border-radius: 12px;
      background: rgba(15, 23, 42, 0.72);
      border: 1px solid rgba(148,163,184,0.08);
    }
    .summary-label {
      color: #94a3b8;
      font-size: 12px;
    }
    .summary-value {
      color: #f8fafc;
      font-size: 14px;
      font-weight: 700;
    }
    .thought-rail {
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-width: 0;
      min-height: 0;
    }
    .topology-rail {
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-width: 0;
      min-height: 0;
    }
    .topology-legend {
      max-height: 260px;
      overflow: auto;
    }
    .topology-instance-list {
      max-height: 420px;
      overflow: auto;
      padding: 12px 14px 14px;
      display: grid;
      gap: 10px;
    }
    .topology-instance-item {
      padding: 10px 0;
      border-bottom: 1px solid rgba(148,163,184,0.06);
    }
    .topology-instance-item:last-child {
      border-bottom: none;
    }
    .topology-instance-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin-bottom: 4px;
    }
    .topology-instance-name {
      color: #f8fafc;
      font-size: 13px;
      font-weight: 600;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .topology-instance-meta,
    .topology-instance-detail {
      color: #94a3b8;
      font-size: 11px;
      line-height: 1.4;
      word-break: break-word;
    }
    .thought-legend,
    .thought-subgraph-list {
      padding: 12px 14px;
    }
    .thought-subgraph-item {
      padding: 10px 0;
      border-bottom: 1px solid rgba(148,163,184,0.06);
    }
    .thought-subgraph-item:last-child {
      border-bottom: none;
    }
    .thought-subgraph-title {
      color: #f8fafc;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 4px;
    }
    .thought-subgraph-meta,
    .thought-subgraph-detail {
      color: #94a3b8;
      font-size: 11px;
    }
    .thought-subgraph-meta {
      margin-bottom: 2px;
    }
    .trace-fullscreen {
      min-height: 480px;
    }
    .trace-shell {
      display: flex;
      flex-direction: column;
      gap: 14px;
      height: calc(100vh - 220px);
      min-height: 560px;
      margin-bottom: 18px;
      padding: 14px;
      background:
        radial-gradient(circle at top left, rgba(59, 130, 246, 0.12), transparent 28%),
        radial-gradient(circle at bottom right, rgba(16, 185, 129, 0.10), transparent 24%),
        linear-gradient(180deg, #0c1220, #090d17);
      border: 1px solid rgba(148,163,184,0.1);
      border-radius: 16px;
      overflow: hidden;
    }
    .trace-header {
      padding: 0 4px;
      border-bottom: none;
    }
    .trace-layout {
      display: grid;
      grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
      gap: 14px;
      min-height: 0;
      flex: 1 1 auto;
    }
    .trace-event-list {
      max-height: 100%;
      overflow: auto;
      padding: 12px 14px 14px;
      display: grid;
      gap: 10px;
    }
    .trace-event-item {
      border: 1px solid rgba(148,163,184,0.08);
      border-radius: 12px;
      background: rgba(15, 23, 42, 0.64);
      padding: 10px 12px;
    }
    .trace-event-head {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 8px;
    }
    .trace-event-index {
      color: #94a3b8;
      font-size: 11px;
    }
    .trace-event-title {
      color: #f8fafc;
      font-size: 13px;
      font-weight: 600;
    }
    .trace-event-body {
      margin: 0;
      color: #cbd5e1;
      font-size: 11px;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-word;
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
    .activity-body { flex: 1; min-width: 0; }
    .activity-title { font-size: 13px; font-weight: 600; color: #e2e8f0; margin-bottom: 2px; }
    .activity-desc { font-size: 12px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .activity-time { font-size: 11px; color: #64748b; margin-top: 2px; }
    @media (max-width: 1200px) {
      .main-grid { grid-template-columns: 1fr; }
      .bottom-tables { grid-template-columns: 1fr; }
      .right-stack { flex-direction: row; flex-wrap: wrap; }
      .right-stack app-panel-card { flex: 1; min-width: 240px; }
      .legend-grid-nodes { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .topology-layout,
      .thought-layout,
      .trace-layout { grid-template-columns: 1fr; }
      .topology-rail,
      .thought-rail { flex-direction: row; flex-wrap: wrap; }
      .topology-rail app-panel-card,
      .thought-rail app-panel-card { flex: 1; min-width: 260px; }
      .topology-instance-list { max-height: 280px; }
    }
    @media (max-width: 768px) {
      .page-header { flex-direction: column; gap: 12px; }
      .legend-grid-nodes { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .topology-summary-strip,
      .thought-summary-strip { grid-template-columns: 1fr; }
      .topology-rail,
      .thought-rail { flex-direction: column; }
      .topology-rail app-panel-card,
      .thought-rail app-panel-card { min-width: 0; }
    }
  `]
})
export class SwarmManagementPageComponent {
  readonly state = inject(StateService);
  readonly activeTab = signal('概览');
  readonly showOpsDropdown = signal(false);
  readonly tabs = ['概览', 'Agent 图', '执行轨迹', '思维图谱', 'Agents', '任务', '知识', '记忆', '设置'];
  readonly thoughtNodeLegendItems = THOUGHT_NODE_LEGEND_ENTRIES;
  readonly thoughtRelationLegendItems = THOUGHT_RELATION_LEGEND_ENTRIES;

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

  traceEventLabel(event: unknown): string {
    if (event && typeof event === 'object') {
      const record = event as Record<string, unknown>;
      const label = record['type'] ?? record['event'] ?? record['kind'];
      if (typeof label === 'string' && label.trim()) {
        return label;
      }
    }
    return 'event';
  }

}
