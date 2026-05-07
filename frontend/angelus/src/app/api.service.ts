import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { normalizeJsonValue } from './json-utils';
import type {
  AgentListResponse,
  AgentRoundRequest,
  AgentRoundResponse,
  ApiIndexResponse,
  GraphResponse,
  GraphSnapshot,
  GraphDiffResponse,
  GraphStateResponse,
  HealthResponse,
  HistoryEntry,
  HistoryResponse,
  KnowledgeCatalogItem,
  KnowledgeListResponse,
  LogListResponse,
  MemoryListResponse,
  MemoryCatalogItem,
  MetricsResponse,
  TaskListResponse,
  ReadyResponse,
  RunSnapshot,
  RunStartResponse,
  RunStopResponse,
  RunSwarmRequest,
  RunSwarmResponse,
  SettingsResponse,
  SwarmApisResponse,
  SwarmDetailResponse,
  SwarmListResponse,
  SwarmSummary,
  SwarmStatsResponse,
  ToolListResponse,
  UpdateSettingsRequest,
  ThoughtGraphResponse,
  ExecutionTraceResponse,
  RunStreamEvent,
  RuntimeSwarmSummary,
} from './api.types';

export function normalizeApiBaseUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return '';
  }

  const stripped = trimmed.replace(/\/+$/, '');
  if (/^https?:\/\//i.test(stripped)) {
    try {
      const parsed = new URL(stripped);
      parsed.pathname = parsed.pathname.replace(/\/api$/i, '');
      return parsed.toString().replace(/\/+$/, '');
    } catch {
      return stripped.replace(/\/api$/i, '');
    }
  }

  return stripped.replace(/\/api$/i, '');
}

export function joinUrl(baseUrl: string, path: string): string {
  const normalizedInput = normalizeApiBaseUrl(baseUrl);
  const base = normalizedInput || '';
  const normalizedBase = base.endsWith('/') ? base.slice(0, -1) : base;
  if (!path) {
    return normalizedBase;
  }
  const trimmedPath = path.trim();
  const canonicalPath = trimmedPath === '/' ? '' : trimmedPath.replace(/\/+$/, '');
  if (!canonicalPath) {
    return normalizedBase;
  }
  const normalizedPath = canonicalPath.startsWith('/') ? canonicalPath : `/${canonicalPath}`;

  if (/^https?:\/\//i.test(normalizedBase)) {
    return `${normalizedBase}${normalizedPath}`;
  }

  return `${normalizedBase}${normalizedPath}`;
}

type RawSwarmListResponse = {
  success: boolean;
  swarms: RuntimeSwarmSummary[];
};

type RuntimeGraphNode = {
  type?: string;
  class?: string;
  id?: string;
  name?: string;
  node_name?: string;
  node_type?: string;
  agent_id?: string;
  tool_name?: string;
  metadata?: unknown;
  input_mapping?: unknown;
};

type RuntimeGraphEdge = {
  source?: string;
  target?: string;
  label?: string | null;
};

interface StreamClient {
  onmessage: ((event: MessageEvent<string>) => void) | null;
  onerror: ((event: Event) => void) | null;
  close(): void;
}

function createMessageEvent(data: string): MessageEvent<string> {
  return {
    data,
    lastEventId: '',
    origin: '',
    ports: [],
    source: null,
    type: 'message',
    bubbles: false,
    cancelBubble: false,
    cancelable: false,
    composed: false,
    defaultPrevented: false,
    eventPhase: 0,
    isTrusted: true,
    returnValue: true,
    timeStamp: Date.now(),
    preventDefault(): void {},
    stopImmediatePropagation(): void {},
    stopPropagation(): void {},
    composedPath(): EventTarget[] { return []; },
    initEvent(): void {},
  } as unknown as MessageEvent<string>;
}

@Injectable({
  providedIn: 'root',
})
export class ApiService {
  constructor(private readonly http: HttpClient) {}

  async index(baseUrl = ''): Promise<ApiIndexResponse> {
    const [health, swarms] = await Promise.all([
      this.health(baseUrl),
      this.listSwarms(baseUrl),
    ]);
    return {
      success: health.success,
      service: 'angelus',
      swarm_count: swarms.swarms.length,
      load_error: null,
      api_root: baseUrl.trim() || '',
    };
  }

