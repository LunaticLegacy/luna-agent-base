import { ChangeDetectionStrategy, Component, Input, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import type { TaskItem } from './services/state.service';

interface TaskGraphNode {
  task: TaskItem;
  x: number;
  y: number;
  depth: number;
  index: number;
}

interface TaskGraphEdge {
  from: TaskGraphNode;
  to: TaskGraphNode;
  path: string;
}

interface TaskTheme {
  fill: string;
  stroke: string;
  glow: string;
  accent: string;
  label: string;
  subtle: string;
}

@Component({
  selector: 'app-task-graph-viewer',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="task-graph-host">
      @if (taskCount() > 0) {
        <div class="task-graph-status">
          <div class="task-graph-status-main">
            {{ taskCount() }} 任务 · {{ edgeCount() }} 依赖边 · {{ readyCount() }} 可执行 · {{ blockedCount() }} 阻塞中
          </div>
          <div class="task-graph-status-meta">任务图按依赖层级自动展开，箭头表示“前置任务 → 后继任务”。</div>
        </div>

        <svg class="task-graph-svg" [attr.viewBox]="viewBox()" preserveAspectRatio="xMidYMid meet" role="img" aria-label="任务关系图">
          <defs>
            <marker id="task-arrowhead" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
              <polygon points="0 0, 10 4, 0 8" fill="rgba(148, 163, 184, 0.72)" />
            </marker>
            <filter id="task-glow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="2.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          <g>
            @for (edge of renderEdges(); track edge.from.task.id + '->' + edge.to.task.id) {
              <path
                class="task-edge"
                [attr.d]="edge.path"
                marker-end="url(#task-arrowhead)"
              />
            }

            @for (node of renderNodes(); track node.task.id) {
              <g
                class="task-node"
                [style.--task-fill]="themeFor(node.task).fill"
                [style.--task-stroke]="themeFor(node.task).stroke"
                [style.--task-glow]="themeFor(node.task).glow"
                [style.--task-accent]="themeFor(node.task).accent"
                [style.--task-label]="themeFor(node.task).label"
                [style.--task-subtle]="themeFor(node.task).subtle"
                [attr.transform]="'translate(' + node.x + ',' + node.y + ')'"
              >
                <rect class="task-node-shell" x="0" y="0" [attr.width]="nodeWidth" [attr.height]="nodeHeight" rx="18" />
                <rect class="task-node-accent" x="0" y="0" [attr.width]="nodeWidth" height="4" rx="2" />

                <text class="task-node-title" x="16" y="28">{{ taskTitle(node.task) }}</text>
                <text class="task-node-meta" x="16" y="50">
                  {{ shortId(node.task.id) }} · {{ statusLabel(node.task.status) }} · {{ priorityLabel(node.task.priority) }}
                </text>
                <text class="task-node-meta task-node-meta-secondary" x="16" y="70">
                  依赖 {{ node.task.dependencies.length }} · 后继 {{ node.task.nextTasks.length }}
                </text>

                <title>{{ taskTitle(node.task) }} · {{ node.task.id }}</title>
              </g>
            }
          </g>
        </svg>
      } @else {
        <div class="task-graph-empty">
          <div class="task-graph-empty-title">暂无可展开的任务图</div>
          <div class="task-graph-empty-text">请先加载任务列表，或切换到包含任务数据的 swarm。</div>
        </div>
      }
    </div>
  `,
  styleUrls: ['./task-graph-viewer.component.sass'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TaskGraphViewerComponent {
  readonly nodeWidth = 228;
  readonly nodeHeight = 88;
  readonly padding = 72;
  readonly horizontalGap = 36;
  readonly verticalGap = 120;

  private readonly taskList = signal<TaskItem[]>([]);
  readonly renderNodes = signal<TaskGraphNode[]>([]);
  readonly renderEdges = signal<TaskGraphEdge[]>([]);
  readonly viewBox = signal('0 0 800 420');

  readonly taskCount = computed(() => this.taskList().length);
  readonly edgeCount = computed(() => this.renderEdges().length);
  readonly readyCount = computed(() => this.taskList().filter((task) => task.status === 'pending' && task.dependencies.every((dep) => this.taskList().some((candidate) => candidate.id === dep && candidate.status === 'success'))).length);
  readonly blockedCount = computed(() => this.taskList().filter((task) => task.status === 'pending' && !task.dependencies.every((dep) => this.taskList().some((candidate) => candidate.id === dep && candidate.status === 'success'))).length);

  @Input() set tasks(value: TaskItem[] | null) {
    this.taskList.set([...(value ?? [])]);
    this.rebuildLayout();
  }

  themeFor(task: TaskItem): TaskTheme {
    switch (task.status) {
      case 'running':
        return {
          fill: 'rgba(124, 58, 237, 0.16)',
          stroke: 'rgba(196, 181, 253, 0.95)',
          glow: 'rgba(139, 92, 246, 0.38)',
          accent: 'rgba(196, 181, 253, 0.95)',
          label: '#f5f3ff',
          subtle: '#ddd6fe',
        };
      case 'success':
        return {
          fill: 'rgba(16, 185, 129, 0.14)',
          stroke: 'rgba(110, 231, 183, 0.92)',
          glow: 'rgba(16, 185, 129, 0.34)',
          accent: 'rgba(110, 231, 183, 0.92)',
          label: '#ecfdf5',
          subtle: '#a7f3d0',
        };
      case 'failed':
        return {
          fill: 'rgba(239, 68, 68, 0.14)',
          stroke: 'rgba(248, 113, 113, 0.96)',
          glow: 'rgba(239, 68, 68, 0.34)',
          accent: 'rgba(248, 113, 113, 0.96)',
          label: '#fef2f2',
          subtle: '#fecaca',
        };
      case 'cancelled':
        return {
          fill: 'rgba(100, 116, 139, 0.18)',
          stroke: 'rgba(148, 163, 184, 0.84)',
          glow: 'rgba(100, 116, 139, 0.26)',
          accent: 'rgba(148, 163, 184, 0.84)',
          label: '#e2e8f0',
          subtle: '#cbd5e1',
        };
      case 'timeout':
        return {
          fill: 'rgba(245, 158, 11, 0.16)',
          stroke: 'rgba(253, 224, 71, 0.92)',
          glow: 'rgba(245, 158, 11, 0.34)',
          accent: 'rgba(253, 224, 71, 0.92)',
          label: '#fffbeb',
          subtle: '#fde68a',
        };
      default:
        return {
          fill: 'rgba(148, 163, 184, 0.14)',
          stroke: 'rgba(203, 213, 225, 0.88)',
          glow: 'rgba(148, 163, 184, 0.24)',
          accent: 'rgba(203, 213, 225, 0.88)',
          label: '#f8fafc',
          subtle: '#cbd5e1',
        };
    }
  }

  taskTitle(task: TaskItem): string {
    const raw = task.name?.trim() || task.id;
    return raw.length > 18 ? `${raw.slice(0, 18)}…` : raw;
  }

  statusLabel(status: TaskItem['status']): string {
    const map: Record<TaskItem['status'], string> = {
      pending: '待处理',
      running: '运行中',
      success: '成功',
      failed: '失败',
      cancelled: '已取消',
      timeout: '超时',
    };
    return map[status] ?? status;
  }

  priorityLabel(priority: TaskItem['priority']): string {
    const map: Record<TaskItem['priority'], string> = {
      low: '低',
      medium: '中',
      high: '高',
      urgent: '紧急',
    };
    return map[priority] ?? priority;
  }

  shortId(value: string): string {
    const text = String(value || '').trim();
    return text.length > 16 ? `${text.slice(0, 16)}…` : text;
  }

  private rebuildLayout(): void {
    const tasks = this.taskList();
    if (!tasks.length) {
      this.renderNodes.set([]);
      this.renderEdges.set([]);
      this.viewBox.set('0 0 800 420');
      return;
    }

    const taskMap = new Map(tasks.map((task) => [task.id, task] as const));
    const depthCache = new Map<string, number>();
    const visiting = new Set<string>();

    const depthOf = (taskId: string): number => {
      if (depthCache.has(taskId)) return depthCache.get(taskId) ?? 0;
      if (visiting.has(taskId)) return 0;
      visiting.add(taskId);
      const task = taskMap.get(taskId);
      if (!task) {
        visiting.delete(taskId);
        depthCache.set(taskId, 0);
        return 0;
      }
      const parents = (task.dependencies ?? []).filter((depId) => taskMap.has(depId));
      const depth = parents.length ? Math.max(...parents.map((depId) => depthOf(depId) + 1)) : 0;
      visiting.delete(taskId);
      depthCache.set(taskId, depth);
      return depth;
    };

    const priorityWeight: Record<TaskItem['priority'], number> = { urgent: 0, high: 1, medium: 2, low: 3 };
    const statusWeight: Record<TaskItem['status'], number> = { running: 0, pending: 1, success: 2, timeout: 3, failed: 4, cancelled: 5 };

    const grouped = new Map<number, TaskItem[]>();
    for (const task of tasks) {
      const depth = depthOf(task.id);
      const bucket = grouped.get(depth) ?? [];
      bucket.push(task);
      grouped.set(depth, bucket);
    }

    const depths = [...grouped.keys()].sort((a, b) => a - b);
    const layers = depths.map((depth) => {
      const layerTasks = [...(grouped.get(depth) ?? [])].sort((a, b) => {
        const statusDiff = statusWeight[a.status] - statusWeight[b.status];
        if (statusDiff !== 0) return statusDiff;
        const priorityDiff = priorityWeight[a.priority] - priorityWeight[b.priority];
        if (priorityDiff !== 0) return priorityDiff;
        const createdDiff = String(a.createdAt).localeCompare(String(b.createdAt));
        if (createdDiff !== 0) return createdDiff;
        return a.id.localeCompare(b.id);
      });
      return { depth, tasks: layerTasks };
    });

    const layerWidths = layers.map((layer) => this.nodeWidth * layer.tasks.length + this.horizontalGap * Math.max(0, layer.tasks.length - 1));
    const maxLayerWidth = Math.max(this.nodeWidth, ...layerWidths);

    const nodes: TaskGraphNode[] = [];
    for (const layer of layers) {
      const totalWidth = this.nodeWidth * layer.tasks.length + this.horizontalGap * Math.max(0, layer.tasks.length - 1);
      const startX = this.padding + (maxLayerWidth - totalWidth) / 2;
      const y = this.padding + layer.depth * (this.nodeHeight + this.verticalGap);
      layer.tasks.forEach((task, index) => {
        nodes.push({
          task,
          x: startX + index * (this.nodeWidth + this.horizontalGap),
          y,
          depth: layer.depth,
          index,
        });
      });
    }

    const byTaskId = new Map(nodes.map((node) => [node.task.id, node] as const));
    const edges: TaskGraphEdge[] = [];
    for (const task of tasks) {
      const target = byTaskId.get(task.id);
      if (!target) continue;
      for (const dependencyId of task.dependencies ?? []) {
        const source = byTaskId.get(dependencyId);
        if (!source || source.task.id === target.task.id) continue;
        edges.push({
          from: source,
          to: target,
          path: this.edgePath(source, target),
        });
      }
    }

    const maxDepth = layers.reduce((max, layer) => Math.max(max, layer.depth), 0);
    const width = maxLayerWidth + this.padding * 2;
    const height = this.padding * 2 + (maxDepth + 1) * this.nodeHeight + maxDepth * this.verticalGap;

    this.renderNodes.set(nodes);
    this.renderEdges.set(edges);
    this.viewBox.set(`0 0 ${Math.ceil(width)} ${Math.ceil(height)}`);
  }

  private edgePath(from: TaskGraphNode, to: TaskGraphNode): string {
    const sx = from.x + this.nodeWidth / 2;
    const sy = from.y + this.nodeHeight;
    const tx = to.x + this.nodeWidth / 2;
    const ty = to.y;
    const curve = Math.max(72, Math.abs(ty - sy) * 0.45);
    return `M ${sx} ${sy} C ${sx} ${sy + curve}, ${tx} ${ty - curve}, ${tx} ${ty}`;
  }
}
