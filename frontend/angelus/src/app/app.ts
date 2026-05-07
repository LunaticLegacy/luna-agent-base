import { Component, DestroyRef, inject, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { StateService } from './services/state.service';
import { SidebarComponent } from './shared/sidebar.component';
import { TopbarComponent } from './shared/topbar.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, SidebarComponent, TopbarComponent],
  templateUrl: './app.html',
  styleUrl: './app.sass'
})
export class AppComponent {
  readonly state = inject(StateService);
  private readonly destroyRef = inject(DestroyRef);

  constructor() {
    this.state.init(this.destroyRef);
  }

  readonly pageTitle = computed(() => {
    const path = typeof window !== 'undefined' ? window.location.pathname : '/';
    const map: Record<string, string> = {
      '/': '概览',
      '/swarm': 'Swarm 管理',
      '/agents': '智能体',
      '/tasks': '后台任务',
      '/knowledge': '知识库',
      '/tools': '工具管理',
      '/memory': '记忆系统',
      '/logs': '系统日志',
      '/settings': '系统设置',
    };
    return map[path] || '概览';
  });
}
