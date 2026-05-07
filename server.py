"""Angelus v2 server — thin REST API over modules.llm_fetcher."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from modules.llm_fetcher.swarm.swarm import AgentSwarm, SwarmSpec
from modules.llm_fetcher.agent import Agent as LlmAgent
from modules.llm_fetcher.llm_fetcher import LLMFetcher
from modules.llm_fetcher.tool import Tool, ToolRegistry
from modules.llm_fetcher.swarm.execution_graph import (
    ExecutionGraph,
    InputNode,
    OutputNode,
    JoinNode,
    AgentNode,
    ToolNode,
    RouterNode,
)

# ---------------------------------------------------------------------------
# In-memory swarm registry
# ---------------------------------------------------------------------------

class SwarmStore:
    """Holds loaded swarms in memory."""

    def __init__(self) -> None:
        self._swarms: Dict[str, AgentSwarm] = {}
        self._history: Dict[str, List[Dict[str, Any]]] = {}

    def list(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": name,
                "agent_count": len(s.agents),
                "tool_count": len(s.tool_registry._tools) if hasattr(s, "tool_registry") else 0,
            }
            for name, s in self._swarms.items()
        ]

    def get(self, name: str) -> AgentSwarm:
        if name not in self._swarms:
            raise HTTPException(404, f"Swarm '{name}' not found")
        return self._swarms[name]

    def add(self, name: str, swarm: AgentSwarm) -> None:
        self._swarms[name] = swarm
        self._history[name] = []

    def remove(self, name: str) -> None:
        self._swarms.pop(name, None)
        self._history.pop(name, None)

    def push_history(self, name: str, entry: Dict[str, Any]) -> None:
        self._history.setdefault(name, []).append(entry)

    def get_history(self, name: str, limit: int = 20) -> List[Dict[str, Any]]:
        return (self._history.get(name) or [])[-limit:]


store = SwarmStore()

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Angelus v2", version="0.2.0")


# ── Health ──

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── Swarm management ──

@app.get("/api/swarms")
async def list_swarms():
    return {"swarms": store.list()}


class LoadRequest(BaseModel):
    source: str


@app.post("/api/swarms/load")
async def load_swarm(req: LoadRequest):
    """Load a swarm from a directory path (compatible with old angelus packages)."""
    pkg_path = Path(req.source)
    if not pkg_path.exists():
        raise HTTPException(404, f"Package path not found: {req.source}")

    swarm_toml = pkg_path / "swarm.toml"
    if not swarm_toml.exists():
        raise HTTPException(400, f"No swarm.toml in {req.source}")

    # Minimal load: read the manifest, build the graph
    try:
        import tomllib
        with open(swarm_toml, "rb") as f:
            manifest = tomllib.load(f)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse swarm.toml: {e}")

    swarm_name = manifest.get("swarm", {}).get("name", pkg_path.name)

    # Build ExecutionGraph from graph.py if present
    graph_py = pkg_path / "graph.py"
    graph: Optional[ExecutionGraph] = None
    if graph_py.exists():
        import importlib.util, sys as sys_mod
        mod_name = f"_swarm_{swarm_name}_graph"
        spec = importlib.util.spec_from_file_location(mod_name, graph_py)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys_mod.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            if hasattr(mod, "build_graph"):
                graph = mod.build_graph(None)

    if graph is None:
        raise HTTPException(400, f"Failed to build graph from {graph_py}")

    swarm = AgentSwarm(graph=graph)

    # Register tools from the tool pool if any
    llm_config = manifest.get("llm", {}).get("default", {})
    for nid, node in graph.nodes.items():
        if isinstance(node, AgentNode) and node.agent is None:
            agent = LlmAgent(
                llm_handler=LLMFetcher(
                    api_url=llm_config.get("api_url"),
                    api_key=llm_config.get("api_key"),
                    model=llm_config.get("model", "deepseek/deepseek-v4-pro"),
                    provider=llm_config.get("provider", "litellm"),
                ),
                system_prompt=node.system_prompt if hasattr(node, "system_prompt") else "",
            )
            swarm.add_agent(nid, agent)

    store.add(swarm_name, swarm)
    return {"name": swarm_name, "id": swarm_name}


@app.delete("/api/swarms/{name}")
async def unload_swarm(name: str):
    store.remove(name)
    return {"success": True}


# ── Graph ──

@app.get("/api/swarms/{name}/graph")
async def get_graph(name: str):
    swarm = store.get(name)
    g = swarm.graph
    if g is None:
        return {"nodes": [], "edges": []}

    node_type_map = {
        InputNode: "input", OutputNode: "output", JoinNode: "join",
        AgentNode: "agent", ToolNode: "tool", RouterNode: "router",
    }

    nodes = [
        {"id": nid, "name": nid, "type": node_type_map.get(type(n), "unknown")}
        for nid, n in g.nodes.items()
    ]
    edges = [
        {"source": e.source_id, "target": e.target_id, "label": e.label}
        for e in g.edges
    ]
    return {"nodes": nodes, "edges": edges}


# ── Run (SSE) ──

class RunRequest(BaseModel):
    input: str = ""
    context: Optional[Dict[str, Any]] = None


@app.post("/api/swarms/{name}/run")
async def run_swarm(name: str, req: RunRequest):
    swarm = store.get(name)
    run_id = uuid.uuid4().hex[:12]

    async def event_stream():
        yield f"data: {json.dumps({'event': 'start', 'run_id': run_id, 'timestamp': time.time()})}\n\n"

        try:
            ctx = await swarm.run(req.input)
            output = ctx.get_output(list(ctx.node_outputs.keys())[-1]) if ctx.node_outputs else None
            trace = [{"node": nid, "output": str(out)[:500]} for nid, out in ctx.node_outputs.items()]

            yield f"data: {json.dumps({'event': 'result', 'run_id': run_id, 'output': str(output)[:5000], 'trace': trace, 'timestamp': time.time()})}\n\n"

            store.push_history(name, {
                "input": req.input, "output": str(output)[:5000],
                "timestamp": time.time(), "run_id": run_id,
            })
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'run_id': run_id, 'error': str(e), 'timestamp': time.time()})}\n\n"

        yield f"data: {json.dumps({'event': 'done', 'run_id': run_id, 'timestamp': time.time()})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── History ──

@app.get("/api/swarms/{name}/history")
async def get_history(name: str):
    return {"history": store.get_history(name)}


# ── Entry point ──

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8877)
