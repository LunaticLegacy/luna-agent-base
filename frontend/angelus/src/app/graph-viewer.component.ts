import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import type { GraphEdgeSnapshot, GraphNodeSnapshot, GraphSnapshot } from './api.types';

interface RenderNode {
  node: GraphNodeSnapshot;
  x: number;
  y: number;
}

interface RenderEdge {
  edge: GraphEdgeSnapshot;
  from: RenderNode | undefined;
  to: RenderNode | undefined;
}

@Component({
  selector: 'app-graph-viewer',
  standalone: true,
  template: `
    <div class="graph-viewer">
      <svg
        [attr.viewBox]="viewBox"
        preserveAspectRatio="xMidYMid meet"
        class="graph-svg"
        role="img"
        [attr.aria-label]="ariaLabel"
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

        <!-- Edges -->
        @for (renderEdge of renderEdges; track renderEdge.edge.from_node_id + '-' + renderEdge.edge.to_node_id) {
          @if (renderEdge.from && renderEdge.to) {
            <line
              [attr.x1]="renderEdge.from.x"
              [attr.y1]="renderEdge.from.y"
              [attr.x2]="renderEdge.to.x"
              [attr.y2]="renderEdge.to.y"
              class="graph-edge"
              [class.active]="isEdgeActive(renderEdge.edge)"
              marker-end="url(#arrowhead)"
            />
          }
        }

        <!-- Nodes -->
        @for (renderNode of renderNodes; track renderNode.node.node_id) {
          <g
            class="graph-node"
            [class.entry]="renderNode.node.node_id === graph?.entry_node_id"
            [class.exit]="renderNode.node.node_id === graph?.exit_node_id"
            [class.active]="renderNode.node.node_id === activeNodeId"
          >
            <!-- Hexagon for center node, rect for others -->
            @if (isCenterNode(renderNode.node)) {
              <polygon
                [attr.points]="hexagonPoints(renderNode.x, renderNode.y, nodeRadius + 4)"
                class="graph-node-hex"
              />
            } @else {
              <rect
                [attr.x]="renderNode.x - nodeRadius - 2"
                [attr.y]="renderNode.y - nodeRadius * 0.6"
                [attr.width]="nodeRadius * 2 + 4"
                [attr.height]="nodeRadius * 1.2"
                rx="6"
                class="graph-node-rect"
              />
            }

            <!-- Active pulse ring -->
            @if (renderNode.node.node_id === activeNodeId) {
              <circle
                [attr.cx]="renderNode.x"
                [attr.cy]="renderNode.y"
                [attr.r]="nodeRadius + 10"
                fill="none"
                stroke="rgba(139, 92, 246, 0.25)"
                stroke-width="1.5"
                class="pulse-ring"
              />
            }

            <text
              [attr.x]="renderNode.x"
              [attr.y]="renderNode.y - 2"
              text-anchor="middle"
              class="graph-node-label"
            >
              {{ renderNode.node.node_name }}
            </text>
            <text
              [attr.x]="renderNode.x"
              [attr.y]="renderNode.y + 10"
              text-anchor="middle"
              class="graph-node-type"
            >
              {{ renderNode.node.node_type }}
            </text>
          </g>
        }
      </svg>
    </div>
  `,
  styleUrl: './graph-viewer.component.sass',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class GraphViewerComponent {
  @Input() graph: GraphSnapshot | null = null;
  @Input() activeNodeId: number | null = null;

  readonly svgWidth = 420;
  readonly svgHeight = 280;
  readonly nodeRadius = 22;
  readonly padding = 50;

  get viewBox(): string {
    return `0 0 ${this.svgWidth} ${this.svgHeight}`;
  }

  get ariaLabel(): string {
    const g = this.graph;
    if (!g) return 'Graph visualization';
    return `Graph ${g.graph_name} with ${g.node_count} nodes and ${g.edge_count} edges`;
  }

  isCenterNode(node: GraphNodeSnapshot): boolean {
    return node.node_id === this.graph?.entry_node_id;
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

  get renderNodes(): RenderNode[] {
    const g = this.graph;
    if (!g || g.nodes.length === 0) return [];

    const nodes = [...g.nodes];
    const entryId = g.entry_node_id ?? nodes[0]?.node_id;

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
        depths.set(node.node_id, maxDepth + 1);
      }
    }

    // Radial layout: entry at center, others around in rings
    const layers = new Map<number, GraphNodeSnapshot[]>();
    for (const node of nodes) {
      const d = depths.get(node.node_id) ?? 0;
      if (!layers.has(d)) layers.set(d, []);
      layers.get(d)!.push(node);
    }

    const result: RenderNode[] = [];
    const centerX = this.svgWidth / 2;
    const centerY = this.svgHeight / 2;

    // Entry node at center
    const entryNode = nodes.find((n) => n.node_id === entryId);
    if (entryNode) {
      result.push({ node: entryNode, x: centerX, y: centerY });
    }

    // Other nodes in concentric rings
    const sortedDepths = Array.from(layers.keys()).filter((d) => d > 0).sort((a, b) => a - b);
    const maxRing = sortedDepths.length > 0 ? Math.max(...sortedDepths) : 1;
    const maxRadius = Math.min(this.svgWidth, this.svgHeight) / 2 - this.padding;

    for (const depth of sortedDepths) {
      const layerNodes = layers.get(depth)!;
      const ringRadius = (depth / maxRing) * maxRadius;
      const angleStep = (2 * Math.PI) / layerNodes.length;
      // Offset angle so first node is at top
      const angleOffset = -Math.PI / 2;

      for (let i = 0; i < layerNodes.length; i++) {
        const angle = angleOffset + i * angleStep;
        const x = centerX + ringRadius * Math.cos(angle);
        const y = centerY + ringRadius * Math.sin(angle);
        result.push({ node: layerNodes[i], x, y });
      }
    }

    return result;
  }

  get renderEdges(): RenderEdge[] {
    const g = this.graph;
    if (!g) return [];
    const nodes = this.renderNodes;
    return g.edges.map((edge) => ({
      edge,
      from: nodes.find((n) => n.node.node_id === edge.from_node_id),
      to: nodes.find((n) => n.node.node_id === edge.to_node_id),
    }));
  }

  isEdgeActive(edge: GraphEdgeSnapshot): boolean {
    return edge.from_node_id === this.activeNodeId || edge.to_node_id === this.activeNodeId;
  }
}
