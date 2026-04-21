import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import {
  ApiIndexResponse,
  AgentRoundRequest,
  AgentRoundResponse,
  HealthResponse,
  ReadyResponse,
  RunSwarmRequest,
  RunSnapshot,
  StartSwarmRunResponse,
  SwarmGraphResponse,
  SwarmDetailResponse,
  SwarmListResponse,
} from './api.types';

@Injectable({
  providedIn: 'root',
})
export class ApiService {
  private readonly http = inject(HttpClient);

  index(baseUrl = '/api') {
    return firstValueFrom(this.http.get<ApiIndexResponse>(baseUrl));
  }

  health(baseUrl = '/api') {
    return firstValueFrom(this.http.get<HealthResponse>(`${baseUrl}/health`));
  }

  ready(baseUrl = '/api') {
    return firstValueFrom(this.http.get<ReadyResponse>(`${baseUrl}/ready`));
  }

  listSwarms(baseUrl = '/api') {
    return firstValueFrom(this.http.get<SwarmListResponse>(`${baseUrl}/swarms`));
  }

  getSwarm(baseUrl: string, swarmName: string) {
    return firstValueFrom(
      this.http.get<SwarmDetailResponse>(`${baseUrl}/swarms/${encodeURIComponent(swarmName)}`),
    );
  }

  getSwarmGraph(baseUrl: string, swarmName: string) {
    return firstValueFrom(
      this.http.get<SwarmGraphResponse>(`${baseUrl}/swarms/${encodeURIComponent(swarmName)}/graph`),
    );
  }

  startSwarmRun(baseUrl: string, swarmName: string, request: RunSwarmRequest) {
    return firstValueFrom(
      this.http.post<StartSwarmRunResponse>(
        `${baseUrl}/swarms/${encodeURIComponent(swarmName)}/runs`,
        request,
      ),
    );
  }

  getRun(baseUrl: string, runId: string) {
    return firstValueFrom(this.http.get<{ success: boolean; run: RunSnapshot }>(`${baseUrl}/runs/${encodeURIComponent(runId)}`));
  }

  streamRunEvents(baseUrl: string, runId: string) {
    return new EventSource(`${baseUrl}/runs/${encodeURIComponent(runId)}/events`);
  }

  runAgentRound(baseUrl: string, swarmName: string, agentId: string, request: AgentRoundRequest) {
    return firstValueFrom(
      this.http.post<AgentRoundResponse>(
        `${baseUrl}/swarms/${encodeURIComponent(swarmName)}/agents/${encodeURIComponent(agentId)}/round`,
        request,
      ),
    );
  }
}
