import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-modal',
  standalone: true,
  imports: [CommonModule],
  template: `
    @if (open) {
      <div class="modal-overlay" (click)="onOverlayClick()">
        <div class="modal modal--{{ size }}" (click)="$event.stopPropagation()">
          <div class="modal-header">
            <div>
              <h3>{{ title }}</h3>
              @if (subtitle) {
                <p class="modal-subtitle">{{ subtitle }}</p>
              }
            </div>
            <button class="modal-close" (click)="close.emit()">×</button>
          </div>
          <div class="modal-body">
            <ng-content></ng-content>
          </div>
          @if (hasFooter) {
            <div class="modal-footer">
              <ng-content select="[footer]"></ng-content>
            </div>
          }
        </div>
      </div>
    }
  `,
  styles: [`
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,.5);
      z-index: 300;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .modal {
      background: #131827;
      border: 1px solid rgba(148,163,184,.1);
      border-radius: 14px;
      width: 100%;
      max-width: 600px;
      max-height: 90vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .modal--wide { max-width: 1200px; }
    .modal--full { max-width: 95vw; max-height: 95vh; }
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      padding: 16px 20px;
      border-bottom: 1px solid rgba(148,163,184,.08);
    }
    .modal-header h3 {
      margin: 0;
      font-size: 15px;
      font-weight: 600;
      color: #f8fafc;
    }
    .modal-subtitle {
      margin: 4px 0 0;
      font-size: 12px;
      color: #64748B;
    }
    .modal-close {
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
    .modal-close:hover {
      background: rgba(255,255,255,.06);
      color: #F1F5F9;
    }
    .modal-body {
      flex: 1;
      overflow-y: auto;
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
      min-height: 0;
    }
    .modal-footer {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      padding: 12px 20px;
      border-top: 1px solid rgba(148,163,184,.08);
    }
  `]
})
export class ModalComponent {
  @Input({ required: true }) open = false;
  @Input({ required: true }) title = '';
  @Input() subtitle?: string;
  @Input() hasFooter = false;
  @Input() closeOnOverlay = true;
  @Input() size: 'normal' | 'wide' | 'full' = 'normal';

  @Output() close = new EventEmitter<void>();

  onOverlayClick(): void {
    if (this.closeOnOverlay) {
      this.close.emit();
    }
  }
}
