import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', loadComponent: () => import('./pages/overview.page').then(m => m.OverviewPageComponent) },
  { path: 'swarm', loadComponent: () => import('./pages/swarm-management.page').then(m => m.SwarmManagementPageComponent) },
  { path: 'agents', loadComponent: () => import('./pages/agents.page').then(m => m.AgentsPageComponent) },
  { path: 'tasks', loadComponent: () => import('./pages/tasks.page').then(m => m.TasksPageComponent) },
  { path: 'knowledge', loadComponent: () => import('./pages/knowledge.page').then(m => m.KnowledgePageComponent) },
  { path: 'tools', loadComponent: () => import('./pages/tools.page').then(m => m.ToolsPage) },
  { path: 'memory', loadComponent: () => import('./pages/memory.page').then(m => m.MemoryPageComponent) },
  { path: 'logs', loadComponent: () => import('./pages/logs.page').then(m => m.LogsPage) },
  { path: 'settings', loadComponent: () => import('./pages/settings.page').then(m => m.SettingsPage) },
];
