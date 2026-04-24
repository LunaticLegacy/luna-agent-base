import { useEffect, useRef } from 'react';
import * as THREE from 'three';

const MONOLITH_VERTEX = `
varying vec3 vLocalPosition;
varying vec3 vWorldPosition;
void main() {
  vLocalPosition = position;
  vec4 worldPos = modelMatrix * vec4(position, 1.0);
  vWorldPosition = worldPos.xyz;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const MONOLITH_FRAGMENT = `
uniform vec3 edgeGlowColor;
uniform vec3 worldGlowColor;
uniform float glowIntensity;
varying vec3 vLocalPosition;
varying vec3 vWorldPosition;
void main() {
  float edgeWidth = 0.05;
  float edgeFactor = smoothstep(edgeWidth, 0.0, min(min(vLocalPosition.x, vLocalPosition.y), vLocalPosition.z));
  vec3 finalColor = mix(vec3(0.04, 0.06, 0.12), vec3(1.0), edgeFactor * 0.8);
  finalColor += edgeGlowColor * edgeFactor * 1.5;
  float distanceFactor = length(vWorldPosition) * 0.3;
  vec3 externalGlow = worldGlowColor * glowIntensity * max(0.0, 1.0 - distanceFactor);
  finalColor += externalGlow;
  gl_FragColor = vec4(finalColor, 0.92);
}
`;

const STARFIELD_VERTEX = `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position, 1.0);
}
`;

const STARFIELD_FRAGMENT = `
uniform float uTime;
varying vec2 vUv;

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
    mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
    u.y
  );
}

float fbm(vec2 p) {
  float value = 0.0;
  float amplitude = 0.5;
  for (int i = 0; i < 4; i++) {
    value += amplitude * noise(p);
    p *= 2.0;
    amplitude *= 0.5;
  }
  return value;
}

