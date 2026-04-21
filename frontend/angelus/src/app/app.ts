import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from './api.service';
import {
  ApiIndexResponse,
  GraphEdgeSnapshot,
  GraphNodeSnapshot,
  GraphSnapshot,
  HealthResponse,
  ReadyResponse,
  RunEvent,
  RunSnapshot,
  StartSwarmRunResponse,
  SwarmDetails,
  SwarmSummary,
} from './api.types';

interface MarkdownBlock {
  kind: 'heading' | 'paragraph' | 'list' | 'quote' | 'code' | 'divider';
  html: string;
}

interface FactRow {
  key: string;
  value: string;
}

interface ResultSection {
  title: string;
  facts: FactRow[];
  blocks: MarkdownBlock[];
  rawJson: string;
}

interface TraceView {
  title: string;
  status: string;
  branch: string;
  meta: FactRow[];
  inputBlocks: MarkdownBlock[];
  outputBlocks: MarkdownBlock[];
  error: string | null;
  rawJson: string;
}

interface ResultView {
  summary: FactRow[];
  sections: ResultSection[];
  trace: TraceView[];
  rawJson: string;
}

interface GraphNodeView extends GraphNodeSnapshot {
  status: 'pending' | 'running' | 'completed' | 'failed';
  isEntry: boolean;
  isExit: boolean;
}

interface GraphEdgeView extends GraphEdgeSnapshot {
  active: boolean;
}

interface GraphView {
  graphName: string;
  entryNodeId: number | null;
  exitNodeId: number | null;
  nodeCount: number;
  edgeCount: number;
  currentNodeId: number | null;
  currentNodeName: string | null;
  currentNodeType: string | null;
  status: string | null;
  rounds: number;
  nodes: GraphNodeView[];
  edges: GraphEdgeView[];
  rawJson: string;
}

interface GraphSpectrumNodeView extends GraphNodeView {
  x: number;
  y: number;
  width: number;
  height: number;
  labelLines: string[];
}

interface GraphSpectrumEdgeView extends GraphEdgeView {
  d: string;
}

interface GraphSpectrumView {
  width: number;
  height: number;
  viewBox: string;
  zoom: number;
  panX: number;
  panY: number;
  panTransform: string;
  scaleTransform: string;
  nodes: GraphSpectrumNodeView[];
  edges: GraphSpectrumEdgeView[];
  rawJson: string;
}

interface GraphDragState {
  pointerId: number;
  startClientX: number;
  startClientY: number;
  originPanX: number;
  originPanY: number;
}

interface RunEventView {
  eventType: string;
  title: string;
  timestamp: string;
  status: string;
  nodeName: string;
  branch: string;
  summary: string;
  rawJson: string;
}

interface RunLiveView {
  run: RunSnapshot;
  events: RunEventView[];
  stateView: ResultView | null;
  finalStateView: ResultView | null;
  rawJson: string;
}

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.sass'
})
export class App implements OnDestroy {
  private readonly api = inject(ApiService);
  private runEventSource: EventSource | null = null;
  private graphDragState: GraphDragState | null = null;
  private readonly runEventTypes = [
    'run.started',
    'node.started',
    'node.completed',
    'node.failed',
    'branch.started',
    'branch.completed',
    'branch.failed',
    'run.completed',
    'run.failed',
  ];

  protected readonly title = signal('Angelus Swarm Console');
  protected readonly apiBaseUrl = signal('/api');
  protected readonly loading = signal(false);
  protected readonly executionLoading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly graphError = signal<string | null>(null);
  protected readonly runError = signal<string | null>(null);

  protected readonly apiIndex = signal<ApiIndexResponse | null>(null);
  protected readonly health = signal<HealthResponse | null>(null);
  protected readonly ready = signal<ReadyResponse | null>(null);
  protected readonly swarms = signal<SwarmSummary[]>([]);
  protected readonly selectedSwarmName = signal<string | null>(null);
  protected readonly selectedSwarm = signal<SwarmDetails | null>(null);
  protected readonly selectedGraph = signal<GraphSnapshot | null>(null);
  protected readonly selectedAgentId = signal<string | null>(null);
  protected readonly graphTab = signal<'snapshot' | 'spectrum'>('spectrum');
  protected readonly controlMode = signal<'agent' | 'swarm'>('agent');
  protected readonly agentPage = signal<'input' | 'output'>('input');
  protected readonly swarmPage = signal<'input' | 'output'>('input');
  protected readonly graphZoom = signal(1);
  protected readonly graphPanX = signal(0);
  protected readonly graphPanY = signal(0);
  protected readonly graphDragging = signal(false);
  protected readonly activeRun = signal<RunSnapshot | null>(null);
  protected readonly activeRunEvents = signal<RunEventView[]>([]);
  protected readonly activeRunCompleted = signal(false);
  protected readonly agentRunOutput = signal<Record<string, unknown> | null>(null);
  protected readonly agentRunView = computed(() => this.buildAgentRunView(this.agentRunOutput()));
  protected readonly swarmTask = signal('Draft a concise swarm summary for the selected workflow.');
  protected readonly swarmContext = signal('Use the selected swarm as the source of truth and keep the answer grounded in its output.');
  protected readonly swarmAudience = signal('General audience');
  protected readonly swarmOutputFormat = signal('Markdown summary with headings and bullets.');
  protected readonly swarmConstraints = signal('');
  protected readonly swarmRequestPayload = computed(() => this.buildSwarmRequestPayload());
  protected readonly swarmRequestView = computed(() => this.buildPayloadView(this.swarmRequestPayload()));
  protected readonly graphView = computed(() => this.buildGraphView(this.selectedGraph(), this.activeRun()));
  protected readonly graphSpectrumView = computed(() => this.buildGraphSpectrumView(this.graphView(), this.graphZoom()));
  protected readonly liveRunView = computed(() => this.buildRunLiveView(this.activeRun(), this.activeRunEvents()));

