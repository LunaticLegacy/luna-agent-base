import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import type {
  AgentListResponse,
  AgentRoundRequest,
  AgentRoundResponse,
  ApiIndexResponse,
  GraphSnapshot,
  GraphDiffResponse,
  GraphStateResponse,
  HealthResponse,
  KnowledgeCatalogItem,
  KnowledgeListResponse,
  LogListResponse,
  MemoryListResponse,
  MemoryCatalogItem,
  MetricsResponse,
  TaskListResponse,
  TaskGraphResponse,
  ReadyResponse,
  RunSnapshot,
  RunStartResponse,
  RunSwarmRequest,
  RunSwarmResponse,
  SettingsResponse,
  SwarmApisResponse,
  SwarmDetailResponse,
  SwarmListResponse,
  SwarmStatsResponse,
  ToolListResponse,
  UpdateSettingsRequest,
  ThoughtGraphResponse,
  ExecutionTraceResponse,
} from './api.types';

export function joinUrl(baseUrl: string, path: string): string {
  const base = baseUrl.trim() || '/api';
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

@Injectable({
  providedIn: 'root',
})
export class ApiService {
  constructor(private readonly http: HttpClient) {}

  index(baseUrl = '/api'): Promise<ApiIndexResponse> {
    return firstValueFrom(this.http.get<ApiIndexResponse>(joinUrl(baseUrl, '')));
  }

  health(baseUrl = '/api'): Promise<HealthResponse> {
    return firstValueFrom(this.http.get<HealthResponse>(joinUrl(baseUrl, '/runtime/health')));
  }

  ready(baseUrl = '/api'): Promise<ReadyResponse> {
    return firstValueFrom(this.http.get<ReadyResponse>(joinUrl(baseUrl, '/runtime/ready')));
  }

  getSettings(baseUrl = '/api'): Promise<SettingsResponse> {
    return firstValueFrom(this.http.get<SettingsResponse>(joinUrl(baseUrl, '/settings')));
  }

  updateSettings(baseUrl = '/api', body: UpdateSettingsRequest): Promise<SettingsResponse> {
    return firstValueFrom(this.http.put<SettingsResponse>(joinUrl(baseUrl, '/settings'), body));
  }

  listSwarms(baseUrl = '/api'): Promise<SwarmListResponse> {
    return firstValueFrom(this.http.get<SwarmListResponse>(joinUrl(baseUrl, '/swarms')));
  }

  loadSwarm(
    baseUrl: string,
    request: { package_path?: string; source?: string; swarm_name?: string; replace?: boolean }
  ): Promise<{ success: boolean; action: string; swarm: SwarmDetailResponse['swarm'] }> {
    return firstValueFrom(
      this.http.post<{ success: boolean; action: string; swarm: SwarmDetailResponse['swarm'] }>(
        joinUrl(baseUrl, '/swarms'),
        request
      )
    );
  }

  getSwarm(baseUrl: string, swarmName: string): Promise<SwarmDetailResponse> {
    return firstValueFrom(
      this.http.get<SwarmDetailResponse>(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}`))
    );
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

  getTaskGraph(
    baseUrl: string,
    swarmName: string
  ): Promise<TaskGraphResponse> {
    return firstValueFrom(
      this.http.get<TaskGraphResponse>(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/task-graph`))
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

  getGraph(baseUrl: string, swarmName: string): Promise<{ success: boolean; swarm: string; graph: GraphSnapshot }> {
    return firstValueFrom(
      this.http.get<{ success: boolean; swarm: string; graph: GraphSnapshot }>(
        joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/agent-graph`)
      )
    );
  }

  getGraphState(baseUrl: string, swarmName: string, sinceRevision?: number): Promise<GraphStateResponse> {
    return firstValueFrom(
      this.http.post<GraphStateResponse>(
        joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/graph/state`),
        { since_revision: sinceRevision }
      )
    );
  }

  getGraphDiff(baseUrl: string, swarmName: string, sinceRevision: number): Promise<GraphDiffResponse> {
    return firstValueFrom(
      this.http.post<GraphDiffResponse>(
        joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/graph/diff`),
        { since_revision: sinceRevision }
      )
    );
  }

  getThoughtGraph(baseUrl: string, swarmName: string): Promise<ThoughtGraphResponse> {
    return firstValueFrom(
      this.http.get<ThoughtGraphResponse>(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/thought-graph`))
    );
  }

  getExecutionTrace(
    baseUrl: string,
    swarmName: string,
    runId?: string
  ): Promise<ExecutionTraceResponse> {
    const path = runId
      ? `/swarms/${encodeURIComponent(swarmName)}/execution-traces/${encodeURIComponent(runId)}`
      : `/swarms/${encodeURIComponent(swarmName)}/execution-traces/latest`;
    return firstValueFrom(
      this.http.get<ExecutionTraceResponse>(joinUrl(baseUrl, path))
    );
  }

  reloadSwarm(
    baseUrl: string,
    swarmName: string,
    request: { force?: boolean; package_path?: string; source?: string } = {}
  ): Promise<{ success: boolean; action: string; swarm: SwarmDetailResponse['swarm'] }> {
    return firstValueFrom(
      this.http.post<{ success: boolean; action: string; swarm: SwarmDetailResponse['swarm'] }>(
        joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/reload`),
        request
      )
    );
  }

  unloadSwarm(
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

  runSwarm(baseUrl: string, swarmName: string, request: RunSwarmRequest): Promise<RunSwarmResponse> {
    return firstValueFrom(
      this.http.post<RunSwarmResponse>(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/runs/execute`), request)
    );
  }

  startRun(baseUrl: string, swarmName: string, request: RunSwarmRequest): Promise<RunStartResponse> {
    return firstValueFrom(
      this.http.post<RunStartResponse>(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/runs`), request)
    );
  }

  getRun(baseUrl: string, runId: string): Promise<{ success: boolean; run: RunSnapshot }> {
    return firstValueFrom(
      this.http.get<{ success: boolean; run: RunSnapshot }>(
        joinUrl(baseUrl, `/runs/${encodeURIComponent(runId)}`)
      )
    );
  }

  runAgentRound(
    baseUrl: string,
    swarmName: string,
    agentId: string,
    request: AgentRoundRequest
  ): Promise<AgentRoundResponse> {
    return firstValueFrom(
      this.http.post<AgentRoundResponse>(
        joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/agents/${encodeURIComponent(agentId)}/round`),
        request
      )
    );
  }
}
