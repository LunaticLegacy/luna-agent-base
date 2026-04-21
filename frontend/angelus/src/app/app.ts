import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import enUS from './i18n/en-US.json';
import zhCN from './i18n/zh-CN.json';

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
  rawMetadata: Record<string, unknown>;
  routePolicy: 'all' | 'first' | null;
  joinNodeId: number | null;
  branchIndex: number | null;
  branchIndexes: number[];
  branchSourceNodeId: number | null;
  derivedRole: string;
  semanticTags: string[];
  warnings: string[];
  skillMetadata: GraphSkillMetadataView | null;
}

interface GraphSkillMetadataView {
  contractVersion: string | null;
  capability: string | null;
  description: string | null;
  inputSchema: unknown;
  outputSchema: unknown;
  requiresTools: string[];
  requiresSkills: string[];
  preconditions: string[];
  postconditions: string[];
  failurePolicy: string | null;
  parallelizable: boolean | null;
  rawMetadata: Record<string, unknown>;
  warnings: string[];
}

interface GraphEdgeView extends GraphEdgeSnapshot {
  active: boolean;
  derivedFromMetadata: string[] | null;
  derivedRelation: boolean;
}

interface GraphBranchGroupView {
  sourceNodeId: number;
  sourceNodeName: string | null;
  joinNodeId: number | null;
  branchIndexes: number[];
  branchNodeIds: number[];
}

interface GraphJoinGroupView {
  joinNodeId: number;
  joinNodeName: string | null;
  sourceNodeIds: number[];
  sourceNodeNames: string[];
}

interface GraphSemanticSummaryView {
  entryNodeId: number | null;
  exitNodeId: number | null;
  branchGroups: GraphBranchGroupView[];
  joinGroups: GraphJoinGroupView[];
  unresolvedMetadataHints: string[];
}

interface GraphRuntimeContextView {
  currentBranchIndex: number | null;
  currentBranchSourceNodeId: number | null;
  nodeBranchIndexes: Map<number, Set<number>>;
  nodeBranchSourceNodeIds: Map<number, Set<number>>;
  sourceBranchGroups: Map<number, {
    branchIndexes: Set<number>;
    branchNodeIds: Set<number>;
    joinNodeId: number | null;
  }>;
  unresolvedMetadataHints: string[];
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
  branchIndex: number | null;
  branchSourceNodeId: number | null;
  semanticSummary: GraphSemanticSummaryView;
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
  displayScale: number;
  panX: number;
  panY: number;
  panTransform: string;
  scaleTransform: string;
  branchIndex: number | null;
  branchSourceNodeId: number | null;
  semanticSummary: GraphSemanticSummaryView;
  nodes: GraphSpectrumNodeView[];
  edges: GraphSpectrumEdgeView[];
  rawJson: string;
}

interface GraphNodeDetailView {
  node: GraphSpectrumNodeView;
  summary: FactRow[];
  semanticChips: string[];
  skillChips: string[];
  runtimeChips: string[];
  sections: ResultSection[];
  rawJson: string;
}

interface GraphDragState {
  pointerId: number;
  startClientX: number;
  startClientY: number;
  originPanX: number;
  originPanY: number;
  activated: boolean;
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

interface ExecutionFeedbackView {
  title: string;
  message: string;
  status: 'idle' | 'running' | 'success' | 'error';
  progress: number;
  indeterminate: boolean;
  tone: 'neutral' | 'running' | 'success' | 'error';
}

type LocaleCode = 'zh-CN' | 'en-US';
type LocaleBundle = typeof zhCN;

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
  private readonly bundles: Record<LocaleCode, LocaleBundle> = {
    'zh-CN': zhCN,
    'en-US': enUS as LocaleBundle,
  };
  protected readonly locale = signal<LocaleCode>(this.resolveInitialLocale());
  protected get text(): LocaleBundle {
    return this.bundles[this.locale()];
  }
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

  protected readonly title = computed(() => this.text.app.title);
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
  protected readonly graphLayout = signal<'horizontal' | 'vertical'>('horizontal');
  protected readonly controlMode = signal<'agent' | 'swarm'>('agent');
  protected readonly agentPage = signal<'input' | 'output'>('input');
  protected readonly swarmPage = signal<'input' | 'output'>('input');
  protected readonly graphZoom = signal(1);
  protected readonly graphPanX = signal(0);
  protected readonly graphPanY = signal(0);
  protected readonly graphDragging = signal(false);
  protected readonly selectedGraphNodeId = signal<number | null>(null);
  protected readonly activeRun = signal<RunSnapshot | null>(null);
  protected readonly activeRunEvents = signal<RunEventView[]>([]);
  protected readonly activeRunCompleted = signal(false);
  protected readonly agentRunStatus = signal<'idle' | 'running' | 'success' | 'error'>('idle');
  protected readonly swarmRunStatus = signal<'idle' | 'launching' | 'running' | 'success' | 'error'>('idle');
  protected readonly agentRunOutput = signal<Record<string, unknown> | null>(null);
  protected readonly agentRunView = computed(() => this.buildAgentRunView(this.agentRunOutput()));
  protected readonly swarmTask = signal(this.text.swarm.placeholders.task);
  protected readonly swarmContext = signal(this.text.swarm.placeholders.context);
  protected readonly swarmAudience = signal(this.text.swarm.placeholders.audience);
  protected readonly swarmOutputFormat = signal(this.text.swarm.placeholders.outputFormat);
  protected readonly swarmConstraints = signal('');
  protected readonly swarmRequestPayload = computed(() => this.buildSwarmRequestPayload());
  protected readonly swarmRequestView = computed(() => this.buildPayloadView(this.swarmRequestPayload()));
  protected readonly graphView = computed(() => this.buildGraphView(this.selectedGraph(), this.activeRun()));
  protected readonly graphSpectrumView = computed(() => this.buildGraphSpectrumView(this.graphView(), this.graphZoom(), this.graphLayout()));
  protected readonly graphNodeDetailView = computed(() => this.buildGraphNodeDetailView(this.graphSpectrumView(), this.selectedGraphNodeId()));
  protected readonly liveRunView = computed(() => this.buildRunLiveView(this.activeRun(), this.activeRunEvents()));
  protected readonly executionFeedbackView = computed(() =>
    this.buildExecutionFeedbackView(
      this.controlMode(),
      this.agentRunStatus(),
      this.swarmRunStatus(),
      this.activeRun(),
      this.activeRunEvents(),
      this.executionLoading(),
      this.runError(),
    ),
  );

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

  protected readonly agentMessage = signal(this.text.agent.placeholders.message);
  protected readonly agentRounds = signal(0);
  protected readonly agentAdditionalPrompt = signal('');

  constructor() {
    void this.loadOverview();
  }

  ngOnDestroy() {
    this.closeRunStream();
  }

  setLocale(value: string) {
    const nextLocale: LocaleCode = value === 'zh-CN' ? 'zh-CN' : 'en-US';
    this.locale.set(nextLocale);
    try {
      window.localStorage.setItem('angelus.locale', nextLocale);
    } catch {
      // Ignore persistence failures and keep the in-memory locale.
    }
  }

