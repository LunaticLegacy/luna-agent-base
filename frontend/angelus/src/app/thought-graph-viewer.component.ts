import { ChangeDetectionStrategy, Component, ElementRef, Input, NgZone, afterNextRender, inject, signal } from '@angular/core';
import type { ThoughtGraphEdgeSnapshot, ThoughtGraphNodeSnapshot, ThoughtGraphSnapshot } from './api.types';

interface RenderNode {
  node: ThoughtGraphNodeSnapshot;
  x: number;
  y: number;
  lane: number;
}

interface RenderEdge {
  edge: ThoughtGraphEdgeSnapshot;
  from: RenderNode | undefined;
  to: RenderNode | undefined;
}

@Component({
  selector: 'app-thought-graph-viewer',
  standalone: true,
  host: {
    class: 'thought-graph-viewer-host',
  },
  template: `
    <div class="thought-viewer" #container>
      <div class="thought-toolbar">
        <button type="button" class="thought-toolbar-btn" (click)="fitToGraph()">适配</button>
        <button type="button" class="thought-toolbar-btn" (click)="resetView()">重置</button>
      </div>
      <div class="thought-status">
        {{ graph?.nodes?.length ?? 0 }} 节点 · {{ graph?.edges?.length ?? 0 }} 边 ·
        {{ (graph?.active_subgraphs?.length ?? 0) }} 子图 · 缩放 {{ (zoom() * 100).toFixed(0) }}%
      </div>
      <svg
        #viewport
        [attr.viewBox]="viewBox()"
        preserveAspectRatio="none"
        class="thought-svg"
        role="img"
        [attr.aria-label]="ariaLabel"
        (pointerdown)="onPointerDown($event)"
        (pointermove)="onPointerMove($event)"
        (pointerup)="onPointerUp($event)"
        (pointerleave)="onPointerUp($event)"
        (wheel)="onWheel($event)"
      >
        <defs>
          <marker id="arrowhead-thought" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="rgba(94, 234, 212, 0.45)" />
          </marker>
          <filter id="thought-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2.5" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>

        <g [attr.transform]="contentTransform()">
          @for (renderEdge of renderEdges(); track renderEdge.edge.edge_id) {
            @if (renderEdge.from && renderEdge.to) {
              <line
                [attr.x1]="renderEdge.from.x"
                [attr.y1]="renderEdge.from.y"
                [attr.x2]="renderEdge.to.x"
                [attr.y2]="renderEdge.to.y"
                class="thought-edge"
                [class.supports]="isSupportEdge(renderEdge.edge)"
                [class.opposes]="isOpposeEdge(renderEdge.edge)"
                [class.speculative]="isSpeculativeEdge(renderEdge.edge)"
                [attr.stroke-dasharray]="edgeDash(renderEdge.edge)"
                marker-end="url(#arrowhead-thought)"
              />
            }
          }

          @for (renderNode of renderNodes(); track renderNode.node.node_id) {
            <g
              class="thought-node"
              [class.fact]="nodeLane(renderNode.node) === 0"
              [class.reasoning]="nodeLane(renderNode.node) === 1"
              [class.risk]="nodeLane(renderNode.node) === 2"
              [class.active]="isActiveNode(renderNode.node)"
              [class.root]="isRootNode(renderNode.node)"
            >
              <circle
                [attr.cx]="renderNode.x"
                [attr.cy]="renderNode.y"
                [attr.r]="nodeRadius() + (isActiveNode(renderNode.node) ? 6 : 0)"
                class="thought-node-ring"
              />
              <rect
                [attr.x]="renderNode.x - nodeWidth() / 2"
                [attr.y]="renderNode.y - nodeHeight() / 2"
                [attr.width]="nodeWidth()"
                [attr.height]="nodeHeight()"
                rx="16"
                class="thought-node-card"
              />
              @if (isActiveNode(renderNode.node)) {
                <circle
                  [attr.cx]="renderNode.x"
                  [attr.cy]="renderNode.y"
                  [attr.r]="nodeRadius() + 13"
                  fill="none"
                  stroke="rgba(94, 234, 212, 0.24)"
                  stroke-width="1.5"
                  class="thought-pulse"
                />
              }
              <text [attr.x]="renderNode.x" [attr.y]="renderNode.y - 6" text-anchor="middle" class="thought-node-label">
                {{ labelForNode(renderNode.node) }}
              </text>
              <text [attr.x]="renderNode.x" [attr.y]="renderNode.y + 10" text-anchor="middle" class="thought-node-type">
                {{ renderNode.node.node_type }}
              </text>
            </g>
          }
        </g>
      </svg>

      <div class="thought-panels">
        <div class="thought-panel">
          <div class="thought-panel-title">活跃子图</div>
          @if (activeSubgraphs().length > 0) {
            <div class="subgraph-list">
              @for (subgraph of activeSubgraphs(); track subgraph.subgraph_id) {
                <div class="subgraph-item" [class.active]="subgraph.subgraph_id === selectedSubgraphId()">
                  <div class="subgraph-head">
                    <span class="subgraph-id mono">{{ subgraph.subgraph_id.slice(0, 8) }}</span>
                    <span class="subgraph-status">{{ subgraph.status }}</span>
                  </div>
                  <div class="subgraph-purpose">{{ subgraph.purpose }}</div>
                  <div class="subgraph-meta">
                    root {{ subgraph.root_node_ids.length }} · frontier {{ subgraph.frontier_node_ids.length }} · {{ subgraph.owner_agent || 'shared' }}
                  </div>
                </div>
              }
            </div>
          } @else {
            <div class="thought-empty">暂无活跃子图</div>
          }
        </div>

        <div class="thought-panel">
          <div class="thought-panel-title">关系图例</div>
          <div class="legend-list">
            <div class="legend-item"><span class="legend-line support"></span><span>supports / verifies</span></div>
            <div class="legend-item"><span class="legend-line oppose"></span><span>opposes / disproves</span></div>
            <div class="legend-item"><span class="legend-line speculative"></span><span>speculates / relates</span></div>
          </div>
        </div>
      </div>
    </div>
  `,
  styleUrls: ['./thought-graph-viewer.component.sass'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ThoughtGraphViewerComponent {
  @Input() graph: ThoughtGraphSnapshot | null = null;

  private readonly el = inject(ElementRef);
  private readonly ngZone = inject(NgZone);

  readonly svgWidth = signal(800);
  readonly svgHeight = signal(520);
  readonly nodeRadius = signal(24);
  readonly nodeWidth = signal(180);
  readonly nodeHeight = signal(54);
  readonly padding = signal(60);
  readonly viewBox = signal('0 0 800 520');
  readonly renderNodes = signal<RenderNode[]>([]);
  readonly renderEdges = signal<RenderEdge[]>([]);
  readonly zoom = signal(1);
  readonly panX = signal(0);
  readonly panY = signal(0);
  readonly selectedSubgraphId = signal<string | null>(null);
  private needsFit = true;

  constructor() {
    afterNextRender(() => {
      this.observeSize();
    });
  }

  get ariaLabel(): string {
    const g = this.graph;
    if (!g) return 'Thought graph visualization';
    return `Thought graph ${g.graph_id} with ${g.nodes.length} nodes and ${g.edges.length} edges`;
  }

  activeSubgraphs() {
    return this.graph?.active_subgraphs ?? [];
  }

  fitToGraph(): void {
    this.needsFit = true;
    this.recalculateLayout();
  }

  resetView(): void {
    this.zoom.set(1);
    this.panX.set(0);
    this.panY.set(0);
    this.needsFit = true;
    this.recalculateLayout();
  }

  onPointerDown(event: PointerEvent): void {
    const target = event.target as HTMLElement | null;
    if (target?.closest('g.thought-node')) return;
    this.dragStartX = event.clientX;
    this.dragStartY = event.clientY;
    this.dragOriginX = this.panX();
    this.dragOriginY = this.panY();
    this.dragging = true;
  }

  onPointerMove(event: PointerEvent): void {
    if (!this.dragging) return;
    const dx = event.clientX - this.dragStartX;
    const dy = event.clientY - this.dragStartY;
    this.panX.set(this.dragOriginX + dx);
    this.panY.set(this.dragOriginY + dy);
  }

  onPointerUp(_event: PointerEvent): void {
    this.dragging = false;
  }

  onWheel(event: WheelEvent): void {
    event.preventDefault();
    const next = Math.max(0.45, Math.min(2.4, this.zoom() * (event.deltaY > 0 ? 0.92 : 1.08)));
    this.zoom.set(next);
  }

  contentTransform(): string {
    return `translate(${this.panX()}, ${this.panY()}) scale(${this.zoom()})`;
  }

  nodeLane(node: ThoughtGraphNodeSnapshot): number {
    const type = node.node_type.toLowerCase();
    if (['fact', 'evidence', 'counterevidence', 'tool_result'].includes(type)) return 0;
    if (['question', 'assumption', 'risk'].includes(type)) return 2;
    return 1;
  }

  labelForNode(node: ThoughtGraphNodeSnapshot): string {
    const text = (node.summary || node.content || node.node_id).trim();
    return text.length > 26 ? `${text.slice(0, 26)}…` : text;
  }

  isRootNode(node: ThoughtGraphNodeSnapshot): boolean {
    return !!this.activeSubgraphs().some((subgraph) => subgraph.root_node_ids.includes(node.node_id));
  }

  isActiveNode(node: ThoughtGraphNodeSnapshot): boolean {
    return !!this.activeSubgraphs().some(
      (subgraph) => subgraph.root_node_ids.includes(node.node_id) || subgraph.frontier_node_ids.includes(node.node_id)
    );
  }

  isSupportEdge(edge: ThoughtGraphEdgeSnapshot): boolean {
    return ['supports', 'verifies', 'evidence_for', 'refines'].includes(edge.relation.toLowerCase());
  }

  isOpposeEdge(edge: ThoughtGraphEdgeSnapshot): boolean {
    return ['opposes', 'disproves', 'questions'].includes(edge.relation.toLowerCase());
  }

  isSpeculativeEdge(edge: ThoughtGraphEdgeSnapshot): boolean {
    return ['speculates', 'relates', 'leads_to', 'depends_on', 'derives_from'].includes(edge.relation.toLowerCase());
  }

  edgeDash(edge: ThoughtGraphEdgeSnapshot): string | null {
    if (this.isOpposeEdge(edge) || edge.relation.toLowerCase() === 'depends_on') return '8 6';
    if (this.isSpeculativeEdge(edge)) return '4 4';
    return null;
  }

  private dragging = false;
  private dragStartX = 0;
  private dragStartY = 0;
  private dragOriginX = 0;
  private dragOriginY = 0;

  private observeSize(): void {
    const container = this.el.nativeElement.querySelector('.thought-viewer') as HTMLElement;
    if (!container) return;

    const update = () => {
      const rect = container.getBoundingClientRect();
      const w = Math.max(440, Math.round(rect.width));
      const h = Math.max(360, Math.round(rect.height));
      this.svgWidth.set(w);
      this.svgHeight.set(h);
      this.viewBox.set(`0 0 ${w} ${h}`);
      this.nodeRadius.set(Math.max(20, Math.min(28, Math.round(Math.min(w, h) / 22))));
      this.nodeWidth.set(Math.max(160, Math.min(240, Math.round(w / 5))));
      this.nodeHeight.set(Math.max(50, Math.min(72, Math.round(h / 10))));
      this.recalculateLayout();
    };

    this.ngZone.run(update);

    const ro = new ResizeObserver(() => {
      this.ngZone.run(update);
    });
    ro.observe(container);
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
    const svgW = this.svgWidth();
    const svgH = this.svgHeight();
    const pad = this.padding();
    const innerWidth = Math.max(1, svgW - pad * 2);
    const innerHeight = Math.max(1, svgH - pad * 2);
    const laneGap = innerHeight / 3;
    const laneGroups = new Map<number, ThoughtGraphNodeSnapshot[]>();
    for (const node of nodes) {
      const lane = this.nodeLane(node);
      const list = laneGroups.get(lane) ?? [];
      list.push(node);
      laneGroups.set(lane, list);
    }

    const activeRoots = new Set(
      (g.active_subgraphs ?? []).flatMap((subgraph) => subgraph.root_node_ids)
    );
    const sortedLanes = [0, 1, 2];
    const renderNodes: RenderNode[] = [];

    for (const lane of sortedLanes) {
      const laneNodes = (laneGroups.get(lane) ?? []).slice().sort((a, b) => {
        const activeA = activeRoots.has(a.node_id) ? 0 : 1;
        const activeB = activeRoots.has(b.node_id) ? 0 : 1;
        if (activeA !== activeB) return activeA - activeB;
        const confidenceDiff = (b.confidence ?? 0) - (a.confidence ?? 0);
        if (confidenceDiff !== 0) return confidenceDiff;
        return a.node_id.localeCompare(b.node_id);
      });
      const y = pad + lane * laneGap + laneGap / 2;
      const count = Math.max(1, laneNodes.length);
      laneNodes.forEach((node, index) => {
        const x = pad + ((index + 1) * innerWidth) / (count + 1);
        renderNodes.push({ node, x, y, lane });
      });
    }

    const nodeById = new Map(renderNodes.map((item) => [item.node.node_id, item]));
    const renderEdges = g.edges.map((edge) => ({
      edge,
      from: nodeById.get(edge.source_id),
      to: nodeById.get(edge.target_id),
    }));

    this.renderNodes.set(renderNodes);
    this.renderEdges.set(renderEdges);
    if (!this.selectedSubgraphId() && g.active_subgraphs?.length) {
      this.selectedSubgraphId.set(g.active_subgraphs[0].subgraph_id);
    }

    if (this.needsFit) {
      this.zoom.set(1);
      this.panX.set(0);
      this.panY.set(0);
      this.needsFit = false;
    }
  }
}
