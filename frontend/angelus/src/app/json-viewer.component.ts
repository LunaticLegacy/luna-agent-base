import { ChangeDetectionStrategy, Component, Input, forwardRef } from '@angular/core';
import { formatPrimitive, isPlainObject, jsonKind, normalizeJsonValue, summarizeJsonValue } from './json-utils';

interface JsonEntry {
  key: string;
  value: unknown;
}

@Component({
  selector: 'app-json-viewer',
  standalone: true,
  template: `
    <section class="json-node" [style.--depth]="depth">
      @if (label) {
        <div class="json-label">{{ label }}</div>
      }

      @if (isComplex()) {
        <details class="json-details" [open]="depth < 1">
          <summary class="json-summary">
            <span class="json-kind">{{ currentKind() }}</span>
            <span class="json-summary-text">{{ summaryText() }}</span>
          </summary>

          <div class="json-children">
            @if (isArray()) {
              @for (item of arrayValue(); track $index) {
                <app-json-viewer [label]="'[' + $index + ']'" [value]="item" [depth]="depth + 1" />
              }
            } @else {
              @for (entry of objectEntries(); track entry.key) {
                <app-json-viewer [label]="entry.key" [value]="entry.value" [depth]="depth + 1" />
              }
            }
          </div>
        </details>
      } @else {
        <div class="json-leaf">
          <span class="json-kind">{{ currentKind() }}</span>
          <span class="json-primitive">{{ primitiveText() }}</span>
        </div>
      }
    </section>
  `,
  styleUrl: './json-viewer.component.sass',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [forwardRef(() => JsonViewerComponent)],
})
export class JsonViewerComponent {
  @Input() label: string | null = null;
  @Input() depth = 0;

  private _value: unknown = null;

  @Input()
  set value(value: unknown) {
    this._value = normalizeJsonValue(value);
  }

  get value(): unknown {
    return this._value;
  }

  currentKind(): string {
    return jsonKind(this._value);
  }

  isArray(): boolean {
    return Array.isArray(this._value);
  }

  isComplex(): boolean {
    return Array.isArray(this._value) || isPlainObject(this._value);
  }

  objectEntries(): JsonEntry[] {
    if (!isPlainObject(this._value)) {
      return [];
    }
    return Object.entries(this._value).map(([key, value]) => ({ key, value }));
  }

  arrayValue(): unknown[] {
    return Array.isArray(this._value) ? this._value : [];
  }

  summaryText(): string {
    return summarizeJsonValue(this._value);
  }

  primitiveText(): string {
    return formatPrimitive(this._value);
  }
}
