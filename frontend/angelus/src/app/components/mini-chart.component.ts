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
    return this.data.length > 0 ? this.data : [30, 45, 35, 50, 40, 55, 45, 60, 50, 45];
  });

  private normalizedPoints = computed(() => {
    const values = this.defaultData().map((value) => (Number.isFinite(value) ? Number(value) : 0));
    const max = Math.max(...values, 1);
    if (values.length === 1) {
      const y = 30 - (values[0] / max) * 28 - 1;
      return [`0,${y}`, `100,${y}`];
    }
    return values.map((value, index) => {
      const x = (index / (values.length - 1)) * 100;
      const y = 30 - (value / max) * 28 - 1;
      return `${x},${y}`;
    });
  });

  linePoints = computed(() => {
    return this.normalizedPoints().join(' ');
  });

  areaPoints = computed(() => {
    const points = this.normalizedPoints().join(' ');
    return `0,30 ${points} 100,30`;
  });
}
