# Angelus 前端 UI/UX 语义规范

> 本文档描述当前前端（`frontend/angelus`）的用户界面语义、信息架构、视觉系统与交互模式，供后续迭代与多 Agent 协作时作为统一参考。

---

## 一、信息架构（Information Architecture）

### 1.1 应用外壳（App Shell）

```
┌─────────────────────────────────────────────┐
│  Sidebar (固定侧边栏, 240px)                 │
│  ├── Brand: Angelus / Lunae                  │
│  ├── Nav Items (10 个固定导航项)             │
│  └── Footer: 当前 Swarm + 系统状态           │
├─────────────────────────────────────────────┤
│  Main Content (自适应主内容区)               │
│  ├── Topbar (顶部栏)                         │
│  │   ├── Breadcrumb: Angelus / 页面标题      │
│  │   ├── 状态 Chip                           │
│  │   ├── 刷新 / 通知 / 用户头像              │
│  └── <router-outlet> (页面内容)              │
└─────────────────────────────────────────────┘
```

### 1.2 路由与页面对应表

| 路由 | 页面组件 | 中文标题 | 核心职责 |
|------|---------|---------|---------|
| `/` | `OverviewPageComponent` | **概览** | 系统仪表盘：统计卡片、Swarm 列表、Agent 图、执行控制台、系统信息 |
| `/swarm` | `SwarmManagementPageComponent` | **Swarm 管理** | 当前 Swarm 详情页，含 9 个 Tab（概览/Agent 图/执行轨迹/思维图谱/Agents/任务/知识/记忆/设置） |
| `/agents` | `AgentsPageComponent` | **智能体** | Agent 列表管理、多维度筛选、右侧详情抽屉 |
| `/tasks` | `TasksPageComponent` | **任务** | 任务列表与监控、统计卡片、筛选栏、右侧详情抽屉 |
| `/knowledge` | `KnowledgePageComponent` | **知识库** | 知识条目 CRUD、知识图谱统计、编辑器弹窗、详情抽屉 |
| `/tools` | `ToolsPage` | **工具** | 系统工具管理、Tab 分类、工具详情卡片 |
| `/memory` | `MemoryPageComponent` | **记忆** | 记忆检索与管理、左右分栏、新建记忆弹窗 |
| `/events` | `EventsPage` | **事件** | 实时事件追踪、SSE 实时流面板、事件表格与导出 |
| `/logs` | `LogsPage` | **日志** | 结构化日志查询、级别筛选、分页与导出 |
| `/settings` | `SettingsPage` | **设置** | API 配置、系统信息、显示设置、系统状态 |

### 1.3 导航语义

侧边栏导航是**全局一级导航**，所有页面平级，无二级菜单。

每个导航项的语义：
- **图标 + 文本**：图标使用内联 SVG（`viewBox="0 0 24 24"`，`stroke="currentColor"`），文本为中文标签
- **激活态**：紫色左边框 + 淡紫背景（`.nav-item.active`）
- **Hover 态**：背景色微亮过渡（`transition: background 0.15s`）

---

## 二、视觉设计系统（Visual Design System）

### 2.1 主题策略

当前为**强制暗色主题（Dark-only）**。设置页中存在 `darkMode` 开关，但仅持久化状态，未驱动任何全局 CSS 变量或类切换。

### 2.2 核心色板

所有色值为硬编码 Hex，无 CSS Custom Properties。

| 语义 | 色值 | 使用场景 |
|------|------|----------|
| 背景深层 | `#060B14` / `#0B0F19` | body、底层背景 |
| 背景卡片 | `#131827` / `#0F172A` / `#0f1525` | 卡片、面板、表格头部 |
| 主文本 | `#F1F5F9` / `#E2E8F0` / `#E0E6F1` | 标题、正文 |
| 次级文本 | `#94A3B8` / `#64748B` / `#cbd5e1` | 标签、提示、时间戳 |
| 主题紫（Accent） | `#8B5CF6` / `#7C3AED` / `#A78BFA` | 主按钮、激活态、边框高亮、图标 |
| 成功绿 | `#10B981` | 在线状态、成功、上涨 |
| 信息蓝 | `#60A5FA` / `#3B82F6` | 信息 badge、链接 |
| 警告琥珀 | `#F59E0B` / `#FCD34D` | 警告、pending |
| 错误红 | `#EF4444` / `#FCA5A5` | 错误、离线、删除 |
| 边框/分割线 | `rgba(148, 163, 184, 0.08~0.16)` | 通用细边框 |

### 2.3 排版

