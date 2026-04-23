import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';
import type {
  AgentListResponse,
  AgentRoundRequest,
  AgentRoundResponse,
  ApiIndexResponse,
  GraphSnapshot,
  HealthResponse,
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
  RunSwarmRequest,
  RunSwarmResponse,
  SettingsResponse,
  SwarmDetailResponse,
  SwarmListResponse,
  SwarmStatsResponse,
  ToolListResponse,
  UpdateSettingsRequest,
  ThoughtGraphResponse,
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

function joinUrlWithQuery(
  baseUrl: string,
  path: string,
  query: Record<string, string | number | boolean | undefined | null> = {}
): string {
  const url = joinUrl(baseUrl, path);
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') {
      continue;
    }
    params.set(key, String(value));
  }
  const queryString = params.toString();
  return queryString ? `${url}${url.includes('?') ? '&' : '?'}${queryString}` : url;
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
    return firstValueFrom(this.http.get<HealthResponse>(joinUrl(baseUrl, '/health')));
  }

  ready(baseUrl = '/api'): Promise<ReadyResponse> {
    return firstValueFrom(this.http.get<ReadyResponse>(joinUrl(baseUrl, '/ready')));
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
        joinUrl(baseUrl, '/swarms/load'),
        request
      )
    );
  }

  getSwarm(baseUrl: string, swarmName: string): Promise<SwarmDetailResponse> {
    return firstValueFrom(
      this.http.get<SwarmDetailResponse>(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}`))
    );
  }

  listAgents(
    baseUrl: string,
    swarmName: string,
    query: Record<string, string | number | boolean | undefined | null> = {}
  ): Promise<AgentListResponse> {
    return firstValueFrom(
      this.http.get<AgentListResponse>(
        joinUrlWithQuery(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/agents`, query)
      )
    );
  }

  listTasks(
    baseUrl: string,
    query: Record<string, string | number | boolean | undefined | null> = {}
  ): Promise<TaskListResponse> {
    return firstValueFrom(this.http.get<TaskListResponse>(joinUrlWithQuery(baseUrl, '/tasks', query)));
  }

  listTools(
    baseUrl: string,
    query: Record<string, string | number | boolean | undefined | null> = {}
  ): Promise<ToolListResponse> {
    return firstValueFrom(this.http.get<ToolListResponse>(joinUrlWithQuery(baseUrl, '/tools', query)));
  }

  getSwarmStats(baseUrl: string, swarmName: string): Promise<SwarmStatsResponse> {
    return firstValueFrom(
      this.http.get<SwarmStatsResponse>(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/stats`))
    );
  }

  listLogs(
    baseUrl: string,
    query: Record<string, string | number | boolean | undefined | null> = {}
  ): Promise<LogListResponse> {
    return firstValueFrom(this.http.get<LogListResponse>(joinUrlWithQuery(baseUrl, '/logs', query)));
  }

  getMetrics(
    baseUrl: string,
    query: Record<string, string | number | boolean | undefined | null> = {}
  ): Promise<MetricsResponse> {
    return firstValueFrom(this.http.get<MetricsResponse>(joinUrlWithQuery(baseUrl, '/metrics', query)));
  }

  listKnowledge(
    baseUrl: string,
    query: Record<string, string | number | boolean | undefined | null> = {}
  ): Promise<KnowledgeListResponse> {
    return firstValueFrom(this.http.get<KnowledgeListResponse>(joinUrlWithQuery(baseUrl, '/knowledge', query)));
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
    return firstValueFrom(this.http.get<MemoryListResponse>(joinUrlWithQuery(baseUrl, '/memory', query)));
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
        joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/graph`)
      )
    );
  }

  getThoughtGraph(baseUrl: string, swarmName: string): Promise<ThoughtGraphResponse> {
    return firstValueFrom(
      this.http.get<ThoughtGraphResponse>(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/thought-graph`))
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
    const query = force ? { force: true } : {};
    return firstValueFrom(
      this.http.delete<{ success: boolean; action: string; swarm: { swarm_name: string; package_path: string } }>(
        joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}`),
        { params: query as Record<string, string | number | boolean> }
      )
    );
  }

  runSwarm(baseUrl: string, swarmName: string, request: RunSwarmRequest): Promise<RunSwarmResponse> {
    return firstValueFrom(
      this.http.post<RunSwarmResponse>(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/run`), request)
    );
  }

  startSwarm(baseUrl: string, swarmName: string, request: RunSwarmRequest): Promise<RunSwarmResponse> {
    const encoded = encodeURIComponent(swarmName);
    const preferred = joinUrl(baseUrl, `/swarms/${encoded}/start`);
    const fallback = joinUrl(baseUrl, `/swarms/${encoded}/run`);
    return firstValueFrom(this.http.post<RunSwarmResponse>(preferred, request)).catch((error: unknown) => {
      if (error instanceof HttpErrorResponse && error.status === 405) {
        return firstValueFrom(this.http.post<RunSwarmResponse>(fallback, request));
      }
      throw error;
    });
  }

  startRun(baseUrl: string, swarmName: string, request: RunSwarmRequest): Promise<RunStartResponse> {
    return firstValueFrom(
      this.http.post<RunStartResponse>(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/runs`), request)
    );
  }

  startSwarmBackground(baseUrl: string, swarmName: string, request: RunSwarmRequest): Promise<RunStartResponse> {
    return firstValueFrom(
      this.http.post<RunStartResponse>(
        joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/start/background`),
        request
      )
    );
  }

  getRun(baseUrl: string, runId: string): Promise<{ success: boolean; run: RunSnapshot }> {
    return firstValueFrom(
      this.http.get<{ success: boolean; run: RunSnapshot }>(
        joinUrl(baseUrl, `/swarms/runs/${encodeURIComponent(runId)}`)
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
