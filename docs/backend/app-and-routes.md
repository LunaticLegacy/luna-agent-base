# 后端入口与路由总览

这份文档只描述当前代码里“后端是怎么启动的、路由是怎么挂上去的、最终对外暴露了哪些 URL”。它不是完整的业务参考，也不替代 `docs/backend/README.md` 里的其他模块说明，重点是把入口和路由绑定关系说清楚，方便排查 404 / 405 / 预检问题。

## 1. 启动入口

后端的真正运行入口在 [`app.py`](/run/media/luna/数据和游戏/Codes/Python/angelus/app.py)：

- `parse_args()` 读取 `--config`、`--host`、`--port`、`--debug`
- `main()` 调用 `create_app(args.config)`
- 然后用 Uvicorn ASGI 服务器启动

也就是说：

- `app.py` 负责“启动进程”
- [`web/app_factory.py`](/run/media/luna/数据和游戏/Codes/Python/angelus/web/app_factory.py) 负责“组装 FastAPI 应用”

`web/__init__.py` 只是把 `create_app` 重新导出，方便 `from web import create_app`。

## 2. App Factory

`create_app(config_path: str | Path = "config.toml") -> FastAPI` 是后端核心组装点。

它做了几件事：

1. 创建 FastAPI app
2. 读取顶层 `config.toml`
3. 构建 runtime registry 和 content store
4. 注册错误处理器
5. 注册 app-level 路由
6. 注册各个 blueprint

如果 `RuntimeRegistry.from_config_path()` 读取配置失败，会捕获 `SwarmLoaderError`，并把 `load_error` 放进 `RuntimeRegistry` 里继续启动。这意味着：

- 服务仍然可以起来
- 但 `/api/runtime/ready` 之类的接口会反映出加载失败

## 3. CORS 与 OPTIONS

`create_app()` 里有一层全局的 `after_request`：

- `Access-Control-Allow-Origin: *`
- `Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS`
- `Access-Control-Allow-Headers: Content-Type, Authorization`

这表示当前后端采用的是“全局统一加 CORS 响应头”的方式，不依赖单独的 CORS 扩展。

另外，`app_factory.py` 还注册了两个统一的 `OPTIONS` 处理器：

- `OPTIONS /`
- `OPTIONS /<path:path>`

它们都直接返回空响应和 `204`。

实际效果是：

- 浏览器的预检请求会被统一接住
- 不需要每个蓝图单独写 `OPTIONS`
- 任何路径的 `OPTIONS` 都会先被这个兜底处理掉

这也是排查前端跨域时最该先看的地方。

## 4. Blueprint 注册

`web/routes/__init__.py` 只做了一件事：把五个蓝图汇总导出。

当前被 `create_app()` 注册的蓝图有：

- `health_bp`
- `catalog_bp`
- `content_bp`
- `settings_bp`
- `swarms_bp`

注册前缀分别是：

- `health_bp` -> `/api`
- `catalog_bp` -> `/api`
- `content_bp` -> `/api`
- `settings_bp` -> `/api`
- `swarms_bp` -> `/api/swarms`

其中 `swarms_bp` 自己在蓝图定义里还带了 `url_prefix="/swarms"`，所以它最终对外的路径会落到 `/api/swarms/...`。

## 5. App-Level 路由

除了 blueprint 以外，`app_factory.py` 还直接注册了几个 app-level 路由。

这些路由是：

- `GET /`
- `GET /api`
- `GET /api/swarms`
- `GET /api/swarms/<swarm_name>`
- `GET /api/swarms/<swarm_name>/agent-graph`

其中：

- `/` 是服务根页
- `/api` 是 API 根页
- `/api/swarms` 返回 swarm 列表
- `/api/swarms/<swarm_name>` 返回单个 swarm 详情
- `/api/swarms/<swarm_name>/agent-graph` 返回单个 swarm 的图快照

注意：

- 这里的 `/api/swarms`、`/api/swarms/<swarm_name>`、`/api/swarms/<swarm_name>/agent-graph` 和 `swarms_bp` 里的同路径 GET 接口是并存的
- 当前代码里它们都确实被注册了
- 实际排查时，看到这些路径时要先确认是命中了 app-level 版本还是 blueprint 版本

