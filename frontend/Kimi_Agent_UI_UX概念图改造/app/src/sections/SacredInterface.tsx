import { useState } from 'react';
import { Command, Sparkles, Search, Code2, FileCode2, MessageSquare, ArrowRight } from 'lucide-react';

const TABS = ['发想', '智能体', '画布'];

const ACTIONS = [
  { label: '发想', icon: Sparkles, desc: '生成创意与方案' },
  { label: '检索', icon: Search, desc: '知识库与文档查询' },
  { label: '编码', icon: Code2, desc: '代码生成与重构' },
  { label: '写码', icon: FileCode2, desc: '文件级代码编写' },
];

export default function SacredInterface() {
  const [activeTab, setActiveTab] = useState(0);
  const [hoveredAction, setHoveredAction] = useState<number | null>(null);

  return (
    <div className="pointer-events-auto flex flex-col items-center gap-8 px-6">
      {/* Giant Title */}
      <div className="text-center">
        <p
          className="font-display text-blow text-blink tracking-tight"
          style={{
            fontSize: 'clamp(48px, 8vw, 96px)',
            lineHeight: 1.0,
            letterSpacing: '-2px',
            color: '#E0E6F1',
            fontWeight: 900,
          }}
        >
          用一句话改变现实
        </p>
        <p
          className="mt-4 font-mono-data tracking-widest uppercase"
          style={{ fontSize: '12px', color: '#5B6B8D', letterSpacing: '0.3em' }}
        >
          Angelus Lunae — Multi-Agent Orchestration Runtime
        </p>
      </div>

      {/* Interface Panel */}
      <div
        className="relative w-full max-w-3xl rounded-sm border border-[#5B6B8D]/20 bg-[#060B14]/40 backdrop-blur-md p-8"
        style={{ boxShadow: '0 0 60px rgba(139, 123, 255, 0.05)' }}
      >
        {/* Subtle grid overlay */}
        <div
          className="absolute inset-0 opacity-[0.03] pointer-events-none"
          style={{
            backgroundImage: `
              linear-gradient(rgba(224, 230, 241, 0.5) 1px, transparent 1px),
              linear-gradient(90deg, rgba(224, 230, 241, 0.5) 1px, transparent 1px)
            `,
            backgroundSize: '40px 40px',
          }}
        />

        {/* Navigation Tabs */}
        <div className="relative flex gap-0 mb-8 border-b border-[#5B6B8D]/20">
          {TABS.map((tab, i) => (
            <button
              key={tab}
              onClick={() => setActiveTab(i)}
              className="relative px-6 py-3 font-mono-data text-sm tracking-wider transition-all duration-300"
              style={{
                color: activeTab === i ? '#E8DCC4' : '#5B6B8D',
                textShadow: activeTab === i ? '0 0 12px rgba(232, 220, 196, 0.4)' : 'none',
              }}
            >
              {tab}
              {activeTab === i && (
                <span
                  className="absolute bottom-0 left-0 w-full h-px"
                  style={{
                    background: 'linear-gradient(90deg, transparent, #E8DCC4, transparent)',
                  }}
                />
              )}
            </button>
          ))}
        </div>

        {/* Command Hint */}
        <div className="flex items-center gap-3 mb-6">
          <Command size={14} className="text-[#5B6B8D]" />
          <span className="font-mono-data text-xs text-[#5B6B8D] tracking-wider">
            输入指令以启动 Agent Swarm 编排...
          </span>
        </div>

        {/* Action Matrix */}
        <div className="grid grid-cols-4 gap-3 mb-8">
          {ACTIONS.map((action, i) => {
            const Icon = action.icon;
            return (
              <button
                key={action.label}
                className="btn-matrix group relative flex flex-col items-center gap-3 py-6 px-4 rounded-sm"
                onMouseEnter={() => setHoveredAction(i)}
                onMouseLeave={() => setHoveredAction(null)}
              >
                <Icon
                  size={22}
                  className="transition-colors duration-500"
                  style={{ color: hoveredAction === i ? '#8B7BFF' : '#5B6B8D' }}
                />
                <span
                  className="font-display text-lg transition-colors duration-500"
                  style={{
                    color: hoveredAction === i ? '#E0E6F1' : '#5B6B8D',
                    fontWeight: 700,
                  }}
                >
                  {action.label}
                </span>
                <span
                  className="font-mono-data text-[10px] tracking-wider opacity-0 group-hover:opacity-100 transition-opacity duration-500"
                  style={{ color: '#5B6B8D' }}
                >
                  {action.desc}
                </span>
              </button>
            );
          })}
        </div>

        {/* Bottom Row: Input + Spark Panel */}
        <div className="flex gap-4">
          {/* Input Area */}
          <div className="flex-1 relative">
            <input
              type="text"
              placeholder="描述你的任务，让多智能体协作完成..."
              className="w-full bg-[#060B14]/60 border border-[#5B6B8D]/20 rounded-sm px-4 py-3 font-mono-data text-sm text-[#E0E6F1] placeholder:text-[#5B6B8D]/50 focus:outline-none focus:border-[#8B7BFF]/50 transition-colors"
              style={{ backdropFilter: 'blur(10px)' }}
            />
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <ArrowRight size={16} className="text-[#5B6B8D]" />
            </div>
          </div>

          {/* Spark Panel */}
          <div
            className="w-64 border border-[#5B6B8D]/15 rounded-sm p-4 bg-[#060B14]/30"
            style={{ backdropFilter: 'blur(10px)' }}
          >
            <div className="flex items-center gap-2 mb-3">
              <MessageSquare size={12} className="text-[#E8DCC4]" />
              <span className="font-mono-data text-[10px] tracking-wider text-[#E8DCC4]">
                流萤摘要
              </span>
            </div>
            <p className="font-mono-data text-xs text-[#5B6B8D] leading-relaxed">
              Swarm 已就绪。7 个 agents 在线，执行图拓扑稳定。可输入任务启动动态编排...
            </p>
            <button className="mt-3 font-mono-data text-[10px] tracking-wider text-[#5B6B8D] hover:text-[#E8DCC4] transition-colors flex items-center gap-1">
              从流萤延续 <ArrowRight size={10} />
            </button>
          </div>
        </div>
      </div>

      {/* Status Row */}
      <div className="flex gap-6">
        {[
          { label: 'API', value: '/api', ok: true },
          { label: '健康', value: '正常', ok: true },
          { label: '就绪', value: '已就绪', ok: true },
          { label: 'Swarms', value: '1 已加载', ok: true },
        ].map((chip) => (
          <span
            key={chip.label}
            className="font-mono-data text-xs px-3 py-1.5 rounded-sm border transition-all duration-300"
            style={{
              color: chip.ok ? '#E0E6F1' : '#5B6B8D',
              borderColor: chip.ok ? 'rgba(232, 220, 196, 0.2)' : 'rgba(91, 107, 141, 0.2)',
              backgroundColor: chip.ok ? 'rgba(232, 220, 196, 0.05)' : 'transparent',
            }}
          >
            {chip.label}: {chip.value}
          </span>
        ))}
      </div>
    </div>
  );
}
