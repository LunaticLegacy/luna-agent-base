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