void main() {
  vec2 uv = (vUv - 0.5) * 2.0;
  float vignette = 1.0 - dot(uv * 0.5, uv * 0.5);
  vignette = smoothstep(0.0, 1.0, vignette);
  float nebula1 = fbm(vUv * 50.0);
  float nebula2 = fbm(vUv * 20.0 + uTime * 0.01);
  float nebulaNoise = nebula1 * 0.3 + nebula2 * 0.7;
  vec3 nebulaColor = nebulaNoise * vec3(0.1, 0.05, 0.2);
  vec3 color = vec3(0.0) * vignette + (nebulaColor * 0.5);
  gl_FragColor = vec4(color, 1.0);
}
`;

const CLOUD_VERTEX = `
varying vec2 vUv;
varying vec3 vWorldPos;
void main() {
  vUv = uv;
  vec4 worldPosition = modelMatrix * vec4(position, 1.0);
  vWorldPos = worldPosition.xyz;
  gl_Position = projectionMatrix * viewMatrix * worldPosition;
}
`;

const CLOUD_FRAGMENT = `
uniform vec3 cloudColor;
uniform float opacity;
varying vec2 vUv;
void main() {
  float dist = distance(vUv, vec2(0.5));
  float circle = smoothstep(0.5, 0.2, dist);
  circle *= pow(dist + 0.1, 1.5);
  float alpha = opacity * circle;
  if (alpha < 0.01) discard;
  gl_FragColor = vec4(cloudColor, alpha);
}
`;

interface ParallaxMonolithProps {
  mouseRef: React.MutableRefObject<{ x: number; y: number }>;
}

export default function ParallaxMonolith({ mouseRef }: ParallaxMonolithProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const animFrameRef = useRef<number>(0);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set(0, 0, 8);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Camera group for parallax
    const cameraGroup = new THREE.Group();
    cameraGroup.add(camera);
    scene.add(cameraGroup);

    // === Starfield Background ===
    const starfieldGeo = new THREE.PlaneGeometry(2, 2);
    const starfieldMat = new THREE.ShaderMaterial({
      vertexShader: STARFIELD_VERTEX,
      fragmentShader: STARFIELD_FRAGMENT,
      uniforms: { uTime: { value: 0 } },
      depthWrite: false,
    });
    const starfield = new THREE.Mesh(starfieldGeo, starfieldMat);
    starfield.renderOrder = -2;
    cameraGroup.add(starfield);

    // === Clouds ===
    const cloudGroup = new THREE.Group();
    const cloudMat1 = new THREE.ShaderMaterial({
      vertexShader: CLOUD_VERTEX,
      fragmentShader: CLOUD_FRAGMENT,
      uniforms: {
        cloudColor: { value: new THREE.Color(0x8B7BFF) },
        opacity: { value: 0.15 },
      },
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const cloudMat2 = new THREE.ShaderMaterial({
      vertexShader: CLOUD_VERTEX,
      fragmentShader: CLOUD_FRAGMENT,
      uniforms: {
        cloudColor: { value: new THREE.Color(0x6B5BFF) },
        opacity: { value: 0.1 },
      },
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
    });

    const cloudGeo1 = new THREE.PlaneGeometry(18, 18);
    const cloud1 = new THREE.Mesh(cloudGeo1, cloudMat1);
    cloud1.position.set(-3, -2, -4);
    cloud1.rotation.z = 0.2;

    const cloudGeo2 = new THREE.PlaneGeometry(16, 16);
    const cloud2 = new THREE.Mesh(cloudGeo2, cloudMat2);
    cloud2.position.set(4, -1, -5);
    cloud2.rotation.z = -0.3;

    cloudGroup.add(cloud1, cloud2);
    scene.add(cloudGroup);

    // === Monolith ===
    const monolithGeo = new THREE.BoxGeometry(1.2, 3.5, 0.8, 1, 1, 1);
    const monolithMat = new THREE.ShaderMaterial({
      vertexShader: MONOLITH_VERTEX,
      fragmentShader: MONOLITH_FRAGMENT,
      uniforms: {
        edgeGlowColor: { value: new THREE.Color(0x8B7BFF) },
        worldGlowColor: { value: new THREE.Color(0x6B5BFF) },
        glowIntensity: { value: 0.4 },
      },
      transparent: true,
    });
    const monolith = new THREE.Mesh(monolithGeo, monolithMat);
    monolith.position.set(0, 0, -1);
    scene.add(monolith);

    // === Rings ===
    const ringGroup = new THREE.Group();
    const ringMat = new THREE.ShaderMaterial({
      vertexShader: MONOLITH_VERTEX,
      fragmentShader: MONOLITH_FRAGMENT,
      uniforms: {
        edgeGlowColor: { value: new THREE.Color(0x8B7BFF) },
        worldGlowColor: { value: new THREE.Color(0x6B5BFF) },
        glowIntensity: { value: 0.3 },
      },
      transparent: true,
      wireframe: true,
    });

    const ring1 = new THREE.Mesh(new THREE.TorusGeometry(2.2, 0.015, 8, 64), ringMat);
    ring1.rotation.x = Math.PI * 0.4;
    ring1.rotation.y = Math.PI * 0.15;

    const ring2 = new THREE.Mesh(new THREE.TorusGeometry(3.0, 0.01, 8, 64), ringMat);
    ring2.rotation.x = Math.PI * 0.35;
    ring2.rotation.y = -Math.PI * 0.1;
    ring2.rotation.z = Math.PI * 0.2;

    ringGroup.add(ring1, ring2);
    ringGroup.position.set(0, 0, -1);
    scene.add(ringGroup);

    // === Animation ===
    const clock = new THREE.Clock();
    let targetRotationX = Math.PI / 8;
    let targetRotationY = 0;

    const animate = () => {
      animFrameRef.current = requestAnimationFrame(animate);
      const elapsed = clock.getElapsedTime();

      // Update starfield time
      starfieldMat.uniforms.uTime.value = elapsed;

      // Mouse parallax with smooth lerp
      const mx = mouseRef.current.x;
      const my = mouseRef.current.y;
      targetRotationX = my * 0.05 + Math.PI / 8;
      targetRotationY = mx * 0.05;

      cameraGroup.rotation.x += (targetRotationX - cameraGroup.rotation.x) * 0.05;
      cameraGroup.rotation.y += (targetRotationY - cameraGroup.rotation.y) * 0.05;

      // Cloud drift
      cloudMat1.uniforms.opacity.value = 0.12 + Math.sin(elapsed * 0.3) * 0.03;
      cloudMat2.uniforms.opacity.value = 0.08 + Math.sin(elapsed * 0.5 + 1) * 0.02;

      // Monolith slow rotation
      monolith.rotation.y = Math.sin(elapsed * 0.15) * 0.05;
      ringGroup.rotation.y += 0.001;
      ringGroup.rotation.x = Math.sin(elapsed * 0.08) * 0.1;

      // Cloud parallax lookAt
      const cloudTargetX = mx * 0.4;
      const cloudTargetY = my * 0.2;
      cloud1.lookAt(cloud1.position.x + cloudTargetX, cloud1.position.y + cloudTargetY, cloud1.position.z + 5);
      cloud2.lookAt(cloud2.position.x - cloudTargetX * 0.5, cloud2.position.y + cloudTargetY * 0.5, cloud2.position.z + 5);

      renderer.render(scene, camera);
    };
    animate();

    // === Resize ===
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
      monolithGeo.dispose();
      monolithMat.dispose();
      cloudGeo1.dispose();
      cloudGeo2.dispose();
      cloudMat1.dispose();
      cloudMat2.dispose();
      starfieldGeo.dispose();
      starfieldMat.dispose();
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
        zIndex: 1,
      }}
    />
  );
}
