import { useState, useEffect, useRef } from 'react';

const LOG_TEMPLATES = [
  { type: 'audit', msg: 'TASK-0 (generate-swarm-manifest) - 运行时长 45.19s —— 状态: 完成' },
  { type: 'info', msg: 'Swarm "deepseek_demo" 已加载 —— 包含 7 个 agents, 4 个 tools' },
  { type: 'graph', msg: 'GraphExecutor: planner → agent_manager → graph_editor 路径已建立' },
  { type: 'agent', msg: '临时 auditor agent 已生成 —— ID: tmp-agent-4f2a8c' },
  { type: 'graph', msg: '动态改图: 将 auditor 节点插入执行图 —— 位置: planner 与 publisher 之间' },
  { type: 'info', msg: 'runtime_info 已落盘 —— agents/deepseek_demo/runtime_info/current.json' },
  { type: 'audit', msg: 'TASK-1 (agent-round) - auditor 产出复核结论 —— 置信度: 0.94' },
  { type: 'agent', msg: 'auditor 生命周期结束 —— 正在从图中移除临时节点' },
  { type: 'graph', msg: 'GraphExecutor: 执行图恢复至原始拓扑 —— 所有临时节点已清理' },
  { type: 'info', msg: 'SSE 事件流推送 —— 连接数: 1, 事件队列: 0' },
  { type: 'audit', msg: 'TASK-2 (publish-output) - 最终结果已写入 outputs/deepseek_demo_final.txt' },
  { type: 'info', msg: 'Session 结束 —— 总运行时长: 2m18s, Agent 调用: 5 次' },
];

const COLORS: Record<string, string> = {
  audit: '\u001b[36m',
  info: '\u001b[32m',
  graph: '\u001b[35m',
  agent: '\u001b[33m',
};

export interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  color: string;
}

export function useConsoleLog(intervalMs = 800) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const indexRef = useRef(0);

  useEffect(() => {
    const timer = setInterval(() => {
      const template = LOG_TEMPLATES[indexRef.current % LOG_TEMPLATES.length];
      indexRef.current++;

      const now = new Date();
      const timestamp = now.toISOString().replace('T', ' ').slice(0, 19);

      const entry: LogEntry = {
        timestamp,
        level: template.type.toUpperCase(),
        message: template.msg,
        color: COLORS[template.type] || '\u001b[37m',
      };

      setLogs(prev => [...prev.slice(-60), entry]);
    }, intervalMs);

    return () => clearInterval(timer);
  }, [intervalMs]);

  return logs;
}
