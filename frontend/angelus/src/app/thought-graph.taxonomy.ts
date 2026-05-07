export interface ThoughtNodeLegendEntry {
  key: string;
  label: string;
  detail: string;
  color: string;
}

export interface ThoughtRelationLegendEntry {
  key: string;
  label: string;
  detail: string;
  color: string;
  dash?: string | null;
}

export interface ThoughtRelationStyle {
  stroke: string;
  glow: string;
  dash: string | null;
}

export const THOUGHT_NODE_LEGEND_ENTRIES: ThoughtNodeLegendEntry[] = [
  { key: 'goal', label: '目标', detail: 'Hexagon', color: '#ddd6fe' },
  { key: 'question', label: '问题', detail: 'Hexagon', color: '#f472b6' },
  { key: 'claim', label: '主张', detail: 'Rect', color: '#93c5fd' },
  { key: 'hypothesis', label: '假说', detail: 'Diamond', color: '#fde68a' },
  { key: 'evidence', label: '证据', detail: 'Circle', color: '#6ee7b7' },
  { key: 'assumption', label: '假设', detail: 'Hexagon', color: '#cbd5e1' },
  { key: 'plan', label: '计划', detail: 'Rect', color: '#a78bfa' },
  { key: 'step', label: '步骤', detail: 'Rect', color: '#c084fc' },
  { key: 'action', label: '行动', detail: 'Rect', color: '#5eead4' },
  { key: 'observation', label: '观察', detail: 'Circle', color: '#67e8f9' },
  { key: 'critique', label: '批判', detail: 'Diamond', color: '#f9a8d4' },
  { key: 'decision', label: '决策', detail: 'Rect', color: '#86efac' },
  { key: 'summary', label: '摘要', detail: 'Rect', color: '#94a3b8' },
  { key: 'memory', label: '记忆', detail: 'Circle', color: '#d8b4fe' },
  { key: 'artifact', label: '产物', detail: 'Rect', color: '#fcd34d' },
  { key: 'error', label: '错误', detail: 'Diamond', color: '#fca5a5' },
];

export const THOUGHT_RELATION_LEGEND_ENTRIES: ThoughtRelationLegendEntry[] = [
  { key: 'supports', label: 'supports', detail: '支持', color: '#34d399' },
  { key: 'opposes', label: 'opposes', detail: '反对', color: '#f87171' },
  { key: 'derives_from', label: 'derives from', detail: '派生自', color: '#22d3ee' },
  { key: 'leads_to', label: 'leads to', detail: '导致', color: '#60a5fa' },
  { key: 'requires', label: 'requires', detail: '需要', color: '#f59e0b', dash: '8 6' },
  { key: 'answers', label: 'answers', detail: '回答', color: '#34d399' },
  { key: 'questions', label: 'questions', detail: '质疑', color: '#f472b6', dash: '5 5' },
  { key: 'refines', label: 'refines', detail: '细化', color: '#c084fc' },
  { key: 'observes', label: 'observes', detail: '观察', color: '#2dd4bf' },
  { key: 'contradicts', label: 'contradicts', detail: '矛盾', color: '#fb7185', dash: '10 5' },
  { key: 'blocks', label: 'blocks', detail: '阻塞', color: '#f43f5e', dash: '6 4' },
  { key: 'produces', label: 'produces', detail: '产生', color: '#84cc16' },
  { key: 'speculates', label: 'speculates', detail: '推测', color: '#a78bfa', dash: '4 4' },
  { key: 'relates', label: 'relates', detail: '关联', color: '#94a3b8' },
  { key: 'evidence_for', label: 'evidence for', detail: '作为证据', color: '#84cc16' },
];

const THOUGHT_RELATION_STYLE_MAP: Record<string, ThoughtRelationStyle> = {
  supports: { stroke: '#34d399', glow: 'rgba(52, 211, 153, 0.35)', dash: null },
  opposes: { stroke: '#f87171', glow: 'rgba(248, 113, 113, 0.35)', dash: null },
  derives_from: { stroke: '#22d3ee', glow: 'rgba(34, 211, 238, 0.34)', dash: null },
  leads_to: { stroke: '#60a5fa', glow: 'rgba(96, 165, 250, 0.34)', dash: null },
  requires: { stroke: '#f59e0b', glow: 'rgba(245, 158, 11, 0.34)', dash: '8 6' },
  answers: { stroke: '#34d399', glow: 'rgba(52, 211, 153, 0.35)', dash: null },
  questions: { stroke: '#f472b6', glow: 'rgba(244, 114, 182, 0.34)', dash: '5 5' },
  refines: { stroke: '#c084fc', glow: 'rgba(192, 132, 252, 0.34)', dash: null },
  observes: { stroke: '#2dd4bf', glow: 'rgba(45, 212, 191, 0.34)', dash: null },
  contradicts: { stroke: '#fb7185', glow: 'rgba(251, 113, 133, 0.34)', dash: '10 5' },
  blocks: { stroke: '#f43f5e', glow: 'rgba(244, 63, 94, 0.34)', dash: '6 4' },
  produces: { stroke: '#84cc16', glow: 'rgba(132, 204, 22, 0.34)', dash: null },
  speculates: { stroke: '#a78bfa', glow: 'rgba(167, 139, 250, 0.34)', dash: '4 4' },
  relates: { stroke: '#94a3b8', glow: 'rgba(148, 163, 184, 0.26)', dash: null },
  evidence_for: { stroke: '#84cc16', glow: 'rgba(132, 204, 22, 0.34)', dash: null },
};

export function thoughtRelationStyle(relation: string): ThoughtRelationStyle {
  const key = String(relation || '').trim().toLowerCase();
  return THOUGHT_RELATION_STYLE_MAP[key] ?? THOUGHT_RELATION_STYLE_MAP['relates'];
}
