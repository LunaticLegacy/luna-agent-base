import { useEffect, useRef } from 'react';
import * as THREE from 'three';

const PARTICLE_VERTEX = `
attribute float aStreamIndex;
attribute float aLife;
attribute float aSpeed;
attribute float aOffset;
attribute vec3 aBasePos;

uniform float uTime;
uniform vec2 uMouse;
uniform float uInfluenceRadius;

varying float vAlpha;
varying float vLife;

void main() {
  vLife = mod(uTime * aSpeed + aOffset, 1.0);
  vAlpha = (1.0 - vLife) * 0.3;

  float streamIdx = aStreamIndex;
  float t = vLife;

  // Curved path: sinusoidal pipeline
  vec3 pos = aBasePos;
  pos.x += t * 12.0 - 6.0;
  pos.y += sin(t * 6.28 + streamIdx * 1.25) * 2.5;
  pos.z += cos(t * 4.18 + streamIdx * 0.78) * 1.5;

  // Mouse influence
  vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
  vec2 screenPos = mvPos.xy / mvPos.z;
  float dist = distance(screenPos, uMouse);
  float influence = smoothstep(uInfluenceRadius, 0.0, dist);

  pos.y += influence * 0.8 * sin(uTime * 3.0 + streamIdx);
  pos.x += influence * 0.3 * cos(uTime * 2.0);

  vAlpha += influence * 0.2;

  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  gl_PointSize = 1.5 + (1.0 - t) * 1.0;
}
`;

const PARTICLE_FRAGMENT = `
uniform vec3 uColor1;
uniform vec3 uColor2;

varying float vAlpha;
varying float vLife;

void main() {
  float d = length(gl_PointCoord - 0.5);
  if (d > 0.5) discard;

  float alpha = smoothstep(0.5, 0.1, d) * vAlpha;
  vec3 color = mix(uColor1, uColor2, vLife);

  gl_FragColor = vec4(color, alpha);
}
`;

interface SwarmParticleStreamsProps {
  mouseRef: React.MutableRefObject<{ x: number; y: number }>;
}

export default function SwarmParticleStreams({ mouseRef }: SwarmParticleStreamsProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const animFrameRef = useRef<number>(0);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 100);
    camera.position.set(0, 0, 10);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    const STREAM_COUNT = 5;
    const PARTICLES_PER_STREAM = 2000;
    const TOTAL_PARTICLES = STREAM_COUNT * PARTICLES_PER_STREAM;

    const positions = new Float32Array(TOTAL_PARTICLES * 3);
    const streamIndices = new Float32Array(TOTAL_PARTICLES);
    const lives = new Float32Array(TOTAL_PARTICLES);
    const speeds = new Float32Array(TOTAL_PARTICLES);
    const offsets = new Float32Array(TOTAL_PARTICLES);
    const basePositions = new Float32Array(TOTAL_PARTICLES * 3);

    for (let s = 0; s < STREAM_COUNT; s++) {
      for (let i = 0; i < PARTICLES_PER_STREAM; i++) {
        const idx = s * PARTICLES_PER_STREAM + i;
        const x = (Math.random() - 0.5) * 2;
        const y = (Math.random() - 0.5) * 2;
        const z = (Math.random() - 0.5) * 2;

        positions[idx * 3] = x;
        positions[idx * 3 + 1] = y;
        positions[idx * 3 + 2] = z;

        basePositions[idx * 3] = x;
        basePositions[idx * 3 + 1] = y;
        basePositions[idx * 3 + 2] = z;

        streamIndices[idx] = s;
        lives[idx] = Math.random();
        speeds[idx] = 0.1 + Math.random() * 0.3;
        offsets[idx] = Math.random() * 6.28;
      }
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('aStreamIndex', new THREE.BufferAttribute(streamIndices, 1));
    geometry.setAttribute('aLife', new THREE.BufferAttribute(lives, 1));
    geometry.setAttribute('aSpeed', new THREE.BufferAttribute(speeds, 1));
    geometry.setAttribute('aOffset', new THREE.BufferAttribute(offsets, 1));
    geometry.setAttribute('aBasePos', new THREE.BufferAttribute(basePositions, 3));

    const material = new THREE.ShaderMaterial({
      vertexShader: PARTICLE_VERTEX,
      fragmentShader: PARTICLE_FRAGMENT,
      uniforms: {
        uTime: { value: 0 },
        uMouse: { value: new THREE.Vector2(0, 0) },
        uInfluenceRadius: { value: 2.0 },
        uColor1: { value: new THREE.Color(0xA0B0D0) },
        uColor2: { value: new THREE.Color(0xE8DCC4) },
      },
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });

    const points = new THREE.Points(geometry, material);
    scene.add(points);

    const clock = new THREE.Clock();

    const animate = () => {
      animFrameRef.current = requestAnimationFrame(animate);
      const elapsed = clock.getElapsedTime();

      material.uniforms.uTime.value = elapsed;
      material.uniforms.uMouse.value.set(mouseRef.current.x * 3, mouseRef.current.y * 3);

      renderer.render(scene, camera);
    };
    animate();

    const handleResize = () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      window.removeEventListener('resize', handleResize);
      renderer.dispose();
      geometry.dispose();
      material.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [mouseRef]);

  return (
    <div
      ref={containerRef}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        zIndex: 0,
        pointerEvents: 'none',
      }}
    />
  );
}