- **字体栈**：`'Noto Sans SC', 'Segoe UI', system-ui, -apple-system, BlinkMacSystemFont, sans-serif`
- **抗锯齿**：`-webkit-font-smoothing: antialiased`
- **无明确的类型比例（Type Scale）**：标题与正文字号由各个页面组件自行定义，常见值为 24px（页面标题）、18px（卡片标题）、14px（正文）、12px（辅助文本）

### 2.4 间距与圆角

| 元素 | 常见值 |
|------|--------|
| 卡片圆角 | `12px` ~ `16px` |
| 按钮圆角 | `8px` ~ `10px` |
| 输入框圆角 | `8px` |
| 卡片内边距 | `16px` ~ `24px` |
| 页面外边距 | `24px` ~ `32px` |
| 元素间隙（gap） | `8px` ~ `16px` |

### 2.5 图标系统

**无外部图标库依赖**（无 FontAwesome、Lucide、Material Icons）。

| 来源 | 使用方式 |
|------|----------|
| **内联 SVG 字符串** | TypeScript 方法返回 SVG 字符串，通过 `[innerHTML]` 绑定（10 个导航图标） |
| **行内 SVG** | 直接写在组件 template 中（顶部栏按钮） |
| **Emoji 字符** | 直接作为操作按钮文字（如 👁 查看、✎ 编辑、🗑 删除） |

SVG 风格：`viewBox="0 0 24 24"`，`fill="none"`，`stroke="currentColor"`，`stroke-width="2"`，通过父级 `color` 控制颜色。

---

## 三、布局模式（Layout Patterns）

### 3.1 页面级布局模板

几乎所有页面遵循同一模板：

```
Page
├── Page Header（标题 + 操作按钮）
├── Stat Cards Row（5~6 个统计卡片）
├── Filter Bar（搜索 + 筛选 + 排序）
├── Content Area（表格 / 网格 / 分栏）
└── Optional: Detail Drawer / Modal
```

### 3.2 统计卡片（Stat Card）

- 固定高度，圆角背景卡片
- 结构：**标题（小字，灰色）→ 主数值（大字，白色）→ 副标题/趋势（小字，带颜色箭头）**
- 趋势方向：`up`（绿）/ `down`（红）/ `neutral`（灰）
- 常见主题色：`good`（绿）、`warning`（琥珀）、`bad`（红）、`neutral`（灰）

### 3.3 表格（Data Table）

- 表头：`background: #0f1525`，文字灰色，字体略小
- 行高：约 52px
- Hover：`background: rgba(148,163,184,0.04)`
- 选中态：紫色左边框 + 淡紫背景
- 分页：页码按钮组（通常由前端本地分页实现）

### 3.4 两栏布局

用于 `memory.page.ts`、部分详情页：
- 左栏固定宽度（`320px` ~ `380px`）：列表 + 搜索
- 右栏自适应：`1fr`，展示详情
- 断点 `<768px` 时堆叠为单列

### 3.5 响应式断点

仅有两档媒体查询：
- `max-width: 1200px`：统计卡片从 5~6 列降为 3~4 列
- `max-width: 768px`：侧边栏隐藏、主内容区全宽、两栏堆叠、抽屉全屏

---

## 四、交互模式（Interaction Patterns）

### 4.1 模态框（Modal）

| 属性 | 实现 |
|------|------|
| 遮罩 | `position: fixed; inset: 0; background: rgba(2, 6, 23, 0.72); backdrop-filter: blur(8px); z-index: 40` |
| 内容框 | 固定定位居中，`translate(-50%, -50%)`，圆角 16px，阴影 `0 30px 80px rgba(0,0,0,0.45)` |
| 动画 | **无进入动画**，直接条件渲染显示 |
| 关闭 | 点击遮罩或 ✕ 按钮，设置 signal 为 `null` |
| 使用场景 | `knowledge.page.ts`（新建/编辑条目）、`memory.page.ts`（新建记忆） |

### 4.2 抽屉（Drawer / 侧边详情面板）

| 属性 | 实现 |
|------|------|
| 遮罩 | `.drawer-overlay`：`fixed inset-0`，半透明黑 |
| 面板 | `.drawer`：`fixed; top: 0; right: 0; width: 480px; height: 100vh; z-index: 50` |
| 动画 | `@keyframes slideIn { from { translateX(100%) } to { translateX(0) } }`，时长 `0.25s ease` |
| 关闭 | 点击遮罩或 ✕ 按钮 |
| 使用场景 | `knowledge.page.ts`（条目详情）、`tasks.page.ts`（任务详情）、`agents.page.ts`（Agent 详情） |

