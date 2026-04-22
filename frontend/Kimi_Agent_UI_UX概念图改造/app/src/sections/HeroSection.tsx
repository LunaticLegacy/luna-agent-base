import { useEffect, useRef, useState } from 'react';
import { Crosshair } from 'lucide-react';
import ParallaxMonolith from '@/components/ParallaxMonolith';
import SwarmParticleStreams from '@/components/SwarmParticleStreams';
import SacredInterface from './SacredInterface';

interface HeroSectionProps {
  mouseRef: React.MutableRefObject<{ x: number; y: number }>;
}

export default function HeroSection({ mouseRef }: HeroSectionProps) {
  const [isHovering, setIsHovering] = useState(false);
  const sectionRef = useRef<HTMLElement>(null);

  return (
    <section
      ref={sectionRef}
      id="hero"
      className="relative w-full overflow-hidden"
      style={{ height: '100vh', minHeight: '700px', cursor: isHovering ? 'none' : 'default' }}
      onMouseEnter={() => setIsHovering(true)}
      onMouseLeave={() => setIsHovering(false)}
    >
      {/* Particle Streams - deepest layer */}
      <SwarmParticleStreams mouseRef={mouseRef} />

      {/* 3D Monolith Scene */}
      <ParallaxMonolith mouseRef={mouseRef} />

      {/* Custom Crosshair Cursor */}
      {isHovering && <CustomCursor mouseRef={mouseRef} />}

      {/* Sacred Interface Overlay */}
      <div className="absolute inset-0 z-10 flex items-center justify-center pointer-events-none">
        <SacredInterface />
      </div>
    </section>
  );
}

function CustomCursor({ mouseRef }: { mouseRef: React.MutableRefObject<{ x: number; y: number }> }) {
  const cursorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let animId: number;
    const loop = () => {
      if (cursorRef.current) {
        const x = ((mouseRef.current.x + 1) / 2) * window.innerWidth;
        const y = ((-mouseRef.current.y + 1) / 2) * window.innerHeight;
        cursorRef.current.style.transform = `translate(${x - 12}px, ${y - 12}px)`;
      }
      animId = requestAnimationFrame(loop);
    };
    loop();
    return () => cancelAnimationFrame(animId);
  }, [mouseRef]);

  return (
    <div
      ref={cursorRef}
      className="fixed top-0 left-0 z-50 pointer-events-none"
      style={{ mixBlendMode: 'difference' }}
    >
      <Crosshair size={24} className="text-[#E0E6F1]" strokeWidth={1} />
    </div>
  );
}
