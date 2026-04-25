# 后端 Catalog 与 Content

这份文档只描述当前代码里的真实实现，范围是：

- `web/catalog.py`
- `web/routes/catalog.py`
- `web/content_store.py`
- `web/routes/content.py`

在应用启动时，这两组蓝图都会挂到 `/api` 前缀下，所以这里写的路径都是实际对外可访问的 URL。

## 一、Catalog 接口总览

`web/routes/catalog.py` 提供的是“只读型聚合接口”，主要从运行时注册表 `angelus_runtime` 里拼装数据。

当前接口如下：

- `POST /api/catalog/swarms/<swarm_name>/agents/search`
- `POST /api/swarms/<swarm_name>/tasks/search`
- `POST /api/catalog/tools/search`
- `GET /api/catalog/swarms/<swarm_name>/stats`
- `POST /api/catalog/events/search`
- `POST /api/catalog/logs/search`
- `POST /api/catalog/metrics`

这些接口本身不改写数据，只负责把 runtime registry、swarm graph、run events 和工具对象整合成前端需要的列表与统计。搜索、筛选和分页条件统一放在 JSON body 里，路径只表达资源身份。

## 二、Agents 是怎么构造的

`POST /api/catalog/swarms/<swarm_name>/agents/search` 会先调用 `build_agent_catalog(swarm, registry.runs.list_runs(swarm_name))`。

构造来源主要有三层：

- `swarm.core.list_agents()` 提供 agent 实例
- `swarm.core.get_execution_graph()` 提供图里的 `AgentNode`
- `registry.runs.list_runs(swarm_name)` 提供历史 run 的事件，作为活动统计来源

### 返回字段

每个 agent item 主要包含：

- `id`
- `name`
- `status`
- `type`
- `capabilities`
- `tags`
- `tasks_executed`
- `success_rate`
- `avg_response_time_ms`
- `token_usage_total`
- `last_activity`

### 计算规则

- `status`
  - 有进行中的 run 时是 `busy`
  - 有失败但没有成功完成时是 `error`
  - 从未执行过时是 `offline`
  - 其他情况是 `online`
- `type`
  - 优先取 node metadata 里的 `role` / `type`
  - 否则根据 agent id 关键词猜测：
    - `plan / coord / orch / organ` -> `coordinator`
    - `review` -> `reviewer`
    - `research / search / inspect` -> `specialist`
    - 默认 `worker`
- `capabilities`
  - 优先取 node metadata 里的 `capabilities`
  - 否则取 agent 自身 `tools`
  - 再不行就按 role 给默认值
- `tags`
  - 优先取 node metadata 里的 `tags`
  - 没有的话按角色补一个默认 tag，`coordinator` 和 `reviewer` 偏 `core`，其他偏 `system`
- `tasks_executed`
  - 来自运行事件里的 `node.started / node.completed / node.failed`
- `success_rate`
  - `completed / executions * 100`
- `avg_response_time_ms`
  - 有完成事件时按累计耗时除以完成次数
  - 没有活动统计时按能力数量给一个估算值
- `token_usage_total`
  - 先从 agent 的 context snapshot 粗算 token
  - 再加上 `executions * 1200`
- `last_activity`
  - 优先用活动记录里的 `last_seen`
  - 没有时回退到图文件的修改时间

### 接口侧过滤

`/api/catalog/swarms/<swarm_name>/agents/search` 还支持在 JSON body 里传入 route 层二次过滤条件：

- `q`
- `status`
- `type`
- `capability`
- `tag`

过滤是字符串包含匹配，不是严格枚举。

## 三、Tasks 是怎么构造的

`POST /api/swarms/<swarm_name>/tasks/search` 调用 `build_task_catalog(...)`。swarm 由路径确定，筛选和分页条件放在 JSON body。

任务不是单独的数据库表，而是来自每个 swarm 的任务图谱（Task Graph）快照，再结合 run 事件填充状态和日志。

