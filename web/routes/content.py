"""内容管理路由（Knowledge / Memory）。

提供对知识库与记忆条目的增删改查接口，所有操作均通过 ContentStore
完成，支持分页与多维度过滤。
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from web.deps import get_content_store, parse_json_body

router = APIRouter()


@router.post("/knowledge/search")
async def list_knowledge(request: Request):
    """分页查询知识库条目。

    Args:
        request: FastAPI 请求对象，请求体支持 type、source、tag、q、page、limit。

    Returns:
        包含 success=True 与查询结果的字典。
    """
    store = get_content_store(request)
    request_data = await parse_json_body(request)
    payload = store.list_knowledge(
        type_filter=request_data.get("type"),
        source=request_data.get("source"),
        tag=request_data.get("tag"),
        q=request_data.get("q"),
        page=int(request_data.get("page", 1) or 1),
        limit=int(request_data.get("limit", 20) or 20),
    )
    return {"success": True, **payload}


@router.get("/knowledge/{knowledge_id}")
async def get_knowledge(knowledge_id: str, request: Request):
    """根据 ID 获取单条知识库条目。

    Args:
        knowledge_id: 知识条目唯一标识。
        request: FastAPI 请求对象。

    Returns:
        包含 success=True 与 knowledge 详情。

    Raises:
        KeyError: 条目不存在时由 ContentStore 抛出，经错误处理器转为 404。
    """
    store = get_content_store(request)
    return {"success": True, "knowledge": store.get_knowledge(knowledge_id)}


@router.post("/knowledge")
async def create_knowledge(request: Request):
    """新建知识库条目。

    Args:
        request: 请求体为知识条目的 JSON 对象。

    Returns:
        201 响应，包含 success=True 与新建条目。
    """
    store = get_content_store(request)
    item = store.create_knowledge(await parse_json_body(request))
    return JSONResponse({"success": True, "knowledge": item}, status_code=201)


@router.put("/knowledge/{knowledge_id}")
async def update_knowledge(knowledge_id: str, request: Request):
    """更新指定知识库条目。

    Args:
        knowledge_id: 要更新的条目 ID。
        request: 请求体为待合并的 JSON 对象。

    Returns:
        包含 success=True 与更新后条目。
    """
    store = get_content_store(request)
    item = store.update_knowledge(knowledge_id, await parse_json_body(request))
    return {"success": True, "knowledge": item}


@router.delete("/knowledge/{knowledge_id}")
async def delete_knowledge(knowledge_id: str, request: Request):
    """删除指定知识库条目。

    Args:
        knowledge_id: 要删除的条目 ID。
        request: FastAPI 请求对象。

    Returns:
        包含 success=True 与被删除条目。
    """
    store = get_content_store(request)
    item = store.delete_knowledge(knowledge_id)
    return {"success": True, "knowledge": item}


@router.post("/memory/search")
async def list_memory(request: Request):
    """分页查询记忆条目。

    Args:
        request: FastAPI 请求对象，请求体支持 type、source、q、page、limit。

    Returns:
        包含 success=True 与查询结果的字典。
    """
    store = get_content_store(request)
    request_data = await parse_json_body(request)
    payload = store.list_memory(
        type_filter=request_data.get("type"),
        source=request_data.get("source"),
        q=request_data.get("q"),
        page=int(request_data.get("page", 1) or 1),
        limit=int(request_data.get("limit", 20) or 20),
    )
    return {"success": True, **payload}


@router.get("/memory/{memory_id}")
async def get_memory(memory_id: str, request: Request):
    """根据 ID 获取单条记忆条目。

    Args:
        memory_id: 记忆条目唯一标识。
        request: FastAPI 请求对象。

    Returns:
        包含 success=True 与 memory 详情。
    """
    store = get_content_store(request)
    return {"success": True, "memory": store.get_memory(memory_id)}


@router.post("/memory")
async def create_memory(request: Request):
    """新建记忆条目。

    Args:
        request: 请求体为记忆条目的 JSON 对象。

    Returns:
        201 响应，包含 success=True 与新建条目。
    """
    store = get_content_store(request)
    item = store.create_memory(await parse_json_body(request))
    return JSONResponse({"success": True, "memory": item}, status_code=201)


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str, request: Request):
    """删除指定记忆条目。

    Args:
        memory_id: 要删除的条目 ID。
        request: FastAPI 请求对象。

    Returns:
        包含 success=True 与被删除条目。
    """
    store = get_content_store(request)
    item = store.delete_memory(memory_id)
    return {"success": True, "memory": item}
