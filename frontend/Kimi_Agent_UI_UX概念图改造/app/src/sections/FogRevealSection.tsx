import { useEffect, useRef } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { Network, GitBranch, Activity, Eye, Zap, Clock } from 'lucide-react';

gsap.registerPlugin(ScrollTrigger);

const PANELS = [
  {
    icon: Network,
    title: '动态图编排',
    subtitle: 'Dynamic Graph Orchestration',
    desc: '工具可以改图，Agent 可以生成新的 Agent。支持添加边、删边、改 entry / exit，将临时 Agent 插进当前执行图或从中移除。',
    detail: '每一次 graph 变更都会实时写入 runtime_info，让运行中的状态变化可回放、可审计、可调试。',
  },
  {
    icon: GitBranch,
    title: 'Swarm 包机制',
    subtitle: 'Pluggable Swarm Packages',
    desc: '每个 agents/&lt;swarm_name&gt;/ 都是一套独立业务包，包含 swarm.toml、执行图、Agent 定义、Skill 和 Tool。',
    detail: '可插拔架构让不同业务场景相互隔离，通过 config.toml 告诉 runtime 去哪里找 swarm 包。',
  },
  {
    icon: Activity,
    title: '实时执行流',
    subtitle: 'Live Execution Streams',
    desc: '后端支持异步 run session 和 SSE 事件流，前端可实时订阅 Agent 执行状态、graph 变更和工具调用结果。',
    detail: '从 planner 产出的控制计划到 publisher 的最终输出，每一步都在时间轴上留下痕迹。',
  },
  {
    icon: Eye,
    title: '运行时可追踪',
    subtitle: 'Runtime Observability',
    desc: '每一次 Agent / Tool / Graph 的变化，都会写入 current.json 和 events.jsonl。',
    detail: '这让运行中的状态变化可回放、可审计、可调试。完整的执行追踪与容错策略，保障系统质量。',
  },
];

export default function FogRevealSection() {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const fogLayerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    const fogLayer = fogLayerRef.current;
    if (!wrapper || !fogLayer) return;

    const ctx = gsap.context(() => {
      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: wrapper,
          start: 'top 80%',
          end: 'top 20%',
          scrub: true,
        },
      });

      tl.fromTo(
        fogLayer,
        { opacity: 0 },
        { opacity: 1, duration: 0.3 }
      );

      tl.fromTo(
        fogLayer,
        { yPercent: -100 },
        { yPercent: 100, ease: 'none', duration: 1 },
        0
      );

      // Panel reveals
      const panels = gsap.utils.toArray<HTMLElement>('.reveal-panel');
      panels.forEach((panel) => {
        gsap.fromTo(
          panel,
          { clipPath: 'inset(0 100% 0 0)' },
          {
            clipPath: 'inset(0 0% 0 0)',
            ease: 'none',
            scrollTrigger: {
              trigger: fogLayer,
              scrub: true,
              start: 'top 100%',
              end: 'top 40%',
            },
          }
        );
      });
    }, wrapper);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={wrapperRef} className="relative" style={{ minHeight: '200vh' }}>
      {/* Content */}
      <div ref={contentRef} className="relative z-10 pt-40 pb-32">
        <div className="max-w-5xl mx-auto px-6">
          {/* Section Header */}
          <div className="text-center mb-32 reveal-panel">
            <p
              className="font-mono-data text-xs tracking-[0.3em] uppercase mb-4"
              style={{ color: '#5B6B8D' }}
            >
              Core Capabilities
            </p>
            <h2
              className="font-display text-5xl md:text-6xl tracking-tight"
              style={{ color: '#E0E6F1', letterSpacing: '-1px', fontWeight: 900 }}
            >
              核心特性
            </h2>
            <p className="mt-6 text-lg max-w-2xl mx-auto" style={{ color: '#5B6B8D', lineHeight: 1.8 }}>
              复杂的协作不该只是跑起来，还应该被看见、被编辑、被追踪
            </p>
          </div>

          {/* Panels */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {PANELS.map((panel, i) => {
              const Icon = panel.icon;
              return (
                <div
                  key={i}
                  className="reveal-panel group relative border border-[#5B6B8D]/15 rounded-sm p-8 bg-[#060B14]/50 backdrop-blur-sm transition-all duration-500 hover:border-[#8B7BFF]/30"
                  style={{
                    boxShadow: '0 0 40px rgba(139, 123, 255, 0.03)',
                  }}
                >
                  <div className="flex items-start gap-4">
                    <div
                      className="flex-shrink-0 w-12 h-12 rounded-sm border border-[#5B6B8D]/20 flex items-center justify-center transition-all duration-500 group-hover:border-[#8B7BFF]/40"
                      style={{ backgroundColor: 'rgba(139, 123, 255, 0.05)' }}
                    >
                      <Icon size={20} className="text-[#5B6B8D] group-hover:text-[#8B7BFF] transition-colors duration-500" />
                    </div>
                    <div className="flex-1">
                      <h3
                        className="font-display text-xl mb-1"
                        style={{ color: '#E0E6F1', fontWeight: 700 }}
                      >
                        {panel.title}
                      </h3>
                      <p className="font-mono-data text-[10px] tracking-wider mb-3" style={{ color: '#5B6B8D' }}>
                        {panel.subtitle}
                      </p>
                      <p className="text-sm mb-3" style={{ color: '#E0E6F1', lineHeight: 1.7, opacity: 0.8 }}>
                        {panel.desc}
                      </p>
                      <p className="text-xs" style={{ color: '#5B6B8D', lineHeight: 1.7 }}>
                        {panel.detail}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Stats Row */}
          <div className="mt-32 grid grid-cols-3 gap-8 reveal-panel">
            {[
              { icon: Zap, value: '5', label: 'Agents 协作', sub: 'planner, manager, auditor, editor, publisher' },
              { icon: Clock, value: '<3s', label: '动态改图延迟', sub: '运行时插入/移除临时节点' },
              { icon: Activity, value: '100%', label: '执行可追踪', sub: 'runtime_info 自动落盘' },
            ].map((stat, i) => {
              const Icon = stat.icon;
              return (
                <div key={i} className="text-center border-t border-[#5B6B8D]/15 pt-8">
                  <Icon size={18} className="mx-auto mb-4 text-[#5B6B8D]" />
                  <p className="font-display text-4xl mb-2" style={{ color: '#E8DCC4', fontWeight: 900 }}>
                    {stat.value}
                  </p>
                  <p className="font-mono-data text-xs tracking-wider mb-1" style={{ color: '#E0E6F1' }}>
                    {stat.label}
                  </p>
                  <p className="text-xs" style={{ color: '#5B6B8D' }}>
                    {stat.sub}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Fog Layer */}
      <div
        ref={fogLayerRef}
        className="fixed top-0 left-0 w-full pointer-events-none"
        style={{
          height: '200vh',
          zIndex: 5,
          opacity: 0,
          background: `
            radial-gradient(ellipse 80% 60% at 50% 50%, rgba(224, 230, 241, 0.08) 0%, transparent 60%),
            radial-gradient(ellipse 60% 40% at 50% 50%, rgba(139, 123, 255, 0.05) 0%, transparent 50%)
          `,
        }}
      />
    </div>
  );
}