## 6. 公开 URL 结构

下面是按当前代码整理出来的真实公开地址。

### 6.1 基础端点

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/` | 服务根页，返回 `service`、`swarm_count`、`load_error` |
| `GET` | `/api` | API 根页，返回 `api_root` 等摘要信息 |
| `GET` | `/api/settings` | 读取当前 API 配置 |
| `PUT` | `/api/settings` | 更新 API 配置并写回 `config.toml` |
| `OPTIONS` | `/*` | 统一预检响应，返回 `204` |

### 6.2 Health

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/api/runtime/health` | 存活检查 |
| `GET` | `/api/runtime/ready` | 就绪检查，会检查 runtime、swarm 加载和图有效性 |

### 6.3 Catalog

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/api/swarms/<swarm_name>/agents` | swarm 的 agent 目录 |
| `GET` | `/api/tasks` | 任务目录 |
| `GET` | `/api/tools` | 工具目录 |
| `GET` | `/api/catalog/swarms/<swarm_name>/stats` | swarm 统计信息 |
| `GET` | `/api/events` | 事件目录 |
| `GET` | `/api/logs` | 日志目录 |
| `GET` | `/api/metrics` | 指标查询 |

### 6.4 Content

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/api/knowledge` | 知识列表 |
| `GET` | `/api/knowledge/<knowledge_id>` | 知识详情 |
| `POST` | `/api/knowledge` | 创建知识 |
| `PUT` | `/api/knowledge/<knowledge_id>` | 更新知识 |
| `DELETE` | `/api/knowledge/<knowledge_id>` | 删除知识 |
| `GET` | `/api/memory` | 记忆列表 |
| `GET` | `/api/memory/<memory_id>` | 记忆详情 |
| `POST` | `/api/memory` | 创建记忆 |
| `DELETE` | `/api/memory/<memory_id>` | 删除记忆 |

### 6.5 Swarms

| Method | Path | 说明 |
|---|---|---|
| `POST` | `/api/swarms` | 加载 swarm |
| `GET` | `/api/swarms/<swarm_name>` | swarm 详情 |
| `GET` | `/api/swarms/<swarm_name>/agent-graph` | swarm 图快照 |
| `POST` | `/api/swarms/<swarm_name>/runs/execute` | 同步运行 swarm |
| `POST` | `/api/swarms/<swarm_name>/runs` | 后台运行 |
| `GET` | `/api/runs/<run_id>` | 运行快照 |
| `GET` | `/api/runs/<run_id>/events` | 运行事件流，SSE |
| `DELETE` | `/api/swarms/<swarm_name>` | 卸载 swarm |
| `POST` | `/api/swarms/<swarm_name>/reload` | 热重载 swarm |
| `POST` | `/api/swarms/<swarm_name>/agents/<agent_id>/round` | 单个 agent 的 round 调用 |

## 7. 实际排查时最容易踩的点

1. `OPTIONS` 不是 405 的来源
   - 由于有全局 `OPTIONS` 兜底，浏览器预检一般不会直接挂在 FastAPI 的默认 405 上

2. `/api/swarms` 由 swarms 路由模块统一承载
   - `app_factory.py` 只负责注册路由模块
   - 列表、加载、详情、运行入口都在 `web/routes/swarms.py`

3. `runs` 是独立资源
   - 启动 run 属于 swarm：`/api/swarms/<swarm_name>/runs`
   - 查询 run 属于 run 资源：`/api/runs/<run_id>`

4. `app.py` 只是入口，不承担路由组织
   - 真正要查“接口为什么 405 / 404”，主要看 `web/app_factory.py` 和 `web/routes/*`

## 8. 一句话结论

当前后端的公开接口分成三层：

- `app.py` 负责启动
- `web/app_factory.py` 负责应用组装、CORS、OPTIONS 和少量 app-level 路由
- `web/routes/` 负责大部分真实 API

如果你要继续排查“某个 API 为什么没进断点”，最有效的检查顺序是：

1. 看路径是否真的注册
2. 看 `url_prefix` 有没有叠加错
3. 看请求方法是否匹配
4. 看是否被全局 `OPTIONS` 或 app-level 路由提前接住