  private resolveInitialLocale(): LocaleCode {
    try {
      const stored = window.localStorage.getItem('angelus.locale');
      if (stored === 'zh-CN' || stored === 'en-US') {
        return stored;
      }
    } catch {
      // Fall back to navigator/default locale.
    }

    const preferred = typeof navigator !== 'undefined' ? navigator.language : '';
    if (preferred.toLowerCase().startsWith('zh')) {
      return 'zh-CN';
    }
    return 'en-US';
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
    this.selectedGraphNodeId.set(null);
    this.graphDragState = null;
    this.graphTab.set('spectrum');
    this.graphLayout.set('horizontal');
    this.controlMode.set('agent');
    this.agentPage.set('input');
    this.swarmPage.set('input');
    this.selectedSwarmName.set(swarmName);
    this.agentRunStatus.set('idle');
    this.swarmRunStatus.set('idle');
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

  setGraphLayout(value: 'horizontal' | 'vertical') {
    this.graphLayout.set(value);
    this.graphPanX.set(0);
    this.graphPanY.set(0);
    this.graphDragging.set(false);
    this.graphDragState = null;
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

  selectGraphNode(nodeId: number, event?: MouseEvent) {
    event?.stopPropagation();
    this.selectedGraphNodeId.set(nodeId);
  }

  clearGraphSelection() {
    this.selectedGraphNodeId.set(null);
  }

  startGraphDrag(event: PointerEvent) {
    if (!this.graphSpectrumView()) {
      return;
    }

    const target = event.target as Element | null;
    if (target?.closest('button, a, input, textarea, select, summary, details, .graph-spectrum-inspector')) {
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
      activated: false,
    };
  }

  moveGraphDrag(event: PointerEvent) {
    const drag = this.graphDragState;
    if (!drag || drag.pointerId !== event.pointerId) {
      return;
    }

    event.preventDefault();
    const threshold = 4;
    const distanceX = event.clientX - drag.startClientX;
    const distanceY = event.clientY - drag.startClientY;
    if (!drag.activated) {
      if (Math.hypot(distanceX, distanceY) < threshold) {
        return;
      }
      drag.activated = true;
      this.graphDragging.set(true);
    }

    const deltaX = distanceX;
    const deltaY = distanceY;
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
      this.swarmRunStatus.set('error');
      this.runError.set(this.text.messages.selectSwarmToRun);
      return;
    }

    const payload = this.swarmRequestPayload();
    if (!this.safeString(payload['text'])) {
      this.swarmRunStatus.set('error');
      this.runError.set(this.text.messages.taskRequired);
      return;
    }

    this.executionLoading.set(true);
    this.runError.set(null);
    this.swarmRunStatus.set('launching');
    try {
      const response = await this.api.startSwarmRun(this.apiBaseUrl(), name, {
        input: payload,
        rounds: this.swarmRounds(),
      });
      this.beginRunFollow(response);
    } catch (error) {
      this.swarmRunStatus.set('error');
      this.runError.set(this.formatError(error));
    } finally {
      this.executionLoading.set(false);
    }
  }

  async runSelectedAgent() {
    const swarm = this.selectedSwarm();
    if (!swarm) {
      this.agentRunStatus.set('error');
      this.runError.set(this.text.messages.selectSwarmToRunAgent);
      return;
    }

    const agentId = this.selectedAgentId();
    if (!agentId) {
      this.agentRunStatus.set('error');
      this.runError.set(this.text.messages.swarmHasNoAgents);
      return;
    }

    this.executionLoading.set(true);
    this.runError.set(null);
    this.agentRunStatus.set('running');
    this.agentRunOutput.set(null);
    try {
      const response = await this.api.runAgentRound(this.apiBaseUrl(), swarm.swarm_name, agentId, {
        message: this.agentMessage().trim(),
        rounds: this.agentRounds(),
        additional_prompt: this.agentAdditionalPrompt().trim() || undefined,
      });
      this.agentRunOutput.set(response as unknown as Record<string, unknown>);
      this.agentRunStatus.set('success');
    } catch (error) {
      this.agentRunStatus.set('error');
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
    this.swarmRunStatus.set('running');
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
        this.runError.set(this.text.messages.liveStreamDisconnected);
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

    // Refresh graph structure if the event references a node not present in the current snapshot
    // (e.g. dynamically inserted nodes like researcher_runtime).
    if (payload.node_id !== undefined && payload.node_id !== null) {
      const nodeId = Number(payload.node_id);
      const graph = this.selectedGraph();
      if (graph && !graph.nodes.some((n) => n.node_id === nodeId)) {
        void this.reloadSelectedGraph();
      }
    }

    if (eventType === 'run.completed' || eventType === 'run.failed') {
      this.activeRunCompleted.set(true);
      this.swarmRunStatus.set(eventType === 'run.completed' ? 'success' : 'error');
      this.closeRunStream();
      void this.reloadSelectedGraph();
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

  displayHealthStatus(value: string | null) {
    if (value === 'ok') {
      return this.text.status.ok;
    }
    if (value === 'error') {
      return this.text.status.error;
    }
    return this.text.status.unknown;
  }

  displayReadyStatus(value: boolean | null | undefined) {
    return value ? this.text.status.yes : this.text.status.no;
  }

  displayBinary(value: boolean | null | undefined) {
    return value ? this.text.status.yes : this.text.status.no;
  }

  displayRunStatus(value: string | null | undefined) {
    switch (value?.toLowerCase()) {
      case 'queued':
      case 'pending':
        return this.text.status.pending;
      case 'launching':
        return this.text.status.launching;
      case 'running':
        return this.text.status.running;
      case 'completed':
        return this.text.status.completed;
      case 'failed':
        return this.text.status.failed;
      case 'success':
        return this.text.status.success;
      case 'error':
        return this.text.status.error;
      case 'idle':
        return this.text.status.idle;
      default:
        return value ?? this.text.status.unknown;
    }
  }

  displayNodeStatus(value: string | null | undefined) {
    switch (value?.toLowerCase()) {
      case 'pending':
        return this.text.status.pending;
      case 'running':
        return this.text.status.running;
      case 'completed':
        return this.text.status.completed;
      case 'failed':
        return this.text.status.failed;
      default:
        return value ?? this.text.status.unknown;
    }
  }

  displayRoutePolicy(value: 'all' | 'first' | null) {
    switch (value) {
      case 'all':
        return this.text.graph.routePolicyAll;
      case 'first':
        return this.text.graph.routePolicyFirst;
      default:
        return this.text.graph.routePolicyDefault;
    }
  }

  displayBranchLabel(branch: string | null | undefined) {
    const value = branch?.trim();
    if (!value || value === 'main') {
      return this.text.status.mainBranch;
    }
    return `${this.text.status.branchPrefix} ${value}`;
  }

  displayEventStatus(value: string | null | undefined) {
    return this.displayRunStatus(value);
  }

  displayJsonShape(value: unknown) {
    if (Array.isArray(value)) {
      return this.text.status.array;
    }
    if (value === null) {
      return this.text.status.null;
    }
    switch (typeof value) {
      case 'object':
        return this.text.status.object;
      case 'string':
        return this.text.status.string;
      case 'number':
        return this.text.status.number;
      case 'boolean':
        return this.text.status.boolean;
      default:
        return this.text.status.unknown;
    }
  }

  safeBinaryText(value: unknown) {
    return this.safeBoolean(value) ? this.text.status.yes : this.text.status.no;
  }

  interpolate(template: string, values: Record<string, string>) {
    return template.replace(/\{\{(\w+)\}\}/g, (_, key: string) => values[key] ?? '');
  }

  translateFactKey(key: string) {
    const map: Record<string, string> = {
      metadata: this.text.nodeDetail.fields.metadata,
      raw_metadata: this.text.nodeDetail.fields.rawMetadata,
      state: this.text.nodeDetail.fields.state,
      state_snapshot: this.text.nodeDetail.fields.stateSnapshot,
      final_state: this.text.nodeDetail.fields.finalState,
      input_payload: this.text.nodeDetail.fields.inputPayload,
      output_payload: this.text.nodeDetail.fields.outputPayload,
      payload: this.text.nodeDetail.fields.payload,
      raw_response: this.text.nodeDetail.fields.rawResponse,
      assistant_message: this.text.nodeDetail.fields.assistantMessage,
      message: this.text.nodeDetail.fields.message,
      detail: this.text.nodeDetail.fields.detail,
      summary: this.text.nodeDetail.fields.summary,
      branch_results: this.text.nodeDetail.fields.branchResults,
      trace: this.text.trace.titlePrefix,
      content: this.text.nodeDetail.fields.content,
      status: this.text.nodeDetail.summary.status,
      type: this.text.nodeDetail.summary.type,
      role: this.text.nodeDetail.summary.role,
      entry: this.text.nodeDetail.summary.entry,
      exit: this.text.nodeDetail.summary.exit,
      agent: this.text.nodeDetail.summary.agent,
      tool: this.text.nodeDetail.summary.tool,
      'route policy': this.text.nodeDetail.summary.routePolicy,
      route_policy: this.text.nodeDetail.summary.routePolicy,
      'join target': this.text.nodeDetail.summary.joinTarget,
      join_node_id: this.text.nodeDetail.summary.joinTarget,
      'branch index': this.text.nodeDetail.summary.branchIndex,
      branch_index: this.text.nodeDetail.summary.branchIndex,
      next: this.text.nodeDetail.summary.next,
      next_node_ids: this.text.nodeDetail.summary.next,
      derived_role: this.text.nodeDetail.fields.derivedRole,
      semantic_tags: this.text.nodeDetail.fields.semanticTags,
      branch_source_node_id: this.text.graph.summary.branchSource,
      contract_version: this.text.nodeDetail.chips.contract,
      capability: this.text.nodeDetail.chips.capability,
      description: this.text.nodeDetail.fields.description,
      input_schema: this.text.nodeDetail.fields.inputSchema,
      output_schema: this.text.nodeDetail.fields.outputSchema,
      requires_tools: this.text.nodeDetail.fields.requiresTools,
      requires_skills: this.text.nodeDetail.fields.requiresSkills,
      preconditions: this.text.nodeDetail.fields.preconditions,
      postconditions: this.text.nodeDetail.fields.postconditions,
      failure_policy: this.text.nodeDetail.chips.failure,
      parallelizable: this.text.nodeDetail.chips.parallel,
      additional_prompt: this.text.nodeDetail.fields.additionalPrompt,
      input_mapping: this.text.nodeDetail.fields.inputMapping,
      text: this.text.swarm.input.task,
      context: this.text.agent.output.context,
      audience: this.text.swarm.input.audience,
      output_format: this.text.swarm.input.outputFormat,
      constraints: this.text.swarm.input.constraints,
      result: this.text.agent.output.result,
      error: this.text.status.error,
      branch: this.text.trace.branch,
      node_name: this.text.nodeDetail.fields.nodeName,
      node_type: this.text.nodeDetail.summary.type,
      current_node_name: this.text.nodeDetail.fields.currentNodeName,
      current_node_type: this.text.nodeDetail.fields.currentNodeType,
      current_node_id: this.text.nodeDetail.fields.currentNodeId,
      rounds: this.text.agent.summary.rounds,
      run_id: this.text.labels.runId,
      event_count: this.text.graph.summary.nodes,
      created_at: this.text.nodeDetail.fields.createdAt,
      started_at: this.text.nodeDetail.fields.startedAt,
      finished_at: this.text.nodeDetail.fields.finishedAt,
      swarm: this.text.labels.swarm,
      agent_id: this.text.labels.agent,
      graph_file: this.text.nodeDetail.fields.graphFile,
      manifest_path: this.text.nodeDetail.fields.manifestPath,
      package_path: this.text.nodeDetail.fields.packagePath,
    };
    return map[key] ?? key;
  }

  localizeFactPath(path: string) {
    return path
      .split('.')
      .map((segment) => {
        const match = segment.match(/^([^[\]]+)(.*)$/);
        if (!match) {
          return segment;
        }
        const base = this.translateFactKey(match[1]);
        return `${base}${match[2] ?? ''}`;
      })
      .join('.');
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
      this.agentMessage.set(this.text.messages.inspectCurrentRequest);
    }
  }

  private toNumber(value: unknown) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  private formatError(error: unknown) {
    if (error instanceof HttpErrorResponse) {
      const statusText = error.status ? `${error.status} ${error.statusText || this.text.errors.httpError}` : this.text.errors.httpError;
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
        { key: this.text.agent.summary.agent, value: this.safeString(value['agent_id']) ?? this.text.status.unknown },
        { key: this.text.agent.summary.swarm, value: this.safeString(value['swarm']) ?? this.text.status.unknown },
        { key: this.text.status.success, value: this.safeBinaryText(value['success']) },
      ],
      sections: this.buildSectionsFromRecord([
        { title: this.text.agent.output.result, value: value['result'] },
        { title: this.text.agent.output.context, value: value['context'] },
      ]),
      trace: [],
      rawJson: this.prettyJson(value),
    };
  }

  private buildExecutionFeedbackView(
    mode: 'agent' | 'swarm',
    agentStatus: 'idle' | 'running' | 'success' | 'error',
    swarmStatus: 'idle' | 'launching' | 'running' | 'success' | 'error',
    run: RunSnapshot | null,
    events: RunEventView[],
    loading: boolean,
    runError: string | null,
  ): ExecutionFeedbackView {
    if (mode === 'agent') {
      if (agentStatus === 'running') {
        return {
          title: this.text.feedback.agent.runningTitle,
          message: this.text.feedback.agent.runningMessage,
          status: 'running',
          progress: 62,
          indeterminate: true,
          tone: 'running',
        };
      }
      if (agentStatus === 'success') {
        return {
          title: this.text.feedback.agent.successTitle,
          message: this.text.feedback.agent.successMessage,
          status: 'success',
          progress: 100,
          indeterminate: false,
          tone: 'success',
        };
      }
      if (agentStatus === 'error') {
        return {
          title: this.text.feedback.agent.errorTitle,
          message: runError ?? this.text.feedback.agent.errorMessage,
          status: 'error',
          progress: 100,
          indeterminate: false,
          tone: 'error',
        };
      }
      return {
        title: this.text.feedback.agent.idleTitle,
        message: this.text.feedback.agent.idleMessage,
        status: 'idle',
        progress: 0,
        indeterminate: false,
        tone: 'neutral',
      };
    }

    if (swarmStatus === 'launching' || (loading && !run)) {
      return {
        title: this.text.feedback.swarm.launchingTitle,
        message: this.text.feedback.swarm.launchingMessage,
        status: 'running',
        progress: 26,
        indeterminate: true,
        tone: 'running',
      };
    }

    if (run) {
      const status = run.status?.toLowerCase() ?? 'idle';
      if (status === 'completed' || swarmStatus === 'success') {
        return {
          title: this.text.feedback.swarm.successTitle,
          message: run.finished_at
            ? this.interpolate(this.text.feedback.swarm.finishedAtTemplate, {
                time: new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(run.finished_at)),
              })
            : this.text.feedback.swarm.successMessage,
          status: 'success',
          progress: 100,
          indeterminate: false,
          tone: 'success',
        };
      }
      if (status === 'failed' || swarmStatus === 'error') {
        return {
          title: this.text.feedback.swarm.errorTitle,
          message: run.error ?? runError ?? this.text.feedback.swarm.errorMessage,
          status: 'error',
          progress: 100,
          indeterminate: false,
          tone: 'error',
        };
      }
      const estimated = Math.min(92, 18 + events.length * 7);
      return {
        title: this.text.feedback.swarm.liveTitle,
        message: events.length
          ? this.interpolate(this.text.feedback.progress.eventsReceived, { count: String(events.length) })
          : this.text.feedback.swarm.liveMessage,
        status: 'running',
        progress: estimated,
        indeterminate: false,
        tone: 'running',
      };
    }

    if (swarmStatus === 'error') {
      return {
        title: this.text.feedback.swarm.errorTitle,
        message: runError ?? this.text.feedback.swarm.errorMessage,
        status: 'error',
        progress: 100,
        indeterminate: false,
        tone: 'error',
      };
    }

    return {
      title: this.text.feedback.swarm.idleTitle,
      message: this.text.feedback.swarm.idleMessage,
      status: 'idle',
      progress: 0,
      indeterminate: false,
      tone: 'neutral',
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
    const runtimeContext = this.extractRuntimeGraphContext(run);
    const nodeLookup = new Map<number, GraphNodeSnapshot>();
    graph.nodes.forEach((node) => nodeLookup.set(node.node_id, node));
    const summary = this.buildGraphSemanticSummary(graph, nodeLookup, runtimeContext);

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
      branchIndex: runtimeContext.currentBranchIndex,
      branchSourceNodeId: runtimeContext.currentBranchSourceNodeId,
      semanticSummary: summary,
      nodes: graph.nodes.map((node) => ({
        ...this.normalizeGraphNode(node, graph, runtimeContext),
        status: this.resolveNodeStatus(node.node_id, currentNodeId, completedNodeIds, failedNodeIds, currentStatus),
        isEntry: graph.entry_node_id === node.node_id,
        isExit: graph.exit_node_id === node.node_id,
      })),
      edges: this.normalizeGraphEdges(graph, nodeLookup, currentNodeId, runtimeContext),
      rawJson: this.prettyJson(graph),
    };
  }

  private extractRuntimeGraphContext(run: RunSnapshot | null): GraphRuntimeContextView {
    const context: GraphRuntimeContextView = {
      currentBranchIndex: null,
      currentBranchSourceNodeId: null,
      nodeBranchIndexes: new Map<number, Set<number>>(),
      nodeBranchSourceNodeIds: new Map<number, Set<number>>(),
      sourceBranchGroups: new Map<number, { branchIndexes: Set<number>; branchNodeIds: Set<number>; joinNodeId: number | null }>(),
      unresolvedMetadataHints: [],
    };

    if (!run) {
      return context;
    }

    const scan = (value: unknown) => {
      if (!this.isRecord(value)) {
        return;
      }

      const metadata = this.isRecord(value['metadata']) ? value['metadata'] : null;
      if (metadata) {
        const branchIndex = this.readNumber(metadata['branch_index']);
        const branchSourceNodeId = this.readNumber(metadata['branch_source_node_id']);
        if (branchIndex !== null) {
          context.currentBranchIndex = branchIndex;
        }
        if (branchSourceNodeId !== null) {
          context.currentBranchSourceNodeId = branchSourceNodeId;
        }
      }

      const branchResults = value['branch_results'];
      if (this.isRecord(branchResults)) {
        for (const [sourceKey, rawResults] of Object.entries(branchResults)) {
          const sourceNodeId = this.readNumber(sourceKey);
          if (sourceNodeId === null || !Array.isArray(rawResults)) {
            continue;
          }

          const group = context.sourceBranchGroups.get(sourceNodeId) ?? {
            branchIndexes: new Set<number>(),
            branchNodeIds: new Set<number>(),
            joinNodeId: null,
          };

          for (const rawResult of rawResults) {
            if (!this.isRecord(rawResult)) {
              continue;
            }

            const branchIndex = this.readNumber(rawResult['branch_index']);
            const branchNodeId = this.readNumber(rawResult['branch_node_id']);
            const branchMetadata = this.isRecord(rawResult['metadata']) ? rawResult['metadata'] : null;
            const nestedJoinNodeId = branchMetadata ? this.readNumber(branchMetadata['join_node_id']) : null;
            if (branchIndex !== null) {
              group.branchIndexes.add(branchIndex);
            }
            if (branchNodeId !== null) {
              group.branchNodeIds.add(branchNodeId);
              this.addNodeBranchIndex(context.nodeBranchIndexes, branchNodeId, branchIndex);
              this.addNodeBranchSource(context.nodeBranchSourceNodeIds, branchNodeId, sourceNodeId);
            }
            if (nestedJoinNodeId !== null) {
              group.joinNodeId = nestedJoinNodeId;
            }

            const trace = Array.isArray(rawResult['trace']) ? rawResult['trace'] : [];
            for (const traceEntry of trace) {
              if (!this.isRecord(traceEntry)) {
                continue;
              }
              const traceNodeId = this.readNumber(traceEntry['node_id']);
              if (traceNodeId === null) {
                continue;
              }
              if (branchIndex !== null) {
                this.addNodeBranchIndex(context.nodeBranchIndexes, traceNodeId, branchIndex);
              }
              this.addNodeBranchSource(context.nodeBranchSourceNodeIds, traceNodeId, sourceNodeId);
            }
          }

          context.sourceBranchGroups.set(sourceNodeId, group);
        }
      }

      const trace = Array.isArray(value['trace']) ? value['trace'] : [];
      for (const traceEntry of trace) {
        scan(traceEntry);
      }
    };

    scan(run.state);
    scan(run.final_state);

    return context;
  }

  private addNodeBranchIndex(map: Map<number, Set<number>>, nodeId: number, branchIndex: number | null) {
    if (branchIndex === null) {
      return;
    }
    const set = map.get(nodeId) ?? new Set<number>();
    set.add(branchIndex);
    map.set(nodeId, set);
  }

  private addNodeBranchSource(map: Map<number, Set<number>>, nodeId: number, sourceNodeId: number | null) {
    if (sourceNodeId === null) {
      return;
    }
    const set = map.get(nodeId) ?? new Set<number>();
    set.add(sourceNodeId);
    map.set(nodeId, set);
  }

  private buildGraphSemanticSummary(
    graph: GraphSnapshot,
    nodeLookup: Map<number, GraphNodeSnapshot>,
    runtimeContext: GraphRuntimeContextView,
  ): GraphSemanticSummaryView {
    const branchGroups: GraphBranchGroupView[] = [];
    const joinGroupMap = new Map<number, GraphJoinGroupView>();
    const unresolvedMetadataHints: string[] = [...runtimeContext.unresolvedMetadataHints];

    for (const node of graph.nodes) {
      const metadata = this.isRecord(node.metadata) ? node.metadata : {};
      const routePolicy = this.normalizeRoutePolicy(metadata['route_policy']);
      const joinNodeId = this.readNumber(metadata['join_node_id']);
      const branchIndexes = [...(runtimeContext.nodeBranchIndexes.get(node.node_id) ?? new Set<number>())].sort((a, b) => a - b);
      const branchSourceNodeIds = [...(runtimeContext.nodeBranchSourceNodeIds.get(node.node_id) ?? new Set<number>())].sort((a, b) => a - b);

      if (routePolicy === 'all' || joinNodeId !== null) {
        branchGroups.push({
          sourceNodeId: node.node_id,
          sourceNodeName: node.node_name,
          joinNodeId,
          branchIndexes,
          branchNodeIds: branchIndexes.length || branchSourceNodeIds.length ? [...new Set([...node.next_node_ids, ...branchSourceNodeIds])] : [...node.next_node_ids],
        });
      }

      if (joinNodeId !== null) {
        const joinGroup = joinGroupMap.get(joinNodeId) ?? {
          joinNodeId,
          joinNodeName: nodeLookup.get(joinNodeId)?.node_name ?? null,
          sourceNodeIds: [],
          sourceNodeNames: [],
        };
        joinGroup.sourceNodeIds.push(node.node_id);
        joinGroup.sourceNodeNames.push(node.node_name);
        joinGroupMap.set(joinNodeId, joinGroup);
      }

      if (joinNodeId !== null && !nodeLookup.has(joinNodeId)) {
        unresolvedMetadataHints.push(this.interpolate(this.text.graph.unresolvedHintTemplate, {
          nodeId: String(node.node_id),
          joinNodeId: String(joinNodeId),
        }));
      }
    }

    const summary: GraphSemanticSummaryView = {
      entryNodeId: graph.entry_node_id,
      exitNodeId: graph.exit_node_id,
      branchGroups,
      joinGroups: [...joinGroupMap.values()],
      unresolvedMetadataHints: [...new Set(unresolvedMetadataHints)],
    };

    return summary;
  }

  private normalizeGraphNode(
    node: GraphNodeSnapshot,
    graph: GraphSnapshot,
    runtimeContext: GraphRuntimeContextView,
  ): Omit<GraphNodeView, 'status' | 'isEntry' | 'isExit'> {
    const rawMetadata = this.isRecord(node.metadata) ? this.toJsonableRecord(node.metadata) : {};
    const routePolicy = this.normalizeRoutePolicy(rawMetadata['route_policy']);
    const joinNodeId = this.readNumber(rawMetadata['join_node_id']);
    const branchIndexes = [...(runtimeContext.nodeBranchIndexes.get(node.node_id) ?? new Set<number>())].sort((left, right) => left - right);
    const branchSourceNodeIds = [...(runtimeContext.nodeBranchSourceNodeIds.get(node.node_id) ?? new Set<number>())].sort((left, right) => left - right);
    const skillMetadata = this.extractSkillMetadata(rawMetadata);
    const semanticTags = this.buildGraphSemanticTags(node, graph, routePolicy, joinNodeId, branchIndexes, branchSourceNodeIds, skillMetadata);
    const derivedRole = this.pickDerivedGraphRole(node, graph, routePolicy, joinNodeId, branchIndexes, branchSourceNodeIds);
    const warnings = this.collectGraphNodeWarnings(node, graph, routePolicy, joinNodeId, skillMetadata, branchIndexes, branchSourceNodeIds);

    return {
      ...node,
      rawMetadata,
      routePolicy,
      joinNodeId,
      branchIndex: branchIndexes[0] ?? null,
      branchIndexes,
      branchSourceNodeId: branchSourceNodeIds[0] ?? null,
      derivedRole,
      semanticTags,
      warnings,
      skillMetadata,
    };
  }

  private normalizeGraphEdges(
    graph: GraphSnapshot,
    nodeLookup: Map<number, GraphNodeSnapshot>,
    currentNodeId: number | null,
    runtimeContext: GraphRuntimeContextView,
  ): GraphEdgeView[] {
    const structuralEdges = graph.edges.map((edge) => ({
      ...edge,
      active: currentNodeId !== null && edge.from_node_id === currentNodeId,
      derivedFromMetadata: null,
      derivedRelation: false,
    }));

    const seen = new Set(structuralEdges.map((edge) => this.edgeSignature(edge.from_node_id, edge.to_node_id, edge.label, edge.condition, edge.priority)));
    const derivedEdges: GraphEdgeView[] = [];

    for (const node of graph.nodes) {
      const metadata = this.isRecord(node.metadata) ? node.metadata : {};
      const routePolicy = this.normalizeRoutePolicy(metadata['route_policy']);
      const joinNodeId = this.readNumber(metadata['join_node_id']);
      if (routePolicy !== 'all' || joinNodeId === null) {
        continue;
      }
      if (!nodeLookup.has(joinNodeId)) {
        continue;
      }
      const signature = this.edgeSignature(node.node_id, joinNodeId, 'join', 'metadata.join_node_id', 1000);
      if (seen.has(signature)) {
        continue;
      }
      seen.add(signature);
      derivedEdges.push({
        from_node_id: node.node_id,
        to_node_id: joinNodeId,
        label: this.text.graph.edgeJoin,
        condition: 'metadata.join_node_id',
        priority: 1000,
        active: currentNodeId !== null && node.node_id === currentNodeId,
        derivedFromMetadata: ['join_node_id'],
        derivedRelation: true,
      });
    }

    const runtimeEdges: GraphEdgeView[] = [];
    runtimeContext.sourceBranchGroups.forEach((group, sourceNodeId) => {
      if (!nodeLookup.has(sourceNodeId) || group.joinNodeId === null || !nodeLookup.has(group.joinNodeId)) {
        return;
      }
      const signature = this.edgeSignature(sourceNodeId, group.joinNodeId, 'join', 'runtime.branch_join', 999);
      if (seen.has(signature)) {
        return;
      }
      seen.add(signature);
      runtimeEdges.push({
        from_node_id: sourceNodeId,
        to_node_id: group.joinNodeId,
        label: this.text.graph.edgeBranchJoin,
        condition: 'runtime.branch_join',
        priority: 999,
        active: currentNodeId !== null && sourceNodeId === currentNodeId,
        derivedFromMetadata: ['branch_index', 'branch_source_node_id'],
        derivedRelation: true,
      });
    });

    return [...structuralEdges, ...derivedEdges, ...runtimeEdges].sort(
      (left, right) =>
        left.from_node_id - right.from_node_id ||
        left.priority - right.priority ||
        left.to_node_id - right.to_node_id ||
        (left.label ?? '').localeCompare(right.label ?? '') ||
        (left.condition ?? '').localeCompare(right.condition ?? ''),
    );
  }

  private edgeSignature(fromNodeId: number, toNodeId: number, label: string | null | undefined, condition: string | null | undefined, priority: number) {
    return `${fromNodeId}:${toNodeId}:${priority}:${label ?? ''}:${condition ?? ''}`;
  }

  private normalizeRoutePolicy(rawValue: unknown): 'all' | 'first' | null {
    const text = this.safeString(rawValue)?.toLowerCase() ?? '';
    if (text === 'all') {
      return 'all';
    }
    if (text === 'first') {
      return 'first';
    }
    return null;
  }

  private extractSkillMetadata(rawMetadata: Record<string, unknown>): GraphSkillMetadataView | null {
    const skillKeys = [
      'contract_version',
      'capability',
      'description',
      'input_schema',
      'output_schema',
      'requires_tools',
      'requires_skills',
      'preconditions',
      'postconditions',
      'failure_policy',
      'parallelizable',
    ];
    const hasAny = skillKeys.some((key) => rawMetadata[key] !== undefined);
    if (!hasAny) {
      return null;
    }

    const warnings: string[] = [];
    if (rawMetadata['input_schema'] !== undefined && !this.isRecord(rawMetadata['input_schema'])) {
      warnings.push(this.text.nodeDetail.warnings.inputSchema);
    }
    if (rawMetadata['output_schema'] !== undefined && !this.isRecord(rawMetadata['output_schema'])) {
      warnings.push(this.text.nodeDetail.warnings.outputSchema);
    }

    return {
      contractVersion: this.safeString(rawMetadata['contract_version']),
      capability: this.safeString(rawMetadata['capability']),
      description: this.safeString(rawMetadata['description']),
      inputSchema: this.toJsonableValue(rawMetadata['input_schema']),
      outputSchema: this.toJsonableValue(rawMetadata['output_schema']),
      requiresTools: this.toStringList(rawMetadata['requires_tools']),
      requiresSkills: this.toStringList(rawMetadata['requires_skills']),
      preconditions: this.toStringList(rawMetadata['preconditions']),
      postconditions: this.toStringList(rawMetadata['postconditions']),
      failurePolicy: this.safeString(rawMetadata['failure_policy']),
      parallelizable: Object.prototype.hasOwnProperty.call(rawMetadata, 'parallelizable')
        ? typeof rawMetadata['parallelizable'] === 'boolean'
          ? rawMetadata['parallelizable']
          : null
        : null,
      rawMetadata: this.toJsonableRecord(rawMetadata),
      warnings,
    };
  }

  private buildGraphSemanticTags(
    node: GraphNodeSnapshot,
    graph: GraphSnapshot,
    routePolicy: 'all' | 'first' | null,
    joinNodeId: number | null,
    branchIndexes: number[],
    branchSourceNodeIds: number[],
    skillMetadata: GraphSkillMetadataView | null,
  ): string[] {
    const tags = new Set<string>();
    if (graph.entry_node_id === node.node_id) {
      tags.add(this.text.labels.entry);
    }
    if (graph.exit_node_id === node.node_id) {
      tags.add(this.text.nodeDetail.summary.exit);
    }
    if (routePolicy === 'all') {
      tags.add(this.text.graph.semantic.branchSource);
      tags.add(this.text.graph.routePolicyAll);
    } else if (routePolicy === 'first') {
      tags.add(this.text.graph.routePolicyFirst);
    }
    if (joinNodeId !== null) {
      tags.add(this.text.graph.semantic.joinTarget);
    }
    if (branchIndexes.length) {
      branchIndexes.forEach((index) => tags.add(`${this.text.status.branchPrefix} ${index}`));
    }
    if (branchSourceNodeIds.length) {
      branchSourceNodeIds.forEach((sourceId) => tags.add(`${this.text.graph.sourcePrefix} ${sourceId}`));
    }
    if (node.agent_id) {
      tags.add(this.text.labels.agent);
    }
    if (node.tool_name) {
      tags.add(this.text.labels.tool);
    }
    if (skillMetadata) {
      tags.add(this.text.nodeDetail.chips.skill);
      if (skillMetadata.capability) {
        tags.add(`${this.text.nodeDetail.chips.capability}：${skillMetadata.capability}`);
      }
    }
    return [...tags];
  }

  private pickDerivedGraphRole(
    node: GraphNodeSnapshot,
    graph: GraphSnapshot,
    routePolicy: 'all' | 'first' | null,
    joinNodeId: number | null,
    branchIndexes: number[],
    branchSourceNodeIds: number[],
  ): string {
    if (graph.entry_node_id === node.node_id) {
      return this.text.labels.entry;
    }
    if (graph.exit_node_id === node.node_id) {
      return this.text.nodeDetail.summary.exit;
    }
    if (routePolicy === 'all' && joinNodeId !== null) {
      return this.text.graph.semantic.branchSource;
    }
    if (routePolicy === 'all') {
      return this.text.graph.semantic.branchSource;
    }
    if (joinNodeId !== null) {
      return this.text.graph.semantic.joinTarget;
    }
    if (branchIndexes.length || branchSourceNodeIds.length) {
      return this.text.graph.semantic.branchMember;
    }
    if (node.tool_name) {
      return this.text.labels.tool;
    }
    if (node.agent_id) {
      return this.text.labels.agent;
    }
    return this.text.graph.semantic.node;
  }

  private collectGraphNodeWarnings(
    node: GraphNodeSnapshot,
    graph: GraphSnapshot,
    routePolicy: 'all' | 'first' | null,
    joinNodeId: number | null,
    skillMetadata: GraphSkillMetadataView | null,
    branchIndexes: number[],
    branchSourceNodeIds: number[],
  ): string[] {
    const warnings: string[] = [];
    const metadata = this.isRecord(node.metadata) ? node.metadata : {};
    const knownKeys = new Set([
      'route_policy',
      'join_node_id',
      'contract_version',
      'capability',
      'description',
      'input_schema',
      'output_schema',
      'requires_tools',
      'requires_skills',
      'preconditions',
      'postconditions',
      'failure_policy',
      'parallelizable',
    ]);

    for (const key of Object.keys(metadata)) {
      if (!knownKeys.has(key)) {
        warnings.push(this.interpolate(this.text.nodeDetail.warnings.unknownKey, { key }));
      }
    }

    if (routePolicy === null && Object.prototype.hasOwnProperty.call(metadata, 'route_policy')) {
      warnings.push(this.interpolate(this.text.nodeDetail.warnings.routePolicy, { value: String(metadata['route_policy']) }));
    }

    if (joinNodeId !== null && !graph.nodes.some((item) => item.node_id === joinNodeId)) {
      warnings.push(this.interpolate(this.text.nodeDetail.warnings.joinNodeMissing, { value: String(joinNodeId) }));
    }

    if (skillMetadata?.warnings.length) {
      warnings.push(...skillMetadata.warnings);
    }

    if (branchIndexes.length === 0 && branchSourceNodeIds.length > 0) {
      warnings.push(this.text.nodeDetail.warnings.runtimeBranchSource);
    }

    return [...new Set(warnings)];
  }

  private toStringList(value: unknown): string[] {
    if (Array.isArray(value)) {
      return value
        .map((item) => this.safeString(item))
        .filter((item): item is string => Boolean(item));
    }
    const text = this.safeString(value);
    return text ? [text] : [];
  }

  private toJsonableValue(value: unknown): unknown {
    return this.cloneJsonValue(value);
  }

  private toJsonableRecord(value: Record<string, unknown>): Record<string, unknown> {
    try {
      const parsed = JSON.parse(JSON.stringify(value));
      return this.isRecord(parsed) ? parsed : {};
    } catch {
      return {};
    }
  }

  private cloneJsonValue(value: unknown): unknown {
    try {
      return JSON.parse(JSON.stringify(value));
    } catch {
      return value;
    }
  }

  private buildGraphSpectrumView(view: GraphView | null, zoom: number, layoutMode: 'horizontal' | 'vertical'): GraphSpectrumView | null {
    if (!view) {
      return null;
    }

    const safeZoom = this.clampGraphZoom(zoom);
    const displayScale = safeZoom * 2;
    const horizontal = layoutMode === 'horizontal';
    const nodeWidth = horizontal ? 176 : 122;
    const nodeHeight = horizontal ? 44 : 58;
    const levelGap = horizontal ? 172 : 112;
    const nodeGap = horizontal ? 18 : 22;
    const padding = 20;

    const layout = this.layoutGraphNodes(view, nodeWidth, nodeHeight, levelGap, nodeGap, padding, layoutMode);
    const positions = layout.positions;
    const widestSpan = Math.max(layout.widestSpan, 1);
    const width = horizontal
      ? Math.max(1120, padding * 2 + layout.maxLevel * levelGap + nodeWidth)
      : Math.max(1120, padding * 2 + widestSpan * nodeWidth + Math.max(0, widestSpan - 1) * nodeGap);
    const height = horizontal
      ? Math.max(180, padding * 2 + widestSpan * nodeHeight + Math.max(0, widestSpan - 1) * nodeGap)
      : Math.max(180, padding * 2 + layout.maxLevel * levelGap + nodeHeight);
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
      const midY = y1 + Math.max(22, (y2 - y1) / 2);
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
      displayScale,
      panX,
      panY,
      panTransform: `translate(${panX} ${panY})`,
      scaleTransform: `scale(${displayScale})`,
      branchIndex: view.branchIndex,
      branchSourceNodeId: view.branchSourceNodeId,
      semanticSummary: view.semanticSummary,
      nodes: layoutNodes,
      edges: layoutEdges,
      rawJson: this.prettyJson({
        zoom: safeZoom,
        layoutMode,
        panX,
        panY,
        layout: layoutNodes.map((node) => ({
          node_id: node.node_id,
          x: node.x,
          y: node.y,
          width: node.width,
          height: node.height,
        })),
        branchIndex: view.branchIndex,
        branchSourceNodeId: view.branchSourceNodeId,
        semanticSummary: view.semanticSummary,
      }),
    };
  }

