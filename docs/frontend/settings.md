# Settings 页面实现现状

本文只记录 `frontend/angelus/src/app/pages/settings.page.ts` 以及其依赖的 `state.service.ts`、`api.service.ts` 中与 Settings 板块相关的实现现状。

## 1. 页面定位

当前 `Settings` 页面是一个配置面板，支持以下两类设置：

- **API 配置**（已连接真实行为）
  - 后端 API 地址
  - API 超时（秒）
  - SSE 重连间隔（秒）
  - 自动重连 SSE 流
- **显示设置**（已连接真实行为）
  - 深色模式
  - 紧凑布局
  - 显示调试信息
  - 语言

所有设置均已接入 `localStorage` 持久化，点击"保存更改"后生效并保留。

## 2. 设置持久化模型

`StateService` 通过 `localStorage` 前缀 `angelus_` 保存以下字段：

| 字段 | 类型 | 默认值 | 生效范围 |
|---|---|---|---|
| `apiBaseUrl` | string | `/api` | 全局 API 请求基址 |
| `apiTimeout` | number | `30` | HTTP 请求超时（秒） |
| `reconnectInterval` | number | `5` | SSE 断开后重连等待（秒） |
| `autoReconnect` | boolean | `true` | SSE 断开后是否自动重连 |
| `darkMode` | boolean | `true` | 页面明暗主题 |
| `compactMode` | boolean | `false` | 布局紧凑程度 |
| `showDebug` | boolean | `false` | 是否展示调试信息 |
| `language` | string | `zh` | 界面语言 |

### 加载时机

`StateService.init()` 会在应用初始化时调用 `loadSettings()`，从 `localStorage` 恢复所有已保存的值。

### 保存时机

用户点击 Settings 页面的"保存更改"按钮时，调用 `StateService.saveSettings(...)`，一次性写入所有设置到 `localStorage`，并触发 `settingsSaved` 信号（2 秒后自动清除）。

## 3. 各设置项的真实行为

### 3.1 后端 API 地址

- 保存后立即更新 `apiBaseUrl` signal
- 后续所有 `ApiService` 调用都会使用新地址
- 不会回写到后端配置文件

### 3.2 API 超时

- 保存后写入 `angelus_apiTimeout`
- `timeout.interceptor.ts` 会从 `localStorage` 读取该值
- 使用 rxjs `timeout` 操作符为每个 HTTP 请求添加超时限制
- 超时后会抛出状态码为 0 的 `HttpErrorResponse`，错误消息包含"请求超时"

### 3.3 SSE 重连间隔 & 自动重连

- `StateService.watchRun()` 创建 `EventSource` 监听实时事件流
- 当连接断开（`onerror`）时，如果 `autoReconnect` 为 `true`，会在 `reconnectInterval` 秒后自动重新创建连接
- 重连计时器在 `closeStream()` 或组件销毁时会被清理

### 3.4 深色模式

- 保存后立即调用 `applyTheme()`
- 为 `document.body` 添加/移除 `dark` 或 `light` class
- 实际样式变化需要项目 CSS 中定义对应的 `.dark` / `.light` 规则

### 3.5 紧凑布局 / 显示调试信息 / 语言

- 保存后持久化到 `localStorage`
- 当前 UI 层已读取这些信号，但部分子组件可能尚未完全响应
- 这些设置属于前端运行时偏好，不影响后端行为

## 4. 保存按钮的行为

`saveSettings()` 执行以下动作：

1. 收集页面当前所有设置值
2. 调用 `StateService.saveSettings({...})`
3. 写入 `localStorage`
4. 应用主题变更
5. 触发 `settingsSaved` 信号，页面右上角显示"✓ 已保存"（2 秒后消失）

如果 `localStorage` 不可用（如隐私模式），保存操作会静默失败，不会抛出错误。

## 5. 系统信息区

`系统信息` 区块当前都是展示型字段：

- `版本`：写死为 `v1.0.0-alpha`
- `Angular`：写死为 `19.0.0`
- `Node.js`：写死为 `v20.x`
- `构建时间`：组件实例化时用 `new Date().toLocaleString('zh-CN')` 生成
- `API 状态`：根据 `state.health()?.status === 'ok'` 显示在线 / 离线

其中只有 `API 状态` 会跟后端健康检查结果联动，其他都是静态文本或一次性生成值。

## 6. 系统状态区

`系统状态` 区块是只读的，直接从 `StateService` 读取：

- `后端健康`：`state.health()`
- `就绪状态`：`state.ready()`
- `Swarm 数量`：`state.swarms().length`
- `Agent 总数`：`state.totalAgents()`

## 7. 当前限制

- 设置目前只保存在浏览器本地，不会同步到后端配置
- 多浏览器/多设备之间不会共享设置
- `language` 切换只持久化值，完整国际化需要后续补充翻译文件
- `compactMode` 和 `showDebug` 的信号已就绪，但部分子组件可能尚未响应

## 8. 与 `ApiService` 的关系

`ApiService` 本身没有直接读取 Settings，但：

- 所有 API 地址通过 `StateService.baseUrl()` 间接使用
- HTTP 超时通过 `timeout.interceptor.ts` 从 `localStorage` 读取，无需修改 `ApiService`
- SSE 重连逻辑直接在 `StateService.watchRun()` 中实现
