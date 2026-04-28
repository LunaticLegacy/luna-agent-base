import { ChangeDetectionStrategy, Component, Input, ElementRef, afterNextRender, signal, inject, NgZone, type SimpleChanges } from '@angular/core';
import type { GraphEdgeSnapshot, GraphNodeSnapshot, GraphSnapshot } from './api.types';

interface RenderNode {
  node: GraphNodeSnapshot;
  x: number;
  y: number;
  depth: number;
  labelLines: string[];
}

interface RenderEdge {
  edge: GraphEdgeSnapshot;
  from: RenderNode | undefined;
  to: RenderNode | undefined;
  path: string;
}

@Component({
  selector: 'app-graph-viewer',
  standalone: true,
  host: {
    class: 'graph-viewer-host',
  },
  template: `
      <div class="graph-viewer" #container>
        <div class="graph-toolbar">
          <button type="button" class="graph-toolbar-btn" (click)="fitToGraph()">适配</button>
          <button type="button" class="graph-toolbar-btn" (click)="resetView()">重置</button>
        </div>
        <div class="graph-status">
          <div class="graph-status-main">
            {{ graphKindLabel() }} · {{ graph?.nodes?.length ?? 0 }} 节点 · {{ graph?.edges?.length ?? 0 }} 边 · 缩放 {{ (zoom() * 100).toFixed(0) }}%
          </div>
          <div class="graph-status-meta">
            版本 {{ graphRevisionLabel() }} · {{ graphChangeLabel() }}
          </div>
        </div>
      <svg
        #viewport
        [attr.viewBox]="viewBox()"
        preserveAspectRatio="none"
        class="graph-svg"
        role="img"
        [attr.aria-label]="ariaLabel"
        (pointerdown)="onPointerDown($event)"
        (pointermove)="onPointerMove($event)"
        (pointerup)="onPointerUp($event)"
        (pointerleave)="onPointerUp($event)"
        (wheel)="onWheel($event)"
      >
        <defs>
          <marker
            id="arrowhead"
            markerWidth="8"
            markerHeight="6"
            refX="7"
            refY="3"
            orient="auto"
          >
            <polygon points="0 0, 8 3, 0 6" fill="rgba(139, 92, 246, 0.5)" />
          </marker>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>

        <g [attr.transform]="contentTransform()">
          <!-- Edges -->
          @for (renderEdge of renderEdges(); track renderEdge.edge.from_node_id + '-' + renderEdge.edge.to_node_id + '-' + (renderEdge.edge.label ?? '') + '-' + (renderEdge.edge.condition ?? '')) {
            @if (renderEdge.from && renderEdge.to) {
              <path
                [attr.d]="renderEdge.path"
                class="graph-edge"
                [class.active]="isEdgeActive(renderEdge.edge)"
                marker-end="url(#arrowhead)"
              />
            }
          }

          <!-- Nodes -->
          @for (renderNode of renderNodes(); track renderNode.node.node_id) {
            <g
              class="graph-node"
              [class.entry]="nodeRole(renderNode.node) === 'entry'"
              [class.agent-node]="nodeRole(renderNode.node) === 'agent'"
              [class.tool-node]="nodeRole(renderNode.node) === 'tool'"
              [class.exit]="nodeRole(renderNode.node) === 'exit'"
              [class.active]="renderNode.node.node_id === activeNodeId"
              [class.quarantined]="isQuarantined(renderNode.node)"
            >
              @if (isCenterNode(renderNode.node)) {
                <polygon
                  [attr.points]="hexagonPoints(renderNode.x, renderNode.y, nodeRadius() + 4)"
                  class="graph-node-hex"
                />
              } @else {
                <rect
                  [attr.x]="renderNode.x - nodeRadius() - 2"
                  [attr.y]="renderNode.y - nodeRadius() * 0.6"
                  [attr.width]="nodeRadius() * 2 + 4"
                  [attr.height]="nodeRadius() * 1.2"
                  rx="6"
                  class="graph-node-rect"
                />
              }

              @if (renderNode.node.node_id === activeNodeId) {
                <circle
                  [attr.cx]="renderNode.x"
                  [attr.cy]="renderNode.y"
                  [attr.r]="nodeRadius() + 10"
                  fill="none"
                  stroke="rgba(139, 92, 246, 0.25)"
                  stroke-width="1.5"
                  class="pulse-ring"
                />
              }

              <text
                [attr.x]="renderNode.x"
                [attr.y]="renderNode.y - nodeRadius() - 14"
                text-anchor="middle"
                class="graph-node-label"
              >
                @for (line of renderNode.labelLines; track $index; let lineIndex = $index) {
                  <tspan [attr.x]="renderNode.x" [attr.dy]="lineIndex === 0 ? 0 : 12">{{ line }}</tspan>
                }
              </text>
              <text
                [attr.x]="renderNode.x"
                [attr.y]="renderNode.y + nodeRadius() + 14"
                text-anchor="middle"
                class="graph-node-type"
              >
                {{ renderNode.node.node_type }}
              </text>
            </g>
          }
        </g>
      </svg>
    </div>
  `,
  styleUrl: './graph-viewer.component.sass',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class GraphViewerComponent {
  @Input() graph: GraphSnapshot | null = null;
  @Input() activeNodeId: number | null = null;

  private readonly el = inject(ElementRef);
  private readonly ngZone = inject(NgZone);
  private readonly dragState = signal<{
    dragging: boolean;
    startX: number;
    startY: number;
    panX: number;
    panY: number;
  }>({ dragging: false, startX: 0, startY: 0, panX: 0, panY: 0 });

  readonly svgWidth = signal(800);
  readonly svgHeight = signal(520);
  readonly nodeRadius = signal(26);
  readonly padding = signal(60);

  viewBox = signal('0 0 800 520');
  renderNodes = signal<RenderNode[]>([]);
  renderEdges = signal<RenderEdge[]>([]);
  readonly zoom = signal(1);
  readonly panX = signal(0);
  readonly panY = signal(0);
  private needsFit = true;

  constructor() {
    afterNextRender(() => {
      this.observeSize();
    });
  }

  private observeSize(): void {
    const container = this.el.nativeElement.querySelector('.graph-viewer') as HTMLElement;
    if (!container) return;

    const update = () => {
      const rect = container.getBoundingClientRect();
      const w = Math.max(400, Math.round(rect.width));
      const h = Math.max(300, Math.round(rect.height));
      this.svgWidth.set(w);
      this.svgHeight.set(h);
      this.viewBox.set(`0 0 ${w} ${h}`);
      this.nodeRadius.set(Math.max(20, Math.min(32, Math.round(Math.min(w, h) / 18))));
      this.recalculateLayout();
    };

    // Run initial layout inside Zone so Angular detects signal changes
    this.ngZone.run(update);

    const ro = new ResizeObserver(() => {
      this.ngZone.run(update);
    });
    ro.observe(container);
  }

  get ariaLabel(): string {
    const g = this.graph;
    if (!g) return 'Agent 图可视化';
    return `${this.graphKindLabel()} ${g.graph_name} with ${g.node_count} nodes and ${g.edge_count} edges`;
  }

  graphKindLabel(): string {
    return this.graph?.graph_kind === 'execution' ? '执行图' : 'Agent 图';
  }

  isCenterNode(node: GraphNodeSnapshot): boolean {
    return node.node_id === this.graph?.entry_node_id;
  }

  graphRevisionLabel(): string {
    const revision = this.graph?.revision;
    return typeof revision === 'number' && Number.isFinite(revision) ? `#${revision}` : '—';
  }

  graphChangeLabel(): string {
    const summary = this.graph?.last_change?.summary?.trim();
    if (summary) {
      return summary;
    }
    const updatedAt = this.graph?.updated_at?.trim();
    return updatedAt ? `更新于 ${updatedAt}` : '暂无变更记录';
  }

  nodeRole(node: GraphNodeSnapshot): 'entry' | 'agent' | 'tool' | 'exit' {
    if (node.node_id === this.graph?.entry_node_id) {
      return 'entry';
    }
    if (node.node_id === this.graph?.exit_node_id) {
      return 'exit';
    }
    if (node.node_type === 'ToolNode') {
      return 'tool';
    }
    return 'agent';
  }

  hexagonPoints(cx: number, cy: number, r: number): string {
    const points: string[] = [];
    for (let i = 0; i < 6; i++) {
      const angle = (Math.PI / 3) * i - Math.PI / 6;
      const x = cx + r * Math.cos(angle);
      const y = cy + r * Math.sin(angle);
      points.push(`${x},${y}`);
    }
    return points.join(' ');
  }

  wrapNodeLabel(label: string, maxChars = 12, maxLines = 2): string[] {
    const cleaned = String(label || '').trim().replace(/\s+/g, ' ');
    if (!cleaned) {
      return [''];
    }

    const words = cleaned.split(/[_\-\s]+/).filter(Boolean);
    const tokens = words.length > 0 ? words : [cleaned];
    const lines: string[] = [];
    let current = '';

    const pushCurrent = () => {
      if (current) {
        lines.push(current);
        current = '';
      }
    };

    const splitToken = (token: string): string[] => {
      if (token.length <= maxChars) {
        return [token];
      }
      const parts: string[] = [];
      for (let i = 0; i < token.length; i += maxChars) {
        parts.push(token.slice(i, i + maxChars));
      }
      return parts;
    };

    for (const token of tokens.flatMap((item) => splitToken(item))) {
      if (!current) {
        current = token;
        continue;
      }
      if (`${current} ${token}`.length <= maxChars) {
        current = `${current} ${token}`;
        continue;
      }
      pushCurrent();
      if (lines.length >= maxLines - 1) {
        current = token;
        break;
      }
      current = token;
    }

    pushCurrent();

    if (lines.length > maxLines) {
      lines.length = maxLines;
    }

    const original = cleaned.replace(/_/g, ' ');
    const rendered = lines.length > 0 ? lines : [original];
    const renderedText = rendered.join(' ');
    if (rendered.length === maxLines && renderedText.length < original.length) {
      rendered[maxLines - 1] = `${rendered[maxLines - 1].slice(0, Math.max(1, maxChars - 1))}…`;
    }

    return rendered;
  }

  private recalculateLayout(): void {
    const g = this.graph;
    if (!g || g.nodes.length === 0) {
      this.renderNodes.set([]);
      this.renderEdges.set([]);
      this.zoom.set(1);
      this.panX.set(0);
      this.panY.set(0);
      return;
    }

    const nodes = [...g.nodes];
    const entryId = g.entry_node_id ?? nodes[0]?.node_id;
    const svgW = this.svgWidth();
    const svgH = this.svgHeight();
    const pad = this.padding();
    const nr = this.nodeRadius();

    const fallbackOrder = new Map<number, number>(nodes.map((node, index) => [node.node_id, index]));

    // BFS for depth levels
    const depths = new Map<number, number>();
    const visited = new Set<number>();
    const queue: { id: number; depth: number }[] = [{ id: entryId, depth: 0 }];

    while (queue.length > 0) {
      const current = queue.shift()!;
      if (visited.has(current.id)) continue;
      visited.add(current.id);
      depths.set(current.id, current.depth);

      const node = nodes.find((n) => n.node_id === current.id);
      if (node) {
        for (const nextId of node.next_node_ids) {
          if (!visited.has(nextId)) {
            queue.push({ id: nextId, depth: current.depth + 1 });
          }
        }
      }
    }

    let maxDepth = 0;
    for (const d of depths.values()) maxDepth = Math.max(maxDepth, d);
    for (const node of nodes) {
      if (!depths.has(node.node_id)) {
        depths.set(node.node_id, maxDepth + 1 + (fallbackOrder.get(node.node_id) ?? 0) * 0.02);
      }
    }

    // Radial layout
    const layers = new Map<number, GraphNodeSnapshot[]>();
    for (const node of nodes) {
      const d = Math.round(depths.get(node.node_id) ?? 0);
      if (!layers.has(d)) layers.set(d, []);
      layers.get(d)!.push(node);
    }

    const result: RenderNode[] = [];
    const centerY = svgH / 2;
    const horizontalPad = Math.max(80, Math.min(180, svgW * 0.1));
    const verticalPad = Math.max(70, Math.min(140, svgH * 0.12));
    const columnCount = Math.max(1, Math.max(...layers.keys()));
    const availableWidth = Math.max(1, svgW - horizontalPad * 2);
    const xStep = columnCount > 0 ? availableWidth / columnCount : 0;
    const usableHeight = Math.max(1, svgH - verticalPad * 2);
    const minYGap = Math.max(this.nodeRadius() * 3.6, 88);

    const sortedDepths = Array.from(layers.keys()).sort((a, b) => a - b);
    for (const depth of sortedDepths) {
      const layerNodes = layers.get(depth)!;
      const x = depth === 0 ? horizontalPad : horizontalPad + xStep * depth;
      const layerCount = layerNodes.length;
      const span = layerCount <= 1 ? 0 : Math.min(usableHeight, (layerCount - 1) * minYGap);
      const startY = centerY - span / 2;
      const yStep = layerCount <= 1 ? 0 : span / Math.max(1, layerCount - 1);

      for (let i = 0; i < layerNodes.length; i++) {
        const node = layerNodes[i];
        const jitter = layerCount <= 1 ? 0 : ((i % 2 === 0 ? -1 : 1) * Math.min(18, this.nodeRadius() * 0.45));
        const y = layerCount <= 1 ? centerY : startY + i * yStep + jitter;
        result.push({
          node,
          x,
          y,
          depth,
          labelLines: this.wrapNodeLabel(node.node_name),
        });
      }
    }

    this.renderNodes.set(result);

    this.renderEdges.set(
      g.edges.map((edge) => {
        const from = result.find((n) => n.node.node_id === edge.from_node_id);
        const to = result.find((n) => n.node.node_id === edge.to_node_id);
        return {
          edge,
          from,
          to,
          path: this.edgePath(from, to),
        };
      })
    );

    if (this.needsFit) {
      this.needsFit = false;
      queueMicrotask(() => this.fitToGraph());
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['graph']) {
      this.needsFit = true;
      this.recalculateLayout();
    }
  }

  isQuarantined(node: GraphNodeSnapshot): boolean {
    const meta = node.metadata;
    return typeof meta === 'object' && meta !== null && !Array.isArray(meta) && !!meta['quarantined'];
  }

  isEdgeActive(edge: GraphEdgeSnapshot): boolean {
    return edge.from_node_id === this.activeNodeId || edge.to_node_id === this.activeNodeId;
  }

  private nodeFootprint(renderNode: RenderNode): { rx: number; ry: number } {
    const nr = this.nodeRadius();
    if (this.isCenterNode(renderNode.node)) {
      return { rx: nr + 4, ry: nr + 4 };
    }
    return { rx: nr + 2, ry: nr * 0.62 };
  }

  private edgeAnchors(from: RenderNode, to: RenderNode): {
    startX: number;
    startY: number;
    endX: number;
    endY: number;
  } {
    const fromBox = this.nodeFootprint(from);
    const toBox = this.nodeFootprint(to);
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const absDx = Math.max(1, Math.abs(dx));
    const absDy = Math.max(1, Math.abs(dy));
    const fromScale = Math.max(absDx / fromBox.rx, absDy / fromBox.ry, 1);
    const toScale = Math.max(absDx / toBox.rx, absDy / toBox.ry, 1);
    return {
      startX: from.x + dx / fromScale,
      startY: from.y + dy / fromScale,
      endX: to.x - dx / toScale,
      endY: to.y - dy / toScale,
    };
  }

  private edgePath(from: RenderNode | undefined, to: RenderNode | undefined): string {
    if (!from || !to) {
      return '';
    }

    const { startX, startY, endX, endY } = this.edgeAnchors(from, to);
    const dx = endX - startX;
    const dy = endY - startY;
    const direction = dx >= 0 ? 1 : -1;
    const curveBias = Math.max(42, Math.min(170, Math.abs(dx) * 0.36));
    const verticalBias = Math.max(18, Math.min(70, Math.abs(dy) * 0.28));
    const lift = dy === 0 ? -verticalBias : Math.sign(dy) * verticalBias * 0.35;
    const c1x = startX + direction * curveBias;
    const c1y = startY + lift;
    const c2x = endX - direction * curveBias;
    const c2y = endY - lift;
    return `M ${startX} ${startY} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${endX} ${endY}`;
  }

  contentTransform(): string {
    return `matrix(${this.zoom()}, 0, 0, ${this.zoom()}, ${this.panX()}, ${this.panY()})`;
  }

  fitToGraph(): void {
    const nodes = this.renderNodes();
    const svgW = this.svgWidth();
    const svgH = this.svgHeight();
    if (!nodes.length || svgW <= 0 || svgH <= 0) {
      this.zoom.set(1);
      this.panX.set(0);
      this.panY.set(0);
      return;
    }

    const nr = this.nodeRadius();
    let minX = Number.POSITIVE_INFINITY;
    let minY = Number.POSITIVE_INFINITY;
    let maxX = Number.NEGATIVE_INFINITY;
    let maxY = Number.NEGATIVE_INFINITY;

    for (const item of nodes) {
      const labelWidth = Math.max(64, ...item.labelLines.map((line) => line.length * 7.5));
      const labelHeight = Math.max(12, item.labelLines.length * 12);
      minX = Math.min(minX, item.x - Math.max(nr + 32, labelWidth / 2 + 16));
      minY = Math.min(minY, item.y - nr - 24 - labelHeight);
      maxX = Math.max(maxX, item.x + Math.max(nr + 32, labelWidth / 2 + 16));
      maxY = Math.max(maxY, item.y + nr + 40);
    }

    const graphW = Math.max(1, maxX - minX);
    const graphH = Math.max(1, maxY - minY);
    const scale = Math.min((svgW - 48) / graphW, (svgH - 48) / graphH);
    const safeScale = Math.max(0.35, Math.min(1, Number.isFinite(scale) ? scale : 1));
    const contentW = graphW * safeScale;
    const contentH = graphH * safeScale;

    this.zoom.set(safeScale);
    this.panX.set((svgW - contentW) / 2 - minX * safeScale);
    this.panY.set((svgH - contentH) / 2 - minY * safeScale);
  }

  resetView(): void {
    this.fitToGraph();
  }

  onPointerDown(event: PointerEvent): void {
    if (event.button !== 0) return;
    const state = this.dragState();
    this.dragState.set({
      dragging: true,
      startX: event.clientX,
      startY: event.clientY,
      panX: this.panX(),
      panY: this.panY(),
    });
    (event.currentTarget as SVGSVGElement | null)?.setPointerCapture?.(event.pointerId);
  }

  onPointerMove(event: PointerEvent): void {
    const state = this.dragState();
    if (!state.dragging) return;
    const dx = event.clientX - state.startX;
    const dy = event.clientY - state.startY;
    this.panX.set(state.panX + dx);
    this.panY.set(state.panY + dy);
  }

  onPointerUp(event: PointerEvent): void {
    const state = this.dragState();
    if (!state.dragging) return;
    this.dragState.set({ ...state, dragging: false });
    (event.currentTarget as SVGSVGElement | null)?.releasePointerCapture?.(event.pointerId);
  }

  onWheel(event: WheelEvent): void {
    event.preventDefault();
    const svg = event.currentTarget as SVGSVGElement | null;
    const rect = svg?.getBoundingClientRect();
    if (!rect) return;

    const cursorX = event.clientX - rect.left;
    const cursorY = event.clientY - rect.top;
    const currentZoom = this.zoom();
    const delta = event.deltaY > 0 ? 0.9 : 1.1;
    const nextZoom = Math.max(0.35, Math.min(2.5, currentZoom * delta));
    const zoomRatio = nextZoom / currentZoom;

    this.panX.set(cursorX - (cursorX - this.panX()) * zoomRatio);
    this.panY.set(cursorY - (cursorY - this.panY()) * zoomRatio);
    this.zoom.set(nextZoom);
  }
}
