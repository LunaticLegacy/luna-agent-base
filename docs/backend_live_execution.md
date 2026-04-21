# 后端实时执行接口

本文档补充当前后端的“C 方案”实时执行能力。

目标是把一次 swarm 执行拆成三层：

- 静态图快照
- 异步 run session
- SSE 实时事件流

## 1. 总体流程

```mermaid
flowchart TD
    A[POST /api/swarms/<swarm>/runs] --> B[RunRegistry 创建 run_id]
    B --> C[后台线程 asyncio.run(graph.run)]
    C --> D[GraphExecutor 发出 run/node/branch 事件]
    D --> E[RunRecord 缓存当前状态与事件]
    E --> F[GET /api/runs/<run_id> 查询状态]
    E --> G[GET /api/runs/<run_id>/events 订阅 SSE]
```

## 2. 新增接口

### 2.1 `GET /api/swarms/<swarm_name>/graph`

返回当前执行图的静态快照。

用途：

- 前端先绘制完整图
- 再叠加当前运行态

### 2.2 `POST /api/swarms/<swarm_name>/runs`

启动一个异步运行会话。

行为：

- 读取请求体里的 `input` 和 `rounds`
- 创建 `run_id`
- 立即返回 `202 Accepted`
- 后台继续执行图

返回字段：

- `run.run_id`
- `run.status`
- `run.events_url`
- `run.status_url`

### 2.3 `GET /api/runs/<run_id>`

查询运行会话当前状态。

适合：

- 轮询更新
- 调试
- 后端状态页

### 2.4 `GET /api/runs/<run_id>/events`

订阅 SSE 事件流。

前端可据此实时更新：

- 当前节点高亮
- 分支执行状态
- trace 面板
- 错误提示

流式连接建立后，后端会先推送一条 `run.snapshot`，再持续推送后续事件。

## 3. 事件类型

当前后端会发这些事件：

- `run.started`
- `node.started`
- `node.completed`
- `node.failed`
- `branch.started`
- `branch.completed`
- `branch.failed`
- `run.completed`
- `run.failed`

## 4. run 状态

run session 的状态字段会在这些值之间切换：

- `queued`
- `running`
- `completed`
- `failed`

## 5. 状态快照

`GET /api/runs/<run_id>` 返回的快照包含：

- `current_node_id`
- `current_node_name`
- `current_node_type`
- `rounds`
- `state`
- `final_state`
- `event_count`

其中：

- `state` 是当前进度快照
- `final_state` 只在 run 结束后有值

## 6. 同步与异步的关系

现有同步接口仍保留：

- `POST /api/swarms/<swarm_name>/run`

它仍然直接返回最终结果，方便旧调用方和简单调试。

新的异步接口用于实时可视化和前端追踪。

## 7. 实现要点

- `ExecutionGraph.run(...)` 现在支持 `run_id`、`swarm_name` 和 `event_sink`
- `GraphExecutor` 会在节点开始、完成、失败和分支处理时发事件
- `RunRegistry` 在内存中缓存运行状态和事件
- SSE 端点会先推送一条 `run.snapshot`，再持续推送后续事件