### 4.3 下拉菜单（Dropdown）

| 属性 | 实现 |
|------|------|
| 触发 | 按钮点击切换 `signal<boolean>` |
| 菜单位置 | `position: absolute; top: calc(100% + 6px); right: 0;` |
| 样式 | 圆角 8~10px，深色背景 `#1e293b`，阴影 `0 10px 30px rgba(0,0,0,0.4)` |
| 分隔线 | `.dropdown-divider`：1px 半透明线 |
| 危险项 | `.dropdown-item.danger`：红色文字 |
| 使用场景 | `swarm-management.page.ts`（操作菜单） |

### 4.4 按钮语义

| 类型 | 视觉特征 | 使用场景 |
|------|---------|---------|
| **Primary** | 紫底白字，`background: #7C3AED`，Hover 加深 | 主要操作（启动、保存、创建） |
| **Secondary** | 透明底 + 紫边框 | 次要操作（取消、返回） |
| **Ghost** | 透明底，Hover 微亮 | 工具栏图标按钮 |
| **Danger** | 红底或红字 | 删除、卸载、强制操作 |
| **Disabled** | 透明度降低，无 Hover 效果 | 表单未就绪或加载中 |

### 4.5 表单输入

- 输入框：`background: rgba(15, 23, 42, 0.6)`，圆角 8px，聚焦时紫色边框
- 下拉选择：与输入框同风格，选项列表深色浮层
- 开关（Toggle）：圆角长条，激活态为紫色
- 标签：灰色小字，位于输入框上方

### 4.6 状态徽章（Status Badge）

组件 `app-status-badge` 根据状态字符串自动映射颜色：

| 状态关键词 | 颜色 |
|-----------|------|
| `good`, `success`, `completed`, `online`, `active` | 绿色 |
| `warning`, `pending`, `idle`, `queued` | 琥珀色 |
| `bad`, `failed`, `error`, `offline`, `critical` | 红色 |
| `running`, `connecting`, `open` | 蓝色/紫色（呼吸动画） |
| 其他 | 灰色 |

### 4.7 实时指示器

- **Live Badge**：绿色圆点 + "LIVE" 文字，`pulse` 动画（`opacity` 1 ↔ 0.3）
- **Graph 活跃边**：`dashFlow` 动画（`stroke-dashoffset` 流动）
- **Graph 活跃节点**：`pulseRing` 动画（脉冲光环）

---

## 五、组件语义（Component Semantics）

### 5.1 可复用组件清单

| 组件 | 输入（@Input） | 输出（@Output） | 职责 |
|------|--------------|----------------|------|
| `app-stat-card` | `title`, `value`, `subtitle`, `trend`, `tone` | 无 | 统计卡片展示 |
| `app-mini-chart` | `color`, `data` | 无 | 迷你趋势图（SVG `polygon` + `polyline`） |
| `app-status-badge` | `status`, `label` | 无 | 状态徽章，自动映射颜色 |
| `app-graph-viewer` | `graph`, `activeNodeId` | 无 | SVG Agent 图可视化，支持拖拽、缩放、高亮 |
| `app-thought-graph-viewer` | `graph` | 无 | 思维图谱可视化，按 lane 布局（fact/reasoning/risk） |
| `app-json-viewer` | `label`, `depth`, `value` | 无 | JSON 树形查看器，支持递归折叠/展开 |

> **注意**：当前所有可复用组件均为**纯展示型**，仅有 `@Input`，无 `@Output` 或 `EventEmitter`。页面操作通过直接调用 `StateService` 方法完成。

### 5.2 页面组件模式

每个页面组件均为 Angular **standalone 组件**，遵循统一模式：

```ts
@Component({
  selector: 'app-xxx-page',
  standalone: true,
  imports: [CommonModule],
  template: `...`, // 内联模板
  styles: [`...`]  // 内联样式
})
export class XxxPageComponent {
  readonly state = inject(StateService);
  // 局部信号：搜索、筛选、分页、选中项
  readonly searchQuery = signal('');
  readonly selectedItem = signal<Item | null>(null);
  // 局部 computed：过滤、分页
  readonly filteredItems = computed(() => { ... });
}
```

---

## 六、状态管理与数据流语义

### 6.1 架构原则

