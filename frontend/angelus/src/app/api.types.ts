export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export interface JsonObject {
  [key: string]: JsonValue;
}

export interface HealthResponse {
  success: boolean;
  status: string;
}

export interface RuntimeSwarmSummary {
  name: string;
  agent_count: number;
  tool_count: number;
}

export interface GraphResponseNode {
  id: string;
  name: string;
  type: string;
  metadata?: JsonValue;
}

export interface GraphResponseEdge {
  source: string;
  target: string;
  label?: string | null;
}

export interface GraphResponse {
  name: string;
  nodes: GraphResponseNode[];
  edges: GraphResponseEdge[];
}

export interface HistoryEntry {
  timestamp: string;
  input: JsonValue;
  output: JsonValue;
  trace?: JsonValue | null;
}

export interface HistoryResponse {
  history: HistoryEntry[];
}

export interface RunStreamEvent {
  event: 'start' | 'run.started' | 'node.started' | 'node.completed' | 'node.failed' | 'branch.started' | 'run.snapshot' | 'run.completed' | 'run.failed' | 'result' | 'stopped' | 'error' | 'done';
  data: JsonValue;
}

export interface ApiIndexResponse {
  success: boolean;
  service: string;
  swarm_count: number;
  load_error: string | null;
  api_root: string;
}

export interface ReadyInvalidSwarm {
  swarm: string;
  errors: string[];
}

export interface ReadyResponse {
  success: boolean;
  ready: boolean;
  swarm_count?: number;
  reason?: string;
  load_error?: string;
  invalid_swarms?: ReadyInvalidSwarm[];
}

export interface SwarmSummary {
  swarm_name: string;
  package_path: string;
  manifest_path: string;
  graph_file: string;
  agent_count: number;
  skill_count: number;
  tool_count: number;
  api_count: number;
  graph_attached: boolean;
  graph_valid: boolean;
  graph_errors: string[];
  graph_warnings: string[];
  active_run_count?: number;
  active_run_ids?: string[];
  agent_files?: string[];
  graph?: GraphSnapshot | null;
}

export interface SwarmDetails extends SwarmSummary {
  agent_files: string[];
  graph?: GraphSnapshot | null;
}

export interface SwarmApiCatalogItem {
  name: string;
  origin: 'native' | 'package' | string;
  source: string | null;
  type: string;
}

export interface SwarmListResponse {
  success: boolean;
  swarms: SwarmSummary[];
}

export interface SwarmDetailResponse {
  success: boolean;
  swarm: SwarmDetails;
}

export interface GraphNodeSnapshot {
  node_id: number;
  node_name: string;
  node_type: string;
  next_node_ids: number[];
  metadata: JsonValue;
  agent_id?: string;
  additional_prompt?: string | null;
  tool_name?: string;
  input_mapping?: JsonValue;
}

export interface GraphEdgeSnapshot {
  from_node_id: number;
  to_node_id: number;
  label: string | null;
  condition: string | null;
  priority: number;
}

export interface GraphChangeSummary {
  change_id: string;
  kind: string;
  subject: {
    type: string;
    id: string | number | null;
  };
  summary: string;
}

export interface GraphSnapshot {
  graph_name: string;
  graph_kind?: 'agent' | 'execution' | string;
  entry_node_id: number | null;
  exit_node_id: number | null;
  node_count: number;
  edge_count: number;
  nodes: GraphNodeSnapshot[];
  edges: GraphEdgeSnapshot[];
  revision?: number;
  hash?: string;
  updated_at?: string;
  last_change?: GraphChangeSummary | null;
}

export interface GraphStateSnapshot {
  graph_name: string | null;
  graph_kind?: 'agent' | 'execution' | string;
  entry_node_id: number | null;
  exit_node_id: number | null;
  node_count: number;
  edge_count: number;
  nodes: GraphNodeSnapshot[];
  edges: GraphEdgeSnapshot[];
  revision: number;
  hash: string;
  updated_at: string;
  last_change: GraphChangeSummary | null;
}

export interface GraphPatchOp {
  op: 'upsert_node' | 'remove_node' | 'add_edge' | 'remove_edge' | 'update_graph_meta';
  node?: GraphNodeSnapshot;
  node_id?: number;
  edge?: GraphEdgeSnapshot;
  from_node_id?: number;
  to_node_id?: number;
  label?: string | null;
  condition?: string | null;
  priority?: number;
  entry_node_id?: number | null;
  exit_node_id?: number | null;
}

