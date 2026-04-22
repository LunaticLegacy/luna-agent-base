import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StateService } from '../services/state.service';

interface KnowledgeEntry {
  id: string;
  title: string;
  type: 'document' | 'vector' | 'rule' | 'snippet';
  source: string;
  tags: string[];
  status: 'active' | 'draft' | 'archived';
  citations: number;
  createdAt: string;
  content: string;
  meta: {
    author: string;
    version: string;
    updatedAt: string;
    size: string;
  };
  related: string[];
}

const MOCK_ENTRIES: KnowledgeEntry[] = [
  {
    id: 'kb-001',
    title: 'Swarm 编排最佳实践',
    type: 'document',
    source: '官方文档',
    tags: ['swarm', 'orchestration', 'guide'],
    status: 'active',
    citations: 42,
    createdAt: '2026-04-20',
    content: '本指南涵盖了多智能体系统的核心编排模式，包括层级控制、协商机制、投票决策与动态任务分配。',
    meta: { author: 'CoreTeam', version: 'v2.1', updatedAt: '2026-04-21', size: '24 KB' },
    related: ['kb-003', 'kb-005'],
  },
  {
    id: 'kb-002',
    title: 'PlannerAgent 行为向量',
    type: 'vector',
    source: '运行时采集',
    tags: ['agent', 'planner', 'embedding'],
    status: 'active',
    citations: 128,
    createdAt: '2026-04-18',
    content: '768 维向量表示，捕获 PlannerAgent 在任务分解场景中的决策边界与偏好分布。',
    meta: { author: 'System', version: 'v1', updatedAt: '2026-04-22', size: '3.2 MB' },
    related: ['kb-001'],
  },
  {
    id: 'kb-003',
    title: 'API 错误码对照表',
    type: 'rule',
    source: '手动录入',
    tags: ['api', 'reference', 'error-handling'],
    status: 'active',
    citations: 15,
    createdAt: '2026-04-15',
    content: '涵盖 HTTP 400/401/403/404/422/500/503 等状态码的标准化处理建议与重试策略。',
    meta: { author: 'DevOps', version: 'v1.3', updatedAt: '2026-04-19', size: '8 KB' },
    related: ['kb-001'],
  },
  {
    id: 'kb-004',
    title: '待审：新图遍历算法草稿',
    type: 'document',
    source: '社区贡献',
    tags: ['graph', 'algorithm', 'draft'],
    status: 'draft',
    citations: 0,
    createdAt: '2026-04-21',
    content: '基于 DFS 与 BFS 混合策略的图遍历优化方案，尚待评审与基准测试验证。',
    meta: { author: 'Contributor-A', version: 'v0.2', updatedAt: '2026-04-21', size: '12 KB' },
    related: [],
  },
  {
    id: 'kb-005',
    title: 'Prompt 模板：总结生成',
    type: 'snippet',
    source: '模板库',
    tags: ['prompt', 'nlp', 'template'],
    status: 'active',
    citations: 67,
    createdAt: '2026-04-10',
    content: '你是一个专业的内容摘要助手。请根据以下输入生成简洁、准确、保留关键信息的总结。',
    meta: { author: 'NLPTeam', version: 'v3.0', updatedAt: '2026-04-20', size: '1 KB' },
    related: ['kb-001'],
  },
  {
    id: 'kb-006',
    title: '旧版技能配置归档',
    type: 'document',
    source: '历史迁移',
    tags: ['legacy', 'archive'],
    status: 'archived',
    citations: 2,
    createdAt: '2025-12-01',
    content: '2025 Q4 技能配置快照，仅供历史追溯，不再用于生产环境。',
    meta: { author: 'System', version: 'v0.9', updatedAt: '2026-01-15', size: '56 KB' },
    related: [],
  },
];