  async health(baseUrl = ''): Promise<HealthResponse> {
    return firstValueFrom(this.http.get<HealthResponse>(joinUrl(baseUrl, '/health')));
  }

  async ready(baseUrl = ''): Promise<ReadyResponse> {
    const health = await this.health(baseUrl).catch(() => ({ success: false, status: 'offline' }));
    const swarms = await this.listSwarms(baseUrl).catch(() => ({ success: false, swarms: [] as SwarmListResponse['swarms'] }));
    return {
      success: health.success,
      ready: health.status === 'ok',
      swarm_count: swarms.swarms.length,
      reason: health.status === 'ok' ? undefined : 'backend unavailable',
      invalid_swarms: [],
    };
  }

  getSettings(baseUrl = ''): Promise<SettingsResponse> {
    return Promise.resolve({
      success: true,
      settings: {
        api: {
          base_url: baseUrl.trim() || '',
          timeout_seconds: 30,
          sse_reconnect_interval_seconds: 5,
          auto_reconnect: true,
        },
      },
    });
  }

  updateSettings(_baseUrl = '', body: UpdateSettingsRequest): Promise<SettingsResponse> {
    return Promise.resolve({
      success: true,
      settings: {
        api: {
          base_url: body.api.base_url.trim() || '',
          timeout_seconds: body.api.timeout_seconds,
          sse_reconnect_interval_seconds: body.api.sse_reconnect_interval_seconds,
          auto_reconnect: body.api.auto_reconnect,
        },
      },
    });
  }

  async listSwarms(baseUrl = ''): Promise<SwarmListResponse> {
    const raw = await firstValueFrom(this.http.get<RawSwarmListResponse>(joinUrl(baseUrl, '/swarms')));
    const swarms = await Promise.all(
      raw.swarms.map(async (item) => this.enrichSwarmSummary(baseUrl, item.name, item.agent_count, item.tool_count))
    );
    return {
      success: raw.success,
      swarms,
    };
  }

  async loadSwarm(
    baseUrl: string,
    request: { package_path?: string; source?: string; swarm_name?: string; replace?: boolean }
  ): Promise<{ success: boolean; action: string; swarm: SwarmDetailResponse['swarm'] }> {
    const response = await firstValueFrom(
      this.http.post<{ name: string; id: string; message: string }>(joinUrl(baseUrl, '/swarms/load'), {
        source: request.source ?? request.package_path ?? request.swarm_name ?? '',
      })
    );
    const swarm = await this.getSwarm(baseUrl, response.name);
    return {
      success: true,
      action: response.message || 'loaded',
      swarm: swarm.swarm,
    };
  }

  async getSwarm(baseUrl: string, swarmName: string): Promise<SwarmDetailResponse> {
    const [listResult, graphResult, historyResult] = await Promise.all([
      this.listSwarms(baseUrl).catch(() => ({ success: false, swarms: [] as SwarmListResponse['swarms'] })),
      this.getGraph(baseUrl, swarmName).catch(() => this.emptyGraphSnapshot(swarmName)),
      this.getHistory(baseUrl, swarmName).catch(() => ({ history: [] as HistoryEntry[] })),
    ]);
    const fallback = listResult.swarms.find((item) => item.swarm_name === swarmName) ?? this.buildSummaryShell(swarmName);
    return {
      success: true,
      swarm: {
        ...fallback,
        agent_files: this.agentFilesFromGraph(graphResult.graph),
        graph: graphResult.graph,
        active_run_count: historyResult.history.length > 0 ? 1 : 0,
        active_run_ids: historyResult.history.length > 0 ? [historyResult.history[historyResult.history.length - 1].timestamp] : [],
      },
    };
  }

