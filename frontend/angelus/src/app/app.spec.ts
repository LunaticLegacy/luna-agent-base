import { TestBed } from '@angular/core/testing';
import { App } from './app';
import { ApiService } from './api.service';
import {
  ApiIndexResponse,
  HealthResponse,
  ReadyResponse,
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
    expect(compiled.querySelector('h1')?.textContent).toContain('Angelus Swarm Console');
  });
});
