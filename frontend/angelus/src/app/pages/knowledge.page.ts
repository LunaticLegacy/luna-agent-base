import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StateService, KnowledgeEntry } from '../services/state.service';
import { DrawerComponent, EmptyStateComponent, FilterBarComponent, ModalComponent, PageHeaderComponent, PanelCardComponent, StatCardGridComponent } from '../shared';

@Component({
  selector: 'app-knowledge-page',
  standalone: true,
  imports: [CommonModule, PageHeaderComponent, StatCardGridComponent, PanelCardComponent, FilterBarComponent, EmptyStateComponent, ModalComponent, DrawerComponent],
  template: `
    <div class="page">
      <!-- Header -->
      <app-page-header title="知识库" subtitle="管理文档、向量、规则与代码片段">
        <div actions>
          <button class="btn btn-primary" (click)="createEntry()">+ 新建条目</button>
        </div>
      </app-page-header>

      <!-- Stat Cards -->
      <app-stat-card-grid [cards]="[
        { label: '总条目', value: state.knowledgeStats().total, subtitle: '知识库规模' },
        { label: '文档数', value: state.knowledgeStats().documents, subtitle: '文本类' },
        { label: '向量条目', value: state.knowledgeStats().vectors, subtitle: 'Embedding', tone: 'purple' },
        { label: '引用次数', value: state.knowledgeStats().citations, subtitle: '被检索引用', tone: 'good' },
        { label: '最近更新', value: state.knowledgeStats().recentUpdates, subtitle: '活跃维护' }
      ]"></app-stat-card-grid>

      <!-- Filter Bar -->
      <app-filter-bar>
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
      </app-filter-bar>

      <!-- Knowledge Table -->
      <app-panel-card class="table-panel" [noPadding]="true">
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
                      <button class="icon-btn danger" title="删除" (click)="deleteEntry(entry); $event.stopPropagation()">🗑</button>
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
      </app-panel-card>

      <!-- Graph Knowledge Section -->
      <app-panel-card class="graph-section" title="Graph 知识图谱" [badge]="state.resolvedGraph() ? '已连接' : '未加载'">
        <div class="graph-body">
          @if (state.resolvedGraph()) {
            <div class="graph-stats">
              <div class="graph-stat">
                <div class="graph-stat-label">节点数</div>
                <div class="graph-stat-value">{{ state.resolvedGraph()!.node_count }}</div>
              </div>
              <div class="graph-stat">
                <div class="graph-stat-label">边数</div>
                <div class="graph-stat-value">{{ state.resolvedGraph()!.edge_count }}</div>
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
              当前图快照来自 <code>{{ state.selectedSwarmName() ?? '未选择' }}</code>，包含 {{ state.resolvedGraph()!.node_count }} 个节点与 {{ state.resolvedGraph()!.edge_count }} 条边。
            </div>
          } @else {
            <app-empty-state message="尚未加载图数据，请在概览页选择 Swarm 以获取 Graph 快照。"></app-empty-state>
          }
        </div>
      </app-panel-card>

      <!-- Editor Modal -->
      <app-modal [open]="editorOpen()" [title]="editorMode() === 'create' ? '新建条目' : '编辑条目'" [subtitle]="editorMode() === 'create' ? '创建新的知识记录' : (editorId() ?? '')" [hasFooter]="true" (close)="closeEditor()">
        <div class="editor-grid">
          <label class="field">
            <span>标题</span>
            <input class="input" [value]="editorTitle()" (input)="editorTitle.set($any($event).target.value)" />
          </label>
          <label class="field">
            <span>类型</span>
            <select class="input" [value]="editorType()" (change)="editorType.set($any($event).target.value)">
              <option value="document">文档</option>
              <option value="vector">向量</option>
              <option value="rule">规则</option>
              <option value="snippet">片段</option>
            </select>
          </label>
          <label class="field">
            <span>来源</span>
            <input class="input" [value]="editorSource()" (input)="editorSource.set($any($event).target.value)" />
          </label>
          <label class="field">
            <span>标签</span>
            <input class="input" [value]="editorTags()" (input)="editorTags.set($any($event).target.value)" placeholder="用逗号分隔" />
          </label>
          <label class="field">
            <span>状态</span>
            <select class="input" [value]="editorStatus()" (change)="editorStatus.set($any($event).target.value)">
              <option value="active">活跃</option>
              <option value="draft">草稿</option>
              <option value="archived">归档</option>
            </select>
          </label>
          <label class="field full">
            <span>内容</span>
            <textarea class="textarea" rows="10" [value]="editorContent()" (input)="editorContent.set($any($event).target.value)"></textarea>
          </label>
        </div>
        <div footer>
          <button class="btn btn-secondary" (click)="closeEditor()">取消</button>
          <button class="btn btn-primary" (click)="saveEntry()" [disabled]="state.loadingDetails()">{{ state.loadingDetails() ? '保存中...' : '保存' }}</button>
        </div>
      </app-modal>

      <!-- Right Drawer -->
      @if (selectedEntry()) {
        <app-drawer [open]="true" [title]="selectedEntry()!.title" [subtitle]="selectedEntry()!.id" (close)="closeDrawer()">
          <div class="drawer-section">
            <h4>内容预览</h4>
            <div class="preview-box">{{ selectedEntry()!.content }}</div>
          </div>
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
              <app-empty-state message="暂无相关条目"></app-empty-state>
            }
          </div>
        </app-drawer>
      }
    </div>
  `,
  styles: [`
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
      margin-bottom: 24px;
    }
    .table-scroll {
      overflow-x: auto;
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
                .icon-btn.danger {
      color: #FCA5A5;
    }
    .icon-btn.danger:hover {
      background: rgba(239,68,68,0.18);
      border-color: rgba(239,68,68,0.3);
      color: #FEE2E2;
    }
    .empty-cell {
      text-align: center;
      color: #64748b;
      padding: 32px;
    }
    .graph-section {
      margin-bottom: 24px;
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
    .editor-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .field {
      display: flex;
      flex-direction: column;
      gap: 8px;
      color: #CBD5E1;
      font-size: 13px;
    }
    .field.full {
      grid-column: 1 / -1;
    }
    .input, .textarea {
      width: 100%;
      border-radius: 10px;
      border: 1px solid rgba(148,163,184,0.16);
      background: #0B0F19;
      color: #F1F5F9;
      padding: 10px 12px;
      font: inherit;
      box-sizing: border-box;
    }
    .textarea {
      resize: vertical;
      min-height: 180px;
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
    @media (max-width: 1200px) {
      .graph-stats { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 768px) {
      .filter-input.search { width: 100%; min-width: unset; }
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
  readonly editorOpen = signal(false);
  readonly editorMode = signal<'create' | 'edit'>('create');
  readonly editorId = signal<string | null>(null);
  readonly editorTitle = signal('');
  readonly editorType = signal<KnowledgeEntry['type']>('document');
  readonly editorSource = signal('');
  readonly editorTags = signal('');
  readonly editorStatus = signal<KnowledgeEntry['status']>('draft');
  readonly editorContent = signal('');



  readonly filteredEntries = computed(() => {
    let list = [...this.state.derivedKnowledge()];
    const q = this.searchQuery().trim().toLowerCase();
    if (q) list = list.filter(e => e.title.toLowerCase().includes(q) || e.tags.some(t => t.toLowerCase().includes(q)));
    if (this.filterType()) list = list.filter(e => e.type === this.filterType());
    if (this.filterSource()) list = list.filter(e => e.source === this.filterSource());
    if (this.filterTag()) list = list.filter(e => e.tags.includes(this.filterTag()));
    if (this.filterDateRange()) {
      const now = Date.now();
      const windowMs = this.filterDateRange() === 'today'
        ? 24 * 60 * 60 * 1000
        : this.filterDateRange() === 'week'
          ? 7 * 24 * 60 * 60 * 1000
          : 30 * 24 * 60 * 60 * 1000;
      list = list.filter((entry) => {
        const raw = entry.meta.updatedAt || entry.createdAt;
        const parsed = Date.parse(raw);
        return Number.isFinite(parsed) && now - parsed <= windowMs;
      });
    }
    return list;
  });

  readonly relatedEntries = computed(() => {
    const current = this.selectedEntry();
    if (!current) return [];
    return this.state.derivedKnowledge().filter(e => current.related.includes(e.id));
  });

  readonly graphDensity = computed(() => {
    const g = this.state.resolvedGraph();
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
    this.editorMode.set('create');
    this.editorId.set(null);
    this.editorTitle.set('');
    this.editorType.set('document');
    this.editorSource.set('手动录入');
    this.editorTags.set('');
    this.editorStatus.set('draft');
    this.editorContent.set('');
    this.editorOpen.set(true);
  }

  editEntry(entry: KnowledgeEntry): void {
    this.editorMode.set('edit');
    this.editorId.set(entry.id);
    this.editorTitle.set(entry.title);
    this.editorType.set(entry.type);
    this.editorSource.set(entry.source);
    this.editorTags.set(entry.tags.join(', '));
    this.editorStatus.set(entry.status);
    this.editorContent.set(entry.content);
    this.editorOpen.set(true);
  }

  closeEditor(): void {
    this.editorOpen.set(false);
  }

  async saveEntry(): Promise<void> {
    const payload = {
      title: this.editorTitle().trim(),
      type: this.editorType(),
      source: this.editorSource().trim(),
      tags: this.editorTags().split(',').map((tag) => tag.trim()).filter(Boolean),
      status: this.editorStatus(),
      content: this.editorContent(),
    };
    if (!payload.title) return;
    const editorId = this.editorId();
    const saved = this.editorMode() === 'create'
      ? await this.state.createKnowledgeEntry(payload)
      : editorId
        ? await this.state.updateKnowledgeEntry(editorId, payload)
        : null;
    if (saved) {
      this.closeEditor();
      this.selectedEntry.set({
        id: saved.id,
        title: saved.title,
        type: saved.type as KnowledgeEntry['type'],
        source: saved.source,
        tags: [...saved.tags],
        status: saved.status as KnowledgeEntry['status'],
        citations: saved.citations,
        createdAt: saved.created_at,
        content: saved.content,
        meta: {
          author: saved.meta?.author ?? 'System',
          version: saved.meta?.version ?? '1.0',
          updatedAt: saved.meta?.updated_at ?? saved.created_at,
          size: saved.meta?.size ?? '-',
        },
        related: [...saved.related],
      });
    }
  }

  async deleteEntry(entry: KnowledgeEntry): Promise<void> {
    if (!window.confirm(`删除知识条目 "${entry.title}" 吗？`)) return;
    const ok = await this.state.deleteKnowledgeEntry(entry.id);
    if (ok && this.selectedEntry()?.id === entry.id) {
      this.closeDrawer();
    }
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
