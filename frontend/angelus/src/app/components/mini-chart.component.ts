import { Component, Input, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-mini-chart',
  standalone: true,
  imports: [CommonModule],
  template: `
    <svg [attr.viewBox]="'0 0 100 30'" preserveAspectRatio="none" class="chart">
      <polygon [attr.points]="areaPoints()" [attr.fill]="color" opacity="0.15" />
      <polyline [attr.points]="linePoints()" [attr.stroke]="color" fill="none" stroke-width="1.5" />
    </svg>
  `,
  styles: [`
    .chart { width:100%; height:40px; }
  `]
})
export class MiniChartComponent {
  @Input() color = '#8B5CF6';
  @Input() data: number[] = [];

  private defaultData = computed(() => {
    const base = this.data.length > 0 ? this.data : [30,45,35,50,40,55,45,60,50,45];
    return base;
  });

  linePoints = computed(() => {
    const d = this.defaultData();
    const max = Math.max(...d, 1);
    return d.map((v, i) => {
      const x = (i / (d.length - 1)) * 100;
      const y = 30 - (v / max) * 28 - 1;
      return `${x},${y}`;
    }).join(' ');
  });

  areaPoints = computed(() => {
    const d = this.defaultData();
    const max = Math.max(...d, 1);
    let pts = d.map((v, i) => {
      const x = (i / (d.length - 1)) * 100;
      const y = 30 - (v / max) * 28 - 1;
      return `${x},${y}`;
    }).join(' ');
    return `0,30 ${pts} 100,30`;
  });
}
