"""Angelus FastAPI REST core.

Thin transparent layer over the Angelus swarm runtime.
Implements the REST surface documented in API_DESIGN.md.
"""

from __future__ import annotations

import asyncio
import json
import os
import tomllib
import traceback
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from core import Core
from modules.llm_fetcher import LLMBackendConfig, LLMFetcher
from modules.llm_fetcher.swarm.execution_graph import ExecutionGraph


# ---------------------------------------------------------------------------
# Global runtime Core
# ---------------------------------------------------------------------------

_core = Core()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "ok"


class SwarmInfo(BaseModel):
    name: str
    agent_count: int
    tool_count: int


class SwarmListResponse(BaseModel):
    swarms: List[SwarmInfo]


class LoadSwarmRequest(BaseModel):
    source: str = Field(..., description="Path to swarm directory or config file")


class LoadSwarmResponse(BaseModel):
    name: str
    id: str
    message: str = "loaded"


class RunRequest(BaseModel):
    input: str
    context: Optional[Dict[str, Any]] = None


class StopRequest(BaseModel):
    mode: Literal["soft", "hard"] = "soft"
    reason: Optional[str] = None


class StopResponse(BaseModel):
    name: str
    mode: Literal["soft", "hard"]
    requested: bool
    reason: Optional[str] = None
    stop_state: Dict[str, Any] = Field(default_factory=dict)


class RunResponse(BaseModel):
    output: str
    trace: Optional[Dict[str, Any]] = None


class GraphResponse(BaseModel):
    name: str
    nodes: Dict[str, Any]
    edges: List[Dict[str, Any]]


class RunRecord(BaseModel):
    timestamp: float
    input: str
    output: str
    trace: Optional[Dict[str, Any]] = None


class HistoryResponse(BaseModel):
    runs: List[RunRecord]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_api_key(expr: str) -> str:
    if expr.startswith("${") and expr.endswith("}"):
        return os.environ.get(expr[2:-1], "")
    return expr


def _build_trace(ctx: Any) -> Dict[str, Any]:
    if hasattr(ctx, "to_dict") and callable(ctx.to_dict):
        try:
            return ctx.to_dict()
        except Exception:
            pass
    return {
        "executed": list(getattr(ctx, "executed", [])),
        "node_outputs": {
            k: str(v) for k, v in dict(getattr(ctx, "node_outputs", {})).items()
        },
    }


