import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StateService } from '../services/state.service';
import { GraphViewerComponent } from '../graph-viewer.component';
import { MiniChartComponent } from '../components/mini-chart.component';

@Component({
  selector: 'app-overview-page',
  standalone: true,
  imports: [CommonModule, GraphViewerComponent, MiniChartComponent],
  template: `
    <div class="page">
      <!-- Section Header -->
      <div class="section-header">
        <div>
          <h1>系统概览</h1>
          <p class="subtitle">实时监控与系统状态仪表盘</p>
        </div>
        <div class="header-actions">
          <button class="btn btn-primary" (click)="state.refreshAll()" [disabled]="state.loading()">
            {{ state.loading() ? '刷新中...' : '刷新数据' }}
          </button>
        </div>
      </div>

      <!-- Stat Cards Row -->
      <div class="stat-cards-row">
        <div class="stat-card">
          <div class="stat-label">系统状态</div>
          <div class="stat-value" [class.success]="state.health()?.status === 'ok'" [class.error]="state.health()?.status !== 'ok'">
            {{ state.health()?.status === 'ok' ? '正常' : state.health()?.status || '未知' }}
          </div>
          <div class="stat-sub">{{ state.ready() ? '就绪' : '未就绪' }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">总Agents</div>
          <div class="stat-value">{{ state.totalAgents() ?? 0 }}</div>
          <div class="stat-sub">活跃运行中</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Swarm数量</div>
          <div class="stat-value">{{ (state.swarms() || []).length }}</div>
          <div class="stat-sub">已配置</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">当前任务</div>
          <div class="stat-value">{{ state.activeRun() ? '运行中' : '空闲' }}</div>
          <div class="stat-sub">{{ state.streamState() || '等待中' }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Graph状态</div>
          <div class="stat-value" [class.success]="!!state.resolvedGraph()">{{ state.resolvedGraph() ? '已加载' : '未加载' }}</div>
          <div class="stat-sub">{{ state.graphSummary() || '—' }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">事件流</div>
          <div class="stat-value">{{ (state.liveEvents() || []).length }}</div>
          <div class="stat-sub">实时事件</div>
        </div>
      </div>

      <!-- Two Column Layout -->
      <div class="two-column-layout">
        <!-- Left: Swarm Selection List -->
        <div class="column-left">
          <div class="panel-card">
            <div class="panel-header">
              <h3>Swarm 列表</h3>
              <span class="badge">{{ (state.swarms() || []).length }}</span>
            </div>
            <div class="swarm-list">
              @for (swarm of state.swarms(); track swarm) {
                <div
                  class="swarm-item"
                  [class.active]="swarm.swarm_name === state.selectedSwarmName()"
                  (click)="state.selectSwarm(swarm.swarm_name)"
                >
                  <div class="swarm-item-name">{{ swarm.swarm_name }}</div>
                  <div class="swarm-item-status">
                    <span class="dot" [class.online]="swarm.swarm_name === state.selectedSwarmName()"></span>
                    {{ swarm.swarm_name === state.selectedSwarmName() ? '活跃' : '待机' }}
                  </div>
                </div>
              } @empty {
                <div class="empty-state">暂无 Swarm</div>
              }
            </div>
          </div>
        </div>

        <!-- Right: Swarm Detail -->
        <div class="column-right">
          <div class="panel-card">
            <div class="panel-header swarm-detail-header">
              <div>
                <h3>{{ state.selectedSwarmName() || '未选择 Swarm' }}</h3>
                <div class="swarm-meta">{{ state.swarmOverview() || '选择一个 Swarm 查看详情' }}</div>
              </div>
              <div class="run-actions">
                <button class="btn btn-secondary" (click)="state.startSwarmStructure()" [disabled]="state.loading() || !state.selectedSwarm()">
                  启动结构
                </button>
                <details #detailRunMenu class="run-menu">
                  <summary
                    class="btn btn-primary run-menu-toggle"
                    [class.disabled]="state.loading() || !state.selectedSwarm()"
                    [attr.aria-disabled]="state.loading() || !state.selectedSwarm()"
                    title="更多启动方式"
                  >
                    更多
                  </summary>
                  <div class="run-menu-panel">
                    <button
                      type="button"
                      class="run-menu-item"
                      (click)="state.startSwarmBackground(); detailRunMenu.open = false"
                      [disabled]="state.loading() || !state.selectedSwarm()"
                    >
                      后台启动
                    </button>
                  </div>
                </details>
              </div>
            </div>

            <div class="topology-section">
              <h4>拓扑视图</h4>
              <div class="graph-container">
                @if (state.resolvedGraph()) {
                  <app-graph-viewer [graph]="state.resolvedGraph()"></app-graph-viewer>
                } @else {
                  <div class="empty-state">加载 Graph 中...</div>
                }
              </div>
            </div>

            <div class="live-activity">
              <h4>实时活动</h4>
              <div class="event-list">
                @for (event of state.liveEvents(); track $index) {
                  <div class="event-item">
                    <span class="event-time">{{ event.timestamp || 'now' }}</span>
                    <span class="event-type">{{ event.tone || 'INFO' }}</span>
                    <span class="event-msg">{{ event.title || event.meta || 'Event' }}</span>
                  </div>
                } @empty {
                  <div class="empty-state">暂无活动</div>
                }
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Execution Console -->
      <div class="panel-card execution-console">
        <div class="panel-header">
          <h3>执行控制台</h3>
          <div class="console-hints">{{ state.selectedRunHint() }} · {{ state.swarmExecutionTemplateLabel() }}</div>
        </div>
        <div class="console-body">
          <div class="console-section">
            <div class="console-section-header">
              <h4>Swarm 运行</h4>
              <span class="console-note">填写自然语言任务，前端会自动组装请求体</span>
            </div>
            <div class="console-row">
              <div class="console-field">
                <label>任务模板</label>
                <select class="console-select" [value]="state.swarmExecutionTemplate()" (change)="state.setSwarmExecutionTemplate($any($event).target.value)">
                  <option value="summary">系统概览</option>
                  <option value="analysis">状态分析</option>
                  <option value="debug">排障建议</option>
                  <option value="custom">自定义</option>
                </select>
              </div>
              <div class="console-field">
                <label>轮次</label>
                <input
                  type="number"
                  class="console-input"
                  [value]="state.swarmRounds()"
                  (input)="state.setSwarmRounds($any($event).target.value)"
                  min="0"
                />
              </div>
              <div class="console-field">
                <label>输出风格</label>
                <select class="console-select" [value]="state.swarmExecutionOutputStyle()" (change)="state.setSwarmExecutionOutputStyle($any($event).target.value)">
                  <option value="markdown">Markdown</option>
                  <option value="bullet">要点列表</option>
                  <option value="brief">简短回答</option>
                </select>
              </div>
              <label class="console-toggle">
                <input type="checkbox" [checked]="state.metaMode()" (change)="state.setMetaMode($any($event).target.checked)" />
                <span>Meta 模式</span>
              </label>
            </div>
            <div class="console-field">
              <label>执行目标</label>
              <textarea
                class="console-textarea"
                rows="4"
                [value]="state.swarmExecutionPrompt()"
                (input)="state.setSwarmExecutionPrompt($any($event).target.value)"
                placeholder="例如：总结系统当前可用的 swarm 与 graph 状态。"
              ></textarea>
            </div>
            <div class="console-field">
              <label>补充上下文</label>
              <textarea
                class="console-textarea"
                rows="3"
                [value]="state.swarmExecutionContext()"
                (input)="state.setSwarmExecutionContext($any($event).target.value)"
                placeholder="填写额外背景、约束或输出要求..."
              ></textarea>
            </div>
            <div class="console-actions">
              <button class="btn btn-primary" (click)="state.startSwarmStructure()" [disabled]="state.loading() || !state.selectedSwarm()">
                启动结构
              </button>
              <details #consoleRunMenu class="run-menu">
                <summary
                  class="btn btn-secondary run-menu-toggle"
                  [class.disabled]="state.loading() || !state.selectedSwarm()"
                  [attr.aria-disabled]="state.loading() || !state.selectedSwarm()"
                  title="更多启动方式"
                >
                  更多
                </summary>
                <div class="run-menu-panel">
                  <button
                    type="button"
                    class="run-menu-item"
                    (click)="state.startSwarmBackground(); consoleRunMenu.open = false"
                    [disabled]="state.loading() || !state.selectedSwarm()"
                  >
                    后台启动
                  </button>
                </div>
              </details>
            </div>
          </div>

          <div class="console-divider"></div>

          <div class="console-section">
            <div class="console-section-header">
              <h4>Agent 调试</h4>
              <span class="console-note">直接驱动单个 Agent 执行一轮</span>
            </div>
            <div class="console-row">
              <div class="console-field">
                <label>轮次</label>
                <input
                  type="number"
                  class="console-input"
                  [value]="state.agentRounds()"
                  (input)="state.setAgentRounds($any($event).target.value)"
                  min="1"
                />
              </div>
              <div class="console-field">
                <label>选择 Agent</label>
                <select class="console-select" [value]="state.selectedAgentId()" (change)="state.setSelectedAgentId($any($event).target.value)">
                  <option value="">自动选择</option>
                  @for (choice of state.agentChoices(); track choice) {
                    <option [value]="choice">{{ choice }}</option>
                  }
                </select>
              </div>
              <div class="console-field flex-grow">
                <label>消息</label>
                <input
                  type="text"
                  class="console-input"
                  [value]="state.agentMessage()"
                  (input)="state.setAgentMessage($any($event).target.value)"
                  placeholder="输入消息..."
                />
              </div>
            </div>
            <div class="console-actions">
              <button class="btn btn-primary" (click)="state.runAgentRound()" [disabled]="state.loading()">
                Agent 调试
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Response Chronicle -->
      @if (state.responseFeed() && (state.responseFeed() || []).length > 0) {
        <div class="panel-card response-chronicle">
          <div class="panel-header">
            <h3>响应记录</h3>
          </div>
          <div class="response-list">
            @for (resp of state.responseFeed(); track $index) {
              <div class="response-item">
                <div class="response-header">
                  <span class="response-agent">{{ resp.meta || 'System' }}</span>
                  <span class="response-time">{{ resp.timestamp || 'now' }}</span>
                </div>
                <div class="response-content">{{ resp.title || resp.meta || 'Response' }}</div>
              </div>
            }
          </div>
        </div>
      }

      <!-- Bottom Metrics Grid -->
      <div class="bottom-grid">
        @for (card of state.metricCards(); track card.label) {
          <div class="sparkline-card">
            <div class="sparkline-label">{{ card.label }}</div>
            <div class="sparkline-head">
              <div class="sparkline-value" [class.success]="card.tone === 'success'" [class.warning]="card.tone === 'warning'" [class.error]="card.tone === 'error'" [class.info]="card.tone === 'info'">
                {{ card.value }}
              </div>
              <div class="sparkline-delta" [class.up]="card.direction === 'up'" [class.down]="card.direction === 'down'">
                {{ card.direction === 'neutral' ? '稳定' : card.delta }}
              </div>
            </div>
            <div class="sparkline-chart">
              <app-mini-chart [data]="card.data" [color]="card.color"></app-mini-chart>
            </div>
          </div>
        }
      </div>

      <!-- System Info Panel -->
      <div class="panel-card system-info">
        <div class="panel-header">
          <h3>系统信息</h3>
        </div>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">API Base URL</span>
            <span class="info-value">{{ state.apiBaseUrl() }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Health</span>
            <span class="info-value" [class.success]="state.health()?.status === 'ok'">{{ state.health()?.status || 'unknown' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Ready</span>
            <span class="info-value">{{ state.ready() ? 'Yes' : 'No' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Selected Swarm</span>
            <span class="info-value">{{ state.selectedSwarmName() || 'None' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Stream State</span>
            <span class="info-value">{{ state.streamState() || 'idle' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Error Detail</span>
            <span class="info-value error-click" (click)="state.copyErrorToClipboard()">{{ state.error() ? 'Click to copy' : 'None' }}</span>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .page {
      padding: 24px;
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
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
      color: #f8fafc;
    }
    .subtitle {
      margin: 4px 0 0;
      color: #94a3b8;
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
      background: #1e293b;
      color: #e2e8f0;
      font-size: 14px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn:hover:not(:disabled) {
      background: #334155;
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
    .btn-secondary {
      background: #1e293b;
      border-color: rgba(148,163,184,0.2);
    }
    .stat-cards-row {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
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
    .stat-value.error { color: #ef4444; }
    .stat-sub {
      font-size: 12px;
      color: #64748b;
    }
    .two-column-layout {
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 16px;
      margin-bottom: 24px;
    }
    .column-left, .column-right {
      display: flex;
      flex-direction: column;
      gap: 16px;
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
      padding: 16px 20px;
      border-bottom: 1px solid rgba(148,163,184,0.08);
    }
    .panel-header h3 {
      margin: 0;
      font-size: 16px;
      font-weight: 600;
      color: #f8fafc;
    }
    .panel-header h4 {
      margin: 0 0 12px;
      font-size: 14px;
      font-weight: 600;
      color: #cbd5e1;
    }
    .badge {
      background: rgba(139,92,246,0.15);
      color: #8B5CF6;
      font-size: 12px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 12px;
    }
    .swarm-list {
      max-height: 400px;
      overflow-y: auto;
    }
    .swarm-item {
      padding: 12px 20px;
      cursor: pointer;
      border-bottom: 1px solid rgba(148,163,184,0.05);
      transition: background 0.2s;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .swarm-item:hover {
      background: rgba(148,163,184,0.05);
    }
    .swarm-item.active {
      background: rgba(139,92,246,0.1);
      border-left: 3px solid #8B5CF6;
    }
    .swarm-item-name {
      font-size: 14px;
      font-weight: 500;
      color: #e2e8f0;
    }
    .swarm-item-status {
      font-size: 12px;
      color: #64748b;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #64748b;
    }
    .dot.online {
      background: #10B981;
      box-shadow: 0 0 6px rgba(16,185,129,0.4);
    }
    .swarm-detail-header {
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 12px;
    }
    .swarm-meta {
      font-size: 13px;
      color: #64748b;
      margin-top: 4px;
    }
    .run-actions {
      display: flex;
      gap: 8px;
    }
    .run-menu {
      position: relative;
    }
    .run-menu > summary {
      list-style: none;
    }
    .run-menu > summary::-webkit-details-marker {
      display: none;
    }
    .run-menu-toggle {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 72px;
    }
    .run-menu-toggle.disabled {
      pointer-events: none;
      opacity: 0.5;
    }
    .run-menu-panel {
      position: absolute;
      top: calc(100% + 8px);
      right: 0;
      min-width: 132px;
      padding: 6px;
      background: #0f1525;
      border: 1px solid rgba(148,163,184,0.12);
      border-radius: 10px;
      box-shadow: 0 16px 40px rgba(0,0,0,0.28);
      z-index: 20;
    }
    .run-menu-item {
      width: 100%;
      border: none;
      background: transparent;
      color: #e2e8f0;
      font-size: 13px;
      text-align: left;
      padding: 8px 10px;
      border-radius: 8px;
      cursor: pointer;
    }
    .run-menu-item:hover:not(:disabled) {
      background: rgba(148,163,184,0.1);
    }
    .run-menu-item:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .topology-section {
      padding: 16px 20px;
      border-bottom: 1px solid rgba(148,163,184,0.08);
    }
    .graph-container {
      background: #0f1525;
      border-radius: 8px;
      min-height: 200px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .graph-container app-graph-viewer {
      width: 100%;
      height: 100%;
      display: block;
      flex: 1 1 auto;
      min-width: 0;
      min-height: 0;
    }
    .live-activity {
      padding: 16px 20px;
    }
    .event-list {
      max-height: 200px;
      overflow-y: auto;
    }
    .event-item {
      display: flex;
      gap: 12px;
      padding: 8px 0;
      font-size: 13px;
      border-bottom: 1px solid rgba(148,163,184,0.05);
    }
    .event-time {
      color: #64748b;
      font-family: monospace;
      min-width: 60px;
    }
    .event-type {
      background: rgba(139,92,246,0.12);
      color: #a78bfa;
      padding: 1px 6px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      min-width: 50px;
      text-align: center;
    }
    .event-msg {
      color: #cbd5e1;
      flex: 1;
    }
    .empty-state {
      padding: 24px;
      text-align: center;
      color: #64748b;
      font-size: 13px;
    }
    .execution-console {
      margin-bottom: 24px;
    }
    .console-hints {
      font-size: 12px;
      color: #64748b;
    }
    .console-body {
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .console-section {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .console-section-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }
    .console-section-header h4 {
      margin: 0;
      font-size: 14px;
      color: #e2e8f0;
    }
    .console-note {
      font-size: 12px;
      color: #64748b;
    }
    .console-row {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: flex-end;
    }
    .console-field {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .console-field label {
      font-size: 12px;
      color: #94a3b8;
      font-weight: 500;
    }
    .console-textarea, .console-input, .console-select {
      background: #0f1525;
      border: 1px solid rgba(148,163,184,0.12);
      border-radius: 8px;
      padding: 8px 12px;
      color: #e2e8f0;
      font-size: 13px;
      outline: none;
    }
    .console-textarea:focus, .console-input:focus, .console-select:focus {
      border-color: #8B5CF6;
    }
    .console-textarea {
      width: 100%;
      resize: vertical;
      font-family: inherit;
    }
    .console-input {
      width: 120px;
    }
    .console-select {
      width: 160px;
      cursor: pointer;
    }
    .console-toggle {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding-bottom: 8px;
      font-size: 13px;
      color: #cbd5e1;
      user-select: none;
    }
    .console-toggle input {
      accent-color: #8B5CF6;
    }
    .console-divider {
      height: 1px;
      background: rgba(148,163,184,0.08);
      margin: 2px 0;
    }
    .flex-grow {
      flex: 1;
    }
    .flex-grow .console-input {
      width: 100%;
    }
    .console-actions {
      display: flex;
      gap: 8px;
      padding-top: 4px;
    }
    .response-chronicle {
      margin-bottom: 24px;
    }
    .response-list {
      max-height: 300px;
      overflow-y: auto;
      padding: 8px 20px;
    }
    .response-item {
      padding: 12px 0;
      border-bottom: 1px solid rgba(148,163,184,0.05);
    }
    .response-header {
      display: flex;
      justify-content: space-between;
      margin-bottom: 6px;
    }
    .response-agent {
      font-size: 13px;
      font-weight: 600;
      color: #8B5CF6;
    }
    .response-time {
      font-size: 12px;
      color: #64748b;
    }
    .response-content {
      font-size: 13px;
      color: #cbd5e1;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .bottom-grid {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }
    .sparkline-card {
      background: #131827;
      border: 1px solid rgba(148,163,184,0.08);
      border-radius: 12px;
      padding: 16px;
    }
    .sparkline-label {
      font-size: 12px;
      color: #94a3b8;
      margin-bottom: 8px;
    }
    .sparkline-value {
      font-size: 20px;
      font-weight: 700;
      color: #f8fafc;
      margin-bottom: 10px;
    }
    .sparkline-value.error { color: #ef4444; }
    .sparkline-value.warning { color: #f59e0b; }
    .sparkline-value.info { color: #60a5fa; }
    .sparkline-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
    }
    .sparkline-delta {
      font-size: 12px;
      font-weight: 600;
      color: #94a3b8;
      white-space: nowrap;
    }
    .sparkline-delta.up { color: #10B981; }
    .sparkline-delta.down { color: #ef4444; }
    .sparkline-chart {
      margin-top: 8px;
      min-height: 44px;
    }
    .system-info {
      margin-bottom: 24px;
    }
    .info-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      padding: 16px 20px;
    }
    .info-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 12px;
      background: #0f1525;
      border-radius: 8px;
    }
    .info-label {
      font-size: 12px;
      color: #94a3b8;
    }
    .info-value {
      font-size: 13px;
      color: #e2e8f0;
      font-weight: 500;
      font-family: monospace;
    }
    .info-value.success { color: #10B981; }
    .error-click {
      color: #ef4444;
      cursor: pointer;
      text-decoration: underline;
    }
    @media (max-width: 1200px) {
      .stat-cards-row { grid-template-columns: repeat(3, 1fr); }
      .bottom-grid { grid-template-columns: repeat(3, 1fr); }
      .two-column-layout { grid-template-columns: 1fr; }
    }
    @media (max-width: 768px) {
      .stat-cards-row { grid-template-columns: repeat(2, 1fr); }
      .bottom-grid { grid-template-columns: repeat(2, 1fr); }
      .info-grid { grid-template-columns: 1fr; }
      .section-header { flex-direction: column; align-items: flex-start; gap: 12px; }
    }
  `]
})
export class OverviewPageComponent {
  readonly state = inject(StateService);
  protected readonly Math = Math;
}
