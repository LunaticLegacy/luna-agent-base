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

