export interface HealthResponse {
  success: boolean;
  status: string;
}

export interface ApiIndexResponse {
  success: boolean;
  service: string;
  swarm_count: number;
  load_error?: string | null;
  api_root?: string;
}

export interface ReadyResponse {
  success: boolean;
  ready: boolean;
  swarm_count?: number;
  reason?: string;
  invalid_swarms?: Array<{ swarm: string; errors: string[] }>;
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
}

export interface SwarmListResponse {
  success: boolean;
  swarms: SwarmSummary[];
}

export interface SwarmDetailResponse {
  success: boolean;
  swarm: SwarmDetails;
}

export interface RunSwarmRequest {
  input: unknown;
  rounds?: number;
}

export interface RunSwarmResponse {
  success: boolean;
  swarm: string;
  rounds: number;
  output: unknown;
  trace: unknown[];
  metadata: Record<string, unknown>;
}

export interface AgentRoundRequest {
  message: string;
  rounds?: number;
  additional_prompt?: string;
}

export interface AgentRoundResponse {
  success: boolean;
  swarm: string;
  agent_id: string;
  result: unknown;
  context: unknown;
}
