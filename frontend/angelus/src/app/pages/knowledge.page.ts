import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StateService, KnowledgeEntry } from '../services/state.service';

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
          <div class="stat-value">{{ state.knowledgeStats().total }}</div>
          <div class="stat-sub">知识库规模</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">文档数</div>
          <div class="stat-value">{{ state.knowledgeStats().documents }}</div>
          <div class="stat-sub">文本类</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">向量条目</div>
          <div class="stat-value accent-purple">{{ state.knowledgeStats().vectors }}</div>
          <div class="stat-sub">Embedding</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">引用次数</div>
          <div class="stat-value success">{{ state.knowledgeStats().citations }}</div>
          <div class="stat-sub">被检索引用</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">最近更新</div>
          <div class="stat-value">—</div>
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

  readonly selectedEntry = signal<KnowledgeEntry | null>(null);
  readonly searchQuery = signal('');
  readonly filterType = signal('');
  readonly filterSource = signal('');
  readonly filterTag = signal('');
  readonly filterDateRange = signal('');



  readonly filteredEntries = computed(() => {
    let list = [...this.state.derivedKnowledge()];
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
    return this.state.derivedKnowledge().filter(e => current.related.includes(e.id));
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