  private buildGraphNodeDetailView(view: GraphSpectrumView | null, selectedNodeId: number | null): GraphNodeDetailView | null {
    if (!view || selectedNodeId === null) {
      return null;
    }

    const node = view.nodes.find((item) => item.node_id === selectedNodeId);
    if (!node) {
      return null;
    }

    return {
      node,
      summary: [
        { key: this.text.nodeDetail.summary.status, value: this.displayNodeStatus(node.status) },
        { key: this.text.nodeDetail.summary.type, value: node.node_type },
        { key: this.text.nodeDetail.summary.role, value: node.derivedRole },
        { key: this.text.nodeDetail.summary.entry, value: this.displayBinary(node.isEntry) },
        { key: this.text.nodeDetail.summary.exit, value: this.displayBinary(node.isExit) },
        { key: this.text.nodeDetail.summary.agent, value: node.agent_id ?? this.text.status.unknown },
        { key: this.text.nodeDetail.summary.tool, value: node.tool_name ?? this.text.status.unknown },
        { key: this.text.nodeDetail.summary.routePolicy, value: this.displayRoutePolicy(node.routePolicy) },
        { key: this.text.nodeDetail.summary.joinTarget, value: node.joinNodeId !== null ? String(node.joinNodeId) : this.text.graph.none },
        { key: this.text.nodeDetail.summary.branchIndex, value: node.branchIndexes.length ? node.branchIndexes.join(', ') : this.text.graph.none },
        { key: this.text.nodeDetail.summary.next, value: node.next_node_ids.length ? node.next_node_ids.join(', ') : this.text.graph.none },
      ],
      semanticChips: node.semanticTags,
      skillChips: node.skillMetadata
        ? [
            node.skillMetadata.contractVersion ? `${this.text.nodeDetail.chips.contract} ${node.skillMetadata.contractVersion}` : '',
            node.skillMetadata.capability ? `${this.text.nodeDetail.chips.capability} ${node.skillMetadata.capability}` : '',
            node.skillMetadata.failurePolicy ? `${this.text.nodeDetail.chips.failure} ${node.skillMetadata.failurePolicy}` : '',
            node.skillMetadata.parallelizable === true
              ? this.text.nodeDetail.chips.parallel
              : node.skillMetadata.parallelizable === false
                ? this.text.nodeDetail.chips.serial
                : '',
          ].filter((item): item is string => Boolean(item))
        : [],
      runtimeChips: [
        node.branchIndexes.length ? `${this.text.status.branchPrefix} ${node.branchIndexes.join(', ')}` : '',
        node.branchSourceNodeId !== null ? `${this.text.graph.semantic.branchSource} ${node.branchSourceNodeId}` : '',
        node.warnings.length ? `${node.warnings.length} ${this.text.nodeDetail.chips.warning}` : '',
      ].filter((item): item is string => Boolean(item)),
      sections: this.buildSectionsFromRecord([
        { title: this.text.nodeDetail.sections.semanticMetadata, value: {
          derived_role: node.derivedRole,
          semantic_tags: node.semanticTags,
          route_policy: node.routePolicy,
          join_node_id: node.joinNodeId,
          branch_index: node.branchIndexes,
          branch_source_node_id: node.branchSourceNodeId,
          warnings: node.warnings,
        } },
        { title: this.text.nodeDetail.sections.skillMetadata, value: node.skillMetadata ?? null },
        { title: this.text.nodeDetail.sections.metadata, value: node.metadata },
        {
          title: this.text.nodeDetail.sections.promptAndMapping,
          value: {
            additional_prompt: node.additional_prompt ?? null,
            input_mapping: node.input_mapping ?? null,
          },
        },
      ]),
      rawJson: this.prettyJson({
        ...node,
        raw_metadata: node.rawMetadata,
      }),
    };
  }

