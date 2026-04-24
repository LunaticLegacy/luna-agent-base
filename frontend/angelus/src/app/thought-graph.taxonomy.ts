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
  { key: 'fact', label: '事实', detail: 'Circle', color: '#67e8f9' },
  { key: 'evidence', label: '证据', detail: 'Circle', color: '#6ee7b7' },
  { key: 'tool_result', label: '工具结果', detail: 'Circle', color: '#fcd34d' },
  { key: 'reasoning', label: '推理', detail: 'Rect', color: '#a5b4fc' },
  { key: 'claim', label: '主张', detail: 'Rect', color: '#93c5fd' },
  { key: 'decision', label: '决策', detail: 'Rect', color: '#86efac' },
  { key: 'goal', label: '目标', detail: 'Hexagon', color: '#ddd6fe' },
  { key: 'question', label: '问题', detail: 'Hexagon', color: '#f472b6' },
  { key: 'assumption', label: '假设', detail: 'Hexagon', color: '#cbd5e1' },
  { key: 'hypothesis', label: '假说', detail: 'Diamond', color: '#fde68a' },
  { key: 'guess', label: '猜测', detail: 'Diamond', color: '#fdba74' },
  { key: 'risk', label: '风险', detail: 'Diamond', color: '#fca5a5' },
  { key: 'counterevidence', label: '反证', detail: 'Diamond', color: '#fb7185' },
  { key: 'execution_trace', label: '执行轨迹', detail: 'Trace', color: '#5eead4' },
];

export const THOUGHT_RELATION_LEGEND_ENTRIES: ThoughtRelationLegendEntry[] = [
  { key: 'supports', label: 'supports', detail: '支持', color: '#34d399' },
  { key: 'opposes', label: 'opposes', detail: '反对', color: '#f87171' },
  { key: 'derives_from', label: 'derives from', detail: '派生自', color: '#22d3ee' },
  { key: 'leads_to', label: 'leads to', detail: '导致', color: '#60a5fa' },
  { key: 'depends_on', label: 'depends on', detail: '依赖', color: '#f59e0b', dash: '8 6' },
  { key: 'questions', label: 'questions', detail: '质疑', color: '#f472b6', dash: '5 5' },
  { key: 'refines', label: 'refines', detail: '细化', color: '#c084fc' },
  { key: 'verifies', label: 'verifies', detail: '验证', color: '#2dd4bf' },
  { key: 'disproves', label: 'disproves', detail: '否证', color: '#fb7185' },
  { key: 'speculates', label: 'speculates', detail: '推测', color: '#a78bfa', dash: '4 4' },
  { key: 'relates', label: 'relates', detail: '关联', color: '#94a3b8' },
  { key: 'evidence_for', label: 'evidence for', detail: '作为证据', color: '#84cc16' },
];

const THOUGHT_RELATION_STYLE_MAP: Record<string, ThoughtRelationStyle> = {
  supports: { stroke: '#34d399', glow: 'rgba(52, 211, 153, 0.35)', dash: null },
  opposes: { stroke: '#f87171', glow: 'rgba(248, 113, 113, 0.35)', dash: null },
  derives_from: { stroke: '#22d3ee', glow: 'rgba(34, 211, 238, 0.34)', dash: null },
  leads_to: { stroke: '#60a5fa', glow: 'rgba(96, 165, 250, 0.34)', dash: null },
  depends_on: { stroke: '#f59e0b', glow: 'rgba(245, 158, 11, 0.34)', dash: '8 6' },
  questions: { stroke: '#f472b6', glow: 'rgba(244, 114, 182, 0.34)', dash: '5 5' },
  refines: { stroke: '#c084fc', glow: 'rgba(192, 132, 252, 0.34)', dash: null },
  verifies: { stroke: '#2dd4bf', glow: 'rgba(45, 212, 191, 0.34)', dash: null },
  disproves: { stroke: '#fb7185', glow: 'rgba(251, 113, 133, 0.34)', dash: '10 5' },
  speculates: { stroke: '#a78bfa', glow: 'rgba(167, 139, 250, 0.34)', dash: '4 4' },
  relates: { stroke: '#94a3b8', glow: 'rgba(148, 163, 184, 0.26)', dash: null },
  evidence_for: { stroke: '#84cc16', glow: 'rgba(132, 204, 22, 0.34)', dash: null },
};

export function thoughtRelationStyle(relation: string): ThoughtRelationStyle {
  const key = String(relation || '').trim().toLowerCase();
  return THOUGHT_RELATION_STYLE_MAP[key] ?? THOUGHT_RELATION_STYLE_MAP['relates'];
}