export interface GraphPatch {
  base_revision: number;
  current_revision: number;
  graph_id: string | null;
  is_gap_free: boolean;
  operations: GraphPatchOp[];
  last_change: GraphChangeSummary | null;
}

export interface GraphStateResponse {
  success: boolean;
  swarm: string;
  graph: GraphStateSnapshot;
  has_changes_since: boolean;
}

export interface GraphDiffResponse {
  success: boolean;
  swarm: string;
  patch: GraphPatch;
}

export interface GraphEventsResponse {
  success: boolean;
  swarm: string;
  graph: GraphStateSnapshot;
  has_changes_since: boolean;
}

export interface ThinkingGraphNodeSnapshot {
  id: number;
  created_by: string;
  description: string;
  node_type: string;
  info: string;
  tags: string[];
  confidence: number;
  payload: JsonObject;
}

export interface ThinkingGraphEdgeSnapshot {
  id: number;
  created_by: string;
  description: string;
  edge_type: string;
  source_id: number;
  target_id: number;
  strength: number;
}

export interface ThinkingGraphTransactionRecord {
  transaction_id: number;
  operation: string;
  object_kind: string;
  object_id: number;
  before: JsonValue | null;
  after: JsonValue | null;
  version_before: number;
  version_after: number;
  created_by: string;
  timestamp: string;
  metadata: JsonObject;
}

export interface ThinkingGraphSnapshot {
  format: 'thinking-graph/config' | string;
  schema_version: string;
  version: number;
  next_object_id: number;
  transaction_id: number;
  nodes: Record<string, ThinkingGraphNodeSnapshot>;
  edges: Record<string, ThinkingGraphEdgeSnapshot>;
  transaction_log: ThinkingGraphTransactionRecord[];
  node_count: number;
  edge_count: number;
  transaction_count: number;
  last_transaction_id: number | null;
}

export interface ThoughtGraphResponse {
  success: boolean;
  swarm: string;
  thinking_graph: ThinkingGraphSnapshot;
}

export type ThoughtGraphNodeSnapshot = ThinkingGraphNodeSnapshot;
export type ThoughtGraphEdgeSnapshot = ThinkingGraphEdgeSnapshot;
export type ThoughtGraphSnapshot = ThinkingGraphSnapshot;

export interface ExecutionTraceResponse {
  success: boolean;
  swarm: string;
  run: RunSnapshot | null;
  events: JsonValue[];
}

export interface RunSwarmRequest {
  input: JsonValue | JsonObject;
  rounds?: number;
  meta_mode?: boolean;
}

export interface RunSwarmResponse {
  success: boolean;
  swarm: string;
  rounds: number;
  output: JsonValue;
  trace: JsonValue;
  metadata: JsonValue;
}

export interface RunStartResponse {
  success: boolean;
  status: string;
  swarm: string;
  run: RunSnapshot;
}

export interface RunStopResponse {
  success: boolean;
  run_id: string;
  stop_type: string;
  status: string;
}

export interface RunSnapshot {
  success: boolean;
  run_id: string;
  swarm: string;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  rounds: number;
  current_node_id: number | null;
  current_node_name: string | null;
  current_node_type: string | null;
  state: JsonValue;
  final_state: JsonValue;
  error: string | null;
  event_count: number;
  events_url: string;
  status_url: string;
}

export interface AgentRoundRequest {
  message: string;
  rounds?: number;
  additional_prompt?: string | null;
}

export interface AgentRoundResponse {
  success: boolean;
  swarm: string;
  agent_id: string;
  result: JsonValue;
  context: JsonValue;
}

export interface ApiSettings {
  base_url: string;
  timeout_seconds: number;
  sse_reconnect_interval_seconds: number;
  auto_reconnect: boolean;
  require_auth?: boolean;
  api_token?: string | null;
  api_token_env?: string;
  api_token_set?: boolean;
  cors_allowed_origins?: string[];
}

export interface SettingsResponse {
  success: boolean;
  settings: {
    api: ApiSettings;
  };
}

export interface UpdateSettingsRequest {
  api: ApiSettings;
}

export interface AgentCatalogItem {
  id: string;
  name: string;
  status: 'online' | 'offline' | 'running' | 'error';
  type: 'coordinator' | 'worker' | 'specialist' | 'reviewer' | string;
  capabilities: string[];
  tags: string[];
  tasks_executed: number;
  success_rate: number;
  avg_response_time_ms: number;
  token_usage_total: number;
  last_activity: string;
}