def _sse_event(event: str, data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def _load_swarm_from_source(source: str) -> tuple[str, Any]:
    """Best-effort swarm loading from a file-system path.

    Supports:
    - A ``.json`` snapshot file (round-trippable, via :meth:`AgentSwarm.load`)
    - A directory containing ``swarm.toml``
    - A ``.toml`` file directly

    Returns ``(name, swarm)`` where swarm is an :class:`AgentSwarm`.
    """
    path = Path(source).expanduser().resolve()

    if not path.exists():
        raise ValueError(f"Source not found: {source}")

    # --- Snapshot JSON ----------------------------------------------------
    if path.is_file() and path.suffix == ".json":
        from modules.llm_fetcher.swarm.swarm import AgentSwarm

        # For a snapshot we need an LLM fetcher.  We inspect the payload
        # to see if it embeds a minimal backend config, otherwise we require
        # the caller to set ANGELUS_API_KEY and a default provider.
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        spec = snapshot.get("spec", {})
        name = spec.get("name", path.stem)

        fetcher = _resolve_fetcher_from_env()
        swarm = AgentSwarm.load(path, llm_fetcher=fetcher)
        _core.register_swarm(name, swarm)
        return name, swarm

    # --- TOML / directory -------------------------------------------------
    manifest: Dict[str, Any] = {}
    if path.is_dir():
        toml_path = path / "swarm.toml"
        if toml_path.is_file():
            with open(toml_path, "rb") as fh:
                manifest = tomllib.load(fh)
        package_root = path
    elif path.is_file() and path.suffix == ".toml":
        with open(path, "rb") as fh:
            manifest = tomllib.load(fh)
        package_root = path.parent
    else:
        raise ValueError(f"Unsupported swarm source: {source}")

    swarm_cfg = manifest.get("swarm", {})
    name = swarm_cfg.get("name", path.stem if path.is_file() else path.name)

    fetcher = _resolve_fetcher_from_manifest(manifest)
    swarm = _core.create_swarm(name, llm_fetcher=fetcher)

    # --- Optional graph.py ------------------------------------------------
    graph_file = swarm_cfg.get("graph_file", "graph.py")
    graph_path = package_root / graph_file
    if graph_path.is_file() and fetcher is not None:
        try:
            import importlib.util

            mod_name = f"_angelus_swarm_graph_{name}"
            spec = importlib.util.spec_from_file_location(mod_name, graph_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "build_graph"):
                    graph = mod.build_graph(swarm)
                    if isinstance(graph, ExecutionGraph):
                        swarm.execution_graph = graph
        except Exception as exc:
            _core.record_runtime_change(
                action="load_graph_skipped",
                subject_kind="swarm",
                subject_id=name,
                detail={"reason": str(exc), "graph_file": str(graph_path)},
            )

    # --- Global variables -------------------------------------------------
    globals_cfg = manifest.get("globals")
    if globals_cfg is not None:
        _core.set_global_variables(globals_cfg)

    # --- Tool capabilities ------------------------------------------------
    tool_caps = manifest.get("tool_capabilities", {})
    for tool_name, caps in tool_caps.items():
        if isinstance(caps, list):
            _core.set_tool_capabilities(tool_name, caps)

    return name, swarm


def _resolve_fetcher_from_manifest(manifest: Dict[str, Any]) -> Optional[LLMFetcher]:
    llm_block = manifest.get("llm", {}).get("default", {})
    if llm_block.get("api_url"):
        backend = LLMBackendConfig(
            name=llm_block.get("name", "default"),
            provider=llm_block.get("provider", "openai"),
            api_url=llm_block["api_url"],
            api_key=_resolve_api_key(llm_block.get("api_key", "")),
            model=llm_block.get("model", ""),
        )
        return LLMFetcher(backends=[backend])
    return None


def _resolve_fetcher_from_env() -> LLMFetcher:
    """Build a minimal LLMFetcher from environment variables.

    Looks for ANGELUS_API_KEY and falls back to standard provider env vars.
    """
    api_key = os.environ.get("ANGELUS_API_KEY", "")
    if not api_key:
        # Try common provider keys as fallback
        for env_var in ("OPENAI_API_KEY", "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY"):
            api_key = os.environ.get(env_var, "")
            if api_key:
                break

    provider = os.environ.get("ANGELUS_PROVIDER", "openai")
    api_url = os.environ.get("ANGELUS_API_URL", "")
    model = os.environ.get("ANGELUS_MODEL", "")

    backend = LLMBackendConfig(
        name="default",
        provider=provider,
        api_url=api_url or "",
        api_key=api_key,
        model=model,
    )
    return LLMFetcher(backends=[backend])


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(config_path: Optional[Path] = None) -> FastAPI:
    app = FastAPI(
        title="Angelus API",
        description="Thin REST layer over the Angelus swarm runtime.",
        version="2.0.0",
    )

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/swarms", response_model=SwarmListResponse)
    async def list_swarms() -> SwarmListResponse:
        infos = [SwarmInfo(**item) for item in _core.list_swarms()]
        return SwarmListResponse(swarms=infos)

    @app.post("/swarms/load", response_model=LoadSwarmResponse)
    async def load_swarm(req: LoadSwarmRequest) -> LoadSwarmResponse:
        try:
            name, _swarm = await _load_swarm_from_source(req.source)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return LoadSwarmResponse(name=name, id=name)

    @app.delete("/swarms/{name}")
    async def unload_swarm(name: str) -> JSONResponse:
        if name not in _core.swarms:
            raise HTTPException(status_code=404, detail=f"Swarm '{name}' not found.")
        _core.remove_swarm(name)
        return JSONResponse({"detail": "unloaded"})

    @app.post("/swarms/{name}/run")
    async def run_swarm(name: str, req: RunRequest) -> StreamingResponse:
        try:
            swarm = _core.get_swarm(name)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Swarm '{name}' not found.")

        async def event_stream() -> AsyncIterator[str]:
            ctx: Any = None
            yield _sse_event("start", {"input": req.input})
            try:
                ctx = await swarm.run(req.input)

                output = ""
                node_outputs = getattr(ctx, "node_outputs", {})
                if node_outputs:
                    for node_id, value in node_outputs.items():
                        if "output" in str(node_id).lower():
                            output = str(value)
                            break
                    if not output:
                        output = str(list(node_outputs.values())[-1])
                else:
                    output = str(ctx)

                trace = _build_trace(ctx)
                _core.record_run(name, req.input, output, trace)
                yield _sse_event("result", {"output": output, "trace": trace})
            except asyncio.CancelledError as exc:
                stop_state = getattr(swarm.execution_graph, "stop_state", {})
                payload: Dict[str, Any] = {
                    "detail": str(exc) or "run cancelled",
                    "stop_state": stop_state,
                }
                if ctx is not None:
                    payload["trace"] = _build_trace(ctx)
                yield _sse_event("stopped", payload)
            except Exception as exc:
                yield _sse_event(
                    "error",
                    {"detail": str(exc), "traceback": traceback.format_exc()},
                )
            yield _sse_event("done", {})

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
        )

    @app.post("/swarms/{name}/stop", response_model=StopResponse)
    async def stop_swarm(name: str, req: StopRequest) -> StopResponse:
        try:
            swarm = _core.get_swarm(name)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Swarm '{name}' not found.")

        if req.mode == "soft":
            swarm.request_soft_stop(reason=req.reason)
        elif req.mode == "hard":
            swarm.request_hard_stop(reason=req.reason)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported stop mode: {req.mode}")

        stop_state = getattr(swarm.execution_graph, "stop_state", {})
        return StopResponse(
            name=name,
            mode=req.mode,
            requested=True,
            reason=req.reason,
            stop_state=dict(stop_state),
        )

    @app.get("/swarms/{name}/graph", response_model=GraphResponse)
    async def get_graph(name: str) -> GraphResponse:
        try:
            snap = _core.get_agent_graph_snapshot(name)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Swarm '{name}' not found.")
        return GraphResponse(
            name=snap.get("graph_name", name),
            nodes=snap.get("nodes", {}),
            edges=snap.get("edges", []),
        )

    @app.get("/swarms/{name}/history", response_model=HistoryResponse)
    async def get_history(name: str, limit: int = 20) -> HistoryResponse:
        if name not in _core.swarms:
            raise HTTPException(status_code=404, detail=f"Swarm '{name}' not found.")
        runs = _core.get_history(name, limit=limit)
        return HistoryResponse(runs=[RunRecord(**r) for r in runs])

    return app
