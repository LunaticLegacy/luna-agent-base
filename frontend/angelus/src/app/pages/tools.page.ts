import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StateService, ToolItem } from '../services/state.service';
import { StatusBadgeComponent } from '../components/status-badge.component';

@Component({
  selector: 'app-tools-page',
  standalone: true,
  imports: [CommonModule, StatusBadgeComponent],
  template: `
    <div class="page-header">
      <div>
        <h1 class="page-title">工具管理</h1>
        <p class="page-subtitle">管理系统工具、外部 API 和自定义技能</p>
      </div>
      <button class="btn btn-primary">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        注册新工具
      </button>
    </div>

    <div class="stat-grid">
      <div class="stat-card"><div class="stat-label">总工具数</div><div class="stat-value">{{ state.toolStats().total }}</div><div class="stat-sub">已注册</div></div>
      <div class="stat-card"><div class="stat-label">可用工具</div><div class="stat-value stat-green">{{ state.toolStats().available }}</div><div class="stat-sub">正常运行</div></div>
      <div class="stat-card"><div class="stat-label">API 工具</div><div class="stat-value stat-purple">{{ state.toolStats().api }}</div><div class="stat-sub">外部接口</div></div>
      <div class="stat-card"><div class="stat-label">本地技能</div><div class="stat-value stat-amber">{{ state.toolStats().local }}</div><div class="stat-sub">内置函数</div></div>
      <div class="stat-card"><div class="stat-label">今日调用</div><div class="stat-value">{{ state.toolStats().calls | number }}</div><div class="stat-sub">次执行</div></div>
    </div>

    <div class="card">
      <div class="card-header">
        <div class="tabs">
          <button class="tab active">全部工具</button>
          <button class="tab">API 工具</button>
          <button class="tab">本地技能</button>
          <button class="tab">已禁用</button>
        </div>
        <div class="toolbar">
          <input class="input search" placeholder="搜索工具名称..." />
          <select class="input"><option>所有类型</option><option>HTTP</option><option>Python</option><option>Shell</option></select>
          <select class="input"><option>所有状态</option><option>正常</option><option>异常</option></select>
        </div>
      </div>
      <table class="data-table">
        <thead><tr><th>工具名称</th><th>类型</th><th>状态</th><th>描述</th><th>调用次数</th><th>平均耗时</th><th>最后调用</th><th>操作</th></tr></thead>
        <tbody>
          @for (tool of state.derivedTools(); track tool.id) {
            <tr (click)="selectTool(tool)" [class.active]="selectedTool()?.id === tool.id">
              <td><div class="tool-name"><div class="tool-icon">{{ tool.icon }}</div><div><div class="name">{{ tool.name }}</div><div class="id">{{ tool.id }}</div></div></div></td>
              <td><span class="tag" [class.tag-purple]="tool.type==='API'" [class.tag-blue]="tool.type==='本地'">{{ tool.type }}</span></td>
              <td><app-status-badge [status]="tool.status" /></td>
              <td class="muted">{{ tool.desc }}</td>
              <td class="mono">{{ tool.calls | number }}</td>
              <td class="mono">{{ tool.avgMs }}ms</td>
              <td class="muted">{{ tool.lastCall }}</td>
              <td><button class="btn btn-sm">详情</button></td>
            </tr>
          }
        </tbody>
      </table>
    </div>

    @if (selectedTool()) {
      <div class="card">
        <div class="detail-header">
          <div class="detail-title">{{ selectedTool()!.name }}</div>
          <div class="detail-actions">
            <button class="btn btn-sm">测试调用</button>
            <button class="btn btn-sm">编辑</button>
            <button class="btn btn-sm btn-danger">禁用</button>
          </div>
        </div>
        <div class="detail-grid">
          <div class="detail-section">
            <h4>基本信息</h4>
            <div class="detail-row"><span>ID</span><code>{{ selectedTool()!.id }}</code></div>
            <div class="detail-row"><span>类型</span><span>{{ selectedTool()!.type }}</span></div>
            <div class="detail-row"><span>状态</span><app-status-badge [status]="selectedTool()!.status" /></div>
            <div class="detail-row"><span>创建时间</span><span>{{ selectedTool()!.created }}</span></div>
          </div>
          <div class="detail-section">
            <h4>调用统计</h4>
            <div class="detail-row"><span>总调用</span><span class="mono">{{ selectedTool()!.calls | number }}</span></div>
            <div class="detail-row"><span>成功率</span><span class="stat-green">{{ selectedTool()!.successRate }}%</span></div>
            <div class="detail-row"><span>平均耗时</span><span class="mono">{{ selectedTool()!.avgMs }}ms</span></div>
            <div class="detail-row"><span>错误率</span><span class="stat-red">{{ selectedTool()!.errorRate }}%</span></div>
          </div>
          <div class="detail-section wide">
            <h4>参数定义</h4>
            <pre class="code-block">{{ selectedTool()!.schema | json }}</pre>
          </div>
        </div>
      </div>
    }
  `,
  styles: [`
    :host { display:block; }
    .page-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:1.25rem; }
    .page-title { font-size:1.35rem; font-weight:700; color:#F1F5F9; margin:0; }
    .page-subtitle { font-size:.82rem; color:#94A3B8; margin:.25rem 0 0; }
    .btn { display:inline-flex; align-items:center; gap:.4rem; padding:.55rem 1rem; border-radius:8px; border:none; background:linear-gradient(135deg,#7C3AED,#A78BFA); color:#fff; font-size:.82rem; font-weight:600; cursor:pointer; }
    .btn-primary { background:linear-gradient(135deg,#7C3AED,#A78BFA); }
    .btn-sm { padding:.35rem .7rem; font-size:.78rem; }
    .btn-danger { background:rgba(239,68,68,.15); color:#EF4444; border:1px solid rgba(239,68,68,.2); }
    .stat-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:1rem; margin-bottom:1.25rem; }
    .stat-card { background:#131827; border:1px solid rgba(148,163,184,.08); border-radius:12px; padding:1rem 1.1rem; }
    .stat-label { font-size:.72rem; color:#94A3B8; text-transform:uppercase; letter-spacing:.06em; margin-bottom:.4rem; }
    .stat-value { font-size:1.4rem; font-weight:700; color:#F1F5F9; }
    .stat-green { color:#10B981; } .stat-purple { color:#A78BFA; } .stat-amber { color:#F59E0B; } .stat-red { color:#EF4444; }
    .stat-sub { font-size:.72rem; color:#64748B; margin-top:.2rem; }
    .card { background:#131827; border:1px solid rgba(148,163,184,.08); border-radius:12px; overflow:hidden; margin-bottom:1.25rem; }
    .card-header { display:flex; align-items:center; justify-content:space-between; padding:1rem 1.25rem; border-bottom:1px solid rgba(148,163,184,.08); flex-wrap:wrap; gap:.75rem; }
    .tabs { display:flex; gap:.25rem; }
    .tab { padding:.45rem .9rem; border-radius:8px; border:none; background:transparent; color:#94A3B8; font-size:.82rem; cursor:pointer; }
    .tab.active { background:rgba(139,92,246,.12); color:#C4B5FD; }
    .toolbar { display:flex; gap:.5rem; }
    .input { background:#0B0F19; border:1px solid rgba(148,163,184,.12); border-radius:8px; padding:.45rem .7rem; color:#F1F5F9; font-size:.82rem; }
    .input.search { width:200px; }
    .data-table { width:100%; border-collapse:collapse; font-size:.82rem; }
    .data-table th { text-align:left; padding:.7rem 1.25rem; color:#94A3B8; font-weight:500; border-bottom:1px solid rgba(148,163,184,.08); background:#0F131F; }
    .data-table td { padding:.7rem 1.25rem; border-bottom:1px solid rgba(148,163,184,.06); color:#E2E8F0; }
    .data-table tr:hover td { background:rgba(255,255,255,.02); }
    .data-table tr.active td { background:rgba(139,92,246,.06); }
    .tool-name { display:flex; align-items:center; gap:.6rem; }
    .tool-icon { width:2rem; height:2rem; border-radius:8px; background:rgba(139,92,246,.12); display:grid; place-items:center; font-size:.9rem; }
    .name { font-weight:600; color:#F1F5F9; }
    .id { font-size:.72rem; color:#64748B; font-family:'JetBrains Mono',monospace; }
    .tag { padding:.2rem .5rem; border-radius:6px; font-size:.72rem; font-weight:500; }
    .tag-purple { background:rgba(139,92,246,.12); color:#C4B5FD; }
    .tag-blue { background:rgba(59,130,246,.12); color:#93C5FD; }
    .muted { color:#94A3B8; }
    .mono { font-family:'JetBrains Mono',monospace; }
    .detail-header { display:flex; align-items:center; justify-content:space-between; padding:1rem 1.25rem; border-bottom:1px solid rgba(148,163,184,.08); }
    .detail-title { font-size:1.05rem; font-weight:600; color:#F1F5F9; }
    .detail-actions { display:flex; gap:.5rem; }
    .detail-grid { display:grid; grid-template-columns:1fr 1fr; gap:1.25rem; padding:1.25rem; }
    .detail-section.wide { grid-column:1/-1; }
    .detail-section h4 { font-size:.85rem; color:#94A3B8; margin:0 0 .6rem; text-transform:uppercase; letter-spacing:.04em; }
    .detail-row { display:flex; justify-content:space-between; padding:.4rem 0; border-bottom:1px solid rgba(148,163,184,.06); font-size:.82rem; }
    .detail-row span:first-child { color:#94A3B8; }
    .detail-row span:last-child, .detail-row code { color:#F1F5F9; font-family:'JetBrains Mono',monospace; }
    .code-block { background:#0B0F19; border:1px solid rgba(148,163,184,.08); border-radius:8px; padding:.75rem; font-size:.78rem; overflow:auto; max-height:300px; color:#E2E8F0; }
  `]
})
export class ToolsPage {
  readonly state = inject(StateService);

  selectedTool = signal<ToolItem | null>(null);

  selectTool(tool: ToolItem) {
    this.selectedTool.set(tool);
  }
}