export interface AgentCatalogStats {
  total: number;
  active: number;
  success_rate: number;
  avg_response_time_ms: number;
  token_usage_total: number;
}

export interface AgentListResponse {
  success: boolean;
  swarm: string;
  total: number;
  agents: AgentCatalogItem[];
  stats: AgentCatalogStats;
}

export interface TaskCatalogLogItem {
  time: string | null;
  level: 'info' | 'warn' | 'error' | 'success';
  message: string;
}

export interface TaskCatalogItem {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled';
  priority: 'low' | 'medium' | 'high' | 'urgent';
  executor: string;
  duration_ms: number;
  created_at: string;
  description: string;
  input: JsonValue;
  output: JsonValue;
  logs: TaskCatalogLogItem[];
  swarm: string;
  dependencies?: string[];
  next_tasks?: string[];
  failed_count?: number;
  completed_count?: number;
  executed_count?: number;
}

export interface TaskCatalogStats {
  pending: number;
  running: number;
  success: number;
  failed: number;
  avg_duration_ms: number;
}

export interface TaskListResponse {
  success: boolean;
  total: number;
  page: number;
  limit: number;
  items: TaskCatalogItem[];
  stats: TaskCatalogStats;
}

export interface ToolCatalogItem {
  id: string;
  name: string;
  swarm: string;
  type: 'API' | '本地' | string;
  status: 'online' | 'offline' | 'error' | string;
  description: string;
  calls: number;
  avg_ms: number;
  last_call: string;
  success_rate: number;
  error_rate: number;
  created_at: string;
  schema: JsonValue;
}

export interface ToolCatalogStats {
  total: number;
  available: number;
  api: number;
  local: number;
  today_calls: number;
}

export interface ToolListResponse {
  success: boolean;
  tools: ToolCatalogItem[];
  stats: ToolCatalogStats;
}

export interface KnowledgeCatalogItem {
  id: string;
  title: string;
  type: 'document' | 'vector' | 'rule' | 'snippet' | string;
  source: string;
  tags: string[];
  status: 'active' | 'draft' | 'archived' | string;
  citations: number;
  created_at: string;
  content: string;
  meta: {
    author: string;
    version: string;
    updated_at: string;
    size: string;
  };
  related: string[];
}

export interface KnowledgeCatalogStats {
  total: number;
  documents: number;
  vectors: number;
  rules: number;
}

export interface KnowledgeListResponse {
  success: boolean;
  total: number;
  page: number;
  limit: number;
  items: KnowledgeCatalogItem[];
  stats: KnowledgeCatalogStats;
}

export interface MemoryCatalogItem {
  id: string;
  summary: string;
  content: string;
  timestamp: string;
  type: 'episodic' | 'semantic' | 'procedural' | 'working' | string;
  source: string;
  sentiment: number;
  importance: number;
  related_ids: string[];
}

export interface MemoryCatalogStats {
  total: number;
  active: number;
  avg_importance: number;
  long_term: number;
  working: number;
}

export interface MemoryListResponse {
  success: boolean;
  total: number;
  page: number;
  limit: number;
  items: MemoryCatalogItem[];
  stats: MemoryCatalogStats;
}

export interface SwarmStatsResponse {
  success: boolean;
  success_rate: number;
  throughput: number;
  token_usage: number;
  task_distribution: {
    pending: number;
    running: number;
    completed: number;
    failed: number;
    avg_duration_ms: number;
  };
  resource_usage: {
    cpu_percent: number[];
    memory_mb: number[];
  };
  run_count: number;
  active_runs: number;
  agent_count: number;
  tool_count: number;
  api_count: number;
  native_api_count: number;
  package_api_count: number;
}

export interface SwarmApisResponse {
  success: boolean;
  swarm: string;
  apis: SwarmApiCatalogItem[];
}

export interface MetricsResponse {
  success: boolean;
  window: string;
  resolution: string;
  series: {
    cpu_percent: number[];
    memory_mb: number[];
    request_latency_ms: number[];
    throughput_rps: number[];
    token_usage: number[];
    error_rate: number[];
  };
}

export interface LogCatalogItem {
  id: string;
  time: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG';
  service: string;
  message: string;
  raw?: Record<string, any>;
}

export interface LogCatalogStats {
  error: number;
  warn: number;
  info: number;
  debug: number;
}

export interface LogListResponse {
  success: boolean;
  total: number;
  page: number;
  limit: number;
  items: LogCatalogItem[];
  stats: LogCatalogStats;
}
