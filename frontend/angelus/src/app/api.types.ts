export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export interface JsonObject {
  [key: string]: JsonValue;
}

export interface HealthResponse {
  success: boolean;
  status: string;
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

export interface GraphSnapshot {
  graph_name: string;
  entry_node_id: number | null;
  exit_node_id: number | null;
  node_count: number;
  edge_count: number;
  nodes: GraphNodeSnapshot[];
  edges: GraphEdgeSnapshot[];
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

export interface EventCatalogItem {
  id: string;
  time: string;
  level: 'info' | 'warn' | 'error';
  source: string;
  event: string;
  detail: string;
  data: JsonValue;
}

export interface EventCatalogStats {
  today: number;
  errors: number;
  warnings: number;
  infos: number;
}

export interface EventListResponse {
  success: boolean;
  total: number;
  page: number;
  limit: number;
  items: EventCatalogItem[];
  stats: EventCatalogStats;
}

export interface LogCatalogItem {
  id: string;
  time: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG';
  service: string;
  message: string;
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
