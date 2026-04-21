import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from './api.service';
import { ApiIndexResponse, HealthResponse, ReadyResponse, SwarmDetails, SwarmSummary } from './api.types';

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.sass'
})
export class App {
  private readonly api = inject(ApiService);

  protected readonly title = signal('Angelus Swarm Console');
  protected readonly apiBaseUrl = signal('/api');
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly apiIndex = signal<ApiIndexResponse | null>(null);
  protected readonly health = signal<HealthResponse | null>(null);
  protected readonly ready = signal<ReadyResponse | null>(null);
  protected readonly swarms = signal<SwarmSummary[]>([]);
  protected readonly selectedSwarmName = signal<string | null>(null);
  protected readonly selectedSwarm = signal<SwarmDetails | null>(null);
  protected readonly selectedAgentId = signal<string | null>(null);
  protected readonly swarmRunOutput = signal<Record<string, unknown> | null>(null);
  protected readonly agentRunOutput = signal<Record<string, unknown> | null>(null);

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

  protected readonly swarmInput = signal(
    '{\n  "text": "Draft a concise swarm summary for the selected workflow."\n}',
  );
  protected readonly swarmRounds = signal(0);

  protected readonly agentMessage = signal('Please review the latest task state and respond.');
  protected readonly agentRounds = signal(0);
  protected readonly agentAdditionalPrompt = signal('');

  constructor() {
    void this.loadOverview();
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
      }
    } catch (error) {
      this.error.set(this.formatError(error));
    } finally {
      this.loading.set(false);
    }
  }

  async selectSwarm(swarmName: string) {
    this.selectedSwarmName.set(swarmName);
    await this.reloadSelectedSwarm();
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

  async runSwarm() {
    const name = this.selectedSwarmName();
    if (!name) {
      this.error.set('Select a swarm before running it.');
      return;
    }

    this.loading.set(true);
    this.error.set(null);
    try {
      const parsedInput = this.parseJson(this.swarmInput());
      const response = await this.api.runSwarm(this.apiBaseUrl(), name, {
        input: parsedInput,
        rounds: this.swarmRounds(),
      });
      this.swarmRunOutput.set(response as unknown as Record<string, unknown>);
    } catch (error) {
      this.error.set(this.formatError(error));
    } finally {
      this.loading.set(false);
    }
  }

  async runSelectedAgent() {
    const swarm = this.selectedSwarm();
    if (!swarm) {
      this.error.set('Select a swarm before running an agent.');
      return;
    }

    const agentId = this.selectedAgentId();
    if (!agentId) {
      this.error.set('The selected swarm has no agents.');
      return;
    }

    this.loading.set(true);
    this.error.set(null);
    try {
      const response = await this.api.runAgentRound(this.apiBaseUrl(), swarm.swarm_name, agentId, {
        message: this.agentMessage().trim(),
        rounds: this.agentRounds(),
        additional_prompt: this.agentAdditionalPrompt().trim() || undefined,
      });
      this.agentRunOutput.set(response as unknown as Record<string, unknown>);
    } catch (error) {
      this.error.set(this.formatError(error));
    } finally {
      this.loading.set(false);
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

  private parseJson(value: string) {
    const trimmed = value.trim();
    if (!trimmed) {
      return {};
    }
    return JSON.parse(trimmed);
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
}
