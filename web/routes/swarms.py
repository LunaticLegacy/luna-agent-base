"""Swarm 管理路由。

提供 swarm 的列表、加载、卸载、重载、执行图查询、
全局变量管理、运行控制以及单 agent 轮询调用等接口。
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Optional

from core.executor import GraphExecutor
from core.results import ExecutionState
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from web.deps import get_runtime_registry, parse_bool, parse_int, parse_json_body
from web.errors import ApiError, ConflictError, NotFoundError
from web.runs import RunRegistry, serialize_graph_snapshot, serialize_swarm_detail
from web.runtime import RuntimeRegistry
from web.swarm_globals_store import save_global_variables, serialize_global_variables
from web.utils import to_jsonable

router = APIRouter()


# 用于从用户文本中提取显式文件名的正则模式（中英文）
_ARTIFACT_PATH_PATTERNS = [
    re.compile(r"(?:将该文件命名|命名|文件名)\s*为\s+([^\s,;，。]+)", re.IGNORECASE),
    re.compile(r"(?:保存为)\s+([^\s,;，。]+)", re.IGNORECASE),
    re.compile(r"(?:name it|save as)\s+([^\s,;，。]+)", re.IGNORECASE),
]


def extract_artifact_path(text: str) -> Optional[str]:
    """扫描用户文本，提取显式请求的文件名或路径。

    Args:
        text: 用户输入文本。

    Returns:
        提取到的文件名（含扩展名），或 None。
    """
    for pattern in _ARTIFACT_PATH_PATTERNS:
        match = pattern.search(text)
        if match:
            candidate = match.group(1).strip()
            if "." in candidate:
                return candidate
    return None


def normalize_initial_payload(raw: Any) -> Any:
    """将 HTTP 输入归一化为运行时负载。

    - dict 直接透传。
    - str 直接透传。
    - 其他类型强制转为 str。

    Args:
        raw: 原始输入值。

    Returns:
        归一化后的值。
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return raw
    return str(raw)


def _get_swarm_or_404(request: Request, swarm_name: str):
    """从请求中获取指定 swarm，不存在时抛出 NotFoundError。

    Args:
        request: FastAPI 请求对象。
        swarm_name: swarm 名称。

    Returns:
        LoadedSwarm 实例。

    Raises:
        NotFoundError: swarm 不存在时抛出。
    """
    return get_runtime_registry(request).get_swarm(swarm_name)


def resolve_final_output(state: ExecutionState) -> Any:
    """从已完成运行的状态中提取人类可读最终输出。

    遍历 metadata.outputs 并优先提取最后一个节点输出中的
    final_answer / final_report / approved_report / draft_report / content 字段。

    Args:
        state: 执行结束后的状态对象。

    Returns:
        最终输出值。
    """
    outputs = state.metadata.get("outputs")
    if isinstance(outputs, dict) and outputs:
        last_key = list(outputs.keys())[-1]
        last_output = outputs[last_key]
        if isinstance(last_output, dict):
            for key in ("final_answer", "final_report", "approved_report", "draft_report", "content"):
                value = last_output.get(key)
                if value is not None:
                    return value
            return last_output
        return last_output
    return state.payload


def _get_runs_registry(request: Request) -> RunRegistry:
    """从请求中提取运行注册表。

    Args:
        request: FastAPI 请求对象。

    Returns:
        RunRegistry 实例。
    """
    return get_runtime_registry(request).runs


def _serialize_swarm_with_runtime(registry: RuntimeRegistry, swarm) -> dict:
    """序列化 swarm 详情并追加运行时活跃数据。

    Args:
        registry: 运行时注册表。
        swarm: 已加载的 swarm 实例。

    Returns:
        包含活跃运行数与活跃运行 ID 的字典。
    """
    payload = serialize_swarm_detail(swarm)
    payload["active_run_count"] = registry.runs.active_run_count(swarm.manifest.swarm_name)
    payload["active_run_ids"] = registry.runs.active_run_ids(swarm.manifest.swarm_name)
    return payload


