import type { JsonValue } from './api.types';

export type JsonKind = 'null' | 'array' | 'object' | 'string' | 'number' | 'boolean';

export function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function normalizeJsonValue(value: unknown, depth = 0, maxDepth = 5): unknown {
  if (depth > maxDepth) {
    return value;
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (trimmed.startsWith('{') || trimmed.startsWith('[') || trimmed.startsWith('"')) {
      try {
        return normalizeJsonValue(JSON.parse(trimmed), depth + 1, maxDepth);
      } catch {
        return value;
      }
    }
    return value;
  }

  if (Array.isArray(value)) {
    return value.map((item) => normalizeJsonValue(item, depth + 1, maxDepth));
  }

  if (isPlainObject(value)) {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, normalizeJsonValue(item, depth + 1, maxDepth)])
    );
  }

  return value;
}

export function jsonKind(value: unknown): JsonKind {
  if (value === null) {
    return 'null';
  }
  if (Array.isArray(value)) {
    return 'array';
  }
  switch (typeof value) {
    case 'string':
      return 'string';
    case 'number':
      return 'number';
    case 'boolean':
      return 'boolean';
    default:
      return 'object';
  }
}

export function summarizeJsonValue(value: unknown): string {
  if (value === null) {
    return 'null';
  }
  if (Array.isArray(value)) {
    return `${value.length} item${value.length === 1 ? '' : 's'}`;
  }
  if (isPlainObject(value)) {
    const keys = Object.keys(value);
    return `${keys.length} key${keys.length === 1 ? '' : 's'}`;
  }
  if (typeof value === 'string') {
    const collapsed = value.replace(/\s+/g, ' ').trim();
    if (collapsed.length <= 96) {
      return `"${collapsed}"`;
    }
    return `"${collapsed.slice(0, 93)}..."`;
  }
  return String(value);
}

export function formatPrimitive(value: unknown): string {
  if (value === null) {
    return 'null';
  }
  if (typeof value === 'string') {
    return JSON.stringify(value);
  }
  return String(value);
}

export function valuePreview(value: unknown): string {
  const normalized = normalizeJsonValue(value);
  const kind = jsonKind(normalized);
  if (kind === 'array' || kind === 'object') {
    return summarizeJsonValue(normalized);
  }
  return formatPrimitive(normalized);
}

export function asJsonValue(value: unknown): JsonValue {
  return normalizeJsonValue(value) as JsonValue;
}

