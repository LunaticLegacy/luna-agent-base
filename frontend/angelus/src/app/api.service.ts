import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import type {
  AgentRoundRequest,
  AgentRoundResponse,
  ApiIndexResponse,
  GraphSnapshot,
  HealthResponse,
  ReadyResponse,
  RunSnapshot,
  RunStartResponse,
  RunSwarmRequest,
  RunSwarmResponse,
  SwarmDetailResponse,
  SwarmListResponse,
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
