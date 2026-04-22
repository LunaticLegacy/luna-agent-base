import { useEffect } from 'react';
import Lenis from 'lenis';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useNormalizedMouse } from '@/hooks/useNormalizedMouse';
import HeroSection from '@/sections/HeroSection';
import FogRevealSection from '@/sections/FogRevealSection';
import StarfieldConsole from '@/sections/StarfieldConsole';

gsap.registerPlugin(ScrollTrigger);

export default function App() {
  const mouseRef = useNormalizedMouse();

  useEffect(() => {
    const lenis = new Lenis({
      duration: 1.2,
      easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
    });

    lenis.on('scroll', ScrollTrigger.update);

    gsap.ticker.add((time) => {
      lenis.raf(time * 1000);
    });
    gsap.ticker.lagSmoothing(0);

    return () => {
      lenis.destroy();
      gsap.ticker.remove(lenis.raf as unknown as gsap.TickerCallback);
    };
  }, []);

  return (
    <div className="relative" style={{ backgroundColor: '#060B14' }}>
      <HeroSection mouseRef={mouseRef} />
      <FogRevealSection />
      <StarfieldConsole />
    </div>
  );
}