  protected readonly availableAgentIds = computed(() => {
    const swarm = this.selectedSwarm();
    if (!swarm) {
      return [];
    }
    return swarm.agent_files
      .map((fileName: string): string => fileName.split('/').pop()?.replace('.py', '') ?? '')
      .filter((value: string): value is string => Boolean(value));
  });

  protected readonly selectedSummary = computed(() => {
    const name = this.selectedSwarmName();
    return this.swarms().find((item) => item.swarm_name === name) ?? null;
  });

  protected readonly swarmRounds = signal(0);

  protected readonly agentMessage = signal('Please review the latest task state and respond.');
  protected readonly agentRounds = signal(0);
  protected readonly agentAdditionalPrompt = signal('');

  constructor() {
    void this.loadOverview();
  }

  ngOnDestroy() {
    this.closeRunStream();
  }

  async loadOverview() {
    this.loading.set(true);
    this.error.set(null);
    try {
      const [apiIndex, health, ready, swarms] = await Promise.all([
        this.api.index(this.apiBaseUrl()),
        this.api.health(this.apiBaseUrl()),
        this.api.ready(this.apiBaseUrl()),
        this.api.listSwarms(this.apiBaseUrl()),
      ]);

      this.apiIndex.set(apiIndex);
      this.health.set(health);
      this.ready.set(ready);
      this.swarms.set(swarms.swarms);

      if (!this.selectedSwarmName() && swarms.swarms.length > 0) {
        await this.selectSwarm(swarms.swarms[0].swarm_name);
      } else if (this.selectedSwarmName()) {
        await this.reloadSelectedSwarm();
        await this.reloadSelectedGraph();
      }
    } catch (error) {
      this.error.set(this.formatError(error));
    } finally {
      this.loading.set(false);
    }
  }

  async selectSwarm(swarmName: string) {
    this.closeRunStream();
    this.activeRun.set(null);
    this.activeRunEvents.set([]);
    this.activeRunCompleted.set(false);
    this.runError.set(null);
    this.graphError.set(null);
    this.graphZoom.set(1);
    this.graphPanX.set(0);
    this.graphPanY.set(0);
    this.graphDragging.set(false);
    this.graphDragState = null;
    this.graphTab.set('spectrum');
    this.controlMode.set('agent');
    this.agentPage.set('input');
    this.swarmPage.set('input');
    this.selectedSwarmName.set(swarmName);
    await this.reloadSelectedSwarm();
    await this.reloadSelectedGraph();
  }

  async reloadSelectedSwarm() {
    const name = this.selectedSwarmName();
    if (!name) {
      this.selectedSwarm.set(null);
      return;
    }

    try {
      const response = await this.api.getSwarm(this.apiBaseUrl(), name);
      this.selectedSwarm.set(response.swarm);
      this.syncAgentDefaults(response.swarm);
    } catch (error) {
      this.error.set(this.formatError(error));
    }
  }

  async reloadSelectedGraph() {
    const name = this.selectedSwarmName();
    if (!name) {
      this.selectedGraph.set(null);
      return;
    }

    this.graphError.set(null);
    try {
      const response = await this.api.getSwarmGraph(this.apiBaseUrl(), name);
      this.selectedGraph.set(response.graph);
    } catch (error) {
      this.graphError.set(this.formatError(error));
      this.selectedGraph.set(null);
    }
  }

  setGraphTab(value: 'snapshot' | 'spectrum') {
    this.graphTab.set(value);
  }

  setControlMode(value: 'agent' | 'swarm') {
    this.controlMode.set(value);
  }

  setAgentPage(value: 'input' | 'output') {
    this.agentPage.set(value);
  }

  setSwarmPage(value: 'input' | 'output') {
    this.swarmPage.set(value);
  }

  zoomGraphIn() {
    this.graphZoom.set(this.clampGraphZoom(this.graphZoom() + 0.2));
  }

  zoomGraphOut() {
    this.graphZoom.set(this.clampGraphZoom(this.graphZoom() - 0.2));
  }

  resetGraphZoom() {
    this.graphZoom.set(1);
    this.graphPanX.set(0);
    this.graphPanY.set(0);
    this.graphDragging.set(false);
    this.graphDragState = null;
  }

  startGraphDrag(event: PointerEvent) {
    if (!this.graphSpectrumView()) {
      return;
    }

    const target = event.target as Element | null;
    if (target?.closest('button, a, input, textarea, select, summary, details')) {
      return;
    }

    const currentTarget = event.currentTarget as SVGSVGElement | null;
    event.preventDefault();
    currentTarget?.setPointerCapture(event.pointerId);
    this.graphDragging.set(true);
    this.graphDragState = {
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      originPanX: this.graphPanX(),
      originPanY: this.graphPanY(),
    };
  }

  moveGraphDrag(event: PointerEvent) {
    const drag = this.graphDragState;
    if (!drag || drag.pointerId !== event.pointerId) {
      return;
    }

    event.preventDefault();
    const zoom = this.graphSpectrumView()?.zoom ?? this.graphZoom();
    const deltaX = (event.clientX - drag.startClientX) / zoom;
    const deltaY = (event.clientY - drag.startClientY) / zoom;
    this.graphPanX.set(drag.originPanX + deltaX);
    this.graphPanY.set(drag.originPanY + deltaY);
  }