- **单一状态源**：`StateService`（`providedIn: 'root'`）是全局唯一事实来源
- **信号驱动**：全面使用 Angular `signal` + `computed`，无 RxJS Subject/BehaviorSubject
- **自上而下的单向数据流**：`StateService` → Page 组件 → 可复用组件（通过 `@Input`）
- **组件自治局部状态**：每个页面组件仅保留局部 UI 状态（搜索词、分页、选中项）

### 6.2 状态域划分

| 域 | 代表信号 | 说明 |
|----|---------|------|
| **系统状态** | `apiBaseUrl`, `loading`, `error`, `health` | 全局加载、错误、探活 |
| **Swarm/图状态** | `swarms`, `selectedSwarm`, `selectedGraph`, `activeRun`, `streamState` | 当前选中 Swarm、Graph、运行实例、SSE 连接状态 |
| **执行配置** | `swarmExecutionPrompt`, `swarmRounds`, `metaMode`, `agentMessage` | 执行控制台表单状态 |
| **业务数据** | `agents`, `tasks`, `tools`, `events`, `logs`, `metrics`, `knowledge`, `memories` | 各域原始数据 + `xxxLoaded` 标志 |
| **Feed/实时** | `responseFeed`, `liveEvents` | API 审计日志（最多 15 条）、SSE 缓存（最多 20 条） |
| **设置** | `darkMode`, `compactMode`, `apiTimeout`, `autoReconnect` | localStorage 双写 |

### 6.3 数据加载语义

所有 `loadXxx()` 方法遵循统一模板：

```
1. 检查前置条件（如 swarmName 是否存在）
2. 调用 ApiService.xxx()
3. 成功 → 写入 signal → 设置 loaded=true → pushFeed() 审计日志
4. 失败 → 判断是否为离线错误 → 决定是否写入 error signal → pushFeed() 记录失败
```

### 6.4 降级策略（Graceful Degradation）

每个 `derivedXxx()` computed 实现了 **"API 数据优先，离线/无数据时自动降级"**：

| Computed | 降级来源 |
|----------|---------|
| `derivedAgents` | `swarm.agent_files` + `graph.nodes` + `activeRun` + `responseFeed` |
| `derivedTasks` | `activeRun` + `responseFeed` |
| `derivedTools` | `graph.ToolNode` |
| `derivedEvents` | `liveEvents` + `responseFeed` |
| `derivedMetrics` | `responseFeed` + `liveEvents`（Fallback 指标生成） |
| `derivedLogs` | `responseFeed` |

> **语义保证**：UI 永不白屏。即使后端完全不可用，页面仍能基于已有状态和 Feed 历史展示估算数据。

### 6.5 SSE 实时流语义

```
用户点击"启动结构"
→ StateService.startSwarmStructure()
→ ApiService.startSwarmBackground() → 返回 run 快照
→ activeRun.set(run)
→ watchRun(run) 建立 EventSource
→ SSE 事件流入 liveEvents signal
→ derivedEvents / derivedMetrics / activeRunNodeId 自动重算
→ UI 实时更新（Agent 图高亮当前节点、执行轨迹追加、统计变化）
```

SSE 连接状态机：
- `idle` → `connecting` → `open` → (`closed` | `error`)
- `error` + `autoReconnect=true` → 定时重连（`reconnectInterval` 秒）

---

## 七、设置与持久化语义

### 7.1 本地存储（localStorage）

键前缀：`angelus_`

| 键 | 类型 | 语义 |
|----|------|------|
| `angelus_apiBaseUrl` | string | API 根地址 |
| `angelus_apiTimeout` | number | 请求超时秒数 |
| `angelus_reconnectInterval` | number | SSE 重连间隔秒数 |
| `angelus_autoReconnect` | boolean | SSE 断线自动重连 |
| `angelus_darkMode` | boolean | 深色模式开关（当前未驱动样式） |
| `angelus_compactMode` | boolean | 紧凑布局 |
| `angelus_showDebug` | boolean | 显示调试信息 |
| `angelus_language` | string | 界面语言 |

### 7.2 设置同步语义

```
应用启动
→ loadSettings() 从 localStorage 读取 → 写入 signals
→ 调用 syncApiSettingsFromBackend() 获取后端 /settings
→ 若后端成功 → 覆盖本地 signals → 回写 localStorage
→ 若后端失败 → 保留本地状态，静默降级

用户修改设置
→ 页面局部 signal 变化（双向绑定）
→ 点击"保存"
→ StateService.saveSettings()
→ 1. 写 localStorage
→ 2. 调 API PUT /settings
→ 3. 成功后再次同步 signals + localStorage
→ 4. 显示 "已保存" 提示（2 秒后消失）
```

---