def _serialize_graph_with_state(swarm) -> dict:
    """序列化 swarm 的 agent 图并附加运行时状态。

    Args:
        swarm: 已加载的 swarm 实例。

    Returns:
        图快照与运行时状态合并后的字典。

    Raises:
        ApiError: swarm 未附加执行图时抛出。
    """
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm.manifest.swarm_name}' has no execution graph attached.")
    payload = serialize_graph_snapshot(graph)
    payload.update(swarm.core.get_graph_runtime_state())
    return payload


def _serialize_execution_graph_with_state(swarm) -> dict:
    """序列化 swarm 的执行图并附加运行时状态。

    Args:
        swarm: 已加载的 swarm 实例。

    Returns:
        图快照与运行时状态合并后的字典。

    Raises:
        ApiError: swarm 未附加执行图时抛出。
    """
    graph = swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm.manifest.swarm_name}' has no execution graph attached.")
    payload = serialize_graph_snapshot(graph)
    payload["graph_kind"] = getattr(graph, "graph_kind", "execution")
    payload.update(swarm.core.get_graph_runtime_state())
    return payload


async def _execute_swarm_run(request: Request, swarm_name: str, *, use_background: bool = False):
    """执行 swarm 运行，支持同步返回或后台启动。

    同步模式下直接调用 GraphExecutor/MetaExecutor；
    后台模式下通过 RunRegistry.launch_run 在守护线程中执行。

    Args:
        request: FastAPI 请求对象。
        swarm_name: 目标 swarm 名称。
        use_background: 是否后台启动。

    Returns:
        同步模式返回结果字典；后台模式返回 202 JSONResponse。

    Raises:
        ApiError: swarm 无执行图时抛出。
        ConflictError: 该 swarm 已有活跃运行时抛出。
    """
    swarm = _get_swarm_or_404(request, swarm_name)
    graph = swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no agent graph attached.")

    request_data = await parse_json_body(request)
    payload = normalize_initial_payload(request_data.get("input"))
    rounds = int(request_data.get("rounds", 0))
    meta_mode = bool(request_data.get("meta_mode", False))
    runs_registry = _get_runs_registry(request)

    # 同一 swarm 不允许并发运行，防止状态冲突
    if runs_registry.active_run_count(swarm_name) > 0:
        raise ConflictError(
            f"Swarm '{swarm_name}' already has an active run. Wait for it to finish before starting another."
        )

    swarm.core.reset_runtime_state()

    if use_background:
        record = runs_registry.launch_run(
            swarm_name=swarm_name,
            core=swarm.core,
            graph=graph,
            initial_payload=payload,
            rounds=rounds,
            meta_mode=meta_mode,
        )
        return JSONResponse(
            {
                "success": True,
                "status": "started",
                "swarm": swarm_name,
                "run": record.snapshot(),
            },
            status_code=202,
        )

    if meta_mode:
        from core.meta_executor import MetaExecutor

        meta = MetaExecutor(max_iterations=5)
        state = await meta.run(graph, swarm.core, payload, rounds=rounds)
    else:
        state = await GraphExecutor().execute(graph, swarm.core, payload, rounds=rounds)

    return {
        "success": True,
        "swarm": swarm_name,
        "rounds": state.rounds,
        "output": to_jsonable(resolve_final_output(state)),
        "trace": to_jsonable(state.trace),
        "metadata": to_jsonable(state.metadata),
    }


@router.get("")
async def list_swarms(request: Request):
    """列出所有已加载的 swarm。

    Args:
        request: FastAPI 请求对象。

    Returns:
        包含 swarm 列表的字典。
    """
    registry = get_runtime_registry(request)
    return {
        "success": True,
        "swarms": [
            _serialize_swarm_with_runtime(registry, swarm)
            for swarm in registry.swarms.values()
        ],
    }


