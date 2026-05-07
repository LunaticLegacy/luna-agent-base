import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../api.service';
import type { GraphResponse, HistoryEntry } from '../api.types';

@Component({
  selector: 'app-swarm-detail',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule],
  template: `
    <div class="page">
      <a [routerLink]="['/swarms']" class="back">← 返回</a>
      <h1>{{ swarmName }}</h1>

      <div class="tabs">
        <button [class.active]="tab()==='graph'" (click)="tab.set('graph')">图</button>
        <button [class.active]="tab()==='run'" (click)="tab.set('run')">运行</button>
        <button [class.active]="tab()==='history'" (click)="loadHistory();tab.set('history')">历史</button>
      </div>

      <!-- Graph Tab -->
      @if (tab() === 'graph') {
        <div class="graph-shell">
          <svg #svg width="100%" height="400" *ngIf="graph">
            <g *ngFor="let e of graph.edges">
              <line [attr.x1]="nodeX(e.source)" [attr.y1]="nodeY(e.source)"
                    [attr.x2]="nodeX(e.target)" [attr.y2]="nodeY(e.target)"
                    stroke="#999" stroke-width="1.5" />
              <text [attr.x]="(nodeX(e.source)+nodeX(e.target))/2"
                    [attr.y]="(nodeY(e.source)+nodeY(e.target))/2-4"
                    text-anchor="middle" font-size="10" fill="#666">{{e.label}}</text>
            </g>
            <g *ngFor="let n of graph.nodes">
              <circle [attr.cx]="nodeX(n.id)" [attr.cy]="nodeY(n.id)" r="16"
                      [attr.fill]="nodeColor(n.type)" stroke="#333" stroke-width="1.5" />
              <text [attr.x]="nodeX(n.id)" [attr.y]="nodeY(n.id)+24"
                    text-anchor="middle" font-size="11">{{n.name}}</text>
            </g>
          </svg>
        </div>
      }

      <!-- Run Tab -->
      @if (tab() === 'run') {
        <div class="run-panel">
          <textarea [(ngModel)]="inputText" rows="4" placeholder="输入内容..."></textarea>
          <button class="btn primary" (click)="run()" [disabled]="running()">
            {{ running() ? '运行中...' : '▶ 运行' }}
          </button>
          @if (output()) {
            <div class="output">
              <pre>{{ output() | json }}</pre>
            </div>
          }
          @if (error()) {
            <div class="error">{{ error() }}</div>
          }
        </div>
      }

      <!-- History Tab -->
      @if (tab() === 'history') {
        <div class="history-list">
          <div *ngFor="let h of history" class="history-item">
            <div class="h-time">{{ h.timestamp | date:'short' }}</div>
            <div class="h-input">输入：{{ h.input | json }}</div>
            <div class="h-output">输出：{{ h.output | json }}</div>
          </div>
          <div *ngIf="history.length === 0" class="empty">暂无运行记录</div>
        </div>
      }
    </div>
  `,
  styles: [`
    .page { padding: 24px; max-width: 800px; margin: auto; font-family: system-ui; }
    .back { color: #3b82f6; text-decoration: none; font-size: 14px; }
    .tabs { display: flex; gap: 4px; margin: 16px 0; }
    .tabs button { padding: 6px 16px; border: 1px solid #d1d5db; background: #fff; border-radius: 6px; cursor: pointer; }
    .tabs .active { background: #3b82f6; color: #fff; border-color: #3b82f6; }
    .graph-shell { border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; overflow-x: auto; }
    .run-panel { display: flex; flex-direction: column; gap: 12px; }
    textarea { width: 100%; padding: 8px; border: 1px solid #d1d5db; border-radius: 6px; font-family: monospace; resize: vertical; }
    .btn { padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; }
    .btn.primary { background: #3b82f6; color: #fff; }
    .btn:disabled { opacity: .5; }
    .output { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px; }
    .output pre { margin: 0; white-space: pre-wrap; font-size: 13px; }
    .error { color: #dc2626; padding: 8px; background: #fef2f2; border-radius: 6px; }
    .history-item { border-bottom: 1px solid #e5e7eb; padding: 12px 0; }
    .h-time { font-size: 12px; color: #9ca3af; }
    .h-input, .h-output { font-size: 13px; word-break: break-all; }
    .empty { color: #9ca3af; text-align: center; padding: 32px; }
  `]
})
export class SwarmDetailPage implements OnInit {
  private route = inject(ActivatedRoute);
  private api = inject(ApiService);
  swarmName = '';
  graph?: GraphResponse;
  history: HistoryEntry[] = [];
  inputText = '';
  output = signal<unknown>(null);
  error = signal('');
  running = signal(false);
  tab = signal<'graph' | 'run' | 'history'>('graph');

  private nodePositions = new Map<string, { x: number; y: number }>();

  ngOnInit() {
    this.route.params.subscribe(p => {
      this.swarmName = p['name'];
      this.loadGraph();
    });
  }

  async loadGraph() {
    try {
      this.graph = await this.api.getGraph(this.swarmName);
      // Auto-layout nodes in a grid
      this.nodePositions.clear();
      const cols = Math.ceil(Math.sqrt(this.graph.nodes.length));
      this.graph.nodes.forEach((n, i) => {
        this.nodePositions.set(n.id, {
          x: 60 + (i % cols) * 140,
          y: 40 + Math.floor(i / cols) * 80,
        });
      });
    } catch {}
  }

  async loadHistory() {
    try {
      const r = await this.api.getHistory(this.swarmName);
      this.history = r.history;
    } catch {}
  }

  nodeX(id: string) { return this.nodePositions.get(id)?.x ?? 0; }
  nodeY(id: string) { return this.nodePositions.get(id)?.y ?? 0; }
  nodeColor(type: string) {
    const map: Record<string, string> = { agent: '#dbeafe', tool: '#d1fae5', input: '#fef3c7', output: '#fce7f3', join: '#e0e7ff', router: '#f3e8ff' };
    return map[type] || '#e5e7eb';
  }

  async run() {
    this.running.set(true);
    this.output.set(null);
    this.error.set('');
    try {
      const es = this.api.runSwarmStream(this.swarmName, { input: this.inputText });
      es.onmessage = (e: MessageEvent<string>) => {
        const data = JSON.parse(e.data);
        if (data.event === 'result') this.output.set(data.output);
        if (data.event === 'error') this.error.set(data.error);
        if (data.event === 'done') { es.close(); this.running.set(false); }
      };
      es.onerror = () => { this.error.set('连接中断'); this.running.set(false); es.close(); };
    } catch (e) {
      this.error.set(String(e));
      this.running.set(false);
    }
  }
}
