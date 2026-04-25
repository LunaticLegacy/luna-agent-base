# 后端错误与健康检查

本文只描述当前后端代码的真实实现，重点放在：

- 健康检查与就绪检查接口
- `web/errors.py` 里的错误类型
- Flask 如何把异常统一转成 JSON 响应

相关代码：

- [`web/errors.py`](/run/media/luna/数据和游戏/Codes/Python/angelus/web/errors.py)
- [`web/routes/health.py`](/run/media/luna/数据和游戏/Codes/Python/angelus/web/routes/health.py)
- [`web/app_factory.py`](/run/media/luna/数据和游戏/Codes/Python/angelus/web/app_factory.py)

## 路由挂载位置

当前应用在 `create_app()` 里注册这些公开接口：

- `GET /api/runtime/health`
- `GET /api/runtime/ready`

同时，`register_error_handlers(app)` 会在应用启动时注册统一错误处理器，因此绝大多数路由里的异常最后都会被转成 JSON。

## 健康检查接口

### `GET /api/runtime/health`

这个接口是最轻量的存活检查，只返回固定 JSON：

```json
{
  "success": true,
  "status": "ok"
}
```

它不检查运行时注册表、swarm 是否加载成功，也不检查执行图是否可用。

### `GET /api/runtime/ready`

这个接口是就绪检查，会逐层验证后端运行状态。

返回成功时：

```json
{
  "success": true,
  "ready": true,
  "swarm_count": 3
}
```

返回失败时，状态码是 `503`，并且会带上失败原因。

当前的失败条件依次是：

1. `current_app.extensions["angelus_runtime"]` 不存在
   - 返回 `503`
   - 形如：
   ```json
   {
     "success": false,
     "ready": false,
     "reason": "runtime registry missing"
   }
   ```
2. `runtime_registry.load_error` 有值
   - 返回 `503`
   - 形如：
   ```json
   {
     "success": false,
     "ready": false,
     "reason": "swarm load error",
     "load_error": "..."
   }
   ```
3. 当前没有任何 swarm 被加载
   - 返回 `503`
   - 形如：
   ```json
   {
     "success": false,
     "ready": false,
     "reason": "no swarms loaded"
   }
   ```
4. 某些 swarm 的执行图不可用
   - `ready()` 会遍历每个 swarm，调用 `swarm.core.check_execution_graph_available()`
   - 如果校验失败，会收集到 `invalid_swarms`
   - 返回 `503`
   - 形如：
   ```json
   {
     "success": false,
     "ready": false,
     "invalid_swarms": [
       {
         "swarm": "xxx",
         "errors": [...]
       }
     ]
   }
   ```

## 错误类型

`web/errors.py` 当前定义了四个面向 HTTP 的运行时错误类型：

### `ApiError`

- 基类，继承自 `RuntimeError`
- 默认状态码是 `400`
- 提供 `to_response()`，统一返回：

```json
{
  "success": false,
  "error": "错误信息"
}
```

### `NotFoundError`

- 继承 `ApiError`
- 状态码是 `404`
- 适合“资源不存在”这类问题

### `RunNotFoundError`

- 继承 `NotFoundError`
- 目前只是语义上的子类
- 代码里用于表达“找不到某个 live run”

### `ConflictError`

- 继承 `ApiError`
- 状态码是 `409`
- 适合“状态冲突”类问题，比如重复加载 swarm、仍有 active run 时卸载/重载

## Flask 异常如何转成 JSON

`register_error_handlers(app)` 会给 Flask 注册一组统一处理器。

### 1. `ApiError`

所有 `ApiError` 及其子类都会走 `exc.to_response()`。

也就是说，这类错误的响应格式固定为：

- `success: false`
- `error: str(exc)`
- HTTP 状态码由错误类的 `status_code` 决定

### 2. `SwarmLoaderError`

`SwarmLoaderError` 来自 `core.swarm_loader`。

当前处理方式是：

- 返回 JSON
- `success: false`
- `error: str(exc)`
- 状态码固定为 `500`

这意味着如果底层 swarm 加载失败，前端不会拿到 HTML 错误页，而是拿到标准 JSON。

### 3. `KeyError`

`KeyError` 会被统一转成：

- `404`
- JSON 格式
- `success: false`
- `error: str(exc)`

当前 `ContentStore` 里的知识和记忆读写接口，会在找不到条目时抛 `KeyError`，然后被这里接住。

### 4. `ValueError`

`ValueError` 会被统一转成：

- `400`
- JSON 格式
- `success: false`
- `error: str(exc)`

当前 `ContentStore` 在创建知识或记忆时，如果 ID 重复，会抛 `ValueError`，然后进入这个处理器。

### 5. 其他异常

最后还有一个兜底的 `Exception` 处理器：

- 如果异常本身是 `HTTPException`
  - 返回 `exc.description`
  - 状态码用 `exc.code`
- 否则
  - 返回 `500`
  - `error` 为 `str(exc)`

这层兜底的意义是：即使某个路由没有显式抛 `ApiError`，只要异常落到 Flask 全局处理器里，响应仍然会保持 JSON 结构。

## 现有路由里的实际用法

当前代码里，错误处理主要出现在这些场景：

- `web/routes/catalog.py`
  - 运行时注册表不存在时抛 `ApiError("Runtime registry is not initialized.")`
- `web/routes/content.py`
  - content store 不存在时抛 `ApiError("Content store is not initialized.")`
  - 请求体不是 JSON 对象时抛 `ApiError("Request body must be a JSON object.")`
- `web/routes/swarms.py`
  - runtime registry 不存在时抛 `ApiError`
  - swarm 没有 agent graph 时抛 `ApiError`
  - 找不到 run 时抛 `NotFoundError`
  - 运行操作里缺少必要字段时抛 `ApiError`

另外，`web/runtime.py` 会在一些运行时操作中抛：

- `NotFoundError`
- `ConflictError`

这些最终也都会被统一转换成 JSON 响应。

## 当前实现特点

- 健康检查和就绪检查是分开的
- 所有错误响应都保持 JSON，而不是返回 HTML 错误页
- `ApiError` 是当前最常用的业务错误基类
- `KeyError` / `ValueError` 没有在各个路由里单独处理，而是交给全局 error handler
- 目前没有更细分的错误码体系，业务层主要依靠 `error` 字段中的文本和 HTTP 状态码

## 结论

如果你要判断后端是否“活着”：

- 用 `GET /api/runtime/health`

如果你要判断后端是否“可提供业务服务”：

- 用 `GET /api/runtime/ready`

如果你在调试 API 返回：

- 先看路由里是不是显式抛了 `ApiError` / `NotFoundError` / `ConflictError`
- 再看是不是底层 `KeyError` / `ValueError` / `SwarmLoaderError`
- 最后看 Flask 全局兜底有没有把它转成标准 JSON
