import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StateService, MemoryItem } from '../services/state.service';

@Component({
  selector: 'app-memory-page',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="page">
      <!-- Header -->
      <div class="section-header">
        <div>
          <h1>记忆系统</h1>
          <p class="subtitle">Agent 记忆检索、管理与持久化</p>
        </div>
        <div class="header-actions">
          <button class="btn btn-primary" (click)="state.refreshAll()" [disabled]="state.loading()">
            {{ state.loading() ? '刷新中...' : '刷新记忆' }}
          </button>
        </div>
      </div>

      <!-- Stat Cards -->
      <div class="stat-cards-row">
        <div class="stat-card">
          <div class="stat-label">总记忆数</div>
          <div class="stat-value">{{ memories().length }}</div>
          <div class="stat-sub">已存储</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">活跃记忆</div>
          <div class="stat-value accent-purple">{{ state.memoryStats().active }}</div>
          <div class="stat-sub">近 24h 更新</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">平均重要性</div>
          <div class="stat-value">{{ avgImportance() }}</div>
          <div class="stat-sub">0-100 评分</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">记忆类型分布</div>
          <div class="type-bars">
            @for (t of typeDistribution(); track t.type) {
              <div class="type-bar-item">
                <div class="type-bar-track">
                  <div class="type-bar-fill" [style.width.%]="t.pct" [style.background]="t.color"></div>
                </div>
                <div class="type-bar-label">{{ t.label }} {{ t.count }}</div>
              </div>
            }
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">情感得分</div>
          <div class="stat-value" [class]="sentimentClass()">{{ avgSentiment() }}</div>
          <div class="stat-sub">-1 ~ +1 均值</div>
        </div>
      </div>

      <!-- Two Column Layout -->
      <div class="two-column-layout">
        <!-- Left: Memory List -->
        <div class="column-left">
          <div class="panel-card">
            <div class="panel-header">
              <h3>记忆列表</h3>
              <span class="badge">{{ filteredMemories().length }}</span>
            </div>
            <div class="list-filters">
              <input
                type="text"
                class="filter-input search"
                placeholder="搜索记忆..."
                [value]="searchQuery()"
                (input)="searchQuery.set($any($event).target.value)"
              />
              <select class="filter-select" [value]="filterType()" (change)="filterType.set($any($event).target.value)">
                <option value="">全部类型</option>
                <option value="episodic">情景</option>
                <option value="semantic">语义</option>
                <option value="procedural">程序</option>
                <option value="working">工作</option>
              </select>
            </div>
            <div class="memory-list">
              @for (mem of filteredMemories(); track mem.id) {
                <div
                  class="memory-item"
                  [class.active]="selectedMemory()?.id === mem.id"
                  (click)="selectMemory(mem)"
                >
                  <div class="memory-summary">{{ mem.summary }}</div>
                  <div class="memory-meta">
                    <span class="memory-time">{{ mem.timestamp }}</span>
                    <span class="mini-badge" [class]="'type-' + mem.type">{{ typeLabel(mem.type) }}</span>
                  </div>
                  <div class="importance-bar">
                    <div class="importance-track">
                      <div class="importance-fill" [style.width.%]="mem.importance" [style.background]="importanceColor(mem.importance)"></div>
                    </div>
                    <span class="importance-value">{{ mem.importance }}</span>
                  </div>
                </div>
              } @empty {
                <div class="empty-state">暂无匹配记忆</div>
              }
            </div>
          </div>
        </div>

        <!-- Right: Memory Detail -->
        <div class="column-right">
          <div class="panel-card detail-card">
            @if (selectedMemory(); as mem) {
              <div class="detail-header">
                <h3>{{ mem.summary }}</h3>
                <div class="detail-id">{{ mem.id }}</div>
              </div>
              <div class="detail-body">
                <div class="detail-content">{{ mem.content }}</div>

                <div class="detail-section">
                  <h4>元数据</h4>
                  <div class="meta-grid">
                    <div class="meta-item">
                      <span class="meta-key">时间</span>
                      <span class="meta-val">{{ mem.timestamp }}</span>
                    </div>
                    <div class="meta-item">
                      <span class="meta-key">类型</span>
                      <span class="mini-badge" [class]="'type-' + mem.type">{{ typeLabel(mem.type) }}</span>
                    </div>
                    <div class="meta-item">
                      <span class="meta-key">来源</span>
                      <span class="meta-val">{{ mem.source }}</span>
                    </div>
                    <div class="meta-item">
                      <span class="meta-key">情感</span>
                      <span class="meta-val" [class]="sentimentClassFor(mem.sentiment)">{{ mem.sentiment > 0 ? '+' : '' }}{{ mem.sentiment }}</span>
                    </div>
                    <div class="meta-item">
                      <span class="meta-key">重要性</span>
                      <span class="meta-val">{{ mem.importance }}</span>
                    </div>
                    <div class="meta-item">
                      <span class="meta-key">关联</span>
                      <span class="meta-val">{{ mem.relatedIds.length }} 条</span>
                    </div>
                  </div>
                </div>

                <div class="detail-section">
                  <h4>关联记忆</h4>
                  @if (relatedMemories().length) {
                    <div class="related-list">
                      @for (rel of relatedMemories(); track rel.id) {
                        <div class="related-item" (click)="selectMemory(rel)">
                          <div class="related-summary">{{ rel.summary }}</div>
                          <div class="related-meta">
                            <span class="mini-badge" [class]="'type-' + rel.type">{{ typeLabel(rel.type) }}</span>
                            <span class="related-importance">重要性 {{ rel.importance }}</span>
                          </div>
                        </div>
                      }
                    </div>
                  } @else {
                    <div class="empty-state">无关联记忆</div>
                  }
                </div>
              </div>
            } @else {
              <div class="detail-placeholder">
                <div class="empty-state">选择左侧记忆查看详情</div>
              </div>
            }
          </div>
        </div>
      </div>

      <!-- System Memory Panel -->
      <div class="panel-card system-memory">
        <div class="panel-header">
          <h3>System Memory</h3>
          <span class="badge">{{ state.streamState() }}</span>
        </div>
        <div class="system-body">
          <div class="info-grid">
            <div class="info-item">
              <span class="info-key">API Base URL</span>
              <span class="info-val mono">{{ state.apiBaseUrl() }}</span>
            </div>
            <div class="info-item">
              <span class="info-key">Health</span>
              <span class="info-val" [class.success]="state.health()?.status === 'ok'">{{ state.health()?.status || 'unknown' }}</span>
            </div>
            <div class="info-item">
              <span class="info-key">Ready</span>
              <span class="info-val">{{ state.ready() ? 'Yes' : 'No' }}</span>
            </div>
            <div class="info-item">
              <span class="info-key">Selected Swarm</span>
              <span class="info-val mono">{{ state.selectedSwarmName() || 'None' }}</span>
            </div>
            <div class="info-item">
              <span class="info-key">Active Run</span>
              <span class="info-val mono">{{ state.activeRun()?.run_id || 'None' }}</span>
            </div>
            <div class="info-item">
              <span class="info-key">Live Events</span>
              <span class="info-val">{{ (state.liveEvents() || []).length }}</span>
            </div>
          </div>
        </div>
      </div>
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
    .stat-value.error { color: #EF4444; }
    .stat-sub {
      font-size: 12px;
      color: #64748b;
    }
    .type-bars {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-top: 4px;
    }
    .type-bar-item {
      display: flex;
      flex-direction: column;
      gap: 3px;
    }
    .type-bar-track {
      height: 6px;
      background: rgba(148,163,184,0.08);
      border-radius: 3px;
      overflow: hidden;
    }
    .type-bar-fill {
      height: 100%;
      border-radius: 3px;
      transition: width 0.3s ease;
    }
    .type-bar-label {
      font-size: 10px;
      color: #64748b;
    }
    .two-column-layout {
      display: grid;
      grid-template-columns: 380px 1fr;
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
    .badge {
      background: rgba(139,92,246,0.15);
      color: #8B5CF6;
      font-size: 12px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 12px;
    }
    .list-filters {
      display: flex;
      gap: 8px;
      padding: 12px 16px;
      border-bottom: 1px solid rgba(148,163,184,0.06);
    }
    .filter-input, .filter-select {
      background: #0B0F19;
      border: 1px solid rgba(148,163,184,0.12);
      border-radius: 8px;
      padding: 7px 10px;
      color: #F1F5F9;
      font-size: 13px;
      outline: none;
      font-family: 'Noto Sans SC', sans-serif;
    }
    .filter-input:focus, .filter-select:focus {
      border-color: #8B5CF6;
    }
    .filter-input.search {
      flex: 1;
      min-width: 0;
    }
    .filter-select {
      min-width: 100px;
      cursor: pointer;
    }
    .memory-list {
      max-height: 560px;
      overflow-y: auto;
    }
    .memory-item {
      padding: 14px 16px;
      border-bottom: 1px solid rgba(148,163,184,0.05);
      cursor: pointer;
      transition: background 0.15s;
    }
    .memory-item:hover {
      background: rgba(148,163,184,0.04);
    }
    .memory-item.active {
      background: rgba(139,92,246,0.08);
      border-left: 3px solid #8B5CF6;
      padding-left: 13px;
    }
    .memory-summary {
      font-size: 13px;
      font-weight: 500;
      color: #F1F5F9;
      margin-bottom: 6px;
      line-height: 1.4;
    }
    .memory-meta {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
    }
    .memory-time {
      font-size: 11px;
      color: #64748b;
      font-family: 'JetBrains Mono', monospace;
    }
    .mini-badge {
      font-size: 10px;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 10px;
      text-transform: uppercase;
    }
    .type-semantic { background: rgba(59,130,246,0.12); color: #60a5fa; }
    .type-episodic { background: rgba(139,92,246,0.12); color: #a78bfa; }
    .type-procedural { background: rgba(16,185,129,0.12); color: #10B981; }
    .type-working { background: rgba(245,158,11,0.12); color: #F59E0B; }
    .importance-bar {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .importance-track {
      flex: 1;
      height: 4px;
      background: rgba(148,163,184,0.08);
      border-radius: 2px;
      overflow: hidden;
    }
    .importance-fill {
      height: 100%;
      border-radius: 2px;
      transition: width 0.3s ease;
    }
    .importance-value {
      font-size: 11px;
      color: #64748b;
      font-family: 'JetBrains Mono', monospace;
      min-width: 22px;
      text-align: right;
    }
    .detail-card {
      min-height: 480px;
      display: flex;
      flex-direction: column;
    }
    .detail-placeholder {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .detail-header {
      padding: 20px;
      border-bottom: 1px solid rgba(148,163,184,0.08);
    }
    .detail-header h3 {
      margin: 0 0 6px;
      font-size: 16px;
      font-weight: 600;
      color: #F1F5F9;
      line-height: 1.4;
    }
    .detail-id {
      font-size: 11px;
      color: #64748b;
      font-family: 'JetBrains Mono', monospace;
    }
    .detail-body {
      padding: 20px;
      flex: 1;
      overflow-y: auto;
    }
    .detail-content {
      font-size: 14px;
      color: #cbd5e1;
      line-height: 1.7;
      margin-bottom: 24px;
      background: #0B0F19;
      border-radius: 10px;
      padding: 16px;
    }
    .detail-section {
      margin-bottom: 24px;
    }
    .detail-section h4 {
      margin: 0 0 12px;
      font-size: 12px;
      font-weight: 600;
      color: #94A3B8;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .meta-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }
    .meta-item {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 10px 12px;
      background: #0B0F19;
      border-radius: 8px;
    }
    .meta-key {
      font-size: 11px;
      color: #94A3B8;
    }
    .meta-val {
      font-size: 13px;
      color: #F1F5F9;
      font-weight: 500;
    }
    .meta-val.success { color: #10B981; }
    .meta-val.error { color: #EF4444; }
    .meta-val.amber { color: #F59E0B; }
    .related-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .related-item {
      padding: 10px 12px;
      background: #0B0F19;
      border-radius: 8px;
      cursor: pointer;
      transition: background 0.15s;
    }
    .related-item:hover {
      background: rgba(148,163,184,0.06);
    }
    .related-summary {
      font-size: 13px;
      color: #F1F5F9;
      font-weight: 500;
      margin-bottom: 4px;
    }
    .related-meta {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .related-importance {
      font-size: 11px;
      color: #64748b;
      font-family: 'JetBrains Mono', monospace;
    }
    .system-memory {
      margin-bottom: 24px;
    }
    .system-body {
      padding: 16px 20px;
    }
    .info-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
    }
    .info-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 12px;
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
    }
    .info-val.success { color: #10B981; }
    .info-val.mono {
      font-family: 'JetBrains Mono', monospace;
    }
    .empty-state {
      padding: 24px;
      text-align: center;
      color: #64748b;
      font-size: 13px;
    }
    @media (max-width: 1200px) {
      .stat-cards-row { grid-template-columns: repeat(3, 1fr); }
      .two-column-layout { grid-template-columns: 1fr; }
      .meta-grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 768px) {
      .stat-cards-row { grid-template-columns: repeat(2, 1fr); }
      .info-grid { grid-template-columns: 1fr; }
      .meta-grid { grid-template-columns: 1fr; }
      .section-header { flex-direction: column; align-items: flex-start; gap: 12px; }
    }
  `]
})
export class MemoryPageComponent {
  readonly state = inject(StateService);

  readonly selectedMemory = signal<MemoryItem | null>(null);
  readonly searchQuery = signal('');
  readonly filterType = signal('');
  readonly memories = computed(() => this.state.derivedMemories());
  readonly avgImportance = computed(() => {
    if (!this.memories().length) return '0';
    const avg = this.memories().reduce((s, m) => s + m.importance, 0) / this.memories().length;
    return Math.round(avg).toString();
  });
  readonly avgSentiment = computed(() => {
    if (!this.memories().length) return '0.00';
    const avg = this.memories().reduce((s, m) => s + m.sentiment, 0) / this.memories().length;
    return (avg > 0 ? '+' : '') + avg.toFixed(2);
  });
  readonly sentimentClass = computed(() => {
    const v = this.memories().reduce((s, m) => s + m.sentiment, 0) / (this.memories().length || 1);
    if (v >= 0.3) return 'success';
    if (v <= -0.3) return 'error';
    return 'amber';
  });

  readonly typeDistribution = computed(() => {
    const counts: Record<string, number> = {};
    this.memories().forEach(m => { counts[m.type] = (counts[m.type] || 0) + 1; });
    const total = this.memories().length || 1;
    const colors: Record<string, string> = {
      episodic: '#a78bfa',
      semantic: '#60a5fa',
      procedural: '#10B981',
      working: '#F59E0B',
    };
    const labels: Record<string, string> = {
      episodic: '情景',
      semantic: '语义',
      procedural: '程序',
      working: '工作',
    };
    return Object.entries(counts).map(([type, count]) => ({
      type,
      count,
      pct: Math.round((count / total) * 100),
      color: colors[type] ?? '#94A3B8',
      label: labels[type] ?? type,
    }));
  });

  readonly filteredMemories = computed(() => {
    let list = [...this.memories()];
    const q = this.searchQuery().trim().toLowerCase();
    if (q) list = list.filter(m => m.summary.toLowerCase().includes(q) || m.content.toLowerCase().includes(q));
    if (this.filterType()) list = list.filter(m => m.type === this.filterType());
    return list;
  });

  readonly relatedMemories = computed(() => {
    const current = this.selectedMemory();
    if (!current) return [];
    return this.memories().filter(m => current.relatedIds.includes(m.id));
  });

  selectMemory(mem: MemoryItem): void {
    this.selectedMemory.set(mem);
  }

  importanceColor(value: number): string {
    if (value >= 80) return '#EF4444';
    if (value >= 60) return '#F59E0B';
    if (value >= 40) return '#8B5CF6';
    return '#10B981';
  }

  typeLabel(type: MemoryItem['type']): string {
    const map: Record<string, string> = { episodic: '情景', semantic: '语义', procedural: '程序', working: '工作' };
    return map[type.trim()] ?? type;
  }

  sentimentClassFor(v: number): string {
    if (v >= 0.3) return 'success';
    if (v <= -0.3) return 'error';
    return 'amber';
  }
}
