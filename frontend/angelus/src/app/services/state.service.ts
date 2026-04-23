import { DestroyRef, Injectable, computed, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { ApiService, joinUrl } from '../api.service';
import type {
  AgentCatalogItem,
  ApiIndexResponse,
  ApiSettings,
  EventCatalogItem,
  EventListResponse,
  GraphSnapshot,
  HealthResponse,
  KnowledgeCatalogItem,
  LogCatalogItem,
  LogCatalogStats,
  LogListResponse,
  MemoryCatalogItem,
  TaskCatalogItem,
  MetricsResponse,
  ReadyResponse,
  RunSnapshot,
  SwarmDetails,
  SwarmSummary,
  SwarmStatsResponse,
  ToolCatalogItem,
} from '../api.types';
import { asJsonValue, normalizeJsonValue, valuePreview } from '../json-utils';

type SwarmExecutionTemplate = 'summary' | 'analysis' | 'debug' | 'custom';
type SwarmOutputStyle = 'markdown' | 'bullet' | 'brief';

const SWARM_EXECUTION_PRESETS: Record<
  SwarmExecutionTemplate,
  {
    label: string;
    prompt: string;
    context: string;
    outputStyle: SwarmOutputStyle;
  }
> = {
  summary: {
    label: '系统概览',
    prompt: '总结系统当前可用的 swarm 与 graph 状态。',
    context: '请聚焦当前可用的 agent、图结构、运行状态和关键风险。',
    outputStyle: 'markdown',
  },
  analysis: {
    label: '状态分析',
    prompt: '分析当前 swarm 的任务执行情况，并找出瓶颈。',
    context: '请给出关键发现、可执行建议，以及下一步观察重点。',
    outputStyle: 'bullet',
  },
  debug: {
    label: '排障建议',
    prompt: '检查当前 swarm 的执行链路，定位异常并提出修复建议。',
    context: '请重点关注失败节点、超时、重复执行和资源瓶颈。',
    outputStyle: 'brief',
  },
  custom: {
    label: '自定义',
    prompt: '',
    context: '',
    outputStyle: 'markdown',
  },
};

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
  status: 'online' | 'offline' | 'running' | 'error';
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
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled' | 'timeout';
  priority: 'low' | 'medium' | 'high' | 'urgent';
  executor: string;
  duration: string;
  createdAt: string;
  detail: {
    description: string;
    input: unknown;
    output: unknown;
    logs: { time: string; level: 'info' | 'warn' | 'error' | 'success'; message: string }[];
    failureReason?: string;
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

export interface MetricCard {
  label: string;
  value: string;
  fill: number;
  tone?: 'success' | 'warning' | 'error' | 'info';
}

export interface MetricTrendCard extends MetricCard {
  data: number[];
  color: string;
  delta: string;
  direction: 'up' | 'down' | 'neutral';
}

export interface SwarmMgmtTrendCard {
  label: string;
  value: string;
  fill: number;
  color: string;
}

export interface SwarmMgmtTaskSlice {
  label: string;
  count: number;
  percentage: number;
  color: string;
}

export interface TopologyLegendItem {
  label: string;
  detail: string;
  color: string;
  kind: 'dot' | 'line' | 'dashed';
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
  readonly selectedSwarm = signal<SwarmSummary | null>(null);
  readonly selectedAgentIdChoice = signal<string | null>(null);
  readonly selectedGraph = signal<GraphSnapshot | null>(null);
  readonly swarmExecutionTemplate = signal<SwarmExecutionTemplate>('summary');
  readonly swarmExecutionPrompt = signal<string>(SWARM_EXECUTION_PRESETS.summary.prompt);
  readonly swarmExecutionContext = signal<string>(SWARM_EXECUTION_PRESETS.summary.context);
  readonly swarmExecutionOutputStyle = signal<SwarmOutputStyle>(SWARM_EXECUTION_PRESETS.summary.outputStyle);
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
  readonly agents = signal<AgentRow[]>([]);
  readonly agentsLoaded = signal(false);
  readonly tasks = signal<TaskItem[]>([]);
  readonly tasksLoaded = signal(false);
  readonly tools = signal<ToolItem[]>([]);
  readonly toolsLoaded = signal(false);
  readonly swarmStats = signal<SwarmStatsResponse | null>(null);
  readonly swarmStatsLoaded = signal(false);
  readonly events = signal<EventItem[]>([]);
  readonly eventsLoaded = signal(false);
  readonly eventsResponse = signal<EventListResponse | null>(null);
  readonly logs = signal<LogItem[]>([]);
  readonly logsLoaded = signal(false);
  readonly logsResponse = signal<LogListResponse | null>(null);
  readonly metrics = signal<MetricsResponse | null>(null);
  readonly metricsLoaded = signal(false);
  readonly metricsWindow = signal('1h');
  readonly metricsResolution = signal('1m');
  readonly knowledge = signal<KnowledgeEntry[]>([]);
  readonly knowledgeLoaded = signal(false);
  readonly memories = signal<MemoryItem[]>([]);
  readonly memoriesLoaded = signal(false);

  /* ---------- Settings (localStorage-backed) ---------- */
  readonly settingsLoading = signal<boolean>(false);
  readonly settingsSaving = signal<boolean>(false);
  readonly settingsError = signal<string | null>(null);
  readonly apiTimeout = signal<number>(30);
  readonly reconnectInterval = signal<number>(5);
  readonly autoReconnect = signal<boolean>(true);
  readonly darkMode = signal<boolean>(true);
  readonly compactMode = signal<boolean>(false);
  readonly showDebug = signal<boolean>(false);
  readonly language = signal<string>('zh');
  readonly settingsSaved = signal<boolean>(false);

  private readonly feedId = signal(0);
  private eventSource: EventSource | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private refreshGraceful = false;
  private readonly LS_PREFIX = 'angelus_';

  readonly totalAgents = computed(() => this.swarms().reduce((sum, s) => sum + s.agent_count, 0));
  readonly errorCount = computed(() => this.responseFeed().filter((f) => f.tone === 'error').length);
  readonly resolvedGraph = computed<GraphSnapshot | null>(() => this.selectedSwarm()?.graph ?? this.selectedGraph());
  readonly activeRunNodeId = computed(() => {
    const run = this.activeRun();
    return run?.status === 'running' ? run.current_node_id ?? null : null;
  });
  readonly activeRunStatusText = computed(() => {
    const run = this.activeRun();
    return run ? this.runStatusLabel(run.status) : '空闲';
  });

  /* ---------- Derived data (replaces hard-coded mock) ---------- */

  readonly derivedAgents = computed<AgentRow[]>(() => {
    if (this.agentsLoaded()) return this.agents();
    const swarm = this.selectedSwarm();
    const graph = this.resolvedGraph();
    const run = this.activeRun();
    const feed = this.responseFeed();
    if (!swarm?.agent_files?.length) return [];
    return swarm.agent_files.map((file, idx) => {
      const id = this.stripAgentName(file);
      const node = graph?.nodes.find(n => n.agent_id === id || n.node_name === id);
      const isRunning = run?.current_node_name === id && run?.status === 'running';
      const calls = feed.filter(f => f.title.includes(id) || (f.meta && f.meta.includes(id))).length;
      return {
        id, name: id,
        status: (isRunning ? 'running' : 'online') as AgentRow['status'],
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
      active: agents.filter(a => a.status === 'online' || a.status === 'running').length,
      totalTasks: agents.reduce((s, a) => s + a.tasksExecuted, 0),
      avgResponseTime: agents.length ? `${Math.round(agents.reduce((s, a) => s + parseInt(a.avgResponseTime), 0) / agents.length)}ms` : '-',
      totalTokenUsage: agents.reduce((s, a) => s + a.tokenUsage, 0),
    };
  });

  readonly derivedTasks = computed<TaskItem[]>(() => {
    if (this.tasksLoaded()) return this.tasks();
    const feed = this.responseFeed();
    const run = this.activeRun();
    const tasks: TaskItem[] = [];
    if (run) {
      const isTimeout = run.error && this.isTimeoutLike(run.error);
      tasks.push({
        id: run.run_id,
        name: `${run.swarm} 运行`,
        status: (run.status === 'completed' ? 'success' : run.status === 'failed' ? (isTimeout ? 'timeout' : 'failed') : 'running') as TaskItem['status'],
        priority: 'high' as TaskItem['priority'],
        executor: run.swarm,
        duration: run.finished_at && run.started_at ? this.fmtDuration(run.started_at, run.finished_at) : '-',
        createdAt: run.created_at,
        detail: { description: `Swarm ${run.swarm} 执行`, input: run.state, output: run.final_state, logs: [], failureReason: isTimeout ? 'timeout' : run.error ? 'error' : undefined },
      });
    }
    feed.filter(f => f.method === 'POST' && (f.endpoint.includes('/run') || f.endpoint.includes('/round'))).forEach(item => {
      const isTimeout = item.tone === 'error' && this.isTimeoutLike(item.payload);
      tasks.push({
        id: `task-feed-${item.id}`,
        name: item.title,
        status: (isTimeout ? 'timeout' : item.tone === 'error' ? 'failed' : item.tone === 'success' ? 'success' : 'completed') as TaskItem['status'],
        priority: 'medium' as TaskItem['priority'],
        executor: item.meta || 'System',
        duration: '-',
        createdAt: item.timestamp,
        detail: { description: item.title, input: item.payload, output: null, logs: [], failureReason: isTimeout ? 'timeout' : item.tone === 'error' ? 'error' : undefined },
      });
    });
    return tasks;
  });

  readonly taskStats = computed(() => {
    const tasks = this.derivedTasks();
    const completed = tasks.filter(t => t.status === 'success').length;
    const failed = tasks.filter(t => t.status === 'failed' || t.status === 'timeout').length;
    const totalFinished = completed + failed;
    return {
      total: tasks.length,
      running: tasks.filter(t => t.status === 'running').length,
      successRate: totalFinished ? Math.round(completed / totalFinished * 100) : 0,
      avgDuration: '-',
      pending: tasks.filter(t => t.status === 'pending').length,
      timeout: tasks.filter(t => t.status === 'timeout').length,
    };
  });

  readonly derivedTools = computed<ToolItem[]>(() => {
    if (this.toolsLoaded()) return this.tools();
    const graph = this.resolvedGraph();
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
    if (this.eventsLoaded()) return this.events();
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
    const response = this.eventsResponse();
    const events = this.derivedEvents();
    const stats = response?.stats ?? null;
    return {
      today: response?.total ?? events.length,
      errors: stats?.errors ?? events.filter(e => e.level === 'error').length,
      warnings: stats?.warnings ?? events.filter(e => e.level === 'warn').length,
      infos: stats?.infos ?? events.filter(e => e.level === 'info').length,
    };
  });

  readonly derivedMetrics = computed<MetricsResponse>(() => {
    if (this.metricsLoaded() && this.metrics()) {
      return this.metrics()!;
    }
    return this.buildFallbackMetrics();
  });

  readonly metricCards = computed<MetricTrendCard[]>(() => {
    const metrics = this.derivedMetrics().series;
    return [
      this.buildTrendCard('CPU 使用率', metrics.cpu_percent, {
        formatter: (value) => `${Math.round(value)}%`,
        color: '#60a5fa',
        tone: 'info',
      }),
      this.buildTrendCard('内存占用', metrics.memory_mb, {
        formatter: (value) => `${Math.round(value)} MB`,
        color: '#f59e0b',
        tone: 'warning',
      }),
      this.buildTrendCard('请求延迟', metrics.request_latency_ms, {
        formatter: (value) => `${Math.round(value)} ms`,
        color: '#ef4444',
        tone: 'error',
      }),
      this.buildTrendCard('吞吐速率', metrics.throughput_rps, {
        formatter: (value) => `${value.toFixed(2)} rps`,
        color: '#10B981',
        tone: 'success',
      }),
      this.buildTrendCard('Token 用量', metrics.token_usage, {
        formatter: (value) => this.formatCompactCount(value),
        color: '#8B5CF6',
        tone: 'info',
      }),
      this.buildTrendCard('错误率', metrics.error_rate.map((value) => value * 100), {
        formatter: (value) => `${value.toFixed(1)}%`,
        color: '#ef4444',
        tone: 'error',
      }),
    ];
  });

  readonly derivedLogs = computed<LogItem[]>(() => {
    if (this.logsLoaded()) return this.logs();
    return this.responseFeed().map(item => ({
      id: `log-${item.id}`,
      time: item.timestamp,
      level: (item.tone === 'error' ? 'ERROR' : item.tone === 'warn' ? 'WARN' : item.tone === 'success' ? 'INFO' : 'DEBUG') as LogItem['level'],
      service: item.endpoint.includes('/agents/') ? 'agent' : item.endpoint.includes('/swarms/') ? 'swarm' : 'backend',
      message: `${item.method} ${item.endpoint} — ${item.title}`,
    }));
  });

  readonly logStats = computed(() => {
    const response = this.logsResponse();
    const logs = this.derivedLogs();
    const stats: LogCatalogStats | null = response?.stats ?? null;
    return {
      total: response?.total ?? logs.length,
      error: stats?.error ?? logs.filter(l => l.level === 'ERROR').length,
      warn: stats?.warn ?? logs.filter(l => l.level === 'WARN').length,
      info: stats?.info ?? logs.filter(l => l.level === 'INFO').length,
      debug: stats?.debug ?? logs.filter(l => l.level === 'DEBUG').length,
    };
  });

  readonly derivedKnowledge = computed<KnowledgeEntry[]>(() => {
    if (this.knowledgeLoaded()) return this.knowledge();
    const graph = this.resolvedGraph();
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
    const now = Date.now();
    const recentWindowMs = 30 * 24 * 60 * 60 * 1000;
    return {
      total: entries.length,
      documents: entries.filter(e => e.type === 'document').length,
      vectors: entries.filter(e => e.type === 'vector').length,
      citations: entries.reduce((s, e) => s + e.citations, 0),
      recentUpdates: entries.filter((entry) => {
        const raw = entry.meta?.updatedAt || entry.createdAt;
        const parsed = Date.parse(raw);
        return Number.isFinite(parsed) && now - parsed <= recentWindowMs;
      }).length,
    };
  });

  readonly derivedMemories = computed<MemoryItem[]>(() => {
    if (this.memoriesLoaded()) return this.memories();
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
    const now = Date.now();
    const activeWindowMs = 24 * 60 * 60 * 1000;
    return {
      total: memories.length,
      active: memories.filter(m => {
        const parsed = Date.parse(m.timestamp);
        return m.type === 'working' || (Number.isFinite(parsed) && now - parsed <= activeWindowMs);
      }).length,
      avgImportance: memories.length ? (memories.reduce((s, m) => s + m.importance, 0) / memories.length / 100).toFixed(2) : '0',
      longTerm: memories.filter(m => m.type === 'episodic' || m.type === 'semantic').length,
      working: memories.filter(m => m.type === 'working').length,
    };
  });

  readonly swarmMgmtStats = computed(() => {
    const stats = this.swarmStats();
    if (this.swarmStatsLoaded() && stats) {
      return {
        successRate: Math.round(stats.success_rate),
        throughput: stats.throughput,
        tokenUsage: `${Math.round(stats.token_usage / 1000)}K`,
        taskCount: stats.task_distribution.completed + stats.task_distribution.running + stats.task_distribution.pending,
      };
    }
    const run = this.activeRun();
    return {
      successRate: run?.status === 'completed' ? 100 : run?.status === 'failed' ? 0 : 98,
      throughput: run ? Math.round(run.event_count / Math.max(1, run.rounds || 1)) : 0,
      tokenUsage: run ? `${Math.round(run.event_count * 0.5)}K` : '-',
      taskCount: run ? 1 : 0,
    };
  });

  readonly swarmMgmtResourceTrends = computed<SwarmMgmtTrendCard[]>(() => {
    const stats = this.swarmStats();
    if (this.swarmStatsLoaded() && stats) {
      const cpuSeries = stats.resource_usage.cpu_percent ?? [];
      const memorySeries = stats.resource_usage.memory_mb ?? [];
      const latestCpu = this.latestNumber(cpuSeries);
      const latestMemory = this.latestNumber(memorySeries);
      const memoryMax = Math.max(...memorySeries, latestMemory, 1);
      const throughputFill = Math.min(100, Math.max(0, stats.throughput * 12));
      return [
        {
          label: 'CPU',
          value: `${Math.round(latestCpu)}%`,
          fill: Math.min(100, Math.max(0, latestCpu)),
          color: '#8B5CF6',
        },
        {
          label: '内存',
          value: `${Math.round(latestMemory)} MB`,
          fill: Math.min(100, Math.max(0, (latestMemory / memoryMax) * 100)),
          color: '#10B981',
        },
        {
          label: '吞吐',
          value: `${stats.throughput} rps`,
          fill: throughputFill,
          color: '#f59e0b',
        },
      ];
    }

    const run = this.activeRun();
    const feedCount = this.responseFeed().length + this.liveEvents().length;
    const totalAgents = this.totalAgents() || 0;
    return [
      {
        label: 'CPU',
        value: `${Math.min(100, 12 + totalAgents * 4 + feedCount)}%`,
        fill: Math.min(100, 12 + totalAgents * 4 + feedCount),
        color: '#8B5CF6',
      },
      {
        label: '内存',
        value: `${220 + totalAgents * 12 + feedCount * 3} MB`,
        fill: Math.min(100, Math.max(0, (220 + totalAgents * 12 + feedCount * 3) / 8)),
        color: '#10B981',
      },
      {
        label: '吞吐',
        value: run ? `${Math.round(run.event_count / Math.max(1, run.rounds || 1))} rps` : '0 rps',
        fill: run ? Math.min(100, run.event_count * 4) : 0,
        color: '#f59e0b',
      },
    ];
  });

  readonly swarmMgmtTaskSlices = computed<SwarmMgmtTaskSlice[]>(() => {
    const stats = this.swarmStats();
    const distribution = this.swarmStatsLoaded() && stats ? stats.task_distribution : null;
    const counts = distribution
      ? [
          { label: '完成', count: distribution.completed, color: '#10B981' },
          { label: '运行中', count: distribution.running, color: '#3B82F6' },
          { label: '待处理', count: distribution.pending, color: '#3B82F6' },
          { label: '失败', count: distribution.failed, color: '#ef4444' },
        ]
      : (() => {
          const run = this.activeRun();
          const pending = run ? 0 : 1;
          const running = run ? 1 : 0;
          const completed = this.derivedTasks().filter((task) => task.status === 'success').length;
          const failed = this.derivedTasks().filter((task) => task.status === 'failed').length;
          return [
            { label: '完成', count: completed, color: '#10B981' },
            { label: '运行中', count: running, color: '#3B82F6' },
            { label: '待处理', count: pending, color: '#3B82F6' },
            { label: '失败', count: failed, color: '#ef4444' },
          ];
        })();

    const total = Math.max(1, counts.reduce((sum, item) => sum + item.count, 0));
    return counts
      .filter((item) => item.count > 0)
      .map((item) => ({
        ...item,
        percentage: Math.round((item.count / total) * 100),
      }));
  });

  readonly swarmMgmtTaskGradient = computed(() => {
    const slices = this.swarmMgmtTaskSlices();
    if (slices.length === 0) {
      return 'conic-gradient(#10B981 0% 65%, #f59e0b 65% 90%, #ef4444 90% 100%)';
    }
    const total = Math.max(1, slices.reduce((sum, item) => sum + item.count, 0));
    let cursor = 0;
    const segments = slices.map((item) => {
      const span = (item.count / total) * 100;
      const segment = `${item.color} ${cursor.toFixed(1)}% ${(cursor + span).toFixed(1)}%`;
      cursor += span;
      return segment;
    });
    return `conic-gradient(${segments.join(', ')})`;
  });

  readonly topologyLegendItems = computed<TopologyLegendItem[]>(() => {
    const graph = this.resolvedGraph();
    const agents = this.derivedAgents();
    const runningCount = agents.filter((agent) => agent.status === 'running').length;
    const onlineCount = agents.filter((agent) => agent.status === 'online').length;
    if (!graph) {
      return [
        { label: '正在运行', detail: `${runningCount} 个节点`, color: '#3B82F6', kind: 'dot' },
        { label: '在线', detail: `${onlineCount} 个节点`, color: '#10B981', kind: 'dot' },
        { label: '入口节点', detail: '—', color: '#8B5CF6', kind: 'dot' },
        { label: 'Agent 节点', detail: '—', color: '#10B981', kind: 'dot' },
        { label: 'Tool 节点', detail: '—', color: '#f59e0b', kind: 'dot' },
        { label: '退出节点', detail: '—', color: '#ef4444', kind: 'dot' },
        { label: '数据流', detail: '边', color: '#94a3b8', kind: 'line' },
        { label: '控制流', detail: '条件边', color: '#94a3b8', kind: 'dashed' },
      ];
    }

    const agentCount = graph.nodes.filter((node) => node.node_type === 'AgentNode').length;
    const toolCount = graph.nodes.filter((node) => node.node_type === 'ToolNode').length;
    return [
      { label: '正在运行', detail: `${runningCount} 个节点`, color: '#3B82F6', kind: 'dot' },
      { label: '在线', detail: `${onlineCount} 个节点`, color: '#10B981', kind: 'dot' },
      { label: '入口节点', detail: graph.entry_node_id !== null ? `ID ${graph.entry_node_id}` : '无', color: '#8B5CF6', kind: 'dot' },
      { label: 'Agent 节点', detail: `${agentCount} 个`, color: '#10B981', kind: 'dot' },
      { label: 'Tool 节点', detail: `${toolCount} 个`, color: '#f59e0b', kind: 'dot' },
      { label: '退出节点', detail: graph.exit_node_id !== null ? `ID ${graph.exit_node_id}` : '无', color: '#ef4444', kind: 'dot' },
      { label: '数据流', detail: `${graph.edge_count} 条边`, color: '#94a3b8', kind: 'line' },
      { label: '控制流', detail: '条件/回路', color: '#94a3b8', kind: 'dashed' },
    ];
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

  private fmtDurationMs(durationMs: number): string {
    if (!Number.isFinite(durationMs) || durationMs <= 0) return '-';
    const sec = Math.round(durationMs / 1000);
    if (sec < 60) return `${sec}s`;
    if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`;
    return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
  }

  private latestNumber(values: number[]): number {
    if (!Array.isArray(values) || values.length === 0) {
      return 0;
    }
    const last = values[values.length - 1];
    return Number.isFinite(last) ? Number(last) : 0;
  }

  private formatCompactCount(value: number): string {
    if (!Number.isFinite(value) || value <= 0) {
      return '0';
    }
    if (value >= 1_000_000) {
      return `${(value / 1_000_000).toFixed(1)}M`;
    }
    if (value >= 1_000) {
      return `${(value / 1_000).toFixed(1)}K`;
    }
    return `${Math.round(value)}`;
  }

  private buildTrendCard(
    label: string,
    data: number[],
    options: {
      formatter: (value: number) => string;
      color: string;
      tone: MetricTrendCard['tone'];
    }
  ): MetricTrendCard {
    const normalized = Array.isArray(data) ? data.map((value) => (Number.isFinite(value) ? Number(value) : 0)) : [];
    const latest = this.latestNumber(normalized);
    const first = normalized.length > 0 ? normalized[0] : latest;
    const max = Math.max(...normalized, 1);
    const deltaValue = latest - first;
    const deltaDirection: MetricTrendCard['direction'] = deltaValue > 0.5 ? 'up' : deltaValue < -0.5 ? 'down' : 'neutral';
    return {
      label,
      value: options.formatter(latest),
      fill: Math.min(100, Math.max(0, (latest / max) * 100)),
      tone: options.tone,
      data: normalized.length > 0 ? normalized : [0],
      color: options.color,
      delta: `${deltaValue >= 0 ? '+' : ''}${Number.isInteger(deltaValue) ? deltaValue.toFixed(0) : deltaValue.toFixed(1)}`,
      direction: deltaDirection,
    };
  }

  private buildFallbackMetrics(): MetricsResponse {
    const feedCount = this.responseFeed().length + this.liveEvents().length;
    const activeRuns = this.activeRun() ? 1 : 0;
    const totalAgents = this.totalAgents() || 0;
    const errors = Math.max(0, this.errorCount());
    const graphNodes = this.resolvedGraph()?.node_count ?? this.resolvedGraph()?.nodes.length ?? 0;
    const graphFactor = Math.max(1, graphNodes || 1);
    const window = this.metricsWindow();
    const resolution = this.metricsResolution();
    const bucketCount = 12;

    const cpu = Array.from({ length: bucketCount }, (_, idx) => Math.min(100, 12 + totalAgents * 4 + activeRuns * 12 + feedCount + idx));
    const memory = Array.from({ length: bucketCount }, (_, idx) => 220 + graphFactor * 10 + activeRuns * 28 + feedCount * 3 + idx * 4);
    const latency = Array.from({ length: bucketCount }, (_, idx) => 28 + activeRuns * 14 + errors * 3 + idx * 2);
    const throughput = Array.from({ length: bucketCount }, (_, idx) => Number((Math.max(0, feedCount - idx) / 6 + activeRuns * 0.25).toFixed(3)));
    const tokenUsage = Array.from({ length: bucketCount }, (_, idx) => 800 + totalAgents * 220 + feedCount * 90 + idx * 45);
    const errorRate = Array.from({ length: bucketCount }, (_, idx) => Number((Math.min(0.25, errors / Math.max(1, feedCount + activeRuns + idx + 1))).toFixed(4)));

    return {
      success: true,
      window,
      resolution,
      series: {
        cpu_percent: cpu,
        memory_mb: memory,
        request_latency_ms: latency,
        throughput_rps: throughput,
        token_usage: tokenUsage,
        error_rate: errorRate,
      },
    };
  }

  private mapAgentCatalogItem(item: AgentCatalogItem): AgentRow {
    return {
      id: item.id,
      name: item.name,
      status: item.status,
      type: item.type,
      capabilities: [...(item.capabilities ?? [])],
      tags: [...(item.tags ?? [])],
      tasksExecuted: item.tasks_executed ?? 0,
      successRate: item.success_rate ?? 0,
      avgResponseTime: `${Math.round(item.avg_response_time_ms ?? 0)}ms`,
      tokenUsage: item.token_usage_total ?? 0,
      lastActivity: item.last_activity ?? '-',
    };
  }

  private mapTaskCatalogItem(item: TaskCatalogItem): TaskItem {
    return {
      id: item.id,
      name: item.name,
      status: item.status,
      priority: item.priority,
      executor: item.executor,
      duration: this.fmtDurationMs(item.duration_ms ?? 0),
      createdAt: item.created_at,
      detail: {
        description: item.description,
        input: item.input,
        output: item.output,
        logs: item.logs.map((log) => ({
          time: log.time ?? '-',
          level: log.level,
          message: log.message,
        })),
      },
    };
  }

  private mapToolCatalogItem(item: ToolCatalogItem): ToolItem {
    return {
      id: item.id,
      name: item.name,
      icon: item.type === 'API' ? '🌐' : '🔧',
      type: item.type,
      status: item.status,
      desc: item.description,
      calls: item.calls ?? 0,
      avgMs: item.avg_ms ?? 0,
      lastCall: item.last_call ?? '-',
      successRate: item.success_rate ?? 0,
      errorRate: item.error_rate ?? 0,
      created: item.created_at,
      schema: (item.schema && typeof item.schema === 'object' ? (item.schema as Record<string, string>) : {}),
    };
  }

  private mapEventCatalogItem(item: EventCatalogItem): EventItem {
    return {
      id: item.id,
      time: item.time,
      level: item.level,
      source: item.source,
      event: item.event,
      detail: item.detail,
      data: item.data,
    };
  }

  private mapLogCatalogItem(item: LogCatalogItem): LogItem {
    return {
      id: item.id,
      time: item.time,
      level: item.level,
      service: item.service,
      message: item.message,
    };
  }

  private mapKnowledgeCatalogItem(item: KnowledgeCatalogItem): KnowledgeEntry {
    return {
      id: item.id,
      title: item.title,
      type: item.type as KnowledgeEntry['type'],
      source: item.source,
      tags: [...(item.tags ?? [])],
      status: item.status as KnowledgeEntry['status'],
      citations: item.citations ?? 0,
      createdAt: item.created_at,
      content: item.content,
      meta: {
        author: item.meta?.author ?? 'System',
        version: item.meta?.version ?? '1.0',
        updatedAt: item.meta?.updated_at ?? item.created_at,
        size: item.meta?.size ?? '-',
      },
      related: [...(item.related ?? [])],
    };
  }

  private mapMemoryCatalogItem(item: MemoryCatalogItem): MemoryItem {
    return {
      id: item.id,
      summary: item.summary,
      content: item.content,
      timestamp: item.timestamp,
      type: item.type as MemoryItem['type'],
      source: item.source,
      sentiment: item.sentiment ?? 0,
      importance: item.importance ?? 0,
      relatedIds: [...(item.related_ids ?? [])],
    };
  }

  constructor(private readonly apiService: ApiService) {}

  init(destroyRef: DestroyRef): void {
    this.loadSettings();
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

  private _loadNumber(key: string, fallback: number): number {
    try {
      const raw = localStorage.getItem(`${this.LS_PREFIX}${key}`);
      if (raw === null) return fallback;
      const parsed = Number(raw);
      return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
    } catch { return fallback; }
  }

  private _loadBool(key: string, fallback: boolean): boolean {
    try {
      const raw = localStorage.getItem(`${this.LS_PREFIX}${key}`);
      if (raw === null) return fallback;
      return raw === 'true';
    } catch { return fallback; }
  }

  private _loadString(key: string, fallback: string): string {
    try {
      return localStorage.getItem(`${this.LS_PREFIX}${key}`) ?? fallback;
    } catch { return fallback; }
  }

  loadSettings(): void {
    this.apiBaseUrl.set(this._loadString('apiBaseUrl', '/api'));
    this.apiTimeout.set(this._loadNumber('apiTimeout', 30));
    this.reconnectInterval.set(this._loadNumber('reconnectInterval', 5));
    this.autoReconnect.set(this._loadBool('autoReconnect', true));
    this.darkMode.set(this._loadBool('darkMode', true));
    this.compactMode.set(this._loadBool('compactMode', false));
    this.showDebug.set(this._loadBool('showDebug', false));
    this.language.set(this._loadString('language', 'zh'));
    this.applyTheme();
    void this.syncApiSettingsFromBackend();
  }

  private _persistLocalSettings(settings: {
    apiBaseUrl?: string;
    apiTimeout?: number;
    reconnectInterval?: number;
    autoReconnect?: boolean;
    darkMode?: boolean;
    compactMode?: boolean;
    showDebug?: boolean;
    language?: string;
  }): void {
    try {
      if (settings.apiBaseUrl !== undefined) {
        this.apiBaseUrl.set(settings.apiBaseUrl.trim() || '/api');
        localStorage.setItem(`${this.LS_PREFIX}apiBaseUrl`, this.apiBaseUrl());
      }
      if (settings.apiTimeout !== undefined) {
        this.apiTimeout.set(settings.apiTimeout);
        localStorage.setItem(`${this.LS_PREFIX}apiTimeout`, String(settings.apiTimeout));
      }
      if (settings.reconnectInterval !== undefined) {
        this.reconnectInterval.set(settings.reconnectInterval);
        localStorage.setItem(`${this.LS_PREFIX}reconnectInterval`, String(settings.reconnectInterval));
      }
      if (settings.autoReconnect !== undefined) {
        this.autoReconnect.set(settings.autoReconnect);
        localStorage.setItem(`${this.LS_PREFIX}autoReconnect`, String(settings.autoReconnect));
      }
      if (settings.darkMode !== undefined) {
        this.darkMode.set(settings.darkMode);
        localStorage.setItem(`${this.LS_PREFIX}darkMode`, String(settings.darkMode));
      }
      if (settings.compactMode !== undefined) {
        this.compactMode.set(settings.compactMode);
        localStorage.setItem(`${this.LS_PREFIX}compactMode`, String(settings.compactMode));
      }
      if (settings.showDebug !== undefined) {
        this.showDebug.set(settings.showDebug);
        localStorage.setItem(`${this.LS_PREFIX}showDebug`, String(settings.showDebug));
      }
      if (settings.language !== undefined) {
        this.language.set(settings.language);
        localStorage.setItem(`${this.LS_PREFIX}language`, settings.language);
      }
      this.applyTheme();
    } catch {
      // localStorage may be unavailable in some environments
    }
  }

  private _applyApiSettings(settings: ApiSettings, persistLocal = false): void {
    const normalized = {
      base_url: (settings.base_url ?? '/api').trim() || '/api',
      timeout_seconds: Number.isFinite(settings.timeout_seconds) && settings.timeout_seconds > 0 ? settings.timeout_seconds : 30,
      sse_reconnect_interval_seconds:
        Number.isFinite(settings.sse_reconnect_interval_seconds) && settings.sse_reconnect_interval_seconds > 0
          ? settings.sse_reconnect_interval_seconds
          : 5,
      auto_reconnect: Boolean(settings.auto_reconnect),
    };

    this.apiBaseUrl.set(normalized.base_url);
    this.apiTimeout.set(normalized.timeout_seconds);
    this.reconnectInterval.set(normalized.sse_reconnect_interval_seconds);
    this.autoReconnect.set(normalized.auto_reconnect);

    if (!persistLocal) {
      return;
    }

    try {
      localStorage.setItem(`${this.LS_PREFIX}apiBaseUrl`, this.apiBaseUrl());
      localStorage.setItem(`${this.LS_PREFIX}apiTimeout`, String(this.apiTimeout()));
      localStorage.setItem(`${this.LS_PREFIX}reconnectInterval`, String(this.reconnectInterval()));
      localStorage.setItem(`${this.LS_PREFIX}autoReconnect`, String(this.autoReconnect()));
    } catch {
      // localStorage may be unavailable in some environments
    }
  }

  private async syncApiSettingsFromBackend(): Promise<void> {
    this.settingsLoading.set(true);
    this.settingsError.set(null);
    try {
      const response = await this.apiService.getSettings(this.baseUrl());
      if (response.success) {
        this._applyApiSettings(response.settings.api, true);
      }
    } catch {
      // Keep local settings when the backend settings endpoint is unavailable.
    } finally {
      this.settingsLoading.set(false);
    }
  }

  async saveSettings(settings: {
    apiBaseUrl?: string;
    apiTimeout?: number;
    reconnectInterval?: number;
    autoReconnect?: boolean;
    darkMode?: boolean;
    compactMode?: boolean;
    showDebug?: boolean;
    language?: string;
  }): Promise<void> {
    this.settingsSaving.set(true);
    this.settingsError.set(null);
    try {
      this._persistLocalSettings({
        apiBaseUrl: settings.apiBaseUrl,
        darkMode: settings.darkMode,
        compactMode: settings.compactMode,
        showDebug: settings.showDebug,
        language: settings.language,
      });

      const apiPayload: ApiSettings = {
        base_url: settings.apiBaseUrl !== undefined ? (settings.apiBaseUrl.trim() || '/api') : this.apiBaseUrl(),
        timeout_seconds: settings.apiTimeout ?? this.apiTimeout(),
        sse_reconnect_interval_seconds: settings.reconnectInterval ?? this.reconnectInterval(),
        auto_reconnect: settings.autoReconnect ?? this.autoReconnect(),
      };

      const response = await this.apiService.updateSettings(this.baseUrl(), { api: apiPayload });
      if (response.success) {
        this._applyApiSettings(response.settings.api, true);
      }

      this.settingsSaved.set(true);
      setTimeout(() => this.settingsSaved.set(false), 2000);
    } catch (error) {
      this.settingsError.set(error instanceof Error ? error.message : '保存设置失败');
      throw error;
    } finally {
      this.settingsSaving.set(false);
    }
  }

  applyTheme(): void {
    const dm = this.darkMode();
    try {
      if (dm) {
        document.body.classList.add('dark');
        document.body.classList.remove('light');
      } else {
        document.body.classList.add('light');
        document.body.classList.remove('dark');
      }
    } catch { /* ignore */ }
  }

  setSwarmExecutionTemplate(value: string): void {
    const template = value in SWARM_EXECUTION_PRESETS ? (value as SwarmExecutionTemplate) : 'custom';
    this.swarmExecutionTemplate.set(template);
    if (template === 'custom') {
      return;
    }
    const preset = SWARM_EXECUTION_PRESETS[template];
    this.swarmExecutionPrompt.set(preset.prompt);
    this.swarmExecutionContext.set(preset.context);
    this.swarmExecutionOutputStyle.set(preset.outputStyle);
  }

  setSwarmExecutionPrompt(value: string): void { this.swarmExecutionPrompt.set(value); }
  setSwarmExecutionContext(value: string): void { this.swarmExecutionContext.set(value); }
  setSwarmExecutionOutputStyle(value: string): void {
    const next = value === 'brief' || value === 'bullet' || value === 'markdown' ? value : 'markdown';
    this.swarmExecutionOutputStyle.set(next);
  }

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

  async loadOverview(options: { gracefulOffline?: boolean } = {}): Promise<void> {
    const gracefulOffline = options.gracefulOffline ?? true;
    this.loading.set(true);
    this.error.set(null);
    this.refreshGraceful = gracefulOffline;
    try {
      const baseUrl = this.baseUrl();
      const [indexResult, healthResult, readyResult, swarmResult] = await Promise.allSettled([
        this.apiService.index(baseUrl),
        this.apiService.health(baseUrl),
        this.apiService.ready(baseUrl),
        this.apiService.listSwarms(baseUrl),
      ]);
      const issues: string[] = [];
      let offlineDetected = false;
      if (indexResult.status === 'fulfilled') {
        this.apiIndex.set(indexResult.value);
        this.pushFeed('API 索引', 'GET', `${baseUrl}`, 'info', indexResult.value, '根元数据');
      } else if (this.isOfflineLikeError(indexResult.reason)) {
        offlineDetected = true;
      } else {
        issues.push(errorSummary(indexResult.reason));
      }
      if (healthResult.status === 'fulfilled') {
        this.health.set(healthResult.value);
        this.pushFeed('健康检查', 'GET', `${baseUrl}/health`, 'info', healthResult.value);
      } else if (this.isOfflineLikeError(healthResult.reason)) {
        offlineDetected = true;
      } else {
        issues.push(errorSummary(healthResult.reason));
      }
      if (readyResult.status === 'fulfilled') {
        this.ready.set(readyResult.value);
        this.pushFeed('就绪状态', 'GET', `${baseUrl}/ready`, 'info', readyResult.value);
      } else if (this.isOfflineLikeError(readyResult.reason)) {
        offlineDetected = true;
      } else {
        issues.push(errorSummary(readyResult.reason));
      }
      if (swarmResult.status === 'fulfilled') {
        this.swarms.set(swarmResult.value.swarms);
        this.pushFeed('Swarm 注册表', 'GET', `${baseUrl}/swarms`, 'success', swarmResult.value);
        const availableNames = swarmResult.value.swarms.map((s) => s.swarm_name);
        if (!this.selectedSwarmName() || !availableNames.includes(this.selectedSwarmName()!)) {
          this.selectedSwarmName.set(swarmResult.value.swarms[0]?.swarm_name ?? null);
        }
        if (this.selectedSwarmName()) {
          const selectedFromList = swarmResult.value.swarms.find(
            (item) => item.swarm_name === this.selectedSwarmName()
          );
          if (selectedFromList) {
            this.selectedSwarm.set(selectedFromList);
            this.selectedGraph.set(selectedFromList.graph ?? null);
            this.ensureAgentSelection(selectedFromList);
          }
        }
      } else if (this.isOfflineLikeError(swarmResult.reason)) {
        offlineDetected = true;
      } else {
        issues.push(errorSummary(swarmResult.reason));
      }
      await Promise.allSettled([
        this.loadEvents({}, { gracefulOffline }),
        this.loadLogs(),
        this.loadMetrics(),
        this.loadKnowledge(),
        this.loadMemory(),
      ]);
      if (this.selectedSwarmName()) {
        await this.reloadSelectedSwarm({ clearError: false, gracefulOffline });
      } else {
        this.selectedSwarm.set(null);
        this.selectedGraph.set(null);
        this.agents.set([]);
        this.agentsLoaded.set(true);
        this.tasks.set([]);
        this.tasksLoaded.set(true);
        this.tools.set([]);
        this.toolsLoaded.set(true);
        this.swarmStats.set(null);
        this.swarmStatsLoaded.set(false);
      }
      if (offlineDetected && gracefulOffline) {
        this.applyOfflineSnapshot();
      }
      if (issues.length > 0) {
        this.error.set({ summary: issues.join(' · '), message: issues.join('\n'), timestamp: new Date().toISOString() });
      }
    } catch (error) {
      if (gracefulOffline && this.isOfflineLikeError(error)) {
        this.applyOfflineSnapshot();
      } else {
        this.error.set(formatErrorDetail(error));
      }
    } finally {
      this.refreshGraceful = false;
      this.loading.set(false);
    }
  }

  async reloadSelectedSwarm(options: { clearError?: boolean; gracefulOffline?: boolean } = {}): Promise<void> {
    const swarmName = this.selectedSwarmName();
    if (!swarmName) {
      this.selectedSwarm.set(null);
      this.selectedGraph.set(null);
      this.agents.set([]);
      this.agentsLoaded.set(true);
      this.tasks.set([]);
      this.tasksLoaded.set(true);
      this.tools.set([]);
      this.toolsLoaded.set(true);
      this.swarmStats.set(null);
      this.swarmStatsLoaded.set(false);
      return;
    }
    this.loadingDetails.set(true);
    if (options.clearError !== false) this.error.set(null);
    try {
      const baseUrl = this.baseUrl();
      const response = await this.apiService.getSwarm(baseUrl, swarmName);
      this.selectedSwarm.set(response.swarm);
      this.ensureAgentSelection(response.swarm);
      this.pushFeed(`Swarm 详情 · ${swarmName}`, 'GET', `${baseUrl}/swarms/${swarmName}`, 'success', response);
      await Promise.all([
        this.loadSelectedGraph(),
        this.loadAgents(),
        this.loadTasks(),
        this.loadTools(),
        this.loadSwarmStats(),
      ]);
    } catch (error) {
      const fallback = this.swarms().find((item) => item.swarm_name === swarmName) ?? null;
      if (fallback) {
        this.selectedSwarm.set(fallback);
        this.selectedGraph.set(fallback.graph ?? null);
        this.ensureAgentSelection(fallback);
      } else {
        this.selectedSwarm.set(null);
        this.selectedGraph.set(null);
      }
      if (options.gracefulOffline ?? this.refreshGraceful) {
        if (this.isOfflineLikeError(error)) {
          this.applyOfflineSnapshot();
        } else {
          this.error.set(formatErrorDetail(error));
        }
      } else {
        this.error.set(formatErrorDetail(error));
      }
    }
    finally { this.loadingDetails.set(false); }
  }

  async loadSelectedGraph(): Promise<void> {
    const swarmName = this.selectedSwarmName();
    if (!swarmName) { this.selectedGraph.set(null); return; }
    const cached = this.swarms().find((item) => item.swarm_name === swarmName);
    if (cached?.graph) {
      this.selectedGraph.set(cached.graph);
      return;
    }
    try {
      const baseUrl = this.baseUrl();
      const response = await this.apiService.getGraph(baseUrl, swarmName);
      this.selectedGraph.set(response.graph);
      this.pushFeed(`图快照 · ${swarmName}`, 'GET', `${baseUrl}/swarms/${swarmName}/graph`, 'info', response);
    } catch (error) {
      if (cached?.graph) {
        this.selectedGraph.set(cached.graph);
        return;
      }
      if (!this.shouldSuppressOfflineError(error)) {
        this.error.set(formatErrorDetail(error));
      }
      this.selectedGraph.set(null);
    }
  }

  async loadAgents(): Promise<void> {
    const swarmName = this.selectedSwarmName();
    if (!swarmName) {
      this.agents.set([]);
      this.agentsLoaded.set(true);
      return;
    }
    try {
      const response = await this.apiService.listAgents(this.baseUrl(), swarmName, { q: '' });
      this.agents.set(response.agents.map((item) => this.mapAgentCatalogItem(item)));
      this.agentsLoaded.set(true);
      this.pushFeed(`Agents 列表 · ${swarmName}`, 'GET', `${this.baseUrl()}/swarms/${swarmName}/agents`, 'info', response);
    } catch (error) {
      if (!this.shouldSuppressOfflineError(error)) {
        this.error.set(formatErrorDetail(error));
        this.pushFeed(`Agents 列表失败 · ${swarmName}`, 'GET', `${this.baseUrl()}/swarms/${swarmName}/agents`, 'error', { error: errorSummary(error) });
      }
    }
  }

  async loadTasks(): Promise<void> {
    const swarmName = this.selectedSwarmName();
    try {
      const response = await this.apiService.listTasks(this.baseUrl(), {
        swarm: swarmName ?? undefined,
        limit: 500,
        page: 1,
      });
      this.tasks.set(response.items.map((item) => this.mapTaskCatalogItem(item)));
      this.tasksLoaded.set(true);
      this.pushFeed(
        `Tasks 列表${swarmName ? ` · ${swarmName}` : ''}`,
        'GET',
        `${this.baseUrl()}/tasks`,
        'info',
        response
      );
    } catch (error) {
      if (!this.shouldSuppressOfflineError(error)) {
        this.error.set(formatErrorDetail(error));
        this.pushFeed(
          `Tasks 列表失败${swarmName ? ` · ${swarmName}` : ''}`,
          'GET',
          `${this.baseUrl()}/tasks`,
          'error',
          { error: errorSummary(error) }
        );
      }
    }
  }

  async loadTools(): Promise<void> {
    try {
      const response = await this.apiService.listTools(this.baseUrl(), {});
      this.tools.set(response.tools.map((item) => this.mapToolCatalogItem(item)));
      this.toolsLoaded.set(true);
      this.pushFeed('Tools 列表', 'GET', `${this.baseUrl()}/tools`, 'info', response);
    } catch (error) {
      if (!this.shouldSuppressOfflineError(error)) {
        this.error.set(formatErrorDetail(error));
        this.pushFeed('Tools 列表失败', 'GET', `${this.baseUrl()}/tools`, 'error', { error: errorSummary(error) });
      }
    }
  }

  async loadSwarmStats(): Promise<void> {
    const swarmName = this.selectedSwarmName();
    if (!swarmName) {
      this.swarmStats.set(null);
      this.swarmStatsLoaded.set(false);
      return;
    }
    try {
      const response = await this.apiService.getSwarmStats(this.baseUrl(), swarmName);
      this.swarmStats.set(response);
      this.swarmStatsLoaded.set(true);
      this.pushFeed(`Swarm 统计 · ${swarmName}`, 'GET', `${this.baseUrl()}/swarms/${swarmName}/stats`, 'info', response);
    } catch (error) {
      if (!this.shouldSuppressOfflineError(error)) {
        this.error.set(formatErrorDetail(error));
        this.pushFeed(`Swarm 统计失败 · ${swarmName}`, 'GET', `${this.baseUrl()}/swarms/${swarmName}/stats`, 'error', { error: errorSummary(error) });
      }
    }
  }

  async loadEvents(
    query: Record<string, string | number | boolean | undefined | null> = {},
    options: { gracefulOffline?: boolean } = {}
  ): Promise<void> {
    try {
      const response = await this.apiService.listEvents(this.baseUrl(), query);
      this.events.set(response.items.map((item) => this.mapEventCatalogItem(item)));
      this.eventsResponse.set(response);
      this.eventsLoaded.set(true);
      this.pushFeed('事件列表', 'GET', `${this.baseUrl()}/events`, 'info', response);
    } catch (error) {
      if (!(options.gracefulOffline ?? this.refreshGraceful) || !this.isOfflineLikeError(error)) {
        this.error.set(formatErrorDetail(error));
        this.pushFeed('事件列表失败', 'GET', `${this.baseUrl()}/events`, 'error', { error: errorSummary(error) });
      }
    }
  }

  async loadLogs(
    query: Record<string, string | number | boolean | undefined | null> = {}
  ): Promise<void> {
    try {
      const response = await this.apiService.listLogs(this.baseUrl(), query);
      this.logs.set(response.items.map((item) => this.mapLogCatalogItem(item)));
      this.logsResponse.set(response);
      this.logsLoaded.set(true);
      this.pushFeed('日志列表', 'GET', `${this.baseUrl()}/logs`, 'info', response);
    } catch (error) {
      if (!this.shouldSuppressOfflineError(error)) {
        this.logsResponse.set(null);
        this.logsLoaded.set(false);
        this.error.set(formatErrorDetail(error));
        this.pushFeed('日志列表失败', 'GET', `${this.baseUrl()}/logs`, 'error', { error: errorSummary(error) });
      }
    }
  }

  async loadMetrics(): Promise<void> {
    try {
      const response = await this.apiService.getMetrics(this.baseUrl(), {
        window: this.metricsWindow(),
        resolution: this.metricsResolution(),
      });
      this.metrics.set(response);
      this.metricsLoaded.set(true);
      this.pushFeed('系统指标', 'GET', `${this.baseUrl()}/metrics`, 'info', response);
    } catch (error) {
      if (!this.shouldSuppressOfflineError(error)) {
        this.metricsLoaded.set(false);
        this.error.set(formatErrorDetail(error));
        this.pushFeed('系统指标失败', 'GET', `${this.baseUrl()}/metrics`, 'error', { error: errorSummary(error) });
      }
    }
  }

  async loadKnowledge(): Promise<void> {
    try {
      const response = await this.apiService.listKnowledge(this.baseUrl(), { page: 1, limit: 500 });
      this.knowledge.set(response.items.map((item) => this.mapKnowledgeCatalogItem(item)));
      this.knowledgeLoaded.set(true);
      this.pushFeed('知识库列表', 'GET', `${this.baseUrl()}/knowledge`, 'info', response);
    } catch (error) {
      if (!this.shouldSuppressOfflineError(error)) {
        this.knowledgeLoaded.set(false);
        this.error.set(formatErrorDetail(error));
        this.pushFeed('知识库列表失败', 'GET', `${this.baseUrl()}/knowledge`, 'error', { error: errorSummary(error) });
      }
    }
  }

  async loadMemory(): Promise<void> {
    try {
      const response = await this.apiService.listMemory(this.baseUrl(), { page: 1, limit: 500 });
      this.memories.set(response.items.map((item) => this.mapMemoryCatalogItem(item)));
      this.memoriesLoaded.set(true);
      this.pushFeed('记忆库列表', 'GET', `${this.baseUrl()}/memory`, 'info', response);
    } catch (error) {
      if (!this.shouldSuppressOfflineError(error)) {
        this.memoriesLoaded.set(false);
        this.error.set(formatErrorDetail(error));
        this.pushFeed('记忆库列表失败', 'GET', `${this.baseUrl()}/memory`, 'error', { error: errorSummary(error) });
      }
    }
  }

  async loadSwarmFromSource(source: string, replace = false): Promise<void> {
    const trimmed = source.trim();
    if (!trimmed) {
      this.error.set(makeUserError('加载 Swarm 前请输入来源路径或名称。'));
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    try {
      const response = await this.apiService.loadSwarm(this.baseUrl(), { source: trimmed, replace });
      this.pushFeed(`Swarm 加载 · ${response.swarm.swarm_name}`, 'POST', `${this.baseUrl()}/swarms/load`, 'success', response);
      this.selectedSwarmName.set(response.swarm.swarm_name);
      await this.loadOverview({ gracefulOffline: true });
    } catch (error) {
      if (!this.shouldSuppressOfflineError(error)) {
        this.error.set(formatErrorDetail(error));
        this.pushFeed(`Swarm 加载失败 · ${trimmed}`, 'POST', `${this.baseUrl()}/swarms/load`, 'error', { error: errorSummary(error) });
      }
    } finally {
      this.loading.set(false);
    }
  }

  async reloadCurrentSwarm(force = false): Promise<void> {
    const swarmName = this.selectedSwarmName();
    if (!swarmName) {
      this.error.set(makeUserError('重新加载前请选择一个 Swarm。'));
      return;
    }
    this.loadingDetails.set(true);
    this.error.set(null);
    try {
      const response = await this.apiService.reloadSwarm(this.baseUrl(), swarmName, { force });
      this.pushFeed(`Swarm 重载 · ${swarmName}`, 'POST', `${this.baseUrl()}/swarms/${encodeURIComponent(swarmName)}/reload`, 'success', response);
      await this.reloadSelectedSwarm({ clearError: false, gracefulOffline: true });
    } catch (error) {
      if (!this.shouldSuppressOfflineError(error)) {
        this.error.set(formatErrorDetail(error));
        this.pushFeed(`Swarm 重载失败 · ${swarmName}`, 'POST', `${this.baseUrl()}/swarms/${encodeURIComponent(swarmName)}/reload`, 'error', { error: errorSummary(error) });
      }
    } finally {
      this.loadingDetails.set(false);
    }
  }

  async unloadCurrentSwarm(force = false): Promise<void> {
    const swarmName = this.selectedSwarmName();
    if (!swarmName) {
      this.error.set(makeUserError('卸载前请选择一个 Swarm。'));
      return;
    }
    this.loadingDetails.set(true);
    this.error.set(null);
    try {
      const response = await this.apiService.unloadSwarm(this.baseUrl(), swarmName, force);
      this.pushFeed(`Swarm 卸载 · ${swarmName}`, 'DELETE', `${this.baseUrl()}/swarms/${encodeURIComponent(swarmName)}`, 'success', response);
      if (this.selectedSwarmName() === swarmName) {
        this.selectedSwarmName.set(null);
      }
      await this.loadOverview();
    } catch (error) {
      this.error.set(formatErrorDetail(error));
      this.pushFeed(`Swarm 卸载失败 · ${swarmName}`, 'DELETE', `${this.baseUrl()}/swarms/${encodeURIComponent(swarmName)}`, 'error', { error: errorSummary(error) });
    } finally {
      this.loadingDetails.set(false);
    }
  }

  async createKnowledgeEntry(payload: Record<string, unknown>): Promise<KnowledgeCatalogItem | null> {
    this.loadingDetails.set(true);
    this.error.set(null);
    try {
      const response = await this.apiService.createKnowledge(this.baseUrl(), payload);
      this.pushFeed(`知识创建 · ${response.knowledge.id}`, 'POST', `${this.baseUrl()}/knowledge`, 'success', response);
      await this.loadKnowledge();
      return response.knowledge;
    } catch (error) {
      this.error.set(formatErrorDetail(error));
      this.pushFeed('知识创建失败', 'POST', `${this.baseUrl()}/knowledge`, 'error', { error: errorSummary(error) });
      return null;
    } finally {
      this.loadingDetails.set(false);
    }
  }

  async updateKnowledgeEntry(knowledgeId: string, payload: Record<string, unknown>): Promise<KnowledgeCatalogItem | null> {
    this.loadingDetails.set(true);
    this.error.set(null);
    try {
      const response = await this.apiService.updateKnowledge(this.baseUrl(), knowledgeId, payload);
      this.pushFeed(`知识更新 · ${knowledgeId}`, 'PUT', `${this.baseUrl()}/knowledge/${knowledgeId}`, 'success', response);
      await this.loadKnowledge();
      return response.knowledge;
    } catch (error) {
      this.error.set(formatErrorDetail(error));
      this.pushFeed(`知识更新失败 · ${knowledgeId}`, 'PUT', `${this.baseUrl()}/knowledge/${knowledgeId}`, 'error', { error: errorSummary(error) });
      return null;
    } finally {
      this.loadingDetails.set(false);
    }
  }

  async deleteKnowledgeEntry(knowledgeId: string): Promise<boolean> {
    this.loadingDetails.set(true);
    this.error.set(null);
    try {
      const response = await this.apiService.deleteKnowledge(this.baseUrl(), knowledgeId);
      this.pushFeed(`知识删除 · ${knowledgeId}`, 'DELETE', `${this.baseUrl()}/knowledge/${knowledgeId}`, 'success', response);
      await this.loadKnowledge();
      return true;
    } catch (error) {
      this.error.set(formatErrorDetail(error));
      this.pushFeed(`知识删除失败 · ${knowledgeId}`, 'DELETE', `${this.baseUrl()}/knowledge/${knowledgeId}`, 'error', { error: errorSummary(error) });
      return false;
    } finally {
      this.loadingDetails.set(false);
    }
  }

  async createMemoryEntry(payload: Record<string, unknown>): Promise<MemoryItem | null> {
    this.loadingDetails.set(true);
    this.error.set(null);
    try {
      const response = await this.apiService.createMemory(this.baseUrl(), payload);
      this.pushFeed(`记忆创建 · ${response.memory.id}`, 'POST', `${this.baseUrl()}/memory`, 'success', response);
      await this.loadMemory();
      return this.mapMemoryCatalogItem(response.memory);
    } catch (error) {
      this.error.set(formatErrorDetail(error));
      this.pushFeed('记忆创建失败', 'POST', `${this.baseUrl()}/memory`, 'error', { error: errorSummary(error) });
      return null;
    } finally {
      this.loadingDetails.set(false);
    }
  }

  async deleteMemoryEntry(memoryId: string): Promise<boolean> {
    this.loadingDetails.set(true);
    this.error.set(null);
    try {
      const response = await this.apiService.deleteMemory(this.baseUrl(), memoryId);
      this.pushFeed(`记忆删除 · ${memoryId}`, 'DELETE', `${this.baseUrl()}/memory/${memoryId}`, 'success', response);
      await this.loadMemory();
      return true;
    } catch (error) {
      this.error.set(formatErrorDetail(error));
      this.pushFeed(`记忆删除失败 · ${memoryId}`, 'DELETE', `${this.baseUrl()}/memory/${memoryId}`, 'error', { error: errorSummary(error) });
      return false;
    } finally {
      this.loadingDetails.set(false);
    }
  }

  async startSwarmStructure(): Promise<void> {
    const swarmName = this.selectedSwarmName();
    if (!swarmName) { this.error.set(makeUserError('启动结构前请选择一个 Swarm。')); return; }
    const prompt = this.swarmExecutionPrompt().trim();
    if (!prompt) { this.error.set(makeUserError('执行目标不能为空。')); return; }
    this.loading.set(true); this.error.set(null);
    try {
      const response = await this.apiService.startSwarmBackground(this.baseUrl(), swarmName, {
        input: asJsonValue(this.buildSwarmExecutionInput()),
        rounds: this.swarmRounds(),
        meta_mode: this.metaMode(),
      });
      this.activeRun.set(response.run);
      this.pushFeed(`结构启动 · ${swarmName}`, 'POST', joinUrl(this.baseUrl(), `/swarms/${encodeURIComponent(swarmName)}/start/background`), 'success', response);
      this.watchRun(response.run);
    } catch (error) {
      this.error.set(formatErrorDetail(error));
      this.pushFeed(`结构启动失败 · ${swarmName}`, 'POST', joinUrl(this.baseUrl(), `/swarms/${encodeURIComponent(swarmName)}/start/background`), 'error', { error: errorSummary(error) });
    }
    finally { this.loading.set(false); }
  }

  async startSwarmBackground(): Promise<void> {
    await this.startSwarmStructure();
  }

  async runSwarmSync(): Promise<void> {
    await this.startSwarmStructure();
  }

  async startBackgroundRun(): Promise<void> {
    await this.startSwarmBackground();
  }

  async loadRunById(runId: string): Promise<void> {
    try {
      const response = await this.apiService.getRun(this.baseUrl(), runId);
      this.activeRun.set(response.run);
      const endpoint = this.resolveRunUrl(response.run, 'status');
      this.pushFeed(`运行快照 · ${runId}`, 'GET', endpoint, 'info', response);
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
      this.pushFeed(`Agent 调试 · ${agentId}`, 'POST', `${this.baseUrl()}/swarms/${swarmName}/agents/${agentId}/round`, 'success', response);
    } catch (error) { this.error.set(formatErrorDetail(error)); this.pushFeed(`Agent 调试失败 · ${agentId}`, 'POST', `${this.baseUrl()}/swarms/${swarmName}/agents/${agentId}/round`, 'error', { error: errorSummary(error) }); }
    finally { this.loading.set(false); }
  }

  selectedAgentId(): string | null {
    const chosen = this.selectedAgentIdChoice();
    const available = this.agentIdsFromSwarm(this.selectedSwarm());
    if (chosen && available.includes(chosen)) return chosen;
    return this.defaultAgentId();
  }

  agentChoices(): string[] {
    return this.agentIdsFromSwarm(this.selectedSwarm());
  }

  swarmExecutionTemplateLabel(): string {
    return SWARM_EXECUTION_PRESETS[this.swarmExecutionTemplate()].label;
  }

  private ensureAgentSelection(swarm: SwarmSummary | SwarmDetails): void {
    const available = this.agentIdsFromSwarm(swarm);
    const current = this.selectedAgentIdChoice();
    if (!current || !available.includes(current)) this.selectedAgentIdChoice.set(this.defaultAgentId(swarm));
  }

  private defaultAgentId(swarm: SwarmSummary | SwarmDetails | null = this.selectedSwarm()): string | null {
    const agentFiles = this.agentFilesFromSwarm(swarm);
    if (!agentFiles.length) return null;
    const preferred = agentFiles.find((file) => file.includes('planner'));
    return preferred ? this.stripAgentName(preferred) : this.stripAgentName(agentFiles[0]);
  }

  private agentFilesFromSwarm(swarm: SwarmSummary | SwarmDetails | null | undefined): string[] {
    return [...(swarm?.agent_files ?? [])];
  }

  private agentIdsFromSwarm(swarm: SwarmSummary | SwarmDetails | null | undefined): string[] {
    return this.agentFilesFromSwarm(swarm).map((file) => this.stripAgentName(file));
  }

  private stripAgentName(filePath: string): string {
    const normalized = filePath.replace(/\\/g, '/');
    const withoutExt = normalized.replace(/\.[^.]+$/, '');
    return withoutExt.split('/').pop() ?? filePath;
  }

  private buildSwarmExecutionInput(): Record<string, unknown> {
    return {
      template: this.swarmExecutionTemplate(),
      text: this.swarmExecutionPrompt().trim(),
      context: this.swarmExecutionContext().trim() || undefined,
      output_style: this.swarmExecutionOutputStyle(),
    };
  }

  private pushFeed(title: string, method: string, endpoint: string, tone: FeedItem['tone'], payload: unknown, meta?: string): void {
    const item: FeedItem = { id: this.nextFeedId(), title, endpoint, method, tone, timestamp: shortTime(), payload: normalizeJsonValue(payload), meta };
    this.responseFeed.set([item, ...this.responseFeed()].slice(0, 14));
  }

  private watchRun(run: RunSnapshot): void {
    this.closeStream();
    const sourceUrl = this.resolveRunUrl(run, 'events');
    this.streamState.set('connecting');
    this.streamNote.set(`正在监听 ${run.run_id}`);
    const source = new EventSource(sourceUrl);
    this.eventSource = source;
    source.onopen = () => { this.streamState.set('open'); this.streamNote.set(`实时事件流已开启: ${run.run_id}`); };
    source.onerror = () => {
      this.streamState.set('error');
      this.streamNote.set(`实时事件流已中断: ${run.run_id}`);
      if (this.autoReconnect()) {
        const delayMs = this.reconnectInterval() * 1000;
        this.streamNote.set(`${delayMs / 1000}秒后尝试重连...`);
        this.reconnectTimer = setTimeout(() => {
          if (this.activeRun()?.run_id === run.run_id) {
            this.watchRun(run);
          }
        }, delayMs);
      }
    };
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
    if (this.reconnectTimer) { clearTimeout(this.reconnectTimer); this.reconnectTimer = null; }
    this.streamState.set('closed');
  }

  private applyOfflineSnapshot(): void {
    this.health.set({ success: false, status: 'offline' });
    this.ready.set({ success: false, ready: false, reason: '离线' });
    this.streamNote.set('系统离线，已同步本地状态');
    this.closeStream();
  }

  private isOfflineLikeError(error: unknown): boolean {
    if (error instanceof HttpErrorResponse) {
      return error.status === 0 || error.status === 502 || error.status === 504;
    }
    const summary = errorSummary(error).toLowerCase();
    return summary.includes('econnrefused') || summary.includes('failed to fetch') || summary.includes('networkerror') || summary.includes('unknown error');
  }

  isTimeoutError(error: unknown): boolean {
    if (error instanceof HttpErrorResponse) {
      return error.status === 0 || error.status === 504;
    }
    const summary = errorSummary(error).toLowerCase();
    return summary.includes('timeout') || summary.includes('timed out');
  }

  private isTimeoutLike(payload: unknown): boolean {
    if (payload === null || payload === undefined) return false;
    if (typeof payload === 'string') {
      return payload.toLowerCase().includes('timeout') || payload.toLowerCase().includes('timed out') || payload.toLowerCase().includes('请求超时');
    }
    if (typeof payload === 'object') {
      const obj = payload as Record<string, unknown>;
      const errMsg = String(obj?.['error'] ?? obj?.['message'] ?? JSON.stringify(payload)).toLowerCase();
      return errMsg.includes('timeout') || errMsg.includes('timed out') || errMsg.includes('请求超时');
    }
    return false;
  }

  private shouldSuppressOfflineError(error: unknown): boolean {
    return this.refreshGraceful && this.isOfflineLikeError(error);
  }

  private runStatusLabel(status: string | null | undefined): string {
    switch (status) {
      case 'running':
        return '执行中';
      case 'completed':
        return '已完成';
      case 'failed':
        return '失败';
      case 'queued':
        return '排队中';
      default:
        return status || '未知';
    }
  }

  private resolveRunUrl(run: RunSnapshot, kind: 'status' | 'events'): string {
    const legacyPattern = /\/api\/runs\//;
    const rawUrl = kind === 'status' ? run.status_url : run.events_url;
    const canonicalPath = kind === 'status'
      ? `/swarms/runs/${encodeURIComponent(run.run_id)}`
      : `/swarms/runs/${encodeURIComponent(run.run_id)}/events`;
    const trimmedUrl = rawUrl?.trim();

    if (trimmedUrl && !legacyPattern.test(trimmedUrl)) {
      if (trimmedUrl.startsWith('http://') || trimmedUrl.startsWith('https://')) {
        return trimmedUrl;
      }
      if (trimmedUrl.startsWith('/api/')) {
        return trimmedUrl;
      }
      const normalizedBase = this.baseUrl().replace(/\/$/, '');
      return `${normalizedBase}${trimmedUrl.startsWith('/') ? trimmedUrl : `/${trimmedUrl}`}`;
    }

    return joinUrl(this.baseUrl(), canonicalPath);
  }

  feedPreview(item: FeedItem): string { return valuePreview(item.payload); }

  swarmOverview(): string {
    const swarm = this.selectedSwarm();
    return swarm ? `${swarm.agent_count} 智能体 · ${swarm.skill_count} 技能 · ${swarm.tool_count} 工具` : '未选择 Swarm';
  }

  graphSummary(): string {
    const graph = this.resolvedGraph();
    return graph ? `${graph.node_count} 节点 · ${graph.edge_count} 边` : '图未加载';
  }

  selectedRunHint(): string {
    const run = this.activeRun();
    if (!run) {
      return '无运行加载';
    }
    return `${this.runStatusLabel(run.status)} · ${run.event_count} 个事件`;
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