@router.post("")
async def load_swarm(request: Request):
    """加载新的 swarm 包到运行时。

    Args:
        request: 请求体需包含 package_path、source 或 swarm_name。

    Returns:
        201 响应，包含加载后的 swarm 详情。
    """
    registry = get_runtime_registry(request)
    request_data = await parse_json_body(request)
    source = request_data.get("package_path") or request_data.get("source") or request_data.get("swarm_name")
    if not source:
        raise ApiError("Request body must include 'package_path', 'source', or 'swarm_name'.")

    replace = parse_bool(request_data.get("replace", False))
    loaded = registry.load_swarm(source, replace=replace)
    return JSONResponse(
        {
            "success": True,
            "action": "load",
            "swarm": _serialize_swarm_with_runtime(registry, loaded),
        },
        status_code=201,
    )


@router.get("/{swarm_name}")
async def get_swarm(swarm_name: str, request: Request):
    """获取单个 swarm 的详情。

    Args:
        swarm_name: swarm 名称。
        request: FastAPI 请求对象。

    Returns:
        包含 swarm 详情的字典。
    """
    swarm = _get_swarm_or_404(request, swarm_name)
    return {"success": True, "swarm": _serialize_swarm_with_runtime(get_runtime_registry(request), swarm)}


@router.get("/{swarm_name}/agent-graph")
async def get_swarm_graph(swarm_name: str, request: Request):
    """获取 swarm 的 agent 图及运行时状态。

    Args:
        swarm_name: swarm 名称。
        request: FastAPI 请求对象。

    Returns:
        包含图快照的字典。
    """
    swarm = _get_swarm_or_404(request, swarm_name)
    return {"success": True, "swarm": swarm_name, "graph": _serialize_graph_with_state(swarm)}


@router.get("/{swarm_name}/globals")
async def get_swarm_globals(swarm_name: str, request: Request):
    """获取 swarm 的全局变量配置。

    Args:
        swarm_name: swarm 名称。
        request: FastAPI 请求对象。

    Returns:
        包含全局变量的字典。
    """
    swarm = _get_swarm_or_404(request, swarm_name)
    return {
        "success": True,
        "swarm": swarm_name,
        "globals": serialize_global_variables(swarm.manifest.global_variables),
    }


@router.get("/{swarm_name}/apis")
async def get_swarm_apis(swarm_name: str, request: Request):
    """获取 swarm 中注册的所有 API。

    Args:
        swarm_name: swarm 名称。
        request: FastAPI 请求对象。

    Returns:
        包含 API 列表的字典。
    """
    swarm = _get_swarm_or_404(request, swarm_name)
    apis = []
    for api_name in sorted(getattr(swarm.core, "apis", {}).keys()):
        api = swarm.core.get_api(api_name)
        metadata = swarm.core.get_api_metadata(api_name)
        apis.append(
            {
                "name": api_name,
                "origin": metadata.get("origin", "package"),
                "source": metadata.get("source"),
                "type": api.__class__.__name__,
            }
        )
    return {"success": True, "swarm": swarm_name, "apis": apis}


