from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from web.deps import get_content_store, parse_int, parse_json_body

router = APIRouter()


@router.get("/knowledge")
async def list_knowledge(request: Request):
    store = get_content_store(request)
    payload = store.list_knowledge(
        type_filter=request.query_params.get("type"),
        source=request.query_params.get("source"),
        tag=request.query_params.get("tag"),
        q=request.query_params.get("q"),
        page=parse_int(request.query_params.get("page", 1), 1),
        limit=parse_int(request.query_params.get("limit", 20), 20),
    )
    return {"success": True, **payload}


@router.get("/knowledge/{knowledge_id}")
async def get_knowledge(knowledge_id: str, request: Request):
    store = get_content_store(request)
    return {"success": True, "knowledge": store.get_knowledge(knowledge_id)}


@router.post("/knowledge")
async def create_knowledge(request: Request):
    store = get_content_store(request)
    item = store.create_knowledge(await parse_json_body(request))
    return JSONResponse({"success": True, "knowledge": item}, status_code=201)


@router.put("/knowledge/{knowledge_id}")
async def update_knowledge(knowledge_id: str, request: Request):
    store = get_content_store(request)
    item = store.update_knowledge(knowledge_id, await parse_json_body(request))
    return {"success": True, "knowledge": item}


@router.delete("/knowledge/{knowledge_id}")
async def delete_knowledge(knowledge_id: str, request: Request):
    store = get_content_store(request)
    item = store.delete_knowledge(knowledge_id)
    return {"success": True, "knowledge": item}


@router.get("/memory")
async def list_memory(request: Request):
    store = get_content_store(request)
    payload = store.list_memory(
        type_filter=request.query_params.get("type"),
        source=request.query_params.get("source"),
        q=request.query_params.get("q"),
        page=parse_int(request.query_params.get("page", 1), 1),
        limit=parse_int(request.query_params.get("limit", 20), 20),
    )
    return {"success": True, **payload}


@router.get("/memory/{memory_id}")
async def get_memory(memory_id: str, request: Request):
    store = get_content_store(request)
    return {"success": True, "memory": store.get_memory(memory_id)}


@router.post("/memory")
async def create_memory(request: Request):
    store = get_content_store(request)
    item = store.create_memory(await parse_json_body(request))
    return JSONResponse({"success": True, "memory": item}, status_code=201)


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str, request: Request):
    store = get_content_store(request)
    item = store.delete_memory(memory_id)
    return {"success": True, "memory": item}