### 数据来源

- `registry.swarms.values()` 遍历所有 swarm
- `loaded_swarm.core.get_task_graph()` 或任务图谱快照拿节点
- `registry.runs.list_runs(swarm_name)` 构造活动索引
- 图文件的 mtime 作为 `reference_time`

### 返回字段

每个 task item 主要包含：

- `id`
- `name`
- `status`
- `priority`
- `executor`
- `duration_ms`
- `created_at`
- `description`
- `input`
- `output`
- `logs`
- `swarm`
- `failed_count`
- `completed_count`
- `executed_count`

### 状态与优先级

- `status`
  - 基于活动索引里的执行情况计算
  - `AgentNode` 有 active run 时会被强制标成 `running`
  - `AgentNode` 从未执行过且无 active run 时是 `pending`
  - 节点层没有显式成功/失败时，会从 `node.completed / node.failed` 推导
- `priority`
  - 优先从 node metadata 里读取
  - 没有时：
    - `AgentNode` 默认偏高
    - 其他节点默认 `medium`

### 日志和输入输出

- `input` 来自最近一次 `node.started` 的 `input_payload`
- `output` 来自最近一次 `node.completed` 的 `output_payload`
- `logs` 是活动索引里收集的短日志，最多保留最近 8 条

### 查询与分页

支持的查询参数：

- `swarm`
- `status`
- `priority`
- `executor`
- `from`
- `to`
- `q`
- `page`
- `limit`

其中：

- `from` / `to` 会按 ISO 时间过滤 `created_at`
- `q` 会同时搜 id、name、description、executor、input、output 和日志消息
- 返回值包含 `total`、`page`、`limit`、`items`、`stats`
- `stats` 里有 `pending / running / success / failed / avg_duration_ms`

## 四、Tools 是怎么构造的

`POST /api/catalog/tools/search` 调用 `build_tool_catalog(...)`。

这里的 tool 不是从外部工具市场读来的，而是从每个 swarm 的 `core.tools` 实例拼出来。

### 数据来源

- `loaded_swarm.core.tools.items()`
- 图里对应的 `ToolNode`
- 历史 run events 形成的活动索引
- 工具类自身的 `schema` 或 `get_openai_schema()`

### 返回字段

每个 tool item 主要包含：

- `id`
- `name`
- `swarm`
- `type`
- `status`
- `description`
- `calls`
- `avg_ms`
- `last_call`
- `success_rate`
- `error_rate`
- `created_at`
- `schema`

### 计算规则

- `type`
  - 名字、描述、模块名里有 `web / search / http / api` 的，归为 `API`
  - 其他归为 `本地`
- `status`
  - 只要统计到失败就标 `error`
  - 否则标 `online`
- `calls`
  - 来自活动索引中的 `executions`
- `avg_ms`
  - 有完成记录时按耗时均值计算
  - 没有完成但有执行记录时用估算值
- `last_call`
  - 优先用活动索引里的 `last_seen`
  - 没有时回退到工具源码文件的 mtime
- `schema`
  - 优先取 `get_openai_schema()` 里的 `function.parameters`
  - 没有时取 `tool.schema`

### 过滤

支持：

- `type`
- `status`
- `q`
- `swarm`

`q` 会搜 id、name、description、schema 和 swarm 名称。

### 汇总统计

返回的 `stats` 包含：

- `total`
- `available`
- `api`
- `local`
- `today_calls`

## 五、Events 与 Logs 的来源

`POST /api/catalog/events/search` 和 `POST /api/catalog/logs/search` 都基于同一批 observability items。

### 事件来源

观测项是从两种地方收集的：

- 每个 swarm 包目录下的 `runtime_info/events.jsonl`
- 所有 run 的 `record.events`

### Event item 如何生成

`build_event_catalog(...)` 先收集完整 observability items，再按条件过滤、分页。

生成规则大致是：