@router.put("/{swarm_name}/globals")
async def update_swarm_globals(swarm_name: str, request: Request):
    """更新 swarm 的全局变量与可见性配置。

    修改会立即持久化到 manifest.toml，并同步更新 core 的运行时状态。

    Args:
        swarm_name: swarm 名称。
        request: 请求体需包含 globals 和/或 visibility。

    Returns:
        包含更新后全局变量的字典。

    Raises:
        ApiError: 请求体格式不正确时抛出。
    """
    swarm = _get_swarm_or_404(request, swarm_name)
    request_data = await parse_json_body(request)
    globals_section = request_data.get("globals")
    visibility_section = request_data.get("visibility")
    if globals_section is None and visibility_section is None:
        raise ApiError("Request body must include 'globals' and/or 'visibility'.")
    if globals_section is not None and not isinstance(globals_section, dict):
        raise ApiError("'globals' must be a JSON object.")
    if visibility_section is not None and not isinstance(visibility_section, dict):
        raise ApiError("'visibility' must be a JSON object.")

    current_globals = swarm.manifest.global_variables
    values = dict(current_globals.values)
    visibility = {key: list(value) for key, value in current_globals.visibility.items()}
    if isinstance(globals_section, dict):
        for key, value in globals_section.items():
            values[str(key).strip()] = value
    if isinstance(visibility_section, dict):
        for key, agent_list in visibility_section.items():
            if agent_list is None:
                visibility.pop(str(key).strip(), None)
                continue
            if isinstance(agent_list, str):
                agent_list = [agent_list]
            if not isinstance(agent_list, list):
                raise ApiError(f"visibility for '{key}' must be a string array.")
            visibility[str(key).strip()] = [str(item).strip() for item in agent_list if str(item).strip()]

    updated_globals = type(current_globals)(values=values, visibility=visibility)
    save_global_variables(swarm.manifest_path, updated_globals)
    swarm.manifest.global_variables = updated_globals
    swarm.core.set_global_variables(updated_globals)
    swarm.core.record_runtime_change(
        action="set_global_variables",
        subject_kind="globals",
        subject_id=swarm_name,
        detail=serialize_global_variables(updated_globals),
    )
    return {
        "success": True,
        "swarm": swarm_name,
        "globals": serialize_global_variables(updated_globals),
    }


@router.get("/{swarm_name}/execution-graph")
async def get_swarm_execution_graph(swarm_name: str, request: Request):
    """获取 swarm 的执行图及运行时状态。

    Args:
        swarm_name: swarm 名称。
        request: FastAPI 请求对象。

    Returns:
        包含执行图快照的字典。
    """
    swarm = _get_swarm_or_404(request, swarm_name)
    return {"success": True, "swarm": swarm_name, "graph": _serialize_execution_graph_with_state(swarm)}


@router.post("/{swarm_name}/graph/state")
async def get_swarm_graph_state(swarm_name: str, request: Request):
    """获取 swarm 图的当前运行时状态，并判断自指定 revision 以来是否有变更。

    Args:
        swarm_name: swarm 名称。
        request: 请求体可包含 since_revision。

    Returns:
        包含图状态与 has_changes_since 的字典。
    """
    swarm = _get_swarm_or_404(request, swarm_name)
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no agent graph attached.")
    state = swarm.core.get_graph_runtime_state()
    request_data = await parse_json_body(request)
    since_revision = parse_int(request_data.get("since_revision"), 0)
    return {
        "success": True,
        "swarm": swarm_name,
        "graph": state,
        "has_changes_since": int(state.get("revision") or 0) > since_revision,
    }


@router.post("/{swarm_name}/graph/diff")
async def get_swarm_graph_diff(swarm_name: str, request: Request):
    """获取自指定 revision 以来的图变更差异。

    Args:
        swarm_name: swarm 名称。
        request: 请求体可包含 since_revision。

    Returns:
        包含 patch 的字典。
    """
    swarm = _get_swarm_or_404(request, swarm_name)
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no agent graph attached.")
    request_data = await parse_json_body(request)
    since_revision = parse_int(request_data.get("since_revision"), 0)
    diff = swarm.core.get_graph_runtime_diff(since_revision=since_revision)
    return {"success": True, "swarm": swarm_name, "patch": diff}


