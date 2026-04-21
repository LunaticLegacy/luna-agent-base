import { TestBed } from '@angular/core/testing';
import { App } from './app';
import { ApiService } from './api.service';
import {
  ApiIndexResponse,
  HealthResponse,
  ReadyResponse,
  GraphSnapshot,
  SwarmDetailResponse,
  SwarmListResponse,
} from './api.types';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        {
          provide: ApiService,
          useValue: {
            index: async (): Promise<ApiIndexResponse> => ({
              success: true,
              service: 'angelus',
              swarm_count: 1,
              api_root: '/api',
            }),
            health: async (): Promise<HealthResponse> => ({ success: true, status: 'ok' }),
            ready: async (): Promise<ReadyResponse> => ({ success: true, ready: true, swarm_count: 1 }),
            listSwarms: async (): Promise<SwarmListResponse> => ({
              success: true,
              swarms: [
                {
                  swarm_name: 'demo',
                  package_path: '/demo',
                  manifest_path: '/demo/swarm.toml',
                  graph_file: 'graph.py',
                  agent_count: 1,
                  skill_count: 1,
                  tool_count: 1,
                  graph_attached: true,
                  graph_valid: true,
                  graph_errors: [],
                  graph_warnings: [],
                },
              ],
            }),
            getSwarm: async (): Promise<SwarmDetailResponse> => ({
              success: true,
              swarm: {
                swarm_name: 'demo',
                package_path: '/demo',
                manifest_path: '/demo/swarm.toml',
                graph_file: 'graph.py',
                agent_files: ['agents/planner.py'],
                agent_count: 1,
                skill_count: 1,
                tool_count: 1,
                graph_attached: true,
                graph_valid: true,
                graph_errors: [],
                graph_warnings: [],
              },
            }),
            getSwarmGraph: async () => ({
              success: true,
              swarm: 'demo',
              graph: {
                graph_name: 'demo',
                entry_node_id: 1,
                exit_node_id: 1,
                node_count: 1,
                edge_count: 0,
                nodes: [
                  {
                    node_id: 1,
                    node_name: 'planner',
                    node_type: 'AgentNode',
                    next_node_ids: [],
                    metadata: {},
                    agent_id: 'planner',
                  },
                ],
                edges: [],
              } satisfies GraphSnapshot,
            }),
            startSwarmRun: async () => ({
              success: true,
              status: 'started',
              swarm: 'demo',
              run: {
                success: false,
                run_id: 'run-1',
                swarm: 'demo',
                status: 'queued',
                created_at: new Date().toISOString(),
                started_at: null,
                finished_at: null,
                rounds: 0,
                current_node_id: null,
                current_node_name: null,
                current_node_type: null,
                state: {},
                final_state: {},
                error: null,
                event_count: 0,
                events_url: '/api/runs/run-1/events',
                status_url: '/api/runs/run-1',
              },
            }),
            getRun: async () => ({
              success: true,
              run: {
                success: false,
                run_id: 'run-1',
                swarm: 'demo',
                status: 'running',
                created_at: new Date().toISOString(),
                started_at: null,
                finished_at: null,
                rounds: 0,
                current_node_id: 1,
                current_node_name: 'planner',
                current_node_type: 'AgentNode',
                state: {},
                final_state: {},
                error: null,
                event_count: 0,
                events_url: '/api/runs/run-1/events',
                status_url: '/api/runs/run-1',
              },
            }),
            streamRunEvents: () => {
              throw new Error('streamRunEvents should not be called in unit tests');
            },
            runSwarm: async () => ({
              success: true,
              swarm: 'demo',
              rounds: 0,
              output: {},
              trace: [],
              metadata: {},
            }),
            runAgentRound: async () => ({
              success: true,
              swarm: 'demo',
              agent_id: 'planner',
              result: {},
              context: {},
            }),
          },
        },
      ],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('should render title', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('Angelus 编队控制台');
  });
});
