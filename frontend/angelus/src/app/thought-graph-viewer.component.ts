import { ChangeDetectionStrategy, Component, ElementRef, Input, NgZone, afterNextRender, inject, signal } from '@angular/core';
import type {
  ThinkingGraphEdgeSnapshot,
  ThinkingGraphNodeSnapshot,
  ThinkingGraphSnapshot,
  ThinkingGraphTransactionRecord,
} from './api.types';
import { thoughtRelationStyle } from './thought-graph.taxonomy';

type ThoughtNodeShape = 'circle' | 'diamond' | 'hexagon' | 'rect';

interface ThoughtNodeTheme {
  shape: ThoughtNodeShape;
  fill: string;
  stroke: string;
  glow: string;
  accent: string;
  label: string;
  subtle: string;
}

interface RenderNode {
  node: ThinkingGraphNodeSnapshot;
  x: number;
  y: number;
  depth: number;
  index: number;
  label: string;
  radius: number;
}

interface RenderEdge {
  edge: ThinkingGraphEdgeSnapshot;
  from: RenderNode | undefined;
  to: RenderNode | undefined;
  path: string;
  labelX: number;
  labelY: number;
  label: string;
}

@Component({
  selector: 'app-thought-graph-viewer',
  standalone: true,
  host: {
    class: 'thought-graph-viewer-host',
  },
  template: `
    <div class="thought-viewer" #container>
      <div class="graph-toolbar">
        <button type="button" class="graph-toolbar-btn" (click)="fitToGraph()">适配</button>
        <button type="button" class="graph-toolbar-btn" (click)="resetView()">重置</button>
      </div>
      <div class="graph-status">
        {{ graph?.node_count ?? 0 }} 节点 · {{ graph?.edge_count ?? 0 }} 边 ·
        {{ graph?.transaction_count ?? 0 }} 事务 · 缩放 {{ (zoom() * 100).toFixed(0) }}%
      </div>
      <svg
        #viewport
        [attr.viewBox]="viewBox()"
        preserveAspectRatio="none"
        class="graph-svg thought-svg"
        role="img"
        [attr.aria-label]="ariaLabel"
        (pointerdown)="onPointerDown($event)"
        (pointermove)="onPointerMove($event)"
        (pointerup)="onPointerUp($event)"
        (pointerleave)="onPointerUp($event)"
        (wheel)="onWheel($event)"
      >
        <defs>
          <marker id="thought-arrowhead" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="rgba(94, 234, 212, 0.5)" />
          </marker>
          <filter id="thought-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2.5" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g [attr.transform]="contentTransform()">
          @for (renderEdge of renderEdges(); track renderEdge.edge.id) {
            @if (renderEdge.from && renderEdge.to) {
              <g
                class="thought-edge-group"
                [class.active]="isHighlightedEdge(renderEdge.edge)"
                [style.--edge-stroke]="relationTheme(renderEdge.edge).stroke"
                [style.--edge-glow]="relationTheme(renderEdge.edge).glow"
              >
                <path
                  [attr.d]="renderEdge.path"
                  class="thought-edge"
                  [attr.stroke-dasharray]="relationTheme(renderEdge.edge).dash"
                  marker-end="url(#thought-arrowhead)"
                />
                <text
                  [attr.x]="renderEdge.labelX"
                  [attr.y]="renderEdge.labelY"
                  text-anchor="middle"
                  class="thought-edge-label"
                >
                  {{ renderEdge.label }}
                </text>
                <title>{{ edgeTitle(renderEdge.edge) }}</title>
              </g>
            }
          }

          @for (renderNode of renderNodes(); track renderNode.node.id) {
            <g
              class="thought-node"
              [class.active]="isHighlightedNode(renderNode.node)"
              [class.supported]="nodeType(renderNode.node) === 'evidence' || nodeType(renderNode.node) === 'observation' || nodeType(renderNode.node) === 'memory'"
              [class.diagnostic]="nodeType(renderNode.node) === 'question' || nodeType(renderNode.node) === 'critique' || nodeType(renderNode.node) === 'error'"
              [style.--node-fill]="nodeTheme(renderNode.node).fill"
              [style.--node-stroke]="nodeTheme(renderNode.node).stroke"
              [style.--node-glow]="nodeTheme(renderNode.node).glow"
              [style.--node-accent]="nodeTheme(renderNode.node).accent"
              [style.--node-label]="nodeTheme(renderNode.node).label"
              [style.--node-subtle]="nodeTheme(renderNode.node).subtle"
              [style.--node-radius.px]="renderNode.radius"
            >
              <circle
                [attr.cx]="renderNode.x"
                [attr.cy]="renderNode.y"
                [attr.r]="renderNode.radius"
                class="thought-node-shape thought-node-circle"
              />

              @if (isHighlightedNode(renderNode.node)) {
                <circle
                  [attr.cx]="renderNode.x"
                  [attr.cy]="renderNode.y"
                  [attr.r]="renderNode.radius + 16"
                  fill="none"
                  stroke="rgba(94, 234, 212, 0.22)"
                  stroke-width="1.5"
                  class="thought-pulse"
                />
              }

              <text [attr.x]="renderNode.x" [attr.y]="renderNode.y + renderNode.radius + 24" text-anchor="middle" class="thought-node-label">
                {{ renderNode.label }}
              </text>
              <text [attr.x]="renderNode.x" [attr.y]="renderNode.y + renderNode.radius + 40" text-anchor="middle" class="thought-node-type">
                {{ typeLabel(renderNode.node) }}
              </text>
              <title>{{ nodeTitle(renderNode.node) }}</title>
            </g>
          }
        </g>
      </svg>
    </div>
  `,
  styleUrls: ['./thought-graph-viewer.component.sass'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ThoughtGraphViewerComponent {
  @Input() graph: ThinkingGraphSnapshot | null = null;

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
  readonly nodeRadius = signal(24);
  readonly nodeWidth = signal(192);
  readonly nodeHeight = signal(82);
  readonly padding = signal(64);
  readonly viewBox = signal('0 0 800 520');
  readonly renderNodes = signal<RenderNode[]>([]);
  readonly renderEdges = signal<RenderEdge[]>([]);
  readonly zoom = signal(1);
  readonly panX = signal(0);
  readonly panY = signal(0);
  private needsFit = true;

  constructor() {
    afterNextRender(() => {
      this.observeSize();
    });
  }

  get ariaLabel(): string {
    const g = this.graph;
    if (!g) return '思维图谱可视化';
    return `思维图谱版本 ${g.version}，包含 ${g.node_count} 个节点和 ${g.edge_count} 条边`;
  }

  nodeType(node: ThinkingGraphNodeSnapshot): string {
    return String(node.node_type || 'unknown').toLowerCase();
  }

  nodeShape(node: ThinkingGraphNodeSnapshot): ThoughtNodeShape {
    const type = this.nodeType(node);
    if (['evidence', 'observation', 'memory'].includes(type)) return 'circle';
    if (['goal', 'question', 'assumption'].includes(type)) return 'hexagon';
    if (['hypothesis', 'guess', 'risk', 'counterevidence'].includes(type)) return 'diamond';
    return 'rect';
  }

  nodeTheme(node: ThinkingGraphNodeSnapshot): ThoughtNodeTheme {
    const type = this.nodeType(node);
    switch (type) {
      case 'goal':
        return { shape: 'hexagon', fill: 'rgba(124, 58, 237, 0.22)', stroke: 'rgba(221, 214, 254, 0.96)', glow: 'rgba(168, 85, 247, 0.42)', accent: 'rgba(221, 214, 254, 0.96)', label: '#faf5ff', subtle: '#e9d5ff' };
      case 'question':
        return { shape: 'hexagon', fill: 'rgba(192, 38, 211, 0.20)', stroke: 'rgba(244, 114, 182, 0.94)', glow: 'rgba(236, 72, 153, 0.38)', accent: 'rgba(244, 114, 182, 0.94)', label: '#fdf2f8', subtle: '#fbcfe8' };
      case 'assumption':
        return { shape: 'hexagon', fill: 'rgba(71, 85, 105, 0.26)', stroke: 'rgba(203, 213, 225, 0.94)', glow: 'rgba(148, 163, 184, 0.30)', accent: 'rgba(203, 213, 225, 0.94)', label: '#f8fafc', subtle: '#cbd5e1' };
      case 'claim':
        return { shape: 'rect', fill: 'rgba(37, 99, 235, 0.24)', stroke: 'rgba(147, 197, 253, 0.94)', glow: 'rgba(59, 130, 246, 0.38)', accent: 'rgba(147, 197, 253, 0.94)', label: '#eff6ff', subtle: '#bfdbfe' };
      case 'decision':
        return { shape: 'rect', fill: 'rgba(22, 163, 74, 0.22)', stroke: 'rgba(134, 239, 172, 0.95)', glow: 'rgba(34, 197, 94, 0.40)', accent: 'rgba(134, 239, 172, 0.95)', label: '#f0fdf4', subtle: '#bbf7d0' };
      case 'plan':
        return { shape: 'rect', fill: 'rgba(139, 92, 246, 0.24)', stroke: 'rgba(196, 181, 253, 0.96)', glow: 'rgba(168, 85, 247, 0.40)', accent: 'rgba(196, 181, 253, 0.96)', label: '#faf5ff', subtle: '#ddd6fe' };
      case 'step':
        return { shape: 'rect', fill: 'rgba(124, 58, 237, 0.22)', stroke: 'rgba(216, 180, 254, 0.96)', glow: 'rgba(192, 132, 252, 0.38)', accent: 'rgba(216, 180, 254, 0.96)', label: '#faf5ff', subtle: '#e9d5ff' };
      case 'summary':
        return { shape: 'rect', fill: 'rgba(10, 17, 30, 0.84)', stroke: 'rgba(94, 234, 212, 0.42)', glow: 'rgba(94, 234, 212, 0.24)', accent: 'rgba(94, 234, 212, 0.84)', label: '#e2e8f0', subtle: '#94a3b8' };
      case 'evidence':
        return { shape: 'circle', fill: 'rgba(14, 116, 144, 0.26)', stroke: 'rgba(103, 232, 249, 0.96)', glow: 'rgba(34, 211, 238, 0.45)', accent: 'rgba(103, 232, 249, 0.96)', label: '#ecfeff', subtle: '#a5f3fc' };
      case 'observation':
        return { shape: 'circle', fill: 'rgba(5, 150, 105, 0.24)', stroke: 'rgba(110, 231, 183, 0.94)', glow: 'rgba(16, 185, 129, 0.42)', accent: 'rgba(110, 231, 183, 0.94)', label: '#ecfdf5', subtle: '#a7f3d0' };
      case 'hypothesis':
        return { shape: 'diamond', fill: 'rgba(217, 119, 6, 0.24)', stroke: 'rgba(253, 230, 138, 0.96)', glow: 'rgba(245, 158, 11, 0.42)', accent: 'rgba(253, 230, 138, 0.96)', label: '#fffbeb', subtle: '#fde68a' };
      case 'guess':
        return { shape: 'diamond', fill: 'rgba(234, 88, 12, 0.22)', stroke: 'rgba(254, 215, 170, 0.94)', glow: 'rgba(251, 146, 60, 0.38)', accent: 'rgba(254, 215, 170, 0.94)', label: '#fff7ed', subtle: '#fdba74' };
      case 'risk':
        return { shape: 'diamond', fill: 'rgba(153, 27, 27, 0.26)', stroke: 'rgba(252, 165, 165, 0.96)', glow: 'rgba(248, 113, 113, 0.42)', accent: 'rgba(252, 165, 165, 0.96)', label: '#fef2f2', subtle: '#fecaca' };
      case 'counterevidence':
        return { shape: 'diamond', fill: 'rgba(159, 18, 57, 0.26)', stroke: 'rgba(251, 113, 133, 0.96)', glow: 'rgba(244, 63, 94, 0.40)', accent: 'rgba(251, 113, 133, 0.96)', label: '#fff1f2', subtle: '#fda4af' };
      case 'memory':
        return { shape: 'circle', fill: 'rgba(124, 58, 237, 0.20)', stroke: 'rgba(216, 180, 254, 0.94)', glow: 'rgba(192, 132, 252, 0.36)', accent: 'rgba(216, 180, 254, 0.94)', label: '#faf5ff', subtle: '#ddd6fe' };
      case 'artifact':
        return { shape: 'rect', fill: 'rgba(180, 83, 9, 0.24)', stroke: 'rgba(252, 211, 77, 0.96)', glow: 'rgba(245, 158, 11, 0.40)', accent: 'rgba(252, 211, 77, 0.96)', label: '#fffbeb', subtle: '#fde68a' };
      case 'action':
        return { shape: 'rect', fill: 'rgba(6, 182, 212, 0.20)', stroke: 'rgba(165, 243, 252, 0.94)', glow: 'rgba(34, 211, 238, 0.34)', accent: 'rgba(165, 243, 252, 0.94)', label: '#ecfeff', subtle: '#a5f3fc' };
      case 'critique':
        return { shape: 'diamond', fill: 'rgba(219, 39, 119, 0.24)', stroke: 'rgba(249, 168, 212, 0.96)', glow: 'rgba(236, 72, 153, 0.38)', accent: 'rgba(249, 168, 212, 0.96)', label: '#fdf2f8', subtle: '#fbcfe8' };
      case 'error':
        return { shape: 'diamond', fill: 'rgba(127, 29, 29, 0.26)', stroke: 'rgba(252, 165, 165, 0.96)', glow: 'rgba(248, 113, 113, 0.42)', accent: 'rgba(252, 165, 165, 0.96)', label: '#fef2f2', subtle: '#fecaca' };
      default:
        return { shape: this.nodeShape(node), fill: 'rgba(30, 41, 59, 0.28)', stroke: 'rgba(148, 163, 184, 0.9)', glow: 'rgba(148, 163, 184, 0.22)', accent: 'rgba(148, 163, 184, 0.9)', label: '#f8fafc', subtle: '#cbd5e1' };
    }
  }

  labelForNode(node: ThinkingGraphNodeSnapshot, index = 0): string {
    const text = (node.info || node.description || String(node.id)).trim().replace(/\s+/g, ' ');
    const clipped = text.length > 26 ? `${text.slice(0, 26)}…` : text;
    return `${index + 1}. ${clipped}`;
  }

  typeLabel(node: ThinkingGraphNodeSnapshot): string {
    return this.nodeType(node).replace(/_/g, ' ').toUpperCase();
  }

  relationLabel(edge: ThinkingGraphEdgeSnapshot): string {
    return edge.edge_type.replace(/_/g, ' ');
  }

  relationTheme(edge: ThinkingGraphEdgeSnapshot) {
    return thoughtRelationStyle(edge.edge_type);
  }

  nodeTitle(node: ThinkingGraphNodeSnapshot): string {
    const parts = [
      `${this.typeLabel(node)} · confidence ${(node.confidence ?? 0).toFixed(2)}`,
      node.created_by ? `created_by: ${node.created_by}` : '',
      node.description ? `description: ${node.description}` : '',
      node.info ? `info: ${node.info}` : '',
      node.tags?.length ? `tags: ${node.tags.join(', ')}` : '',
      node.payload ? `payload: ${JSON.stringify(node.payload)}` : '',
    ].filter(Boolean);
    return parts.join('\n');
  }

  edgeTitle(edge: ThinkingGraphEdgeSnapshot): string {
    const relation = edge.edge_type.replace(/_/g, ' ');
    const detail = edge.description ? ` · ${edge.description}` : '';
    return `${relation} · strength ${(edge.strength ?? 0).toFixed(2)}${detail}`;
  }

  latestTransaction(): ThinkingGraphTransactionRecord | null {
    const log = this.graph?.transaction_log ?? [];
    return log.length > 0 ? log[log.length - 1] : null;
  }

  isHighlightedNode(node: ThinkingGraphNodeSnapshot): boolean {
    const tx = this.latestTransaction();
    return tx?.object_kind === 'node' && tx.object_id === node.id;
  }

  isHighlightedEdge(edge: ThinkingGraphEdgeSnapshot): boolean {
    const tx = this.latestTransaction();
    return tx?.object_kind === 'edge' && tx.object_id === edge.id;
  }

  isSupportEdge(edge: ThinkingGraphEdgeSnapshot): boolean {
    return ['supports', 'verifies', 'produces', 'refines', 'evidence_for'].includes(edge.edge_type.toLowerCase());
  }

  isOpposeEdge(edge: ThinkingGraphEdgeSnapshot): boolean {
    return ['opposes', 'disproves', 'questions', 'contradicts'].includes(edge.edge_type.toLowerCase());
  }

  isSpeculativeEdge(edge: ThinkingGraphEdgeSnapshot): boolean {
    return ['speculates', 'relates', 'leads_to', 'depends_on', 'derives_from', 'requires', 'blocks', 'answers'].includes(edge.edge_type.toLowerCase());
  }

  edgeDash(edge: ThinkingGraphEdgeSnapshot): string | null {
    return this.relationTheme(edge).dash;
  }

  activeHaloRadius(): number {
    return this.nodeRadius() + 16;
  }

  radiusForNode(node: ThinkingGraphNodeSnapshot): number {
    const type = this.nodeType(node);
    const base = this.nodeRadius();
    if (['evidence', 'observation', 'memory'].includes(type)) return base + 2;
    if (['action', 'artifact'].includes(type)) return base + 1;
    if (['claim', 'decision', 'summary'].includes(type)) return base + 1;
    if (['goal', 'question', 'assumption', 'hypothesis', 'guess', 'risk', 'counterevidence'].includes(type)) return base + 3;
    return base;
  }

  edgePath(from: RenderNode, to: RenderNode, edge: ThinkingGraphEdgeSnapshot): { path: string; labelX: number; labelY: number } {
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const distance = Math.max(1, Math.hypot(dx, dy));
    const fromRadius = Math.max(10, from.radius);
    const toRadius = Math.max(10, to.radius);
    const startX = from.x + (dx / distance) * fromRadius;
    const startY = from.y + (dy / distance) * fromRadius;
    const endX = to.x - (dx / distance) * toRadius;
    const endY = to.y - (dy / distance) * toRadius;
    const midX = (startX + endX) / 2;
    const midY = (startY + endY) / 2;
    const normalX = -dy / distance;
    const normalY = dx / distance;
    const curvatureSeed = `${edge.id}:${edge.edge_type}:${edge.source_id}:${edge.target_id}`;
    let hash = 0;
    for (let i = 0; i < curvatureSeed.length; i += 1) {
      hash = (hash * 33 + curvatureSeed.charCodeAt(i)) | 0;
    }
    const relationBias = this.isOpposeEdge(edge) ? 1 : this.isSupportEdge(edge) ? -1 : 0;
    const bend = Math.min(72, Math.max(16, distance * 0.18)) * (((hash % 3) - 1) * 0.55 + relationBias * 0.28);
    const controlX = midX + normalX * bend;
    const controlY = midY + normalY * bend;
    return {
      path: `M ${startX.toFixed(1)} ${startY.toFixed(1)} Q ${controlX.toFixed(1)} ${controlY.toFixed(1)} ${endX.toFixed(1)} ${endY.toFixed(1)}`,
      labelX: (startX + 2 * controlX + endX) / 4,
      labelY: (startY + 2 * controlY + endY) / 4,
    };
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

  diamondPoints(cx: number, cy: number, rx: number, ry: number): string {
    return [
      `${cx},${cy - ry}`,
      `${cx + rx},${cy}`,
      `${cx},${cy + ry}`,
      `${cx - rx},${cy}`,
    ].join(' ');
  }

  private observeSize(): void {
    const container = this.el.nativeElement.querySelector('.thought-viewer') as HTMLElement;
    if (!container) return;

    const update = () => {
      const rect = container.getBoundingClientRect();
      const w = Math.max(440, Math.round(rect.width));
      const h = Math.max(320, Math.round(rect.height));
      this.svgWidth.set(w);
      this.svgHeight.set(h);
      this.nodeRadius.set(Math.max(20, Math.min(28, Math.round(Math.min(w, h) / 18))));
      this.nodeWidth.set(Math.max(180, Math.min(260, Math.round(w / 4.4))));
      this.nodeHeight.set(Math.max(82, Math.min(112, Math.round(h / 5.2))));
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
    const nodes = this.sortedNodes();
    const edges = this.sortedEdges();
    if (!g || nodes.length === 0) {
      this.renderNodes.set([]);
      this.renderEdges.set([]);
      this.zoom.set(1);
      this.panX.set(0);
      this.panY.set(0);
      return;
    }

    const svgW = this.svgWidth();
    const svgH = this.svgHeight();
    const pad = this.padding();
    const fallbackOrder = new Map<number, number>(nodes.map((node, index) => [node.id, index]));
    const incomingCounts = new Map<number, number>(nodes.map((node) => [node.id, 0]));
    const outgoing = new Map<number, ThinkingGraphEdgeSnapshot[]>();

    for (const edge of edges) {
      if (incomingCounts.has(edge.target_id)) {
        incomingCounts.set(edge.target_id, (incomingCounts.get(edge.target_id) ?? 0) + 1);
      }
      const list = outgoing.get(edge.source_id) ?? [];
      list.push(edge);
      outgoing.set(edge.source_id, list);
    }

    const seeds = nodes.filter((node) => (incomingCounts.get(node.id) ?? 0) === 0).map((node) => node.id);
    if (seeds.length === 0 && nodes[0]) {
      seeds.push(nodes[0].id);
    }

    const depths = new Map<number, number>();
    const queue: { id: number; depth: number }[] = seeds.map((id) => ({ id, depth: 0 }));
    while (queue.length > 0) {
      const current = queue.shift()!;
      const knownDepth = depths.get(current.id);
      if (knownDepth !== undefined && knownDepth <= current.depth) {
        continue;
      }
      depths.set(current.id, current.depth);
      for (const edge of outgoing.get(current.id) ?? []) {
        queue.push({ id: edge.target_id, depth: current.depth + 1 });
      }
    }

    let maxDepth = 0;
    for (const depth of depths.values()) maxDepth = Math.max(maxDepth, depth);
    for (const node of nodes) {
      if (!depths.has(node.id)) {
        const bias = fallbackOrder.get(node.id) ?? 0;
        depths.set(node.id, maxDepth + 1 + bias * 0.02);
      }
    }

    const sortedNodes = nodes.slice().sort((a, b) => {
      const depthDiff = (depths.get(a.id) ?? 0) - (depths.get(b.id) ?? 0);
      if (depthDiff !== 0) return depthDiff;
      const confidenceDiff = (b.confidence ?? 0) - (a.confidence ?? 0);
      if (confidenceDiff !== 0) return confidenceDiff;
      return a.id - b.id;
    });

    const centerX = svgW / 2;
    const centerY = svgH / 2;
    const depthStep = Math.min(160, Math.max(110, svgW * 0.14));
    const orbit = Math.min(svgW, svgH) * 0.22;
    const layerCounts = new Map<number, number>();
    const initialState = new Map<number, { x: number; y: number; vx: number; vy: number }>();

    for (let index = 0; index < sortedNodes.length; index += 1) {
      const node = sortedNodes[index];
      const depth = Math.round(depths.get(node.id) ?? 0);
      const layerIndex = layerCounts.get(depth) ?? 0;
      layerCounts.set(depth, layerIndex + 1);

      const angle = ((index + 1) / (sortedNodes.length + 1)) * Math.PI * 2;
      const radial = orbit + depth * depthStep * 0.42 + layerIndex * 10;
      initialState.set(node.id, {
        x: centerX + Math.cos(angle) * radial,
        y: centerY + Math.sin(angle) * radial * 0.78,
        vx: 0,
        vy: 0,
      });
    }

    const renderedNodes = sortedNodes.map((node, index) => {
      const depth = Math.round(depths.get(node.id) ?? 0);
      const radius = this.radiusForNode(node);
      const label = this.labelForNode(node, index);
      return {
        node,
        x: initialState.get(node.id)?.x ?? centerX,
        y: initialState.get(node.id)?.y ?? centerY,
        depth,
        index,
        label,
        radius,
      };
    });

    const states = new Map(renderedNodes.map((item) => [item.node.id, {
      x: item.x,
      y: item.y,
      vx: 0,
      vy: 0,
    }]));

    const repulsion = Math.min(120000, Math.max(45000, svgW * svgH * 0.22));
    const spring = 0.010;
    const centerPull = 0.008;
    const edgeIdeal = Math.min(190, Math.max(120, Math.round(Math.min(svgW, svgH) / 3.8)));
    const iterations = 90;

    for (let iter = 0; iter < iterations; iter += 1) {
      const alpha = 1 - iter / iterations;

      for (let i = 0; i < renderedNodes.length; i += 1) {
        const a = renderedNodes[i];
        const sa = states.get(a.node.id)!;
        for (let j = i + 1; j < renderedNodes.length; j += 1) {
          const b = renderedNodes[j];
          const sb = states.get(b.node.id)!;
          const dx = sb.x - sa.x;
          const dy = sb.y - sa.y;
          const dist2 = Math.max(36, dx * dx + dy * dy);
          const dist = Math.sqrt(dist2);
          const force = (repulsion * alpha) / dist2;
          const nx = dx / dist;
          const ny = dy / dist;
          sa.vx -= nx * force;
          sa.vy -= ny * force;
          sb.vx += nx * force;
          sb.vy += ny * force;
        }
      }

      for (const edge of edges) {
        const source = states.get(edge.source_id);
        const target = states.get(edge.target_id);
        if (!source || !target) continue;
        const dx = target.x - source.x;
        const dy = target.y - source.y;
        const dist = Math.max(24, Math.hypot(dx, dy));
        const desired = edgeIdeal + (this.isSupportEdge(edge) ? -14 : this.isOpposeEdge(edge) ? 10 : this.isSpeculativeEdge(edge) ? 20 : 0);
        const force = spring * alpha * (dist - desired);
        const nx = dx / dist;
        const ny = dy / dist;
        source.vx += nx * force;
        source.vy += ny * force;
        target.vx -= nx * force;
        target.vy -= ny * force;
      }

      for (const item of renderedNodes) {
        const state = states.get(item.node.id)!;
        const highlightBias = this.isHighlightedNode(item.node) ? 0.022 : 0.010;
        state.vx += (centerX - state.x) * centerPull * highlightBias;
        state.vy += (centerY - state.y) * centerPull * (highlightBias * 0.9);
        state.x += state.vx;
        state.y += state.vy;
        state.vx *= 0.82;
        state.vy *= 0.82;

        const limitX = Math.max(96, svgW / 2 - pad);
        const limitY = Math.max(76, svgH / 2 - pad);
        state.x = Math.min(centerX + limitX, Math.max(centerX - limitX, state.x));
        state.y = Math.min(centerY + limitY, Math.max(centerY - limitY, state.y));
      }
    }

    for (const item of renderedNodes) {
      const state = states.get(item.node.id)!;
      item.x = state.x;
      item.y = state.y;
    }

    this.renderNodes.set(renderedNodes);
    this.renderEdges.set(
      edges.map((edge) => {
        const from = renderedNodes.find((item) => item.node.id === edge.source_id);
        const to = renderedNodes.find((item) => item.node.id === edge.target_id);
        const pathInfo = from && to ? this.edgePath(from, to, edge) : { path: '', labelX: 0, labelY: 0 };
        return {
          edge,
          from,
          to,
          path: pathInfo.path,
          labelX: pathInfo.labelX,
          labelY: pathInfo.labelY,
          label: this.relationLabel(edge),
        };
      })
    );

    if (this.needsFit) {
      this.needsFit = false;
      queueMicrotask(() => this.fitToGraph());
    }
  }

  ngOnChanges(): void {
    this.needsFit = true;
    this.recalculateLayout();
  }

  private sortedNodes(): ThinkingGraphNodeSnapshot[] {
    const entries = Object.values(this.graph?.nodes ?? {});
    return entries.slice().sort((a, b) => a.id - b.id);
  }

  private sortedEdges(): ThinkingGraphEdgeSnapshot[] {
    const entries = Object.values(this.graph?.edges ?? {});
    return entries.slice().sort((a, b) => a.id - b.id);
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
    const edgeLabelPad = 28;
    const labelPadX = 104;
    const labelPadY = 62;
    let minX = Number.POSITIVE_INFINITY;
    let minY = Number.POSITIVE_INFINITY;
    let maxX = Number.NEGATIVE_INFINITY;
    let maxY = Number.NEGATIVE_INFINITY;

    for (const item of nodes) {
      const widthPad = Math.max(item.radius + 26, labelPadX);
      const heightPad = Math.max(item.radius + labelPadY, nr + 42);
      minX = Math.min(minX, item.x - widthPad);
      minY = Math.min(minY, item.y - heightPad);
      maxX = Math.max(maxX, item.x + widthPad);
      maxY = Math.max(maxY, item.y + heightPad + edgeLabelPad * 0.4);
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