@router.get("/{swarm_name}/graph/events/from/{since_revision}")
async def stream_swarm_graph_events(swarm_name: str, since_revision: int, request: Request):
    """以 SSE 流形式推送 swarm 图的运行时变更事件。

    客户端可通过 since_revision 指定起始点，流会持续推送新的
    graph.changed 事件，并周期性发送 keepalive。

    Args:
        swarm_name: swarm 名称。
        since_revision: 起始 revision。
        request: FastAPI 请求对象。

    Returns:
        StreamingResponse，媒体类型为 text/event-stream。
    """
    swarm = _get_swarm_or_404(request, swarm_name)
    graph_getter = getattr(swarm.core, "get_agent_graph", None)
    graph = graph_getter() if callable(graph_getter) else swarm.core.get_execution_graph()
    if graph is None:
        raise ApiError(f"Swarm '{swarm_name}' has no execution graph attached.")
    async def _stream():
        last_revision = since_revision
        yield "retry: 3000\n\n"
        while True:
            events = swarm.core.get_graph_runtime_events(since_revision=last_revision)
            if events:
                for event in events:
                    last_revision = max(last_revision, int(event.get("revision") or last_revision))
                    payload = {
                        "swarm": swarm_name,
                        "graph_id": event.get("snapshot", {}).get("graph_name"),
                        "revision": event.get("revision"),
                        "change": event.get("change"),
                        "action": event.get("action"),
                        "subject_kind": event.get("subject_kind"),
                        "subject_id": event.get("subject_id"),
                    }
                    yield f"event: graph.changed\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(1.5)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{swarm_name}/thought-graph")
async def get_swarm_thought_graph(swarm_name: str, request: Request):
    """获取 swarm 的认知图快照。

    Args:
        swarm_name: swarm 名称。
        request: FastAPI 请求对象。

    Returns:
        包含 thought_graph 的字典。
    """
    swarm = _get_swarm_or_404(request, swarm_name)
    snapshot = swarm.core.get_cognitive_graph_snapshot()
    return {"success": True, "swarm": swarm_name, "thought_graph": to_jsonable(snapshot)}


@router.get("/{swarm_name}/execution-traces/latest")
async def get_swarm_execution_trace(swarm_name: str, request: Request):
    """获取指定 swarm 最近一次运行的执行跟踪。

    Args:
        swarm_name: swarm 名称。
        request: FastAPI 请求对象。

    Returns:
        包含 run 快照与 events 的字典；若无运行记录则返回空事件。
    """
    runs = [record for record in _get_runs_registry(request).list_runs(swarm_name) if record.swarm_name == swarm_name]
    record = runs[-1] if runs else None

    if record is None:
        return {"success": True, "swarm": swarm_name, "run": None, "events": []}

    return {
        "success": True,
        "swarm": swarm_name,
        "run": record.snapshot(),
        "events": to_jsonable(record.events),
    }


@router.get("/{swarm_name}/execution-traces/{run_id}")
async def get_swarm_execution_trace_by_run(swarm_name: str, run_id: str, request: Request):
    """根据 run_id 获取指定 swarm 的执行跟踪。

    Args:
        swarm_name: swarm 名称。
        run_id: 运行唯一标识。
        request: FastAPI 请求对象。

    Returns:
        包含 run 快照与 events 的字典。

    Raises:
        NotFoundError: 运行不存在或不属于该 swarm 时抛出。
    """
    record = _get_runs_registry(request).get_run(run_id)
    if record is None or record.swarm_name != swarm_name:
        raise NotFoundError(f"Unknown run for swarm '{swarm_name}': {run_id}")
    return {
        "success": True,
        "swarm": swarm_name,
        "run": record.snapshot(),
        "events": to_jsonable(record.events),
    }


@router.post("/{swarm_name}/runs/execute")
async def run_swarm(swarm_name: str, request: Request):
    """同步执行 swarm 运行并返回结果。

    Args:
        swarm_name: swarm 名称。
        request: FastAPI 请求对象。

    Returns:
        包含输出、trace、metadata 的字典。
    """
    return await _execute_swarm_run(request, swarm_name)


@router.post("/{swarm_name}/runs")
async def create_run(swarm_name: str, request: Request):
    """在后台启动 swarm 运行并立即返回 202。

    Args:
        swarm_name: swarm 名称。
        request: FastAPI 请求对象。

    Returns:
        202 响应，包含运行快照。
    """
    return await _execute_swarm_run(request, swarm_name, use_background=True)


