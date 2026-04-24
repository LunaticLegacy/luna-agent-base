import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-drawer',
  standalone: true,
  imports: [CommonModule],
  template: `
    @if (open) {
      <div class="drawer-overlay" (click)="onOverlayClick()">
        <div class="drawer" [class.fixed]="variant === 'fixed'" (click)="$event.stopPropagation()">
          <div class="drawer-header">
            <div>
              <h3>{{ title }}</h3>
              @if (subtitle) {
                <p class="drawer-subtitle">{{ subtitle }}</p>
              }
            </div>
            <button class="drawer-close" (click)="close.emit()">×</button>
          </div>
          <div class="drawer-body">
            <ng-content></ng-content>
          </div>
        </div>
      </div>
    }
  `,
  styles: [`
    .drawer-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,.45);
      z-index: 200;
      display: flex;
      justify-content: flex-end;
    }
    .drawer {
      background: #131827;
      border-left: 1px solid rgba(148,163,184,.08);
      width: 480px;
      max-width: 90vw;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .drawer-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      padding: 16px 20px;
      border-bottom: 1px solid rgba(148,163,184,.08);
    }
    .drawer-header h3 {
      margin: 0;
      font-size: 15px;
      font-weight: 600;
      color: #f8fafc;
    }
    .drawer-subtitle {
      margin: 4px 0 0;
      font-size: 12px;
      color: #64748B;
    }
    .drawer-close {
      background: transparent;
      border: none;
      color: #94A3B8;
      font-size: 22px;
      cursor: pointer;
      line-height: 1;
      padding: 0;
      width: 28px;
      height: 28px;
      display: grid;
      place-items: center;
      border-radius: 6px;
    }
    .drawer-close:hover {
      background: rgba(255,255,255,.06);
      color: #F1F5F9;
    }
    .drawer-body {
      flex: 1;
      overflow-y: auto;
      padding: 16px 20px;
    }
  `]
})
export class DrawerComponent {
  @Input({ required: true }) open = false;
  @Input({ required: true }) title = '';
  @Input() subtitle?: string;
  @Input() variant: 'fixed' | 'inline' = 'fixed';
  @Input() closeOnOverlay = true;

  @Output() close = new EventEmitter<void>();

  onOverlayClick(): void {
    if (this.closeOnOverlay) {
      this.close.emit();
    }
  }
}