- `runtime_info/events.jsonl`
  - 解析每行 JSON
  - 变成 runtime 级别事件
- `record.events`
  - 变成 run 级别事件
  - 会保留 `run_id`、`node_id`、`node_name`、`node_type`、`data` 等信息

### Event 返回字段

`POST /api/catalog/events/search` 的 item 主要包含：

- `id`
- `time`
- `level`
- `source`
- `event`
- `detail`
- `data`

统计里会返回：

- `today`
- `errors`
- `warnings`
- `infos`

### Log 返回字段

`POST /api/catalog/logs/search` 也是从同一批 observability items 派生，但字段更偏日志表格：

- `id`
- `time`
- `level`
- `service`
- `message`

其中 `message` 是把 event 名和 detail 拼在一起得到的。

### 过滤参数

这些过滤项通过 JSON body 传入，不使用 query string。

`/api/events` 支持：

- `level`
- `source`
- `from`
- `to`
- `q`
- `page`
- `limit`

`/api/logs` 支持：

- `level`
- `service`
- `from`
- `to`
- `q`
- `page`
- `limit`

两者都按时间倒序排序后再分页。

## 六、Metrics 是怎么构造的

`POST /api/catalog/metrics` 调用 `build_metrics_catalog(...)`。

它不是读 Prometheus 或时序库，而是基于历史 run events 做一个“推导型指标面板”。

### 输入参数

- `window`
- `resolution`

### 处理方式

- `window` 默认 `1h`
- `resolution` 默认 `1m`
- 这两个值都会被解析成秒数
- 最多生成 240 个 bucket
- bucket 的起点取所有 run / event 里最晚时间往前推一个窗口

### 返回值

返回结构是：

- `success`
- `window`
- `resolution`
- `series`

`series` 里有：

- `cpu_percent`
- `memory_mb`
- `request_latency_ms`
- `throughput_rps`
- `token_usage`
- `error_rate`

### 指标口径

这些数值全部是按事件类型推出来的：

- `run.started`
- `run.completed`
- `run.failed`
- `node.started`
- `node.completed`
- `node.failed`

比如：

- CPU 和内存是按活动量、事件数、失败数、token 估算出来的
- latency 是按节点开始/完成时间差估出来的
- throughput 是每个 bucket 内的完成速率
- error_rate 是失败事件占比

## 七、Swarm Stats 是怎么构造的

`GET /api/catalog/swarms/<swarm_name>/stats` 调用 `build_swarm_stats(registry, swarm_name)`。

这是一个 swarm 级别的聚合接口，把 agents、tasks、runs、资源序列合并成一个 dashboard 视图。

### 返回字段

- `success_rate`
- `throughput`
- `token_usage`
- `task_distribution`
- `resource_usage`
- `run_count`
- `active_runs`
- `agent_count`
- `tool_count`

### 计算规则

- `success_rate`
  - 完成 run 中没有 error 的占比
- `throughput`
  - 以 completed run 的时间跨度估算每小时完成量
  - 没有足够时间点时退化为完成 run 数
- `token_usage`
  - 直接取 agent 统计里的 `token_usage_total`
- `task_distribution`
  - 直接来自 `build_task_catalog(...).stats`
  - 其中 `success` 会被改名成 `completed`
- `resource_usage`
  - 由 `_build_resource_usage_series()` 生成
  - 返回 `cpu_percent` 和 `memory_mb` 两条数组

## 八、Content Store 与持久化

`web/routes/content.py` 提供的是可读写接口，底层是 `web/content_store.py` 里的 `ContentStore`。

应用启动时，`ContentStore.from_runtime_registry(...)` 会被挂到 `current_app.extensions["angelus_content"]`，所以 route 层能直接拿到同一个 store 实例。

### 数据文件

当前持久化文件是：

- `data/knowledge.json`
- `data/memory.json`

初始化时如果这两个文件不存在或为空，`ContentStore` 会先从 runtime registry 里 seed 一份初始数据，再写回文件。