  protected isCollapsibleResultSection(title: string) {
    return title.trim() === this.text.agent.output.result;
  }

  private buildRunEventView(event: RunEvent): RunEventView {
    const status = this.safeString(event.status) ?? this.text.status.info;
    const nodeName = this.safeString(event.node_name) ?? this.safeString(event.data['entry_node_name']) ?? 'system';
    const branch = this.safeString(event.branch) ?? 'main';
    const timestamp = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(event.timestamp * 1000));
    const summary = [
      this.eventTitle(event.event_type),
      nodeName,
      branch !== 'main' ? this.displayBranchLabel(branch) : this.text.status.mainBranch,
      this.displayEventStatus(status),
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
        { key: this.text.payload.summary.mode, value: this.text.payload.mode },
        { key: this.text.payload.summary.shape, value: this.displayJsonShape(value) },
        { key: this.text.payload.summary.fields, value: records.length ? `${records.length} ${this.text.status.keysSuffix}` : `0 ${this.text.status.keysSuffix}` },
      ],
      sections: this.buildSectionsFromRecord([{ title: this.text.payload.title, value }]),
      trace: [],
      rawJson: this.prettyJson(value),
    };
  }

  private buildGraphNodeLabelLines(node: GraphNodeView): string[] {
    return [node.node_name];
  }

  private layoutGraphNodes(
    view: GraphView,
    nodeWidth: number,
    nodeHeight: number,
    levelGap: number,
    nodeGap: number,
    padding: number,
    layoutMode: 'horizontal' | 'vertical',
  ): { positions: Map<number, { x: number; y: number }>; widestSpan: number; maxLevel: number } {
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

    let widestSpan = 1;
    grouped.forEach((items) => {
      widestSpan = Math.max(widestSpan, items.length);
    });

    const positions = new Map<number, { x: number; y: number }>();
    const orderedLevels = [...grouped.keys()].sort((left, right) => left - right);
    orderedLevels.forEach((level) => {
      const items = grouped.get(level) ?? [];
      if (layoutMode === 'horizontal') {
        const columnHeight = items.length * nodeHeight + Math.max(0, items.length - 1) * nodeGap;
        const startY = padding + (widestSpan * nodeHeight + Math.max(0, widestSpan - 1) * nodeGap - columnHeight) / 2;
        items.forEach((nodeId, index) => {
          positions.set(nodeId, {
            x: padding + level * levelGap,
            y: startY + index * (nodeHeight + nodeGap),
          });
        });
        return;
      }

      const rowWidth = items.length * nodeWidth + Math.max(0, items.length - 1) * nodeGap;
      const startX = padding + (widestSpan * nodeWidth + Math.max(0, widestSpan - 1) * nodeGap - rowWidth) / 2;
      items.forEach((nodeId, index) => {
        positions.set(nodeId, {
          x: startX + index * (nodeWidth + nodeGap),
          y: padding + level * levelGap,
        });
      });
    });

    return {
      positions,
      widestSpan,
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

    const title = this.safeString(value['node_name']) ?? this.safeString(value['name']) ?? `${this.text.trace.titlePrefix} ${index + 1}`;
    const nodeType = this.safeString(value['node_type']);
    const status = this.safeString(value['status']) ?? this.text.status.unknown;
    const branch = this.safeString(value['branch']) ?? 'main';
    const error = this.safeString(value['error']);
    const meta: FactRow[] = [];

    for (const [key, rawValue] of Object.entries(value)) {
      if (['input_payload', 'output_payload', 'payload', 'raw_response', 'error'].includes(key)) {
        continue;
      }
      const rendered = this.renderFlatValue(rawValue);
      if (rendered) {
        meta.push({ key: this.translateFactKey(key), value: rendered });
      }
    }

    if (nodeType) {
      meta.unshift({ key: this.text.trace.type, value: nodeType });
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
      return prefix ? [{ key: this.localizeFactPath(prefix), value: 'null' }] : [];
    }

    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      return prefix ? [{ key: this.localizeFactPath(prefix), value: String(value) }] : [];
    }

    if (Array.isArray(value)) {
      const primitives = value.filter((item) => item === null || ['string', 'number', 'boolean'].includes(typeof item));
      if (primitives.length && primitives.length === value.length) {
        return prefix ? [{ key: this.localizeFactPath(prefix), value: primitives.map((item) => String(item)).join(', ') }] : [];
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
        rows.push({ key: this.localizeFactPath(nextKey), value: 'null' });
        continue;
      }
      if (typeof rawValue === 'string' || typeof rawValue === 'number' || typeof rawValue === 'boolean') {
        rows.push({ key: this.localizeFactPath(nextKey), value: String(rawValue) });
        continue;
      }
      if (Array.isArray(rawValue)) {
        const primitives = rawValue.filter((item) => item === null || ['string', 'number', 'boolean'].includes(typeof item));
        if (primitives.length && primitives.length === rawValue.length) {
          rows.push({ key: this.localizeFactPath(nextKey), value: primitives.map((item) => String(item)).join(', ') });
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
      return `${value.length} ${this.text.status.itemsSuffix}`;
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
        return this.text.events.runStarted;
      case 'run.completed':
        return this.text.events.runCompleted;
      case 'run.failed':
        return this.text.events.runFailed;
      case 'node.started':
        return this.text.events.nodeStarted;
      case 'node.completed':
        return this.text.events.nodeCompleted;
      case 'node.failed':
        return this.text.events.nodeFailed;
      case 'branch.started':
        return this.text.events.branchStarted;
      case 'branch.completed':
        return this.text.events.branchCompleted;
      case 'branch.failed':
        return this.text.events.branchFailed;
      default:
        return eventType;
    }
  }

  private isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }
}
