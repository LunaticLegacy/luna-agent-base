# Tech Spec — Luna Angelus 概念体验站

## 依赖

| 包名 | 版本 | 用途 |
|------|------|------|
| `react` | `^19.1.0` | UI 框架 |
| `react-dom` | `^19.1.0` | DOM 渲染 |
| `three` | `^0.172.0` | 3D 场景、粒子流、视差残碑 |
| `@types/three` | `^0.172.0` | Three.js 类型定义 |
| `gsap` | `^3.12.7` | 迷雾揭示切片动画、ScrollTrigger |
| `lenis` | `^1.2.3` | 全局平滑滚动 |
| `lucide-react` | `^0.468.0` | 图标（Crosshair、Command 等） |
| `tailwindcss` | `^4.1.0` | 样式体系 |

**字体加载策略**：通过 Google Fonts CDN 引入 `Noto Serif SC`、`Noto Sans SC`、`JetBrains Mono`。在 `index.html` 的 `<head>` 中以 `<link>` 标签预加载，CSS 中使用 `font-display: swap` 避免 FOIT。

---

## 组件清单

### 页面（单页）

| 组件 | 来源 | 说明 |
|------|------|------|
| `App` | 自建 | 顶层布局：Lenis 初始化 + 各区块按顺序组装 |

### 各区块组件

| 组件 | 来源 | 说明 |
|------|------|------|
| `HeroSection` | 自建 | 包含全屏 Three.js Canvas + 悬浮碑文 UI |
| `SacredInterface` | 自建 | 石碑前方的半透明指令面板（Tab + 按钮矩阵 + 流萤面板） |
| `FogRevealSection` | 自建 | 迷雾揭示容器，内部包含多个 `RevealPanel` |
| `RevealPanel` | 自建 | 从迷雾中 clip-path 擦除显现的内容面板 |
| `StarfieldConsole` | 自建 | 底部全宽终端控制台，带自动滚动日志 |

### 核心特效组件

| 组件 | 来源 | 说明 |
|------|------|------|
| `ParallaxMonolith` | 自建 | Three.js 场景：云层 + 残碑 + 星环 + 暗紫星空背景 + 鼠标视差 |
| `SwarmParticleStreams` | 自建 | Three.js Points：5 条粒子流，GPU 驱动，鼠标磁场干扰 |
| `FogLayer` | 自建 | 绝对定位的迷雾遮罩层，GSAP 驱动 |

### Hooks

| Hook | 说明 |
|------|------|
| `useNormalizedMouse` | 监听 mousemove，返回归一化到 `[-1, 1]` 的鼠标坐标 |
| `useLenis` | 初始化 Lenis 实例，绑定 GSAP ScrollTrigger 同步 |
| `useConsoleLog` | 定时生成模拟日志，驱动 `StarfieldConsole` 的自动滚动 |

---

## 动画实现方案

| 动画效果 | 实现库 | 实现方式 | 复杂度 |
|----------|--------|----------|--------|
| 3D 视差残碑（云层 + 残碑 + 星环 + 星空） | Three.js | `ShaderMaterial` + `onBeforeCompile` + FBM 噪声 + 指数平滑跟随 | 🔒 High |
| 迷雾揭示切片 | GSAP ScrollTrigger | `clip-path: inset()` 擦除 + 迷雾层 `yPercent` 穿越 | 🔒 High |
| 多重流萤穿梭 | Three.js | `THREE.Points` + 自定义顶点/片元着色器 + AdditiveBlending | 🔒 High |
| 鼠标视差映射 | Three.js + 自定义 Hook | `useNormalizedMouse` 驱动 `cameraGroup` 旋转 | Medium |
| 自定义指针 | CSS + React State | `onMouseEnter/Leave` 切换 `cursor: none` + 绝对定位 Crosshair 图标 | Low |
| 文本闪烁 | CSS Animation | `@keyframes` 控制 `opacity` 0.8→1.0 循环 | Low |
| 控制台日志滚动 | React State + CSS | `useConsoleLog` 定时追加行 + `scrollTop` 自动滚动 | Low |
| 按钮矩阵光晕 | CSS | `:hover` 时 `box-shadow` 过渡 + `transition` | Low |
| 导航 Tab 选中态 | CSS | 选中时 `color: #E8DCC4` + `text-shadow` 微光 | Low |

---

## 状态与逻辑架构

- **鼠标坐标**：全局共享。`useNormalizedMouse` 通过 React Context 或 ref 透传，供 `ParallaxMonolith` 和 `SwarmParticleStreams` 同时读取，避免重复监听。
- **Lenis 实例**：在 `App` 顶层初始化，通过 Context 提供 `lenis` 实例，供 GSAP ScrollTrigger 的 `scrollerProxy` 绑定。
- **控制台日志**：`useConsoleLog` Hook 内部维护日志数组，通过定时器每 800ms 追加一条模拟日志。`StarfieldConsole` 通过 `useRef` 获取 DOM 节点，在日志更新时自动 `scrollToBottom`。
- **Three.js 场景生命周期**：`ParallaxMonolith` 和 `SwarmParticleStreams` 各自管理独立的 `THREE.WebGLRenderer`，但共享同一个 Canvas 容器（通过 z-index 分层），或使用单一 Renderer 的多个 Scene（`renderer.autoClear = false`）。考虑到两个特效的渲染逻辑差异较大，**推荐方案**：共用同一个 Renderer + 同一个 Canvas，渲染顺序为 粒子流 → 残碑场景，`renderer.clear()` 仅在每帧开始时执行一次。

---

## 其他关键决策

- **单 Canvas 多 Scene 渲染**：`ParallaxMonolith`（背景层）和 `SwarmParticleStreams`（最底层粒子流）共用同一个 `WebGLRenderer`。在 `useFrame` 中先渲染粒子流 Scene（`renderer.autoClear = true`），再渲染残碑 Scene（`renderer.autoClear = false`），确保两层叠加正确。
- **迷雾层与面板擦除的时序耦合**：`FogRevealSection` 内部，`fogLayer` 的 GSAP 动画与每个 `RevealPanel` 的 `clipPath` 动画必须通过 **同一个 ScrollTrigger 区间** 锁定时序。实现时将 `fogLayer` 的 `scrollTrigger` 作为共享触发器，各 `panel` 的 `scrollTrigger.trigger` 均指向 `fogLayer` 元素。
- **字体降级策略**：在 `index.html` 中按以下顺序加载——`JetBrains Mono`（控制台最先出现）→ `Noto Sans SC`（UI 文本）→ `Noto Serif SC`（碑文标题）。CSS 中统一设置 `font-display: swap`，并在 `html` 上添加 `.fonts-loaded` 类控制过渡动画。