@router.post("/{swarm_name}/runs/stop")
async def stop_swarm_runs(swarm_name: str, request: Request):
    """停止指定 swarm 的所有活跃运行。

    请求体示例：{"stop_type": "soft"}

    Args:
        swarm_name: swarm 名称。
        request: FastAPI 请求对象。

    Returns:
        包含已停止运行列表的字典。

    Raises:
        ConflictError: stop_type 不合法时抛出。
    """
    swarm = _get_swarm_or_404(request, swarm_name)
    body = await parse_json_body(request)
    stop_type = str(body.get("stop_type", "soft")).strip().lower()
    if stop_type not in {"soft", "hard"}:
        raise ConflictError(f"Invalid stop_type: '{stop_type}'. Use 'soft' or 'hard'.")

    registry = _get_runs_registry(request)
    active_ids = registry.active_run_ids(swarm_name)
    stopped = []
    for run_id in active_ids:
        record = registry.stop_run(run_id, stop_type=stop_type)
        if record is not None:
            stopped.append({"run_id": run_id, "status": record.status})

    return {
        "success": True,
        "swarm": swarm_name,
        "stop_type": stop_type,
        "stopped": stopped,
        "count": len(stopped),
    }


@router.delete("/{swarm_name}")
async def unload_swarm(swarm_name: str, request: Request):
    """卸载指定 swarm。

    Args:
        swarm_name: swarm 名称。
        request: 请求体可包含 force 字段。

    Returns:
        包含被卸载 swarm 基本信息的字典。
    """
    registry = get_runtime_registry(request)
    request_data = await parse_json_body(request)
    force = parse_bool(request_data.get("force", False))
    unloaded = registry.unload_swarm(swarm_name, force=force)
    return {
        "success": True,
        "action": "unload",
        "swarm": {
            "swarm_name": unloaded.manifest.swarm_name,
            "package_path": str(unloaded.package_path),
        },
    }


@router.post("/{swarm_name}/reload")
async def reload_swarm(swarm_name: str, request: Request):
    """重载指定 swarm。

    Args:
        swarm_name: swarm 名称。
        request: 请求体可包含 force 与 package_path/source 字段。

    Returns:
        包含重载后 swarm 详情的字典。
    """
    registry = get_runtime_registry(request)
    request_data = await parse_json_body(request)
    force = parse_bool(request_data.get("force", False))
    source = request_data.get("package_path") or request_data.get("source")
    reloaded = registry.reload_swarm(swarm_name, force=force, source=source)
    return {
        "success": True,
        "action": "reload",
        "swarm": _serialize_swarm_with_runtime(registry, reloaded),
    }


@router.post("/{swarm_name}/agents/{agent_id}/round")
async def run_agent_round(swarm_name: str, agent_id: str, request: Request):
    """对指定 agent 发起一轮直接调用。

    Args:
        swarm_name: swarm 名称。
        agent_id: agent 标识。
        request: 请求体需包含非空 message 字段。

    Returns:
        包含 result 与 agent 上下文快照的字典。

    Raises:
        ApiError: message 为空时抛出。
    """
    swarm = _get_swarm_or_404(request, swarm_name)
    agent = swarm.core.get_agent(agent_id)
    request_data = await parse_json_body(request)
    user_message = str(request_data.get("message", "")).strip()
    if not user_message:
        raise ApiError("Request body must include a non-empty 'message'.")

    rounds = int(request_data.get("rounds", 0))
    additional_prompt = request_data.get("additional_prompt")
    result = await agent.round_call(
        rounds=rounds,
        user_message=user_message,
        additional_prompt=additional_prompt,
    )
    return {
        "success": True,
        "swarm": swarm_name,
        "agent_id": agent_id,
        "result": to_jsonable(result),
        "context": to_jsonable(agent.get_context_snapshot()),
    }
