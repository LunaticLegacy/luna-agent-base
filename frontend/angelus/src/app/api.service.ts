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
  RunSwarmResponse,
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

  runSwarm(baseUrl: string, swarmName: string, request: RunSwarmRequest) {
    return firstValueFrom(
      this.http.post<RunSwarmResponse>(
        `${baseUrl}/swarms/${encodeURIComponent(swarmName)}/run`,
        request,
      ),
    );
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
