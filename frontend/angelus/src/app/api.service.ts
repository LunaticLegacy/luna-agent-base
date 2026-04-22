import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import type {
  AgentListResponse,
  AgentRoundRequest,
  AgentRoundResponse,
  ApiIndexResponse,
  GraphSnapshot,
  HealthResponse,
  TaskListResponse,
  ReadyResponse,
  RunSnapshot,
  RunStartResponse,
  RunSwarmRequest,
  RunSwarmResponse,
  SwarmDetailResponse,
  SwarmListResponse,
  ToolListResponse,
} from './api.types';

function joinUrl(baseUrl: string, path: string): string {
  const base = baseUrl.trim() || '/api';
  const normalizedBase = base.endsWith('/') ? base.slice(0, -1) : base;
  if (!path) {
    return normalizedBase;
  }
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;

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

  listSwarms(baseUrl = '/api'): Promise<SwarmListResponse> {
    return firstValueFrom(this.http.get<SwarmListResponse>(joinUrl(baseUrl, '/swarms')));
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

  getGraph(baseUrl: string, swarmName: string): Promise<{ success: boolean; swarm: string; graph: GraphSnapshot }> {
    return firstValueFrom(
      this.http.get<{ success: boolean; swarm: string; graph: GraphSnapshot }>(
        joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/graph`)
      )
    );
  }

  runSwarm(baseUrl: string, swarmName: string, request: RunSwarmRequest): Promise<RunSwarmResponse> {
    return firstValueFrom(
      this.http.post<RunSwarmResponse>(joinUrl(baseUrl, `/swarms/${encodeURIComponent(swarmName)}/run`), request)
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