### 写盘方式

所有写操作都会走同一套原子落盘逻辑：

- 先写到同目录的临时文件
- 再 `replace()` 覆盖目标文件

所以一次变更是整文件更新，不是增量 patch。

## 九、Knowledge CRUD

### 路由

- `POST /api/knowledge/search`
- `GET /api/knowledge/<knowledge_id>`
- `POST /api/knowledge`
- `PUT /api/knowledge/<knowledge_id>`
- `DELETE /api/knowledge/<knowledge_id>`

### 列表

`list_knowledge()` 支持：

- `type`
- `source`
- `tag`
- `q`
- `page`
- `limit`

返回结构包含：

- `total`
- `page`
- `limit`
- `items`
- `stats`

其中 `stats` 会统计：

- `total`
- `documents`
- `vectors`
- `rules`

### 单条读取

按 `id` 精确查找，找不到会抛 `KeyError`，最终由 API 层转成错误响应。

### 创建与更新

`create_knowledge()` 会：

- 先规范化 payload
- 自动补默认值
- 生成新的 `id`，除非请求里显式传了 `id`
- 检查 `id` 是否重复
- append 到内存列表
- 立即写回 `data/knowledge.json`

`update_knowledge()` 会：

- 按 `id` 找到已有条目
- 合并 payload，但保留原始 `id` 和 `created_at`
- 重新规范化字段
- 覆盖内存列表中的该条记录
- 写回文件

### 删除

`delete_knowledge()` 会：

- 按 `id` 删除
- 返回被删除的完整条目
- 立刻写回文件

### Knowledge 规范化字段

每条 knowledge 最终会被整理成：

- `id`
- `title`
- `type`
- `source`
- `tags`
- `status`
- `citations`
- `created_at`
- `content`
- `meta`
- `related`

其中 `meta` 里会补：

- `author`
- `version`
- `updated_at`
- `size`

## 十、Memory CRUD

### 路由

- `POST /api/memory/search`
- `GET /api/memory/<memory_id>`
- `POST /api/memory`
- `DELETE /api/memory/<memory_id>`

### 列表

`list_memory()` 支持：

- `type`
- `source`
- `q`
- `page`
- `limit`

返回结构同样包含：

- `total`
- `page`
- `limit`
- `items`
- `stats`

其中 `stats` 会统计：

- `total`
- `active`，近 30 天内的记录数
- `avg_importance`
- `long_term`
- `working`

### 创建与删除

`create_memory()` 会：

- 规范化 payload
- 自动补 `id`
- 检查重复 id
- append 到内存列表
- 写回 `data/memory.json`

`delete_memory()` 会：

- 按 `id` 删除
- 返回被删除的完整条目
- 写回文件

### Memory 规范化字段

每条 memory 最终会被整理成：

- `id`
- `summary`
- `content`
- `timestamp`
- `type`
- `source`
- `sentiment`
- `importance`
- `related_ids`

## 十一、Knowledge / Memory 的默认种子数据

如果初始文件为空，`ContentStore` 不会返回空库，而是先从 runtime registry 生成 seed 数据：

- knowledge 会根据每个 swarm 的 Agent 图或任务图谱生成：
  - 一个 graph overview 文档
  - 若干 node metadata 文档
- memory 会根据历史 run 生成：
  - 一条运行快照
  - 少量关键事件快照

所以这两类内容在“首次启动”时就会有一批系统数据。

## 十二、实现上的几个关键点

- catalog 接口和 content 接口是两套不同职责的后端：
  - catalog 偏运行时聚合，只读
  - content 偏知识/记忆，支持持久化写入
- `agents / tasks / tools / events / logs / metrics / stats` 都是从 runtime registry 和 run events 推导出来的，不依赖独立数据库表
- knowledge 和 memory 是唯一明确落盘到 `data/*.json` 的内容模型
- 所有写入都是整文件原子替换，不是数据库事务