  getSwarmApis(baseUrl: string, swarmName: string): Promise<SwarmApisResponse> {
    return firstValueFrom(
      this.http.get<SwarmApisResponse>(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/apis`))
    );
  }

  listAgents(
    baseUrl: string,
    swarmName: string,
    query: Record<string, string | number | boolean | undefined | null> = {}
  ): Promise<AgentListResponse> {
    return firstValueFrom(
      this.http.post<AgentListResponse>(
        joinUrl(baseUrl, `/catalog/swarms/${encodeURIComponent(swarmName)}/agents/search`),
        query
      )
    );
  }

  listTasks(
    baseUrl: string,
    swarmName: string,
    query: Record<string, string | number | boolean | undefined | null> = {}
  ): Promise<TaskListResponse> {
    return firstValueFrom(
      this.http.post<TaskListResponse>(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/tasks/search`), query)
    );
  }

  listTools(
    baseUrl: string,
    query: Record<string, string | number | boolean | undefined | null> = {}
  ): Promise<ToolListResponse> {
    return firstValueFrom(this.http.post<ToolListResponse>(joinUrl(baseUrl, '/catalog/tools/search'), query));
  }

  getSwarmStats(baseUrl: string, swarmName: string): Promise<SwarmStatsResponse> {
    return firstValueFrom(
      this.http.get<SwarmStatsResponse>(joinUrl(baseUrl, `/catalog/swarms/${encodeURIComponent(swarmName)}/stats`))
    );
  }

  listLogs(
    baseUrl: string,
    query: Record<string, string | number | boolean | undefined | null> = {}
  ): Promise<LogListResponse> {
    return firstValueFrom(this.http.post<LogListResponse>(joinUrl(baseUrl, '/catalog/logs/search'), query));
  }

  getMetrics(
    baseUrl: string,
    query: Record<string, string | number | boolean | undefined | null> = {}
  ): Promise<MetricsResponse> {
    return firstValueFrom(this.http.post<MetricsResponse>(joinUrl(baseUrl, '/catalog/metrics'), query));
  }

  listKnowledge(
    baseUrl: string,
    query: Record<string, string | number | boolean | undefined | null> = {}
  ): Promise<KnowledgeListResponse> {
    return firstValueFrom(this.http.post<KnowledgeListResponse>(joinUrl(baseUrl, '/knowledge/search'), query));
  }

  getKnowledge(baseUrl: string, knowledgeId: string): Promise<{ success: boolean; knowledge: KnowledgeCatalogItem }> {
    return firstValueFrom(
      this.http.get<{ success: boolean; knowledge: KnowledgeCatalogItem }>(
        joinUrl(baseUrl, `/knowledge/${encodeURIComponent(knowledgeId)}`)
      )
    );
  }

  createKnowledge(baseUrl: string, body: Record<string, unknown>): Promise<{ success: boolean; knowledge: KnowledgeCatalogItem }> {
    return firstValueFrom(
      this.http.post<{ success: boolean; knowledge: KnowledgeCatalogItem }>(joinUrl(baseUrl, '/knowledge'), body)
    );
  }

  updateKnowledge(
    baseUrl: string,
    knowledgeId: string,
    body: Record<string, unknown>
  ): Promise<{ success: boolean; knowledge: KnowledgeCatalogItem }> {
    return firstValueFrom(
      this.http.put<{ success: boolean; knowledge: KnowledgeCatalogItem }>(
        joinUrl(baseUrl, `/knowledge/${encodeURIComponent(knowledgeId)}`),
        body
      )
    );
  }

  deleteKnowledge(baseUrl: string, knowledgeId: string): Promise<{ success: boolean; knowledge: KnowledgeCatalogItem }> {
    return firstValueFrom(
      this.http.delete<{ success: boolean; knowledge: KnowledgeCatalogItem }>(
        joinUrl(baseUrl, `/knowledge/${encodeURIComponent(knowledgeId)}`)
      )
    );
  }

  listMemory(
    baseUrl: string,
    query: Record<string, string | number | boolean | undefined | null> = {}
  ): Promise<MemoryListResponse> {
    return firstValueFrom(this.http.post<MemoryListResponse>(joinUrl(baseUrl, '/memory/search'), query));
  }

  getMemory(baseUrl: string, memoryId: string): Promise<{ success: boolean; memory: MemoryCatalogItem }> {
    return firstValueFrom(
      this.http.get<{ success: boolean; memory: MemoryCatalogItem }>(
        joinUrl(baseUrl, `/memory/${encodeURIComponent(memoryId)}`)
      )
    );
  }

  createMemory(baseUrl: string, body: Record<string, unknown>): Promise<{ success: boolean; memory: MemoryCatalogItem }> {
    return firstValueFrom(
      this.http.post<{ success: boolean; memory: MemoryCatalogItem }>(joinUrl(baseUrl, '/memory'), body)
    );
  }

  deleteMemory(baseUrl: string, memoryId: string): Promise<{ success: boolean; memory: MemoryCatalogItem }> {
    return firstValueFrom(
      this.http.delete<{ success: boolean; memory: MemoryCatalogItem }>(
        joinUrl(baseUrl, `/memory/${encodeURIComponent(memoryId)}`)
      )
    );
  }

  async getGraph(baseUrl: string, swarmName: string): Promise<{ success: boolean; swarm: string; graph: GraphSnapshot }>;
  async getGraph(swarmName: string): Promise<GraphResponse>;
  async getGraph(baseUrlOrName: string, swarmName?: string): Promise<{ success: boolean; swarm: string; graph: GraphSnapshot } | GraphResponse> {
    if (typeof swarmName !== 'string') {
      const graph = await this.fetchGraphSnapshot('', baseUrlOrName, 'execution');
      return {
        name: graph.graph_name,
        nodes: graph.nodes.map((node) => ({
          id: String(node.node_id),
          name: node.node_name,
          type: node.node_type,
          metadata: node.metadata,
        })),
        edges: graph.edges.map((edge) => ({
          source: String(edge.from_node_id),
          target: String(edge.to_node_id),
          label: edge.label,
        })),
      };
    }
    const graph = await this.fetchGraphSnapshot(baseUrlOrName, swarmName, 'execution');
    return {
      success: true,
      swarm: swarmName,
      graph,
    };
  }

  async getGraphState(baseUrl: string, swarmName: string, sinceRevision?: number): Promise<GraphStateResponse> {
    const graph = await this.fetchGraphSnapshot(baseUrl, swarmName, 'execution');
    return {
      success: true,
      swarm: swarmName,
      graph: {
        graph_name: graph.graph_name,
        graph_kind: graph.graph_kind,
        entry_node_id: graph.entry_node_id,
        exit_node_id: graph.exit_node_id,
        node_count: graph.node_count,
        edge_count: graph.edge_count,
        nodes: graph.nodes,
        edges: graph.edges,
        revision: graph.revision ?? 0,
        hash: graph.hash ?? '',
        updated_at: graph.updated_at ?? new Date().toISOString(),
        last_change: graph.last_change ?? null,
      },
      has_changes_since: typeof sinceRevision === 'number' ? (graph.revision ?? 0) > sinceRevision : false,
    };
  }

  async getGraphDiff(baseUrl: string, swarmName: string, sinceRevision: number): Promise<GraphDiffResponse> {
    const graph = await this.fetchGraphSnapshot(baseUrl, swarmName, 'execution');
    return {
      success: true,
      swarm: swarmName,
      patch: {
        base_revision: sinceRevision,
        current_revision: graph.revision ?? 0,
        graph_id: swarmName,
        is_gap_free: true,
        operations: [],
        last_change: graph.last_change ?? null,
      },
    };
  }

  async getThoughtGraph(baseUrl: string, swarmName: string): Promise<ThoughtGraphResponse> {
    const response = await firstValueFrom(
      this.http.get<ThoughtGraphResponse>(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/thinking_graph`))
    );
    return response;
  }

  async getExecutionTrace(baseUrl: string, swarmName: string, runId?: string): Promise<ExecutionTraceResponse> {
    const history = await this.getHistory(baseUrl, swarmName);
    const run = history.history.length > 0
      ? this.buildRunSnapshot(swarmName, history.history[history.history.length - 1].input, history.history[history.history.length - 1].output)
      : null;
    return {
      success: true,
      swarm: swarmName,
      run,
      events: history.history.map((item) => item.trace ?? { input: item.input, output: item.output }),
    };
  }

  async reloadSwarm(
    baseUrl: string,
    swarmName: string,
    request: { force?: boolean; package_path?: string; source?: string } = {}
  ): Promise<{ success: boolean; action: string; swarm: SwarmDetailResponse['swarm'] }> {
    const swarm = await this.getSwarm(baseUrl, swarmName);
    return {
      success: true,
      action: request.force ? 'refreshed' : 'loaded',
      swarm: swarm.swarm,
    };
  }

  async unloadSwarm(
    baseUrl: string,
    swarmName: string,
    force = false
  ): Promise<{ success: boolean; action: string; swarm: { swarm_name: string; package_path: string } }> {
    return firstValueFrom(
      this.http.request<{ success: boolean; action: string; swarm: { swarm_name: string; package_path: string } }>(
        'DELETE',
        joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}`),
        { body: { force } }
      )
    );
  }

  async runSwarm(baseUrl: string, swarmName: string, request: RunSwarmRequest): Promise<RunSwarmResponse> {
    const events = await this.collectRunEvents(baseUrl, swarmName, request);
    const result = events.find((item) => item.event === 'result');
    const resultData = result ? (normalizeJsonValue(result.data) as Record<string, unknown>) : null;
    return {
      success: true,
      swarm: swarmName,
      rounds: request.rounds ?? 1,
      output: resultData ? (normalizeJsonValue(resultData['output'] ?? null) as RunSwarmResponse['output']) : null,
      trace: resultData ? (normalizeJsonValue(resultData['trace'] ?? null) as RunSwarmResponse['trace']) : null,
      metadata: normalizeJsonValue({ events: events.map((event) => normalizeJsonValue(event)) }) as RunSwarmResponse['metadata'],
    };
  }

  async startRun(baseUrl: string, swarmName: string, request: RunSwarmRequest): Promise<RunStartResponse> {
    const result = await this.runSwarm(baseUrl, swarmName, request);
    return {
      success: true,
      status: 'completed',
      swarm: swarmName,
      run: this.buildRunSnapshot(swarmName, request.input, result.output, result.trace, request.rounds ?? 1),
    };
  }

  async getRun(baseUrl: string, runId: string): Promise<{ success: boolean; run: RunSnapshot }> {
    return {
      success: true,
      run: this.buildRunSnapshot(runId, null, null),
    };
  }

  async stopRun(baseUrl: string, runId: string, stopType: 'soft' | 'hard' = 'soft'): Promise<RunStopResponse> {
    const response = await this.stopSwarm(baseUrl, runId, stopType);
    return {
      success: response.success,
      run_id: runId,
      stop_type: stopType,
      status: response.requested ? 'stopped' : 'idle',
    };
  }

  async stopSwarm(
    baseUrl: string,
    swarmName: string,
    stopType: 'soft' | 'hard' = 'soft'
  ): Promise<{ success: boolean; name: string; mode: 'soft' | 'hard'; requested: boolean; reason?: string; stop_state: Record<string, unknown> }> {
    return firstValueFrom(
      this.http.post<{ success: boolean; name: string; mode: 'soft' | 'hard'; requested: boolean; reason?: string; stop_state: Record<string, unknown> }>(
        joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/stop`),
        { mode: stopType }
      )
    );
  }

  stopSwarmRuns(baseUrl: string, swarmName: string, stopType: 'soft' | 'hard' = 'soft'): Promise<{ success: boolean; swarm: string; stop_type: string; stopped: Array<{ run_id: string; status: string }>; count: number }> {
    return this.stopSwarm(baseUrl, swarmName, stopType).then((response) => ({
      success: response.success,
      swarm: swarmName,
      stop_type: stopType,
      stopped: [],
      count: response.requested ? 1 : 0,
    }));
  }

  async runAgentRound(
    baseUrl: string,
    swarmName: string,
    agentId: string,
    request: AgentRoundRequest
  ): Promise<AgentRoundResponse> {
    const result = await this.runSwarm(baseUrl, swarmName, {
      input: {
        agent_id: agentId,
        message: request.message,
        additional_prompt: request.additional_prompt ?? null,
      },
      rounds: request.rounds ?? 1,
    });
    return {
      success: true,
      swarm: swarmName,
      agent_id: agentId,
      result: result.output,
      context: result.trace,
    };
  }

  async getHistory(baseUrl: string, swarmName: string): Promise<HistoryResponse>;
  async getHistory(swarmName: string): Promise<{ history: HistoryEntry[] }>;
  async getHistory(baseUrlOrName: string, swarmName?: string): Promise<HistoryResponse | { history: HistoryEntry[] }> {
    const baseUrl = typeof swarmName === 'string' ? baseUrlOrName : '';
    const name = typeof swarmName === 'string' ? swarmName : baseUrlOrName;
    const response = await firstValueFrom(
      this.http.get<{ success: boolean; runs: Array<{ timestamp: string; input: unknown; output: unknown; trace?: unknown }> }>(
        joinUrl(baseUrl, `/swarms/${encodeURIComponent(name)}/history`)
      )
    );
    return {
      history: response.runs.map((run) => ({
        timestamp: run.timestamp,
        input: run.input as HistoryEntry['input'],
        output: run.output as HistoryEntry['output'],
        trace: (run.trace ?? null) as HistoryEntry['trace'],
      })),
    };
  }

  runSwarmStream(swarmName: string, request: RunSwarmRequest, baseUrl = ''): any {
    let cancelled = false;
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
    const client: StreamClient = {
      onmessage: null,
      onerror: null,
      close: () => {
        cancelled = true;
        void reader?.cancel().catch(() => {});
        reader = null;
      },
    };

    void (async () => {
      try {
        const response = await fetch(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/run`), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
          },
          body: JSON.stringify(request),
        });
        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status} ${response.statusText}`.trim());
        }
        reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (!cancelled) {
          const { value, done } = await reader.read();
          if (done) {
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          let boundary = buffer.indexOf('\n\n');
          while (boundary >= 0) {
            const chunk = buffer.slice(0, boundary).trim();
            buffer = buffer.slice(boundary + 2);
            const parsed = this.parseSseChunk(chunk);
            if (parsed && client.onmessage) {
              client.onmessage(createMessageEvent(JSON.stringify(parsed)));
            }
            boundary = buffer.indexOf('\n\n');
          }
        }
      } catch (error) {
        if (!cancelled && client.onerror) {
          client.onerror(error instanceof Event ? error : new Event('error'));
        }
      }
    })();

    return client;
  }

  private async fetchGraphSnapshot(baseUrl: string, swarmName: string, graphKind: 'agent' | 'execution' = 'execution'): Promise<GraphSnapshot> {
    const response = await firstValueFrom(
      this.http.get<{ name: string; nodes: Record<string, RuntimeGraphNode>; edges: RuntimeGraphEdge[] }>(
        joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/graph`)
      )
    );
    return this.normalizeGraphSnapshot(swarmName, response.name, response.nodes ?? {}, response.edges ?? [], graphKind);
  }

  private normalizeGraphSnapshot(
    swarmName: string,
    graphName: string,
    nodes: Record<string, RuntimeGraphNode>,
    edges: RuntimeGraphEdge[],
    graphKind: 'agent' | 'execution' = 'execution'
  ): GraphSnapshot {
    const nodeEntries = Object.entries(nodes);
    const nodeIds = new Map<string, number>();
    nodeEntries.forEach(([key, _node], index) => nodeIds.set(key, index + 1));
    const normalizedNodes = nodeEntries.map(([key, node], index) => {
      const id = index + 1;
      const nodeType = String(node.node_type ?? node.type ?? node.class ?? 'node');
      const name = node.node_name ?? node.name ?? node.id ?? key;
      return {
        node_id: id,
        node_name: name,
        node_type: nodeType,
        next_node_ids: edges
          .filter((edge) => edge.source === key)
          .map((edge) => nodeIds.get(edge.target ?? '') ?? 0)
          .filter((nextId) => nextId > 0),
        metadata: {
          original_id: key,
          class: node.class ?? null,
          agent_id: node.agent_id ?? null,
          tool_name: node.tool_name ?? null,
          raw: normalizeJsonValue(node.metadata ?? node.input_mapping ?? null) as GraphSnapshot['nodes'][number]['metadata'],
        },
        agent_id: node.agent_id,
        tool_name: node.tool_name,
        input_mapping: normalizeJsonValue(node.input_mapping ?? null) as GraphSnapshot['nodes'][number]['input_mapping'],
      };
    });

    return {
      graph_name: graphName || swarmName,
      graph_kind: graphKind,
      entry_node_id: normalizedNodes[0]?.node_id ?? null,
      exit_node_id: normalizedNodes[normalizedNodes.length - 1]?.node_id ?? null,
      node_count: normalizedNodes.length,
      edge_count: edges.length,
      nodes: normalizedNodes,
      edges: edges.map((edge) => ({
        from_node_id: nodeIds.get(edge.source ?? '') ?? 0,
        to_node_id: nodeIds.get(edge.target ?? '') ?? 0,
        label: edge.label ?? null,
        condition: null,
        priority: 0,
      })),
      revision: normalizedNodes.length + edges.length,
      hash: `${graphName || swarmName}:${normalizedNodes.length}:${edges.length}`,
      updated_at: new Date().toISOString(),
      last_change: null,
    };
  }

  private async collectRunEvents(baseUrl: string, swarmName: string, request: RunSwarmRequest): Promise<RunStreamEvent[]> {
    return await new Promise<RunStreamEvent[]>((resolve, reject) => {
      const events: RunStreamEvent[] = [];
      const stream = this.runSwarmStream(swarmName, request, baseUrl);
      stream.onmessage = (event: MessageEvent<string>) => {
        try {
          const payload = JSON.parse(event.data) as RunStreamEvent;
          events.push(payload);
          if (payload.event === 'done') {
            stream.close();
            resolve(events);
          }
        } catch (error) {
          stream.close();
          reject(error);
        }
      };
      stream.onerror = (error: Event) => {
        stream.close();
        reject(error);
      };
    });
  }

  private parseSseChunk(chunk: string): RunStreamEvent | null {
    let event: RunStreamEvent['event'] | null = null;
    let data = '';
    for (const line of chunk.split(/\r?\n/)) {
      if (line.startsWith('event:')) {
        event = line.slice(6).trim() as RunStreamEvent['event'];
      } else if (line.startsWith('data:')) {
        data += line.slice(5).trim();
      }
    }
    if (!event) {
      return null;
    }
    try {
      return { event, data: JSON.parse(data) as RunStreamEvent['data'] };
    } catch {
      return { event, data };
    }
  }

  private buildRunSnapshot(
    swarmName: string,
    input: unknown,
    output: unknown,
    trace: unknown = null,
    rounds = 1
  ): RunSnapshot {
    const now = new Date().toISOString();
    return {
      success: true,
      run_id: `${swarmName}-${Date.now()}`,
      swarm: swarmName,
      status: 'completed',
      created_at: now,
      started_at: now,
      finished_at: now,
      rounds,
      current_node_id: null,
      current_node_name: null,
      current_node_type: null,
      state: input as RunSnapshot['state'],
      final_state: output as RunSnapshot['final_state'],
      error: null,
      event_count: Array.isArray(trace) ? trace.length : 2,
      events_url: '',
      status_url: '',
    };
  }

  private emptyGraphSnapshot(swarmName: string): { success: boolean; swarm: string; graph: GraphSnapshot } {
    return {
      success: true,
      swarm: swarmName,
      graph: {
        graph_name: swarmName,
        graph_kind: 'execution',
        entry_node_id: null,
        exit_node_id: null,
        node_count: 0,
        edge_count: 0,
        nodes: [],
        edges: [],
        revision: 0,
        hash: '',
        updated_at: new Date().toISOString(),
        last_change: null,
      },
    };
  }

  private buildSummaryShell(name: string): SwarmDetailResponse['swarm'] {
    return {
      swarm_name: name,
      package_path: `agents/${name}`,
      manifest_path: `agents/${name}/swarm.toml`,
      graph_file: `agents/${name}/graph.py`,
      agent_count: 0,
      skill_count: 0,
      tool_count: 0,
      api_count: 0,
      graph_attached: false,
      graph_valid: false,
      graph_errors: [],
      graph_warnings: [],
      agent_files: [],
      graph: null,
    };
  }

  private async enrichSwarmSummary(
    baseUrl: string,
    name: string,
    agentCount: number,
    toolCount: number
  ): Promise<SwarmSummary> {
    const graph = await this.getGraph(baseUrl, name).catch(() => this.emptyGraphSnapshot(name));
    return {
      ...this.buildSummaryShell(name),
      agent_count: agentCount,
      tool_count: toolCount,
      graph_attached: graph.graph.node_count > 0,
      graph_valid: graph.graph.node_count > 0,
      graph: graph.graph,
      agent_files: this.agentFilesFromGraph(graph.graph),
      graph_errors: [],
      graph_warnings: [],
    };
  }

  private agentFilesFromGraph(graph: GraphSnapshot): string[] {
    return graph.nodes
      .filter((node) => node.node_type === 'agent' || node.node_type === 'AgentNode')
      .map((node) => node.agent_id || node.node_name || String(node.node_id));
  }
}
