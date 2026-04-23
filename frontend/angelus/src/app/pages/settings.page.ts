import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { StateService } from '../services/state.service';

@Component({
  selector: 'app-settings-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="page-header">
      <div>
        <h1 class="page-title">系统设置</h1>
        <p class="page-subtitle">配置 API 端点、系统参数和个性化选项</p>
      </div>
      <div class="header-actions">
        <span class="save-hint" *ngIf="state.settingsSaved()">✓ 已保存</span>
        <button class="btn btn-primary" (click)="saveSettings()">保存更改</button>
      </div>
    </div>

    <div class="settings-grid">
      <div class="settings-card">
        <h3>API 配置 <span class="badge connected">已连接</span></h3>
        <div class="form-group">
          <label>后端 API 地址</label>
          <input class="input" [(ngModel)]="apiUrl" placeholder="http://localhost:5000" />
          <span class="hint">Flask 后端服务地址，保存后立即生效</span>
        </div>
        <div class="form-group">
          <label>API 超时 (秒)</label>
          <input class="input" type="number" [(ngModel)]="apiTimeout" />
          <span class="hint">HTTP 请求超时时间，保存后立即生效</span>
        </div>
        <div class="form-group">
          <label>SSE 重连间隔 (秒)</label>
          <input class="input" type="number" [(ngModel)]="reconnectInterval" />
          <span class="hint">实时事件流断开后的重连等待时间</span>
        </div>
        <div class="form-group inline">
          <label class="switch">
            <input type="checkbox" [(ngModel)]="autoReconnect" />
            <span class="slider"></span>
          </label>
          <span>自动重连 SSE 流</span>
          <span class="hint-inline">断开后自动尝试重新连接</span>
        </div>
      </div>

      <div class="settings-card">
        <h3>系统信息</h3>
        <div class="info-row"><span>版本</span><code>v1.0.0-alpha</code></div>
        <div class="info-row"><span>Angular</span><code>19.0.0</code></div>
        <div class="info-row"><span>Node.js</span><code>{{ nodeVersion }}</code></div>
        <div class="info-row"><span>构建时间</span><code>{{ buildTime }}</code></div>
        <div class="info-row"><span>API 状态</span>
          <span class="status-badge" [class.online]="state.health()?.status==='ok'">
            <span class="dot"></span>{{ state.health()?.status === 'ok' ? '在线' : '离线' }}
          </span>
        </div>
      </div>

      <div class="settings-card">
        <h3>显示设置 <span class="badge connected">已连接</span></h3>
        <div class="form-group inline">
          <label class="switch">
            <input type="checkbox" [(ngModel)]="darkMode" />
            <span class="slider"></span>
          </label>
          <span>深色模式</span>
          <span class="hint-inline">切换页面明暗主题</span>
        </div>
        <div class="form-group inline">
          <label class="switch">
            <input type="checkbox" [(ngModel)]="compactMode" />
            <span class="slider"></span>
          </label>
          <span>紧凑布局</span>
          <span class="hint-inline">减小间距以展示更多内容</span>
        </div>
        <div class="form-group inline">
          <label class="switch">
            <input type="checkbox" [(ngModel)]="showDebug" />
            <span class="slider"></span>
          </label>
          <span>显示调试信息</span>
          <span class="hint-inline">在界面中展示额外调试数据</span>
        </div>
        <div class="form-group">
          <label>语言</label>
          <select class="input" [(ngModel)]="language">
            <option value="zh">简体中文</option>
            <option value="en">English</option>
          </select>
          <span class="hint">界面语言（部分翻译可能不完整）</span>
        </div>
      </div>

      <div class="settings-card wide">
        <h3>系统状态</h3>
        <div class="status-grid">
          <div class="status-item">
            <div class="status-label">后端健康</div>
            <div class="status-value" [class.ok]="state.health()?.status==='ok'">{{ state.health()?.status === 'ok' ? '正常' : '异常' }}</div>
          </div>
          <div class="status-item">
            <div class="status-label">就绪状态</div>
            <div class="status-value" [class.ok]="state.ready()?.ready">{{ state.ready()?.ready ? '就绪' : '未就绪' }}</div>
          </div>
          <div class="status-item">
            <div class="status-label">Swarm 数量</div>
            <div class="status-value">{{ state.swarms().length || 0 }}</div>
          </div>
          <div class="status-item">
            <div class="status-label">Agent 总数</div>
            <div class="status-value">{{ state.totalAgents() }}</div>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    :host { display:block; }
    .page-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:1.25rem; }
    .page-title { font-size:1.35rem; font-weight:700; color:#F1F5F9; margin:0; }
    .page-subtitle { font-size:.82rem; color:#94A3B8; margin:.25rem 0 0; }
    .header-actions { display:flex; align-items:center; gap:.75rem; }
    .save-hint { font-size:.82rem; color:#10B981; font-weight:600; }
    .btn { display:inline-flex; align-items:center; gap:.4rem; padding:.55rem 1rem; border-radius:8px; border:none; background:linear-gradient(135deg,#7C3AED,#A78BFA); color:#fff; font-size:.82rem; font-weight:600; cursor:pointer; }
    .settings-grid { display:grid; grid-template-columns:1fr 1fr; gap:1.25rem; }
    .settings-card { background:#131827; border:1px solid rgba(148,163,184,.08); border-radius:12px; padding:1.25rem; }
    .settings-card.wide { grid-column:1/-1; }
    .settings-card h3 { font-size:.95rem; font-weight:600; color:#F1F5F9; margin:0 0 1rem; padding-bottom:.75rem; border-bottom:1px solid rgba(148,163,184,.08); display:flex; align-items:center; gap:.5rem; }
    .badge { font-size:.65rem; font-weight:600; padding:.15rem .45rem; border-radius:999px; text-transform:uppercase; letter-spacing:.02em; }
    .badge.connected { background:rgba(16,185,129,.12); color:#10B981; }
    .badge.placeholder { background:rgba(148,163,184,.12); color:#94A3B8; }
    .form-group { margin-bottom:1rem; }
    .form-group:last-child { margin-bottom:0; }
    .form-group label { display:block; font-size:.82rem; color:#94A3B8; margin-bottom:.35rem; }
    .form-group.inline { display:flex; align-items:center; gap:.6rem; flex-wrap:wrap; }
    .form-group.inline label { margin-bottom:0; }
    .input { width:100%; background:#0B0F19; border:1px solid rgba(148,163,184,.12); border-radius:8px; padding:.55rem .75rem; color:#F1F5F9; font-size:.85rem; }
    .input:focus { outline:none; border-color:#8B5CF6; }
    .hint { display:block; font-size:.72rem; color:#64748B; margin-top:.25rem; }
    .hint-inline { font-size:.72rem; color:#64748B; margin-left:auto; }
    .switch { position:relative; display:inline-block; width:40px; height:22px; }
    .switch input { opacity:0; width:0; height:0; }
    .slider { position:absolute; cursor:pointer; top:0; left:0; right:0; bottom:0; background:#334155; border-radius:22px; transition:.3s; }
    .slider:before { position:absolute; content:''; height:16px; width:16px; left:3px; bottom:3px; background:#fff; border-radius:50%; transition:.3s; }
    input:checked + .slider { background:#8B5CF6; }
    input:checked + .slider:before { transform:translateX(18px); }
    .info-row { display:flex; justify-content:space-between; align-items:center; padding:.55rem 0; border-bottom:1px solid rgba(148,163,184,.06); font-size:.85rem; }
    .info-row span:first-child { color:#94A3B8; }
    .info-row code { background:#0B0F19; padding:.2rem .5rem; border-radius:4px; font-size:.78rem; color:#F1F5F9; font-family:'JetBrains Mono',monospace; }
    .status-badge { display:inline-flex; align-items:center; gap:.35rem; padding:.25rem .55rem; border-radius:999px; background:rgba(148,163,184,.1); color:#94A3B8; font-size:.78rem; }
    .status-badge.online { background:rgba(16,185,129,.1); color:#10B981; }
    .dot { width:6px; height:6px; border-radius:50%; background:currentColor; }
    .status-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:1rem; }
    .status-item { background:#0B0F19; border-radius:8px; padding:.75rem 1rem; }
    .status-label { font-size:.72rem; color:#94A3B8; margin-bottom:.25rem; }
    .status-value { font-size:1.1rem; font-weight:700; color:#F1F5F9; }
    .status-value.ok { color:#10B981; }
    @media (max-width:768px) { .settings-grid { grid-template-columns:1fr; } .status-grid { grid-template-columns:1fr 1fr; } }
  `]
})
export class SettingsPage {
  readonly state = inject(StateService);

  apiUrl = signal(this.state.apiBaseUrl());
  apiTimeout = signal(this.state.apiTimeout());
  reconnectInterval = signal(this.state.reconnectInterval());
  autoReconnect = signal(this.state.autoReconnect());
  darkMode = signal(this.state.darkMode());
  compactMode = signal(this.state.compactMode());
  showDebug = signal(this.state.showDebug());
  language = signal(this.state.language());

  nodeVersion = 'v20.x';
  buildTime = new Date().toLocaleString('zh-CN');

  saveSettings() {
    this.state.saveSettings({
      apiBaseUrl: this.apiUrl(),
      apiTimeout: this.apiTimeout(),
      reconnectInterval: this.reconnectInterval(),
      autoReconnect: this.autoReconnect(),
      darkMode: this.darkMode(),
      compactMode: this.compactMode(),
      showDebug: this.showDebug(),
      language: this.language(),
    });
  }
}