## 八、关键用户旅程（User Journeys）

### 8.1 首次进入系统

```
打开应用 → 加载 Overview 页
→ StateService.init() 触发
→ 并行加载：index / health / ready / listSwarms
→ 自动选中第一个 Swarm
→ 级联加载：events / logs / metrics / knowledge / memory
→ 概览页展示：统计卡片 + Swarm 列表 + Agent 图
```

### 8.2 切换 Swarm

```
用户点击侧边栏 Swarm 列表项 / 概览页 Swarm 卡片
→ state.selectSwarm(name)
→ selectedSwarmName.set(name)
→ reloadSelectedSwarm() 触发
→ 6 个并行 API 请求：graph / thought-graph / agents / tasks / tools / stats
→ 所有 derived computed 自动重算
→ 当前页面（无论哪个）UI 更新为新 Swarm 的数据
```

### 8.3 启动一次运行

```
用户在 Overview 页填写执行目标与上下文
→ 选择输出风格、轮次、是否 Meta 模式
→ 点击"启动结构"
→ StateService.startSwarmStructure()
→ POST /swarms/{name}/start/background
→ activeRun.set(run) + watchRun(run)
→ SSE 连接建立
→ Agent 图通过 activeRunNodeId 高亮当前执行节点
→ 事件页实时追加事件
→ 运行完成后 activeRun 状态更新为 completed/failed
```

### 8.4 调试单个 Agent

```
用户在 Overview 页选择 Agent、输入消息、设置轮次
→ 点击"Agent 调试"
→ StateService.runAgentRound()
→ POST /swarms/{name}/agents/{id}/round
→ pushFeed() 记录成功/失败
→ 结果展示在响应记录区
```

### 8.5 管理知识/记忆

```
用户进入 Knowledge / Memory 页
→ 浏览列表（搜索 + 筛选）
→ 点击"新建" → 弹出 Modal
→ 填写表单 → 点击保存
→ ApiService.createKnowledge() / createMemory()
→ 成功后刷新列表 → Modal 关闭
→ 点击条目 → 右侧 Drawer 展示详情
→ 点击编辑 → 弹出 Modal（预填数据）
→ 点击删除 → window.confirm() 确认 → ApiService.deleteXxx()
```

---

## 九、待完善与已知限制

| 限制 | 说明 | 建议方向 |
|------|------|---------|
| **无亮色模式** | `darkMode` 信号存在但未驱动样式 | 建立 CSS 变量体系，替换硬编码色值 |
| **无 Toast 系统** | 状态反馈依赖内联 banner 和按钮文字 | 开发全局 Overlay Toast Service |
| **样式高度重复** | `.btn`、`.stat-card`、`.panel-card` 在每个页面重复定义 | 提取为全局 CSS 工具类或共享 Sass mixin |
| **无 CSS 变量** | 主题切换和维护成本高 | 引入 `:root` CSS Custom Properties |
| **前端分页不完整** | 多数页面前端分页逻辑存在但 UI 缺少页码控件 | 统一分页组件 |
| **时间过滤未实现** | `filterDateRange` 在 UI 中可选但过滤逻辑为空 | 补充 `filteredTasks` 等 computed 中的时间过滤 |
| **平均耗时占位** | `avgDuration` 统计显示为 `-` | 后端补充真实耗时统计或前端基于事件计算 |

---

## 十、术语对照表

| 前端界面用语 | 英文/代码对应 | 后端对应概念 |
|-------------|--------------|-------------|
| 概览 | Overview | `index` + `health` + `listSwarms` |
| Swarm | Swarm | `SwarmManifest` + `LoadedSwarm` |
| 智能体 | Agent | `Agent` / `AgentNode` |
| 任务 | Task | `Task`（一等实体）/ `TaskGraph` |
| 知识库 | Knowledge | `knowledge.json` 条目 |
| 记忆 | Memory | `memory.json` 条目 |
| 事件 | Event | `ExecutionEvent`（SSE 推送） |
| 日志 | Log | `events.jsonl` / `RunRecord.events` |
| Agent 图 | Agent Graph | `ExecutionGraph` 派生的纯 Agent 拓扑 |
| 执行轨迹图 | Execution Trace Graph | `RunRecord` / execution events |
| 思维图谱 | Thought Graph | `CognitiveGraph` |
| 任务图谱 | Task Graph | `TaskGraph` |
| 运行 | Run | `RunRecord`（`run_id`） |
| 结构 | Structure | `graph.run()` 执行 |
| 调试 | Round | `agent.round_call()` |