  endGraphDrag(event: PointerEvent) {
    const drag = this.graphDragState;
    if (!drag || drag.pointerId !== event.pointerId) {
      return;
    }

    const currentTarget = event.currentTarget as SVGSVGElement | null;
    if (currentTarget?.hasPointerCapture(event.pointerId)) {
      currentTarget.releasePointerCapture(event.pointerId);
    }
    this.graphDragging.set(false);
    this.graphDragState = null;
  }

  async runSwarm() {
    const name = this.selectedSwarmName();
    if (!name) {
      this.runError.set('Select a swarm before running it.');
      return;
    }

    const payload = this.swarmRequestPayload();
    if (!this.safeString(payload['text'])) {
      this.runError.set('Task is required before starting the run.');
      return;
    }

    this.executionLoading.set(true);
    this.runError.set(null);
    try {
      const response = await this.api.startSwarmRun(this.apiBaseUrl(), name, {
        input: payload,
        rounds: this.swarmRounds(),
      });
      this.beginRunFollow(response);
    } catch (error) {
      this.runError.set(this.formatError(error));
    } finally {
      this.executionLoading.set(false);
    }
  }

  async runSelectedAgent() {
    const swarm = this.selectedSwarm();
    if (!swarm) {
      this.runError.set('Select a swarm before running an agent.');
      return;
    }

    const agentId = this.selectedAgentId();
    if (!agentId) {
      this.runError.set('The selected swarm has no agents.');
      return;
    }

    this.executionLoading.set(true);
    this.runError.set(null);
    try {
      const response = await this.api.runAgentRound(this.apiBaseUrl(), swarm.swarm_name, agentId, {
        message: this.agentMessage().trim(),
        rounds: this.agentRounds(),
        additional_prompt: this.agentAdditionalPrompt().trim() || undefined,
      });
      this.agentRunOutput.set(response as unknown as Record<string, unknown>);
    } catch (error) {
      this.runError.set(this.formatError(error));
    } finally {
      this.executionLoading.set(false);
    }
  }

  private beginRunFollow(response: StartSwarmRunResponse) {
    this.closeRunStream();
    this.activeRun.set(response.run);
    this.activeRunEvents.set([]);
    this.activeRunCompleted.set(false);
    void this.refreshRunSnapshot(response.run.run_id);
    this.openRunStream(response.run.run_id);
  }

  private async refreshRunSnapshot(runId: string) {
    try {
      const response = await this.api.getRun(this.apiBaseUrl(), runId);
      this.activeRun.set(response.run);
    } catch (error) {
      this.runError.set(this.formatError(error));
    }
  }

  private openRunStream(runId: string) {
    const eventSource = this.api.streamRunEvents(this.apiBaseUrl(), runId);
    this.runEventSource = eventSource;
    this.runEventTypes.forEach((eventType) => {
      eventSource.addEventListener(eventType, (event) => this.handleRunEvent(eventType, event as MessageEvent));
    });
    eventSource.onerror = () => {
      if (this.runEventSource === eventSource && eventSource.readyState !== EventSource.CLOSED) {
        this.runError.set('The live run stream disconnected.');
      }
    };
  }

  private handleRunEvent(eventType: string, event: MessageEvent) {
    let payload: RunEvent;
    try {
      payload = JSON.parse(event.data) as RunEvent;
    } catch {
      return;
    }

    const view = this.buildRunEventView(payload);
    this.activeRunEvents.update((existing) => [...existing, view].slice(-80));
    this.applyRunEvent(payload);

    if (eventType === 'run.completed' || eventType === 'run.failed') {
      this.activeRunCompleted.set(true);
      this.closeRunStream();
    }
  }

