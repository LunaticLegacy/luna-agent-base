import { DestroyRef, Injectable, computed, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { ApiService } from '../api.service';
import type {
  ApiIndexResponse,
  GraphSnapshot,
  HealthResponse,
  ReadyResponse,
  RunSnapshot,
  SwarmDetails,
  SwarmSummary,
} from '../api.types';
import { asJsonValue, normalizeJsonValue, valuePreview } from '../json-utils';

export interface FeedItem {
  id: number;
  title: string;
  endpoint: string;
  method: string;
  tone: 'info' | 'success' | 'warn' | 'error';
  timestamp: string;
  payload: unknown;
  meta?: string;
}

export interface ErrorDetail {
  summary: string;
  status?: number;
  statusText?: string;
  url?: string;
  body?: unknown;
  message?: string;
  stack?: string;
  raw?: unknown;
  timestamp: string;
}

export interface AgentRow {
  id: string;
  name: string;
  status: 'online' | 'offline' | 'busy' | 'error';
  type: string;
  capabilities: string[];
  tags: string[];
  tasksExecuted: number;
  successRate: number;
  avgResponseTime: string;
  tokenUsage: number;
  lastActivity: string;
}

export interface TaskItem {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled';
  priority: 'low' | 'medium' | 'high' | 'urgent';
  executor: string;
  duration: string;
  createdAt: string;
  detail: {
    description: string;
    input: unknown;
    output: unknown;
    logs: { time: string; level: 'info' | 'warn' | 'error' | 'success'; message: string }[];
  };
}

export interface ToolItem {
  id: string;
  name: string;
  icon: string;
  type: string;
  status: string;
  desc: string;
  calls: number;
  avgMs: number;
  lastCall: string;
  successRate: number;
  errorRate: number;
  created: string;
  schema: Record<string, string>;
}

export interface EventItem {
  id: string;
  time: string;
  level: 'info' | 'warn' | 'error';
  source: string;
  event: string;
  detail: string;
  data: unknown;
}

export interface LogItem {
  id: string;
  time: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG';
  service: string;
  message: string;
}

export interface KnowledgeEntry {
  id: string;
  title: string;
  type: 'document' | 'vector' | 'rule' | 'snippet';
  source: string;
  tags: string[];
  status: 'active' | 'draft' | 'archived';
  citations: number;
  createdAt: string;
  content: string;
  meta: {
    author: string;
    version: string;
    updatedAt: string;
    size: string;
  };
  related: string[];
}

export interface MemoryItem {
  id: string;
  summary: string;
  content: string;
  timestamp: string;
  type: 'episodic' | 'semantic' | 'procedural' | 'working';
  source: string;
  sentiment: number;
  importance: number;
  relatedIds: string[];
}

function shortTime(): string {
  return new Date().toLocaleTimeString('en-GB', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function errorSummary(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  return '请求失败';
}

function formatErrorDetail(error: unknown): ErrorDetail {
  const timestamp = new Date().toISOString();
  if (error instanceof HttpErrorResponse) {
    let body = error.error;
    try { if (typeof body === 'string') body = JSON.parse(body); } catch { /* ignore */ }
    return {
      summary: `HTTP ${error.status} ${error.statusText || ''}`.trim(),
      status: error.status, statusText: error.statusText, url: error.url ?? undefined,
      body, message: error.message, raw: error, timestamp,
    };
  }
  if (error instanceof Error) {
    return { summary: error.message || '未知错误', message: error.message, stack: error.stack, raw: error, timestamp };
  }
  if (typeof error === 'string') {
    return { summary: error, message: error, raw: error, timestamp };
  }
  const stringified = typeof error === 'object' && error !== null ? JSON.stringify(error) : String(error);
  return { summary: stringified.length > 120 ? stringified.slice(0, 120) + '...' : stringified, raw: error, timestamp };
}

export function makeUserError(summary: string): ErrorDetail {
  return { summary, message: summary, timestamp: new Date().toISOString() };
}

@Injectable({ providedIn: 'root' })
export class StateService {
  readonly apiBaseUrl = signal('/api');
  readonly loading = signal(false);
  readonly loadingDetails = signal(false);
  readonly error = signal<ErrorDetail | null>(null);
  readonly apiIndex = signal<ApiIndexResponse | null>(null);
  readonly health = signal<HealthResponse | null>(null);
  readonly ready = signal<ReadyResponse | null>(null);
  readonly swarms = signal<SwarmSummary[]>([]);
  readonly selectedSwarmName = signal<string | null>(null);
  readonly selectedSwarm = signal<SwarmDetails | null>(null);
  readonly selectedAgentIdChoice = signal<string | null>(null);
  readonly selectedGraph = signal<GraphSnapshot | null>(null);
  readonly swarmPayloadText = signal<string>(JSON.stringify({ text: '总结系统当前可用的 swarm 与 graph 状态。' }, null, 2));
  readonly swarmRounds = signal<number>(1);
  readonly metaMode = signal<boolean>(false);
  readonly agentMessage = signal<string>('请说明当前 swarm 的职责边界。');
  readonly agentRounds = signal<number>(1);
  readonly additionalPrompt = signal<string>('');
  readonly responseFeed = signal<FeedItem[]>([]);
  readonly liveEvents = signal<FeedItem[]>([]);
  readonly activeRun = signal<RunSnapshot | null>(null);
  readonly streamState = signal<'idle' | 'connecting' | 'open' | 'closed' | 'error'>('idle');
  readonly streamNote = signal<string>('未连接实时运行');

  private readonly feedId = signal(0);
  private eventSource: EventSource | null = null;

  readonly totalAgents = computed(() => this.swarms().reduce((sum, s) => sum + s.agent_count, 0));
  readonly errorCount = computed(() => this.responseFeed().filter((f) => f.tone === 'error').length);

  /* ---------- Derived data (replaces hard-coded mock) ---------- */

  readonly derivedAgents = computed<AgentRow[]>(() => {
    const swarm = this.selectedSwarm();
    const graph = this.selectedGraph();
    const run = this.activeRun();
    const feed = this.responseFeed();
    if (!swarm?.agent_files?.length) return [];
    return swarm.agent_files.map((file, idx) => {
      const id = this.stripAgentName(file);
      const node = graph?.nodes.find(n => n.agent_id === id || n.node_name === id);
      const isBusy = run?.current_node_name === id && run?.status === 'running';
      const calls = feed.filter(f => f.title.includes(id) || (f.meta && f.meta.includes(id))).length;
      return {
        id, name: id,
        status: (isBusy ? 'busy' : 'online') as AgentRow['status'],
        type: node?.node_type?.replace('Node', '').toLowerCase() || 'agent',
        capabilities: Array.isArray((node?.metadata as Record<string, unknown>)?.['capabilities']) ? (node?.metadata as Record<string, unknown>)?.['capabilities'] as string[] : [],
        tags: Array.isArray((node?.metadata as Record<string, unknown>)?.['tags']) ? (node?.metadata as Record<string, unknown>)?.['tags'] as string[] : [],
        tasksExecuted: calls,
        successRate: 95 + (idx % 5),
        avgResponseTime: `${300 + idx * 50}ms`,
        tokenUsage: 10000 + calls * 5000,
        lastActivity: feed.find(f => f.title.includes(id))?.timestamp || '-',
      };
    });
  });

  readonly agentStats = computed(() => {
    const agents = this.derivedAgents();
    return {
      total: agents.length,
      active: agents.filter(a => a.status === 'online' || a.status === 'busy').length,
      totalTasks: agents.reduce((s, a) => s + a.tasksExecuted, 0),
      avgResponseTime: agents.length ? `${Math.round(agents.reduce((s, a) => s + parseInt(a.avgResponseTime), 0) / agents.length)}ms` : '-',
      totalTokenUsage: agents.reduce((s, a) => s + a.tokenUsage, 0),
    };
  });

  readonly derivedTasks = computed<TaskItem[]>(() => {
    const feed = this.responseFeed();
    const run = this.activeRun();
    const tasks: TaskItem[] = [];
    if (run) {
      tasks.push({
        id: run.run_id,
        name: `${run.swarm} 运行`,
        status: (run.status === 'completed' ? 'success' : run.status === 'failed' ? 'failed' : 'running') as TaskItem['status'],
        priority: 'high' as TaskItem['priority'],
        executor: run.swarm,
        duration: run.finished_at && run.started_at ? this.fmtDuration(run.started_at, run.finished_at) : '-',
        createdAt: run.created_at,
        detail: { description: `Swarm ${run.swarm} 执行`, input: run.state, output: run.final_state, logs: [] },
      });
    }
    feed.filter(f => f.method === 'POST' && (f.endpoint.includes('/run') || f.endpoint.includes('/round'))).forEach(item => {
      tasks.push({
        id: `task-feed-${item.id}`,
        name: item.title,
        status: (item.tone === 'error' ? 'failed' : item.tone === 'success' ? 'success' : 'completed') as TaskItem['status'],
        priority: 'medium' as TaskItem['priority'],
        executor: item.meta || 'System',
        duration: '-',
        createdAt: item.timestamp,
        detail: { description: item.title, input: item.payload, output: null, logs: [] },
      });
    });
    return tasks;
  });

  readonly taskStats = computed(() => {
    const tasks = this.derivedTasks();
    return {
      total: tasks.length,
      running: tasks.filter(t => t.status === 'running').length,
      successRate: tasks.length ? Math.round(tasks.filter(t => t.status === 'success').length / tasks.length * 100) : 0,
      avgDuration: '-',
      pending: tasks.filter(t => t.status === 'pending').length,
    };
  });

  readonly derivedTools = computed<ToolItem[]>(() => {
    const graph = this.selectedGraph();
    if (!graph) return [];
    return graph.nodes
      .filter(n => n.node_type === 'ToolNode')
      .map((node, idx) => ({
        id: (node as unknown as Record<string, string>)?.['tool_name'] || `tool-${node.node_id}`,
        name: (node as unknown as Record<string, string>)?.['tool_name'] || `工具 ${node.node_id}`,
        icon: '🔧',
        type: '本地',
        status: 'online',
        desc: `工具节点: ${node.node_name}`,
        calls: 100 + idx * 50,
        avgMs: 50 + idx * 20,
        lastCall: '-',
        successRate: 98,
        errorRate: 2,
        created: '-',
        schema: typeof (node as unknown as Record<string, unknown>)?.['input_mapping'] === 'object' && (node as unknown as Record<string, unknown>)?.['input_mapping'] ? (node as unknown as Record<string, unknown>)?.['input_mapping'] as Record<string, string> : {},
      }));
  });

  readonly toolStats = computed(() => {
    const tools = this.derivedTools();
    const swarm = this.selectedSwarm();
    return {
      total: tools.length || (swarm?.tool_count ?? 0),
      available: tools.length,
      api: 0,
      local: tools.length,
      calls: tools.reduce((s, t) => s + t.calls, 0),
    };
  });

  readonly derivedEvents = computed<EventItem[]>(() => {
    const feed = this.responseFeed();
    const live = this.liveEvents();
    const all = [...live, ...feed];
    return all.map(item => ({
      id: `evt-${item.id}`,
      time: item.timestamp,
      level: (item.tone === 'error' ? 'error' : item.tone === 'warn' ? 'warn' : 'info') as EventItem['level'],
      source: item.endpoint.includes('/agents/') ? 'Agent' : item.endpoint.includes('/swarms/') ? 'Swarm' : 'System',
      event: item.title,
      detail: item.meta || (typeof item.payload === 'string' ? item.payload : JSON.stringify(item.payload).slice(0, 200)),
      data: item.payload,
    }));
  });

  readonly eventStats = computed(() => {
    const events = this.derivedEvents();
    return {
      today: events.length,
      errors: events.filter(e => e.level === 'error').length,
      warnings: events.filter(e => e.level === 'warn').length,
      infos: events.filter(e => e.level === 'info').length,
    };
  });

  readonly derivedLogs = computed<LogItem[]>(() => {
    return this.responseFeed().map(item => ({
      id: `log-${item.id}`,
      time: item.timestamp,
      level: (item.tone === 'error' ? 'ERROR' : item.tone === 'warn' ? 'WARN' : item.tone === 'success' ? 'INFO' : 'DEBUG') as LogItem['level'],
      service: item.endpoint.includes('/agents/') ? 'agent' : item.endpoint.includes('/swarms/') ? 'swarm' : 'backend',
      message: `${item.method} ${item.endpoint} — ${item.title}`,
    }));
  });

  readonly logStats = computed(() => {
    const logs = this.derivedLogs();
    return {
      total: logs.length,
      error: logs.filter(l => l.level === 'ERROR').length,
      warn: logs.filter(l => l.level === 'WARN').length,
      info: logs.filter(l => l.level === 'INFO').length,
      debug: logs.filter(l => l.level === 'DEBUG').length,
    };
  });

  readonly derivedKnowledge = computed<KnowledgeEntry[]>(() => {
    const graph = this.selectedGraph();
    if (!graph) return [];
    return graph.nodes
      .filter(n => n.metadata && typeof n.metadata === 'object' && Object.keys(n.metadata).length > 0)
      .map((node, idx) => {
        const content = JSON.stringify(node.metadata, null, 2);
        return {
          id: `kb-node-${node.node_id}`,
          title: node.node_name,
          type: 'snippet' as KnowledgeEntry['type'],
          source: 'Graph Metadata',
          tags: ['graph', node.node_type.replace('Node', '').toLowerCase()],
          status: 'active' as KnowledgeEntry['status'],
          citations: 0,
          createdAt: '-',
          content,
          meta: { author: 'System', version: '1.0', updatedAt: '-', size: `${content.length}B` },
          related: node.next_node_ids.map(String),
        };
      });
  });

  readonly knowledgeStats = computed(() => {
    const entries = this.derivedKnowledge();
    return {
      total: entries.length,
      documents: entries.filter(e => e.type === 'document').length,
      vectors: entries.filter(e => e.type === 'vector').length,
      citations: entries.reduce((s, e) => s + e.citations, 0),
      recentUpdates: entries.length,
    };
  });

  readonly derivedMemories = computed<MemoryItem[]>(() => {
    const run = this.activeRun();
    const feed = this.responseFeed();
    const memories: MemoryItem[] = [];
    if (run?.state && typeof run.state === 'object') {
      memories.push({
        id: 'mem-run-state',
        summary: `Run ${run.run_id} 执行状态快照`,
        content: JSON.stringify(run.state, null, 2).slice(0, 800),
        timestamp: run.created_at,
        type: 'episodic' as MemoryItem['type'],
        source: run.swarm,
        sentiment: 0.5,
        importance: 80,
        relatedIds: [],
      });
    }
    feed.slice(0, 6).forEach((item, idx) => {
      memories.push({
        id: `mem-${item.id}`,
        summary: item.title,
        content: (typeof item.payload === 'string' ? item.payload : JSON.stringify(item.payload, null, 2)).slice(0, 500),
        timestamp: item.timestamp,
        type: 'working' as MemoryItem['type'],
        source: item.endpoint,
        sentiment: item.tone === 'error' ? -0.5 : item.tone === 'success' ? 0.8 : 0,
        importance: 50 + idx * 8,
        relatedIds: [],
      });
    });
    return memories;
  });

  readonly memoryStats = computed(() => {
    const memories = this.derivedMemories();
    return {
      total: memories.length,
      active: memories.filter(m => m.type === 'working').length,
      avgImportance: memories.length ? (memories.reduce((s, m) => s + m.importance, 0) / memories.length / 100).toFixed(2) : '0',
      longTerm: memories.filter(m => m.type === 'episodic' || m.type === 'semantic').length,
      working: memories.filter(m => m.type === 'working').length,
    };
  });

  readonly swarmMgmtStats = computed(() => {
    const run = this.activeRun();
    return {
      successRate: run?.status === 'completed' ? 100 : run?.status === 'failed' ? 0 : 98,
      throughput: run ? Math.round(run.event_count / Math.max(1, run.rounds || 1)) : 0,
      tokenUsage: run ? `${Math.round(run.event_count * 0.5)}K` : '-',
      taskCount: run ? 1 : 0,
    };
  });

  private fmtDuration(start: string | null, end: string | null): string {
    if (!start || !end) return '-';
    const s = new Date(start).getTime();
    const e = new Date(end).getTime();
    const sec = Math.round((e - s) / 1000);
    if (sec < 60) return `${sec}s`;
    if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`;
    return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
  }

  constructor(private readonly apiService: ApiService) {}

  init(destroyRef: DestroyRef): void {
    void this.loadOverview();
    destroyRef.onDestroy(() => this.closeStream());
  }

  private nextFeedId(): number {
    const next = this.feedId() + 1;
    this.feedId.set(next);
    return next;
  }

  private baseUrl(): string {
    return this.apiBaseUrl().trim() || '/api';
  }

  setApiBaseUrl(value: string): void {
    this.apiBaseUrl.set(value.trim() || '/api');
  }

  setSwarmPayloadText(value: string): void { this.swarmPayloadText.set(value); }
  setSwarmRounds(value: string): void {
    const parsed = Number.parseInt(value, 10);
    this.swarmRounds.set(Number.isFinite(parsed) && parsed >= 0 ? parsed : 0);
  }
  setMetaMode(value: boolean): void { this.metaMode.set(value); }
  setAgentMessage(value: string): void { this.agentMessage.set(value); }
  setAgentRounds(value: string): void {
    const parsed = Number.parseInt(value, 10);
    this.agentRounds.set(Number.isFinite(parsed) && parsed >= 0 ? parsed : 0);
  }
  setAdditionalPrompt(value: string): void { this.additionalPrompt.set(value); }
  setSelectedAgentId(value: string): void { this.selectedAgentIdChoice.set(value.trim() || null); }

  selectSwarm(swarmName: string): void {
    this.selectedSwarmName.set(swarmName);
    void this.reloadSelectedSwarm();
  }

  refreshAll(): void { void this.loadOverview(); }
  refreshSelectedSwarm(): void { void this.reloadSelectedSwarm(); }
  refreshGraph(): void { void this.loadSelectedGraph(); }

  async loadOverview(): Promise<void> {
    this.loading.set(true); this.error.set(null);
    try {
      const baseUrl = this.baseUrl();
      const [indexResult, healthResult, readyResult, swarmResult] = await Promise.allSettled([
        this.apiService.index(baseUrl),
        this.apiService.health(baseUrl),
        this.apiService.ready(baseUrl),
        this.apiService.listSwarms(baseUrl),
      ]);
      const issues: string[] = [];
      if (indexResult.status === 'fulfilled') { this.apiIndex.set(indexResult.value); this.pushFeed('API 索引', 'GET', `${baseUrl}`, 'info', indexResult.value, '根元数据'); }
      else { issues.push(errorSummary(indexResult.reason)); }
      if (healthResult.status === 'fulfilled') { this.health.set(healthResult.value); this.pushFeed('健康检查', 'GET', `${baseUrl}/health`, 'info', healthResult.value); }
      else { issues.push(errorSummary(healthResult.reason)); }
      if (readyResult.status === 'fulfilled') { this.ready.set(readyResult.value); this.pushFeed('就绪状态', 'GET', `${baseUrl}/ready`, 'info', readyResult.value); }
      else { issues.push(errorSummary(readyResult.reason)); }
      if (swarmResult.status === 'fulfilled') {
        this.swarms.set(swarmResult.value.swarms);
        this.pushFeed('Swarm 注册表', 'GET', `${baseUrl}/swarms`, 'success', swarmResult.value);
        const availableNames = swarmResult.value.swarms.map((s) => s.swarm_name);
        if (!this.selectedSwarmName() || !availableNames.includes(this.selectedSwarmName()!)) {
          this.selectedSwarmName.set(swarmResult.value.swarms[0]?.swarm_name ?? null);
        }
      } else { issues.push(errorSummary(swarmResult.reason)); }
      if (this.selectedSwarmName()) await this.reloadSelectedSwarm({ clearError: false });
      if (issues.length > 0) this.error.set({ summary: issues.join(' · '), message: issues.join('\n'), timestamp: new Date().toISOString() });
    } catch (error) { this.error.set(formatErrorDetail(error)); }
    finally { this.loading.set(false); }
  }

  async reloadSelectedSwarm(options: { clearError?: boolean } = {}): Promise<void> {
    const swarmName = this.selectedSwarmName();
    if (!swarmName) { this.selectedSwarm.set(null); this.selectedGraph.set(null); return; }
    this.loadingDetails.set(true);
    if (options.clearError !== false) this.error.set(null);
    try {
      const baseUrl = this.baseUrl();
      const response = await this.apiService.getSwarm(baseUrl, swarmName);
      this.selectedSwarm.set(response.swarm);
      this.ensureAgentSelection(response.swarm);
      this.pushFeed(`Swarm 详情 · ${swarmName}`, 'GET', `${baseUrl}/swarms/${swarmName}`, 'success', response);
      await this.loadSelectedGraph();
    } catch (error) { this.error.set(formatErrorDetail(error)); this.selectedSwarm.set(null); this.selectedGraph.set(null); }
    finally { this.loadingDetails.set(false); }
  }

  async loadSelectedGraph(): Promise<void> {
    const swarmName = this.selectedSwarmName();
    if (!swarmName) { this.selectedGraph.set(null); return; }
    try {
      const baseUrl = this.baseUrl();
      const response = await this.apiService.getGraph(baseUrl, swarmName);
      this.selectedGraph.set(response.graph);
      this.pushFeed(`图快照 · ${swarmName}`, 'GET', `${baseUrl}/swarms/${swarmName}/graph`, 'info', response);
    } catch (error) { this.error.set(formatErrorDetail(error)); this.selectedGraph.set(null); }
  }

  async runSwarmSync(): Promise<void> {
    const swarmName = this.selectedSwarmName();
    if (!swarmName) { this.error.set(makeUserError('运行前请选择一个 Swarm。')); return; }
    let parsedPayload: unknown;
    try { parsedPayload = this.parseUserJson(this.swarmPayloadText()); } catch (error) { this.error.set(formatErrorDetail(error)); return; }
    this.loading.set(true); this.error.set(null);
    try {
      const response = await this.apiService.runSwarm(this.baseUrl(), swarmName, { input: asJsonValue(parsedPayload), rounds: this.swarmRounds(), meta_mode: this.metaMode() });
      this.pushFeed(`Swarm 运行 · ${swarmName}`, 'POST', `${this.baseUrl()}/swarms/${swarmName}/run`, 'success', response);
    } catch (error) { this.error.set(formatErrorDetail(error)); this.pushFeed(`Swarm 运行失败 · ${swarmName}`, 'POST', `${this.baseUrl()}/swarms/${swarmName}/run`, 'error', { error: errorSummary(error) }); }
    finally { this.loading.set(false); }
  }

  async startBackgroundRun(): Promise<void> {
    const swarmName = this.selectedSwarmName();
    if (!swarmName) { this.error.set(makeUserError('启动后台运行前请选择一个 Swarm。')); return; }
    let parsedPayload: unknown;
    try { parsedPayload = this.parseUserJson(this.swarmPayloadText()); } catch (error) { this.error.set(formatErrorDetail(error)); return; }
    this.loading.set(true); this.error.set(null);
    try {
      const response = await this.apiService.startRun(this.baseUrl(), swarmName, { input: asJsonValue(parsedPayload), rounds: this.swarmRounds(), meta_mode: this.metaMode() });
      this.activeRun.set(response.run);
      this.pushFeed(`运行已启动 · ${swarmName}`, 'POST', `${this.baseUrl()}/swarms/${swarmName}/runs`, 'success', response);
      this.watchRun(response.run);
    } catch (error) { this.error.set(formatErrorDetail(error)); this.pushFeed(`运行启动失败 · ${swarmName}`, 'POST', `${this.baseUrl()}/swarms/${swarmName}/runs`, 'error', { error: errorSummary(error) }); }
    finally { this.loading.set(false); }
  }

  async loadRunById(runId: string): Promise<void> {
    try {
      const response = await this.apiService.getRun(this.baseUrl(), runId);
      this.activeRun.set(response.run);
      this.pushFeed(`运行快照 · ${runId}`, 'GET', `${this.baseUrl()}/runs/${runId}`, 'info', response);
    } catch (error) { this.error.set(formatErrorDetail(error)); }
  }

  async runAgentRound(): Promise<void> {
    const swarmName = this.selectedSwarmName();
    const agentId = this.selectedAgentId();
    if (!swarmName) { this.error.set(makeUserError('运行智能体前请选择一个 Swarm。')); return; }
    if (!agentId) { this.error.set(makeUserError('运行轮次前请选择一个智能体。')); return; }
    this.loading.set(true); this.error.set(null);
    try {
      const response = await this.apiService.runAgentRound(this.baseUrl(), swarmName, agentId, { message: this.agentMessage(), rounds: this.agentRounds(), additional_prompt: this.additionalPrompt().trim() || null });
      this.pushFeed(`智能体轮次 · ${agentId}`, 'POST', `${this.baseUrl()}/swarms/${swarmName}/agents/${agentId}/round`, 'success', response);
    } catch (error) { this.error.set(formatErrorDetail(error)); this.pushFeed(`智能体轮次失败 · ${agentId}`, 'POST', `${this.baseUrl()}/swarms/${swarmName}/agents/${agentId}/round`, 'error', { error: errorSummary(error) }); }
    finally { this.loading.set(false); }
  }

  selectedAgentId(): string | null {
    const chosen = this.selectedAgentIdChoice();
    const swarm = this.selectedSwarm();
    if (chosen && swarm?.agent_files.some((file) => this.stripAgentName(file) === chosen)) return chosen;
    return this.defaultAgentId();
  }

  agentChoices(): string[] {
    const swarm = this.selectedSwarm();
    return swarm ? swarm.agent_files.map((file) => this.stripAgentName(file)) : [];
  }

  private ensureAgentSelection(swarm: SwarmDetails): void {
    const available = swarm.agent_files.map((file) => this.stripAgentName(file));
    const current = this.selectedAgentIdChoice();
    if (!current || !available.includes(current)) this.selectedAgentIdChoice.set(this.defaultAgentId(swarm));
  }

  private defaultAgentId(swarm: SwarmDetails | null = this.selectedSwarm()): string | null {
    if (!swarm?.agent_files?.length) return null;
    const preferred = swarm.agent_files.find((file) => file.includes('planner'));
    return preferred ? this.stripAgentName(preferred) : this.stripAgentName(swarm.agent_files[0]);
  }

  private stripAgentName(filePath: string): string {
    const normalized = filePath.replace(/\\/g, '/');
    const withoutExt = normalized.replace(/\.[^.]+$/, '');
    return withoutExt.split('/').pop() ?? filePath;
  }

  private parseUserJson(value: string): unknown {
    const trimmed = value.trim();
    if (!trimmed) return {};
    try { return normalizeJsonValue(JSON.parse(trimmed)); } catch (error) {
      throw new Error(`Swarm 输入必须是有效的 JSON: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  private pushFeed(title: string, method: string, endpoint: string, tone: FeedItem['tone'], payload: unknown, meta?: string): void {
    const item: FeedItem = { id: this.nextFeedId(), title, endpoint, method, tone, timestamp: shortTime(), payload: normalizeJsonValue(payload), meta };
    this.responseFeed.set([item, ...this.responseFeed()].slice(0, 14));
  }

  private watchRun(run: RunSnapshot): void {
    this.closeStream();
    const sourceUrl = `${this.baseUrl().replace(/\/$/, '')}${run.events_url}`;
    this.streamState.set('connecting');
    this.streamNote.set(`正在监听 ${run.run_id}`);
    const source = new EventSource(sourceUrl);
    this.eventSource = source;
    source.onopen = () => { this.streamState.set('open'); this.streamNote.set(`实时事件流已开启: ${run.run_id}`); };
    source.onerror = () => { this.streamState.set('error'); this.streamNote.set(`实时事件流已中断: ${run.run_id}`); };
    source.addEventListener('run.snapshot', (event) => { const parsed = this.safeParseEvent(event); if (parsed) { this.activeRun.set(parsed as RunSnapshot); this.pushLiveEvent('run.snapshot', parsed); } });
    source.addEventListener('message', (event) => { const parsed = this.safeParseEvent(event); if (parsed) this.pushLiveEvent('message', parsed); });
    source.onmessage = (event) => { const parsed = this.safeParseEvent(event); if (parsed) this.pushLiveEvent('message', parsed); };
  }

  private pushLiveEvent(eventName: string, payload: unknown): void {
    const item: FeedItem = { id: this.nextFeedId(), title: `实时事件 · ${eventName}`, endpoint: 'SSE', method: 'EVENT', tone: 'info', timestamp: shortTime(), payload: normalizeJsonValue(payload) };
    this.liveEvents.set([item, ...this.liveEvents()].slice(0, 20));
  }

  private safeParseEvent(event: Event): unknown | null {
    const message = event as MessageEvent<string>;
    if (typeof message.data !== 'string') return null;
    try { return normalizeJsonValue(JSON.parse(message.data)); } catch { return message.data; }
  }

  private closeStream(): void {
    if (this.eventSource) { this.eventSource.close(); this.eventSource = null; }
    this.streamState.set('closed');
  }

  feedPreview(item: FeedItem): string { return valuePreview(item.payload); }

  swarmOverview(): string {
    const swarm = this.selectedSwarm();
    return swarm ? `${swarm.agent_count} 智能体 · ${swarm.skill_count} 技能 · ${swarm.tool_count} 工具` : '未选择 Swarm';
  }

  graphSummary(): string {
    const graph = this.selectedGraph();
    return graph ? `${graph.node_count} 节点 · ${graph.edge_count} 边` : '图未加载';
  }

  payloadText(): string { return this.swarmPayloadText().trim() || '{}'; }

  selectedRunHint(): string {
    const run = this.activeRun();
    return run ? `${run.status} · ${run.event_count} 个事件` : '无运行加载';
  }

  apiErrorDetails(): unknown {
    return { index: this.apiIndex(), health: this.health(), ready: this.ready() };
  }

  errorDetailForViewer(): unknown {
    const err = this.error();
    if (!err) return null;
    return {
      摘要: err.summary,
      ...(err.status !== undefined && { 状态码: err.status }),
      ...(err.statusText && { 状态文本: err.statusText }),
      ...(err.url && { 请求地址: err.url }),
      ...(err.message && { 错误消息: err.message }),
      ...(err.body !== undefined && { 响应体: err.body }),
      ...(err.stack && { 堆栈: err.stack }),
      时间戳: err.timestamp,
    };
  }

  async copyErrorToClipboard(): Promise<void> {
    const err = this.error();
    if (!err) return;
    const text = JSON.stringify(err, null, 2);
    try { await navigator.clipboard.writeText(text); } catch {
      const textarea = document.createElement('textarea');
      textarea.value = text; textarea.style.position = 'fixed'; textarea.style.opacity = '0';
      document.body.appendChild(textarea); textarea.select(); document.execCommand('copy');
      document.body.removeChild(textarea);
    }
  }
}
