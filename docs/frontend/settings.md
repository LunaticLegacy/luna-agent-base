# Settings 页面实现现状

本文只记录 `frontend/angelus/src/app/pages/settings.page.ts` 以及其依赖的 `state.service.ts`、`api.service.ts` 中与 Settings 板块相关的实现现状。

## 1. 页面定位

当前 `Settings` 页面更像是一个“设置面板外壳”，而不是完整的系统配置中心。

页面里确实展示了多项配置项，但就现有代码来看，真正会影响全局运行的只有 API Base URL；其余大多数开关、输入框和下拉框目前都只是本地 UI 状态。

页面本身已经挂载到路由：

- `GET /settings`

对应的组件是：

- [`frontend/angelus/src/app/pages/settings.page.ts`](../../frontend/angelus/src/app/pages/settings.page.ts)

## 2. 页面结构

`SettingsPage` 当前由四个区块组成：

1. 顶部标题区
   - 标题：`系统设置`
   - 副标题：`配置 API 端点、系统参数和个性化选项`
   - 右上角有一个 `保存更改` 按钮

2. `API 配置`
   - 后端 API 地址
   - API 超时
   - SSE 重连间隔
   - 自动重连 SSE 流

3. `系统信息`
   - 版本
   - Angular 版本
   - Node.js 版本
   - 构建时间
   - API 状态

4. `显示设置`
   - 深色模式
   - 紧凑布局
   - 显示调试信息
   - 语言

5. `系统状态`
   - 后端健康
   - 就绪状态
   - Swarm 数量
   - Agent 总数

## 3. 配置项现状

### 3.1 真正会生效的配置

当前只有 `后端 API 地址` 会在点击保存后写回全局状态。

页面初始化时：

- `apiUrl` 会从 `state.apiBaseUrl()` 读取初始值

点击 `保存更改` 时：

- 调用 `state.setApiBaseUrl(this.apiUrl())`

`StateService` 里的实现是：

- [`frontend/angelus/src/app/services/state.service.ts`](../../frontend/angelus/src/app/services/state.service.ts)

它会把值写入 `apiBaseUrl` 这个 signal，并做一次简单清洗：

- 去掉首尾空白
- 为空时回退到 `/api`

这意味着：

- 之后所有依赖 `baseUrl()` 的接口调用都会改用新地址
- 这个改动只存在于当前前端运行时内存里
- 页面代码里没有把它持久化到 `localStorage`
- 也没有回写到后端配置接口

### 3.2 只存在于 UI 的配置

下面这些字段目前只是页面本地状态，没有接到 `StateService` 或 `ApiService` 的实际逻辑：

- `API 超时 (秒)` -> `apiTimeout`
- `SSE 重连间隔 (秒)` -> `reconnectInterval`
- `自动重连 SSE 流` -> `autoReconnect`
- `深色模式` -> `darkMode`
- `紧凑布局` -> `compactMode`
- `显示调试信息` -> `showDebug`
- `语言` -> `language`

它们虽然能在界面上切换，但当前代码里没有看到：

- 持久化保存
- 应用到全局主题
- 应用到 HTTP 超时
- 应用到 SSE 自动重连逻辑
- 应用到调试信息开关
- 应用到语言切换

换句话说，这些都是“可点、可改、但不会真正驱动系统行为”的字段。

## 4. 运行时行为

### 4.1 API 地址的作用范围

`StateService` 中所有数据加载都通过 `baseUrl()` 取值，再传给 `ApiService`。

因此，只要修改了 `apiBaseUrl`：

- 后续的 `loadOverview()`
- `loadAgents()`
- `loadTasks()`
- `loadTools()`
- `loadEvents()`
- `loadLogs()`
- `loadMetrics()`
- `loadKnowledge()`
- `loadMemory()`
- 以及 Swarm 相关操作

都会指向新的前端 API 基址。

### 4.2 保存按钮不会触发额外动作

当前 `saveSettings()` 只做了一件事：

- 更新 `StateService` 的 API Base URL

它没有做这些事情：

- 重新拉取页面数据
- 重新连接 SSE
- 触发页面刷新
- 写入本地存储
- 调用后端保存配置

所以它更像是“更新运行时基址”，不是“提交一份持久化配置”。

### 4.3 系统状态是只读的

页面里的 `系统状态` 区块只是从 `StateService` 直接读值：

- `state.health()`
- `state.ready()`
- `state.swarms().length`
- `state.totalAgents()`

这里没有编辑入口，也没有从设置页反向修改这些状态的逻辑。

## 5. 系统信息区说明

`系统信息` 区块当前都是展示型字段：

- `版本`：写死为 `v1.0.0-alpha`
- `Angular`：写死为 `19.0.0`
- `Node.js`：写死为 `v20.x`
- `构建时间`：组件实例化时用 `new Date().toLocaleString('zh-CN')` 生成
- `API 状态`：根据 `state.health()?.status === 'ok'` 显示在线 / 离线

其中只有 `API 状态` 会跟后端健康检查结果联动，其他都是静态文本或一次性生成值。

## 6. `ApiService` 与 Settings 的关系

`ApiService` 本身没有任何“设置保存”接口，也没有 settings 专用 CRUD。

它做的事情主要是：

- 拼接 API 地址
- 发起请求
- 提供系统各模块的读写接口

因此 Settings 页面目前并不是通过后端接口保存配置，而只是通过 `StateService.setApiBaseUrl()` 修改运行时基址。

从这个角度看，Settings 页面对 `ApiService` 的影响是间接的：

- 先改 `apiBaseUrl`
- 再让所有后续请求走新的 base URL

## 7. 现在能做什么

- 修改前端当前运行时的 API Base URL
- 查看后端健康、就绪、Swarm 数量和 Agent 总数
- 直观看到 API 是否在线
- 在 UI 上切换几个“看起来像设置项”的选项

## 8. 现在还不能做什么

- 不能把设置真正持久化到本地存储
- 不能把设置保存到后端
- 不能让 `apiTimeout` 真正控制请求超时
- 不能让 `reconnectInterval` 真正控制 SSE 重连
- 不能让 `autoReconnect` 真正接管实时流重连策略
- 不能让 `darkMode`、`compactMode`、`showDebug`、`language` 真正驱动全局行为
- 不能在设置页里重新拉取全部数据或立即应用除 API Base URL 外的其他配置