  private applyRunEvent(event: RunEvent) {
    const snapshot = this.extractStateSnapshot(event.data);
    if (snapshot !== null) {
      this.activeRun.update((current) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          rounds: this.readNumber(snapshot['rounds'], current.rounds) ?? current.rounds,
          state: snapshot,
          current_node_id: this.readNumber(snapshot['current_node_id'], current.current_node_id ?? null),
          current_node_name: this.readText(snapshot['current_node_name']) ?? current.current_node_name ?? null,
          current_node_type: this.readText(snapshot['current_node_type']) ?? current.current_node_type ?? null,
          finished_at:
            event.event_type === 'run.completed' || event.event_type === 'run.failed'
              ? current.finished_at ?? new Date().toISOString()
              : current.finished_at,
          status: event.status ?? current.status,
          error: this.readText(snapshot['error']) ?? current.error ?? null,
          final_state:
            event.event_type === 'run.completed' || event.event_type === 'run.failed'
              ? snapshot
              : current.final_state,
        };
      });
    }

    this.activeRun.update((current) => {
      if (!current) {
        return current;
      }
      const currentNodeId = this.readNumber(
        event.node_id ?? event.data['entry_node_id'],
        current.current_node_id ?? null,
      );
      const nextStatus = event.status ?? current.status;
      return {
        ...current,
        current_node_id: currentNodeId,
        current_node_name:
          event.node_name ??
          this.readText(event.data['entry_node_name']) ??
          current.current_node_name ??
          null,
        current_node_type: event.node_type ?? current.current_node_type ?? null,
        rounds: this.readNumber(event.rounds, current.rounds) ?? current.rounds,
        status: nextStatus,
        error: event.event_type.endsWith('.failed') ? (event.error ?? this.readText(event.data['error']) ?? current.error ?? null) : current.error,
      };
    });
  }

  private closeRunStream() {
    if (this.runEventSource) {
      this.runEventSource.close();
      this.runEventSource = null;
    }
  }

  trackBySwarmName(_: number, item: SwarmSummary) {
    return item.swarm_name;
  }

  prettyJson(value: unknown) {
    if (value === null || value === undefined) {
      return '';
    }
    return JSON.stringify(value, null, 2);
  }

  setSwarmRounds(value: unknown) {
    this.swarmRounds.set(this.toNumber(value));
  }

  setAgentRounds(value: unknown) {
    this.agentRounds.set(this.toNumber(value));
  }

  setSwarmTask(value: string) {
    this.swarmTask.set(value);
  }

  setSwarmContext(value: string) {
    this.swarmContext.set(value);
  }

  setSwarmAudience(value: string) {
    this.swarmAudience.set(value);
  }

  setSwarmOutputFormat(value: string) {
    this.swarmOutputFormat.set(value);
  }

  setSwarmConstraints(value: string) {
    this.swarmConstraints.set(value);
  }

  trackByFactKey(_: number, item: FactRow) {
    return item.key;
  }

  trackBySectionTitle(_: number, item: ResultSection) {
    return item.title;
  }

  trackByTraceTitle(_: number, item: TraceView) {
    return item.title;
  }

  renderBlocks(value: unknown) {
    const text = this.extractText(value);
    if (!text) {
      return [];
    }
    return this.markdownToBlocks(text);
  }

  private syncAgentDefaults(swarm: SwarmDetails) {
    const available = this.availableAgentIds();
    const preferred = available.includes('planner') ? 'planner' : available[0] ?? null;
    if (preferred) {
      this.selectedAgentId.set(preferred);
    } else {
      this.selectedAgentId.set(null);
    }
    if (preferred === 'planner') {
      this.agentMessage.set('Please inspect the current request and decide the best next actions.');
    }
  }

  private toNumber(value: unknown) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  private formatError(error: unknown) {
    if (error instanceof HttpErrorResponse) {
      const statusText = error.status ? `${error.status} ${error.statusText || 'HTTP Error'}` : 'HTTP Error';
      const url = error.url ? ` (${error.url})` : '';
      const payload = this.describeHttpErrorPayload(error.error);
      return `${statusText}${url}${payload ? `: ${payload}` : ''}`;
    }
    if (error instanceof Error) {
      return error.message;
    }
    if (typeof error === 'object' && error !== null) {
      return this.describeHttpErrorPayload(error) || JSON.stringify(error);
    }
    return String(error);
  }

  private describeHttpErrorPayload(payload: unknown): string | null {
    if (payload === null || payload === undefined) {
      return null;
    }
    if (typeof payload === 'string') {
      return payload.trim() || null;
    }
    if (typeof payload === 'object') {
      const record = payload as Record<string, unknown>;
      const message = record['error'] ?? record['message'] ?? record['reason'] ?? record['detail'];
      if (typeof message === 'string' && message.trim()) {
        return message.trim();
      }
      try {
        return JSON.stringify(payload);
      } catch {
        return null;
      }
    }
    return String(payload);
  }

  private buildAgentRunView(value: Record<string, unknown> | null): ResultView | null {
    if (!value) {
      return null;
    }
    return {
      summary: [
        { key: 'swarm', value: this.safeString(value['swarm']) ?? 'unknown' },
        { key: 'agent', value: this.safeString(value['agent_id']) ?? 'unknown' },
        { key: 'success', value: this.safeBoolean(value['success']) ? 'true' : 'false' },
      ],
      sections: this.buildSectionsFromRecord([
        { title: 'Result', value: value['result'] },
        { title: 'Context', value: value['context'] },
      ]),
      trace: [],
      rawJson: this.prettyJson(value),
    };
  }

  private buildRunLiveView(run: RunSnapshot | null, events: RunEventView[]): RunLiveView | null {
    if (!run) {
      return null;
    }

    return {
      run,
      events,
      stateView: this.buildPayloadView(run.state),
      finalStateView: this.buildPayloadView(run.final_state),
      rawJson: this.prettyJson(run),
    };
  }

  private buildGraphView(graph: GraphSnapshot | null, run: RunSnapshot | null): GraphView | null {
    if (!graph) {
      return null;
    }

    const currentNodeId = run?.current_node_id ?? null;
    const currentStatus = run?.status ?? null;
    const completedNodeIds = this.extractCompletedNodeIds(run?.state, run?.final_state);
    const failedNodeIds = this.extractFailedNodeIds(run?.state, run?.final_state);

    return {
      graphName: graph.graph_name,
      entryNodeId: graph.entry_node_id,
      exitNodeId: graph.exit_node_id,
      nodeCount: graph.node_count,
      edgeCount: graph.edge_count,
      currentNodeId,
      currentNodeName: run?.current_node_name ?? null,
      currentNodeType: run?.current_node_type ?? null,
      status: currentStatus,
      rounds: run?.rounds ?? 0,
      nodes: graph.nodes.map((node) => ({
        ...node,
        status: this.resolveNodeStatus(node.node_id, currentNodeId, completedNodeIds, failedNodeIds, currentStatus),
        isEntry: graph.entry_node_id === node.node_id,
        isExit: graph.exit_node_id === node.node_id,
      })),
      edges: graph.edges.map((edge) => ({
        ...edge,
        active: currentNodeId !== null && edge.from_node_id === currentNodeId,
      })),
      rawJson: this.prettyJson(graph),
    };
  }

  private buildGraphSpectrumView(view: GraphView | null, zoom: number): GraphSpectrumView | null {
    if (!view) {
      return null;
    }

    const safeZoom = this.clampGraphZoom(zoom);
    const nodeWidth = 190;
    const nodeHeight = 92;
    const levelGap = 180;
    const nodeGap = 70;
    const padding = 56;

    const layout = this.layoutGraphNodes(view, nodeWidth, nodeHeight, levelGap, nodeGap, padding);
    const positions = layout.positions;
    const widestRow = Math.max(layout.widestRow, 1);
    const width = Math.max(960, padding * 2 + widestRow * nodeWidth + Math.max(0, widestRow - 1) * nodeGap);
    const maxLevel = Math.max(layout.maxLevel, 0);
    const height = Math.max(560, padding * 2 + maxLevel * levelGap + nodeHeight);
    const panX = this.graphPanX();
    const panY = this.graphPanY();
    const viewBox = `0 0 ${width} ${height}`;

    const layoutNodes = view.nodes.map((node) => {
      const position = positions.get(node.node_id) ?? { x: padding, y: padding };
      return {
        ...node,
        x: position.x,
        y: position.y,
        width: nodeWidth,
        height: nodeHeight,
        labelLines: this.buildGraphNodeLabelLines(node),
      };
    });

    const nodeLookup = new Map<number, GraphSpectrumNodeView>();
    layoutNodes.forEach((node) => nodeLookup.set(node.node_id, node));

    const layoutEdges = view.edges.map((edge) => {
      const source = nodeLookup.get(edge.from_node_id);
      const target = nodeLookup.get(edge.to_node_id);
      const x1 = source ? source.x + source.width / 2 : padding;
      const y1 = source ? source.y + source.height : padding;
      const x2 = target ? target.x + target.width / 2 : padding;
      const y2 = target ? target.y : padding;
      const midY = y1 + Math.max(54, (y2 - y1) / 2);
      return {
        ...edge,
        d: `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`,
      };
    });

    return {
      width,
      height,
      viewBox,
      zoom: safeZoom,
      panX,
      panY,
      panTransform: `translate(${panX} ${panY})`,
      scaleTransform: `scale(${safeZoom})`,
      nodes: layoutNodes,
      edges: layoutEdges,
      rawJson: this.prettyJson({
        zoom: safeZoom,
        panX,
        panY,
        layout: layoutNodes.map((node) => ({
          node_id: node.node_id,
          x: node.x,
          y: node.y,
          width: node.width,
          height: node.height,
        })),
      }),
    };
  }

  private buildRunEventView(event: RunEvent): RunEventView {
    const status = this.safeString(event.status) ?? 'info';
    const nodeName = this.safeString(event.node_name) ?? this.safeString(event.data['entry_node_name']) ?? 'system';
    const branch = this.safeString(event.branch) ?? 'main';
    const timestamp = new Date(event.timestamp * 1000).toLocaleString();
    const summary = [
      event.event_type,
      nodeName,
      branch !== 'main' ? `branch ${branch}` : '',
      status,
    ]
      .filter((item) => Boolean(item))
      .join(' · ');

    return {
      eventType: event.event_type,
      title: this.eventTitle(event.event_type),
      timestamp,
      status,
      nodeName,
      branch,
      summary,
      rawJson: this.prettyJson(event),
    };
  }

  private buildPayloadView(value: unknown): ResultView | null {
    if (value === null || value === undefined) {
      return null;
    }

    const records = this.isRecord(value) ? Object.keys(value) : [];
    return {
      summary: [
        { key: 'mode', value: 'input draft' },
        { key: 'shape', value: Array.isArray(value) ? 'array' : typeof value },
        { key: 'fields', value: records.length ? `${records.length} keys` : '0 keys' },
      ],
      sections: this.buildSectionsFromRecord([{ title: 'Generated payload', value }]),
      trace: [],
      rawJson: this.prettyJson(value),
    };
  }

  private buildGraphNodeLabelLines(node: GraphNodeView): string[] {
    const lines = [`#${node.node_id} ${node.node_name}`];
    lines.push(node.node_type);
    if (node.agent_id) {
      lines.push(`agent: ${node.agent_id}`);
    }
    if (node.tool_name) {
      lines.push(`tool: ${node.tool_name}`);
    }
    if (node.next_node_ids.length) {
      lines.push(`next: ${node.next_node_ids.join(', ')}`);
    }
    return lines.slice(0, 4);
  }

  private layoutGraphNodes(
    view: GraphView,
    nodeWidth: number,
    nodeHeight: number,
    levelGap: number,
    nodeGap: number,
    padding: number,
  ): { positions: Map<number, { x: number; y: number }>; widestRow: number; maxLevel: number } {
    const outgoing = new Map<number, number[]>();
    const levels = new Map<number, number>();

    view.nodes.forEach((node) => {
      outgoing.set(node.node_id, []);
      levels.set(node.node_id, Number.POSITIVE_INFINITY);
    });

    view.edges.forEach((edge) => {
      const list = outgoing.get(edge.from_node_id);
      if (list) {
        list.push(edge.to_node_id);
      }
    });

    const entryId = view.entryNodeId ?? view.nodes[0]?.node_id ?? null;
    if (entryId !== null) {
      const queue: number[] = [entryId];
      levels.set(entryId, 0);
      while (queue.length) {
        const current = queue.shift() ?? entryId;
        const nextLevel = (levels.get(current) ?? 0) + 1;
        for (const nextId of outgoing.get(current) ?? []) {
          if (nextLevel < (levels.get(nextId) ?? Number.POSITIVE_INFINITY)) {
            levels.set(nextId, nextLevel);
            queue.push(nextId);
          }
        }
      }
    }

    const fallbackLevels = [...view.nodes]
      .sort((left, right) => left.node_id - right.node_id)
      .map((node, index) => ({
        nodeId: node.node_id,
        level: Number.isFinite(levels.get(node.node_id) ?? Number.POSITIVE_INFINITY)
          ? (levels.get(node.node_id) ?? 0)
          : index,
      }));
    fallbackLevels.forEach(({ nodeId, level }) => {
      if (!Number.isFinite(levels.get(nodeId) ?? Number.POSITIVE_INFINITY)) {
        levels.set(nodeId, level);
      }
    });

    const grouped = new Map<number, number[]>();
    view.nodes.forEach((node) => {
      const level = levels.get(node.node_id) ?? 0;
      const group = grouped.get(level) ?? [];
      group.push(node.node_id);
      grouped.set(level, group);
    });

    let widestRow = 1;
    grouped.forEach((items) => {
      widestRow = Math.max(widestRow, items.length);
    });

    const positions = new Map<number, { x: number; y: number }>();
    const orderedLevels = [...grouped.keys()].sort((left, right) => left - right);
    orderedLevels.forEach((level) => {
      const items = grouped.get(level) ?? [];
      const rowWidth = items.length * nodeWidth + Math.max(0, items.length - 1) * nodeGap;
      const startX = padding + (widestRow * nodeWidth + Math.max(0, widestRow - 1) * nodeGap - rowWidth) / 2;
      items.forEach((nodeId, index) => {
        positions.set(nodeId, {
          x: startX + index * (nodeWidth + nodeGap),
          y: padding + level * levelGap,
        });
      });
    });

    return {
      positions,
      widestRow,
      maxLevel: orderedLevels[orderedLevels.length - 1] ?? 0,
    };
  }

  private clampGraphZoom(value: number) {
    return Math.min(2.4, Math.max(0.7, Number.isFinite(value) ? value : 1));
  }

  private buildSwarmRequestPayload(): Record<string, unknown> {
    const payload: Record<string, unknown> = {};
    const task = this.swarmTask().trim();
    const context = this.swarmContext().trim();
    const audience = this.swarmAudience().trim();
    const outputFormat = this.swarmOutputFormat().trim();
    const constraints = this.swarmConstraints()
      .split('\n')
      .map((item) => item.trim())
      .filter((item) => Boolean(item));

    if (task) {
      payload['text'] = task;
    }
    if (context) {
      payload['context'] = context;
    }
    if (audience) {
      payload['audience'] = audience;
    }
    if (outputFormat) {
      payload['output_format'] = outputFormat;
    }
    if (constraints.length) {
      payload['constraints'] = constraints;
    }

    return payload;
  }

  private buildSectionsFromRecord(entries: Array<{ title: string; value: unknown }>): ResultSection[] {
    return entries
      .map((entry) => {
        const facts = this.flattenFacts(entry.value).slice(0, 10);
        const blocks = this.renderBlocks(entry.value);
        if (!facts.length && !blocks.length) {
          return null;
        }
        return {
          title: entry.title,
          facts,
          blocks,
          rawJson: this.prettyJson(entry.value),
        } satisfies ResultSection;
      })
      .filter((item): item is ResultSection => item !== null);
  }

  private buildTraceViews(value: unknown): TraceView[] {
    if (!Array.isArray(value)) {
      return [];
    }

    return value
      .map((entry, index) => this.buildTraceView(entry, index))
      .filter((item): item is TraceView => item !== null);
  }

  private buildTraceView(value: unknown, index: number): TraceView | null {
    if (!this.isRecord(value)) {
      return null;
    }

    const title = this.safeString(value['node_name']) ?? this.safeString(value['name']) ?? `Trace ${index + 1}`;
    const nodeType = this.safeString(value['node_type']);
    const status = this.safeString(value['status']) ?? 'unknown';
    const branch = this.safeString(value['branch']) ?? 'main';
    const error = this.safeString(value['error']);
    const meta: FactRow[] = [];

    for (const [key, rawValue] of Object.entries(value)) {
      if (['input_payload', 'output_payload', 'payload', 'raw_response', 'error'].includes(key)) {
        continue;
      }
      const rendered = this.renderFlatValue(rawValue);
      if (rendered) {
        meta.push({ key, value: rendered });
      }
    }

    if (nodeType) {
      meta.unshift({ key: 'type', value: nodeType });
    }

    return {
      title,
      status,
      branch,
      meta,
      inputBlocks: this.renderBlocks(value['input_payload'] ?? value['input']),
      outputBlocks: this.renderBlocks(
        value['output_payload'] ?? value['payload'] ?? value['assistant_message'] ?? value['result'],
      ),
      error,
      rawJson: this.prettyJson(value),
    };
  }

  private flattenFacts(value: unknown, prefix = '', depth = 0): FactRow[] {
    if (value === null || value === undefined) {
      return prefix ? [{ key: prefix, value: 'null' }] : [];
    }

    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      return prefix ? [{ key: prefix, value: String(value) }] : [];
    }

    if (Array.isArray(value)) {
      const primitives = value.filter((item) => item === null || ['string', 'number', 'boolean'].includes(typeof item));
      if (primitives.length && primitives.length === value.length) {
        return prefix ? [{ key: prefix, value: primitives.map((item) => String(item)).join(', ') }] : [];
      }
      return value.flatMap((item, index) => this.flattenFacts(item, prefix ? `${prefix}[${index}]` : String(index), depth + 1));
    }

    if (!this.isRecord(value)) {
      return [];
    }

    const rows: FactRow[] = [];
    for (const [key, rawValue] of Object.entries(value)) {
      const nextKey = prefix ? `${prefix}.${key}` : key;
      if (rawValue === null || rawValue === undefined) {
        rows.push({ key: nextKey, value: 'null' });
        continue;
      }
      if (typeof rawValue === 'string' || typeof rawValue === 'number' || typeof rawValue === 'boolean') {
        rows.push({ key: nextKey, value: String(rawValue) });
        continue;
      }
      if (Array.isArray(rawValue)) {
        const primitives = rawValue.filter((item) => item === null || ['string', 'number', 'boolean'].includes(typeof item));
        if (primitives.length && primitives.length === rawValue.length) {
          rows.push({ key: nextKey, value: primitives.map((item) => String(item)).join(', ') });
          continue;
        }
      }
      if (depth < 1 && this.isRecord(rawValue)) {
        rows.push(...this.flattenFacts(rawValue, nextKey, depth + 1));
      }
    }
    return rows;
  }

  private renderFlatValue(value: unknown): string | null {
    if (value === null) {
      return 'null';
    }
    if (value === undefined) {
      return null;
    }
    if (typeof value === 'string') {
      return value;
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value);
    }
    if (Array.isArray(value)) {
      const primitives = value.filter((item) => item === null || ['string', 'number', 'boolean'].includes(typeof item));
      if (primitives.length && primitives.length === value.length) {
        return primitives.map((item) => String(item)).join(', ');
      }
      return `${value.length} items`;
    }
    if (this.isRecord(value)) {
      const text = this.extractText(value);
      return text ?? null;
    }
    return null;
  }

  private extractText(value: unknown, seen = new WeakSet<object>()): string | null {
    if (value === null || value === undefined) {
      return null;
    }

    if (typeof value === 'string') {
      const text = value.trim();
      return text || null;
    }

    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value);
    }

    if (Array.isArray(value)) {
      for (const item of value) {
        const text = this.extractText(item, seen);
        if (text) {
          return text;
        }
      }
      return null;
    }

    if (!this.isRecord(value)) {
      return null;
    }

    if (seen.has(value)) {
      return null;
    }
    seen.add(value);

    const preferredKeys = ['assistant_message', 'content', 'text', 'payload', 'message', 'detail', 'summary'];
    for (const key of preferredKeys) {
      const rawValue = value[key];
      if (typeof rawValue === 'string') {
        const text = rawValue.trim();
        if (text) {
          return text;
        }
      }
      if (rawValue && typeof rawValue === 'object') {
        const nested = this.extractText(rawValue, seen);
        if (nested) {
          return nested;
        }
      }
    }

    for (const [key, rawValue] of Object.entries(value)) {
      if (['usage', 'system_fingerprint', 'created', 'id', 'model', 'object', 'service_tier', 'annotations', 'audio', 'function_call', 'tool_calls', 'reasoning_content'].includes(key)) {
        continue;
      }
      const text = this.extractText(rawValue, seen);
      if (text) {
        return text;
      }
    }

    return null;
  }

  private markdownToBlocks(value: string): MarkdownBlock[] {
    const source = value.replace(/\r\n/g, '\n').trim();
    if (!source) {
      return [];
    }

    const lines = source.split('\n');
    const blocks: MarkdownBlock[] = [];
    let index = 0;

    while (index < lines.length) {
      const line = lines[index];
      const trimmed = line.trim();

      if (!trimmed) {
        index += 1;
        continue;
      }

      if (trimmed.startsWith('```')) {
        const language = trimmed.slice(3).trim();
        const code: string[] = [];
        index += 1;
        while (index < lines.length && !lines[index].trim().startsWith('```')) {
          code.push(lines[index]);
          index += 1;
        }
        if (index < lines.length) {
          index += 1;
        }
        blocks.push({
          kind: 'code',
          html: `<pre class="code-block"><code${language ? ` data-lang="${this.escapeHtml(language)}"` : ''}>${this.escapeHtml(
            code.join('\n'),
          )}</code></pre>`,
        });
        continue;
      }

      if (/^#{1,6}\s+/.test(trimmed)) {
        const level = trimmed.match(/^#{1,6}/)?.[0].length ?? 1;
        const text = trimmed.replace(/^#{1,6}\s+/, '');
        blocks.push({
          kind: 'heading',
          html: `<h${level}>${this.inlineMarkdown(text)}</h${level}>`,
        });
        index += 1;
        continue;
      }

      if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
        blocks.push({
          kind: 'divider',
          html: '<hr />',
        });
        index += 1;
        continue;
      }

      if (/^>\s?/.test(trimmed)) {
        const quoteLines: string[] = [];
        while (index < lines.length && /^>\s?/.test(lines[index].trim())) {
          quoteLines.push(lines[index].trim().replace(/^>\s?/, ''));
          index += 1;
        }
        blocks.push({
          kind: 'quote',
          html: `<blockquote>${this.inlineMarkdown(quoteLines.join('\n'))}</blockquote>`,
        });
        continue;
      }

      const orderedMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
      const unorderedMatch = trimmed.match(/^([-*+])\s+(.*)$/);
      if (orderedMatch || unorderedMatch) {
        const ordered = Boolean(orderedMatch);
        const items: string[] = [];
        while (index < lines.length) {
          const current = lines[index].trim();
          const currentOrdered = current.match(/^(\d+)\.\s+(.*)$/);
          const currentUnordered = current.match(/^([-*+])\s+(.*)$/);
          if (ordered && !currentOrdered) {
            break;
          }
          if (!ordered && !currentUnordered) {
            break;
          }
          items.push((currentOrdered?.[2] ?? currentUnordered?.[2] ?? '').trim());
          index += 1;
        }
        blocks.push({
          kind: 'list',
          html: ordered
            ? `<ol>${items.map((item) => `<li>${this.inlineMarkdown(item)}</li>`).join('')}</ol>`
            : `<ul>${items.map((item) => `<li>${this.inlineMarkdown(item)}</li>`).join('')}</ul>`,
        });
        continue;
      }

      const paragraphLines: string[] = [trimmed];
      index += 1;
      while (index < lines.length) {
        const next = lines[index].trim();
        if (
          !next ||
          next.startsWith('```') ||
          /^#{1,6}\s+/.test(next) ||
          /^(\d+)\.\s+/.test(next) ||
          /^([-*+])\s+/.test(next) ||
          /^>\s?/.test(next) ||
          /^(-{3,}|\*{3,}|_{3,})$/.test(next)
        ) {
          break;
        }
        paragraphLines.push(next);
        index += 1;
      }
      blocks.push({
        kind: 'paragraph',
        html: `<p>${this.inlineMarkdown(paragraphLines.join(' '))}</p>`,
      });
    }

    return blocks;
  }

  private inlineMarkdown(value: string): string {
    let html = this.escapeHtml(value);
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/__(.+?)__/g, '<strong>$1</strong>');
    html = html.replace(/(^|[^\*])\*(?!\s)(.+?)(?!\s)\*(?!\*)/g, '$1<em>$2</em>');
    html = html.replace(/(^|[^_])_(?!\s)(.+?)(?!\s)_(?!_)/g, '$1<em>$2</em>');
    html = html.replace(/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
    return html.replace(/\n/g, '<br />');
  }

  private escapeHtml(value: string): string {
    return value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  private safeString(value: unknown): string | null {
    if (typeof value === 'string') {
      const text = value.trim();
      return text || null;
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value);
    }
    return null;
  }

  private safeBoolean(value: unknown): boolean {
    return value === true;
  }

  private readText(value: unknown): string | null {
    return this.safeString(value);
  }

  private readNumber(value: unknown, fallback: number | null = null): number | null {
    if (value === null || value === undefined) {
      return fallback;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  private extractStateSnapshot(value: Record<string, unknown>): Record<string, unknown> | null {
    const snapshot = value['state_snapshot'];
    if (this.isRecord(snapshot)) {
      return snapshot;
    }
    return null;
  }

  private extractCompletedNodeIds(primary: unknown, fallback: unknown): Set<number> {
    const ids = new Set<number>();
    for (const source of [primary, fallback]) {
      if (!this.isRecord(source)) {
        continue;
      }
      const trace = source['trace'];
      if (!Array.isArray(trace)) {
        continue;
      }
      for (const item of trace) {
        if (!this.isRecord(item)) {
          continue;
        }
        const status = this.safeString(item['status']);
        if (status !== 'ok') {
          continue;
        }
        const nodeId = this.readNumber(item['node_id']);
        if (nodeId !== null) {
          ids.add(nodeId);
        }
      }
    }
    return ids;
  }

  private extractFailedNodeIds(primary: unknown, fallback: unknown): Set<number> {
    const ids = new Set<number>();
    for (const source of [primary, fallback]) {
      if (!this.isRecord(source)) {
        continue;
      }
      const trace = source['trace'];
      if (!Array.isArray(trace)) {
        continue;
      }
      for (const item of trace) {
        if (!this.isRecord(item)) {
          continue;
        }
        const status = this.safeString(item['status']);
        if (status !== 'error') {
          continue;
        }
        const nodeId = this.readNumber(item['node_id']);
        if (nodeId !== null) {
          ids.add(nodeId);
        }
      }
    }
    return ids;
  }

  private resolveNodeStatus(
    nodeId: number,
    currentNodeId: number | null,
    completedNodeIds: Set<number>,
    failedNodeIds: Set<number>,
    status: string | null,
  ): 'pending' | 'running' | 'completed' | 'failed' {
    if (failedNodeIds.has(nodeId)) {
      return 'failed';
    }
    if (status === 'failed' && currentNodeId === nodeId) {
      return 'failed';
    }
    if (currentNodeId === nodeId && status === 'running') {
      return 'running';
    }
    if (completedNodeIds.has(nodeId)) {
      return 'completed';
    }
    return 'pending';
  }

  private eventTitle(eventType: string): string {
    switch (eventType) {
      case 'run.started':
        return 'Run started';
      case 'run.completed':
        return 'Run completed';
      case 'run.failed':
        return 'Run failed';
      case 'node.started':
        return 'Node started';
      case 'node.completed':
        return 'Node completed';
      case 'node.failed':
        return 'Node failed';
      case 'branch.started':
        return 'Branch started';
      case 'branch.completed':
        return 'Branch completed';
      case 'branch.failed':
        return 'Branch failed';
      default:
        return eventType;
    }
  }

  private isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }
}
