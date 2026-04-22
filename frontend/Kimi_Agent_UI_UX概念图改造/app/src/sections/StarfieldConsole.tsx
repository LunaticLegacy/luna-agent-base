import { useEffect, useRef } from 'react';
import { useConsoleLog } from '@/hooks/useConsoleLog';
import { Activity, Thermometer, Cpu, HardDrive } from 'lucide-react';

export default function StarfieldConsole() {
  const logs = useConsoleLog(800);
  const consoleRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [logs]);

  const metrics = [
    { icon: Activity, label: '活跃度', value: '97.3%', color: '#4ade80' },
    { icon: Thermometer, label: '温度', value: '42°C', color: '#fbbf24' },
    { icon: Cpu, label: '负载', value: '3.2%', color: '#60a5fa' },
    { icon: HardDrive, label: '内存', value: '1.2G', color: '#a78bfa' },
  ];

  return (
    <footer
      className="relative w-full"
      style={{
        height: '400px',
        backgroundColor: 'rgba(6, 11, 20, 0.85)',
        backdropFilter: 'blur(20px)',
        borderTop: '1px solid rgba(91, 107, 141, 0.1)',
      }}
    >
      {/* Metrics Bar */}
      <div
        className="flex items-center justify-center gap-12 py-4 border-b"
        style={{ borderColor: 'rgba(91, 107, 141, 0.1)' }}
      >
        {metrics.map((m) => {
          const Icon = m.icon;
          return (
            <div key={m.label} className="flex items-center gap-2">
              <Icon size={12} style={{ color: m.color }} />
              <span className="font-mono-data text-[10px] tracking-wider" style={{ color: '#5B6B8D' }}>
                {m.label}
              </span>
              <span className="font-mono-data text-xs" style={{ color: m.color }}>
                {m.value}
              </span>
            </div>
          );
        })}
      </div>

      {/* Console Log Output */}
      <div
        ref={consoleRef}
        className="h-[320px] overflow-y-auto px-8 py-4 font-mono-data"
        style={{ fontSize: '12px', lineHeight: 1.7 }}
      >
        {logs.map((log, i) => (
          <div key={i} className="flex gap-3 mb-0.5">
            <span style={{ color: '#5B6B8D' }}>
              [{log.timestamp}]
            </span>
            <span
              className="tracking-wider"
              style={{
                color:
                  log.level === 'AUDIT'
                    ? '#60a5fa'
                    : log.level === 'GRAPH'
                    ? '#a78bfa'
                    : log.level === 'AGENT'
                    ? '#fbbf24'
                    : '#4ade80',
                fontSize: '10px',
                opacity: 0.7,
              }}
            >
              {log.level}
            </span>
            <span style={{ color: 'rgba(224, 230, 241, 0.7)' }}>
              {log.message}
            </span>
          </div>
        ))}
      </div>

      {/* Gradient Fade at Bottom */}
      <div
        className="absolute bottom-0 left-0 w-full h-8 pointer-events-none"
        style={{
          background: 'linear-gradient(to bottom, transparent, rgba(6, 11, 20, 0.95))',
        }}
      />
    </footer>
  );
}