@Component({
  selector: 'app-knowledge-page',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="page">
      <!-- Header -->
      <div class="section-header">
        <div>
          <h1>知识库</h1>
          <p class="subtitle">管理文档、向量、规则与代码片段</p>
        </div>
        <div class="header-actions">
          <button class="btn btn-primary" (click)="createEntry()">+ 新建条目</button>
        </div>
      </div>

      <!-- Stat Cards -->
      <div class="stat-cards-row">
        <div class="stat-card">
          <div class="stat-label">总条目</div>
          <div class="stat-value">{{ entries().length }}</div>
          <div class="stat-sub">知识库规模</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">文档数</div>
          <div class="stat-value">{{ docCount() }}</div>
          <div class="stat-sub">文本类</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">向量条目</div>
          <div class="stat-value accent-purple">{{ vectorCount() }}</div>
          <div class="stat-sub">Embedding</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">引用次数</div>
          <div class="stat-value success">{{ totalCitations() }}</div>
          <div class="stat-sub">被检索引用</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">最近更新</div>
          <div class="stat-value">{{ lastUpdated() }}</div>
          <div class="stat-sub">活跃维护</div>
        </div>
      </div>

      <!-- Filter Bar -->
      <div class="filter-bar">
        <input
          type="text"
          class="filter-input search"
          placeholder="搜索标题、标签..."
          [value]="searchQuery()"
          (input)="searchQuery.set($any($event).target.value)"
        />
        <select class="filter-select" [value]="filterType()" (change)="filterType.set($any($event).target.value)">
          <option value="">全部类型</option>
          <option value="document">文档</option>
          <option value="vector">向量</option>
          <option value="rule">规则</option>
          <option value="snippet">片段</option>
        </select>
        <select class="filter-select" [value]="filterSource()" (change)="filterSource.set($any($event).target.value)">
          <option value="">全部来源</option>
          <option value="官方文档">官方文档</option>
          <option value="运行时采集">运行时采集</option>
          <option value="手动录入">手动录入</option>
          <option value="社区贡献">社区贡献</option>
          <option value="模板库">模板库</option>
        </select>
        <select class="filter-select" [value]="filterTag()" (change)="filterTag.set($any($event).target.value)">
          <option value="">全部标签</option>
          <option value="swarm">swarm</option>
          <option value="agent">agent</option>
          <option value="api">api</option>
          <option value="graph">graph</option>
          <option value="prompt">prompt</option>
        </select>
        <select class="filter-select" [value]="filterDateRange()" (change)="filterDateRange.set($any($event).target.value)">
          <option value="">全部时间</option>
          <option value="today">今天</option>
          <option value="week">本周</option>
          <option value="month">本月</option>
        </select>
      </div>

      <!-- Knowledge Table -->
      <div class="panel-card table-panel">
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>标题</th>
                <th>类型</th>
                <th>来源</th>
                <th>标签</th>
                <th>状态</th>
                <th>引用</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              @for (entry of filteredEntries(); track entry.id) {
                <tr (click)="selectEntry(entry)">
                  <td>
                    <div class="entry-title">{{ entry.title }}</div>
                    <div class="entry-id">{{ entry.id }}</div>
                  </td>
                  <td>
                    <span class="badge" [class]="'badge-type-' + entry.type">{{ typeLabel(entry.type) }}</span>
                  </td>
                  <td>{{ entry.source }}</td>
                  <td>
                    <div class="tag-list">
                      @for (tag of entry.tags; track tag) {
                        <span class="mini-tag">{{ tag }}</span>
                      }
                    </div>
                  </td>
                  <td>
                    <span class="badge" [class]="'badge-status-' + entry.status">{{ statusLabel(entry.status) }}</span>
                  </td>
                  <td>{{ entry.citations }}</td>
                  <td>{{ entry.createdAt }}</td>
                  <td>
                    <div class="row-actions">
                      <button class="icon-btn" title="查看" (click)="selectEntry(entry); $event.stopPropagation()">👁</button>
                      <button class="icon-btn" title="编辑" (click)="editEntry(entry); $event.stopPropagation()">✎</button>
                    </div>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="8" class="empty-cell">暂无匹配条目</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

      <!-- Graph Knowledge Section -->
      <div class="panel-card graph-section">
        <div class="panel-header">
          <h3>Graph 知识图谱</h3>
          <span class="badge">{{ state.selectedGraph() ? '已连接' : '未加载' }}</span>
        </div>
        <div class="graph-body">
          @if (state.selectedGraph()) {
            <div class="graph-stats">
              <div class="graph-stat">
                <div class="graph-stat-label">节点数</div>
                <div class="graph-stat-value">{{ state.selectedGraph()!.node_count }}</div>
              </div>
              <div class="graph-stat">
                <div class="graph-stat-label">边数</div>
                <div class="graph-stat-value">{{ state.selectedGraph()!.edge_count }}</div>
              </div>
              <div class="graph-stat">
                <div class="graph-stat-label">密度</div>
                <div class="graph-stat-value">{{ graphDensity() }}</div>
              </div>
              <div class="graph-stat">
                <div class="graph-stat-label">Swarm</div>
                <div class="graph-stat-value">{{ state.selectedSwarmName() ?? '-' }}</div>
              </div>
            </div>
            <div class="graph-hint">
              当前图快照来自 <code>{{ state.selectedSwarmName() ?? '未选择' }}</code>，包含 {{ state.selectedGraph()!.node_count }} 个节点与 {{ state.selectedGraph()!.edge_count }} 条边。
            </div>
          } @else {
            <div class="empty-state">尚未加载图数据，请在概览页选择 Swarm 以获取 Graph 快照。</div>
          }
        </div>
      </div>

      <!-- Right Drawer -->
      @if (selectedEntry()) {
        <div class="drawer-overlay" (click)="closeDrawer()"></div>
        <div class="drawer">
          <div class="drawer-header">
            <div>
              <h3>{{ selectedEntry()!.title }}</h3>
              <div class="drawer-sub">{{ selectedEntry()!.id }}</div>
            </div>
            <button class="icon-btn close" (click)="closeDrawer()">✕</button>
          </div>
          <div class="drawer-body">
            <!-- Preview -->
            <div class="drawer-section">
              <h4>内容预览</h4>
              <div class="preview-box">{{ selectedEntry()!.content }}</div>
            </div>
            <!-- Meta -->
            <div class="drawer-section">
              <h4>元信息</h4>
              <div class="info-list">
                <div class="info-row">
                  <span class="info-key">作者</span>
                  <span class="info-val">{{ selectedEntry()!.meta.author }}</span>
                </div>
                <div class="info-row">
                  <span class="info-key">版本</span>
                  <span class="info-val">{{ selectedEntry()!.meta.version }}</span>
                </div>
                <div class="info-row">
                  <span class="info-key">更新时间</span>
                  <span class="info-val">{{ selectedEntry()!.meta.updatedAt }}</span>
                </div>
                <div class="info-row">
                  <span class="info-key">大小</span>
                  <span class="info-val">{{ selectedEntry()!.meta.size }}</span>
                </div>
                <div class="info-row">
                  <span class="info-key">状态</span>
                  <span class="badge" [class]="'badge-status-' + selectedEntry()!.status">{{ statusLabel(selectedEntry()!.status) }}</span>
                </div>
                <div class="info-row">
                  <span class="info-key">引用</span>
                  <span class="info-val">{{ selectedEntry()!.citations }} 次</span>
                </div>
              </div>
            </div>
            <!-- Related -->
            <div class="drawer-section">
              <h4>相关条目</h4>
              @if (relatedEntries().length) {
                <div class="related-list">
                  @for (rel of relatedEntries(); track rel.id) {
                    <div class="related-item" (click)="selectEntry(rel)">
                      <div class="related-title">{{ rel.title }}</div>
                      <span class="badge" [class]="'badge-type-' + rel.type">{{ typeLabel(rel.type) }}</span>
                    </div>
                  }
                </div>
              } @else {
                <div class="empty-state">暂无相关条目</div>
              }
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
      margin-bottom: 24px;
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
    .entry-title {
      font-weight: 500;
      color: #F1F5F9;
    }
    .entry-id {
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
    .badge-type-document { background: rgba(59,130,246,0.12); color: #60a5fa; }
    .badge-type-vector { background: rgba(139,92,246,0.12); color: #a78bfa; }
    .badge-type-rule { background: rgba(245,158,11,0.12); color: #F59E0B; }
    .badge-type-snippet { background: rgba(16,185,129,0.12); color: #10B981; }
    .badge-status-active { background: rgba(16,185,129,0.12); color: #10B981; }
    .badge-status-draft { background: rgba(245,158,11,0.12); color: #F59E0B; }
    .badge-status-archived { background: rgba(148,163,184,0.12); color: #94A3B8; }
    .tag-list {
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
    }
    .mini-tag {
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 10px;
      background: rgba(139,92,246,0.1);
      color: #a78bfa;
    }
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
    .graph-section {
      margin-bottom: 24px;
    }
    .graph-section .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 20px;
      border-bottom: 1px solid rgba(148,163,184,0.08);
    }
    .graph-section .panel-header h3 {
      margin: 0;
      font-size: 16px;
      font-weight: 600;
      color: #f8fafc;
    }
    .graph-body {
      padding: 16px 20px;
    }
    .graph-stats {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 16px;
    }
    .graph-stat {
      background: #0B0F19;
      border-radius: 10px;
      padding: 14px;
      text-align: center;
    }
    .graph-stat-label {
      font-size: 11px;
      color: #94A3B8;
      margin-bottom: 6px;
    }
    .graph-stat-value {
      font-size: 18px;
      font-weight: 700;
      color: #F1F5F9;
      font-family: 'JetBrains Mono', monospace;
    }
    .graph-hint {
      font-size: 13px;
      color: #64748b;
      background: #0B0F19;
      padding: 10px 14px;
      border-radius: 8px;
    }
    .graph-hint code {
      color: #a78bfa;
      font-family: 'JetBrains Mono', monospace;
      background: rgba(139,92,246,0.1);
      padding: 1px 5px;
      border-radius: 4px;
      font-size: 12px;
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
    .preview-box {
      background: #0B0F19;
      border: 1px solid rgba(148,163,184,0.08);
      border-radius: 8px;
      padding: 14px;
      font-size: 13px;
      color: #cbd5e1;
      line-height: 1.6;
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
    .related-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .related-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 12px;
      background: #0B0F19;
      border-radius: 8px;
      cursor: pointer;
      transition: background 0.15s;
    }
    .related-item:hover {
      background: rgba(148,163,184,0.06);
    }
    .related-title {
      font-size: 13px;
      color: #F1F5F9;
      font-weight: 500;
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
      .graph-stats { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 768px) {
      .stat-cards-row { grid-template-columns: repeat(2, 1fr); }
      .filter-bar { flex-direction: column; }
      .filter-input.search { width: 100%; min-width: unset; }
      .drawer { width: 100vw; max-width: 100vw; }
      .graph-stats { grid-template-columns: repeat(2, 1fr); }
    }
  `]
})
export class KnowledgePageComponent {
  readonly state = inject(StateService);

  readonly entries = signal<KnowledgeEntry[]>(MOCK_ENTRIES);
  readonly selectedEntry = signal<KnowledgeEntry | null>(null);
  readonly searchQuery = signal('');
  readonly filterType = signal('');
  readonly filterSource = signal('');
  readonly filterTag = signal('');
  readonly filterDateRange = signal('');

  readonly docCount = computed(() => this.entries().filter(e => e.type === 'document').length);
  readonly vectorCount = computed(() => this.entries().filter(e => e.type === 'vector').length);
  readonly totalCitations = computed(() => this.entries().reduce((s, e) => s + e.citations, 0));
  readonly lastUpdated = computed(() => {
    const dates = this.entries().map(e => e.meta.updatedAt).sort();
    return dates[dates.length - 1] ?? '-';
  });

  readonly filteredEntries = computed(() => {
    let list = [...this.entries()];
    const q = this.searchQuery().trim().toLowerCase();
    if (q) list = list.filter(e => e.title.toLowerCase().includes(q) || e.tags.some(t => t.toLowerCase().includes(q)));
    if (this.filterType()) list = list.filter(e => e.type === this.filterType());
    if (this.filterSource()) list = list.filter(e => e.source === this.filterSource());
    if (this.filterTag()) list = list.filter(e => e.tags.includes(this.filterTag()));
    return list;
  });

  readonly relatedEntries = computed(() => {
    const current = this.selectedEntry();
    if (!current) return [];
    return this.entries().filter(e => current.related.includes(e.id));
  });

  readonly graphDensity = computed(() => {
    const g = this.state.selectedGraph();
    if (!g || g.node_count < 2) return '0.00';
    const max = g.node_count * (g.node_count - 1);
    return (g.edge_count / max).toFixed(3);
  });

  selectEntry(entry: KnowledgeEntry): void {
    this.selectedEntry.set(entry);
  }

  closeDrawer(): void {
    this.selectedEntry.set(null);
  }

  createEntry(): void {
    alert('新建条目功能待实现');
  }

  editEntry(entry: KnowledgeEntry): void {
    alert('编辑条目: ' + entry.id);
  }

  typeLabel(type: KnowledgeEntry['type']): string {
    const map: Record<string, string> = { document: '文档', vector: '向量', rule: '规则', snippet: '片段' };
    return map[type] ?? type;
  }

  statusLabel(status: KnowledgeEntry['status']): string {
    const map: Record<string, string> = { active: '活跃', draft: '草稿', archived: '归档' };
    return map[status] ?? status;
  }
}
