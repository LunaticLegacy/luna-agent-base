"""Angelus + memory_graph llm_fetcher 集成示例。

演示如何在 Angelus 环境中直接使用桥接进来的轻量级组件：
- ExecutionGraph: 并行执行 + 超时控制
- AgentSwarm: Swarm 容器 + 执行图 + 思维图谱
- ThinkingGraph: 动态认知图
"""

import asyncio
import os

from core import (
    LLMFetcher,
    AgentSwarm,
    SwarmSpec,
    GraphExecutionGraph,
    Tool,
)
from core import create_execution_graph_tools, create_thinking_graph_tools


async def demo_parallel_execution():
    """演示 ExecutionGraph 的并行分支能力。"""
    print("\n【并行分支演示】")

    async def slow_fetch(**kwargs):
        await asyncio.sleep(0.3)
        return "fetched: data"

    async def slow_compute(**kwargs):
        await asyncio.sleep(0.3)
        return "computed: data"

    graph = GraphExecutionGraph(max_concurrency=2)
    graph.add_input_node("input")
    graph.add_tool_node(Tool("fetch", "fetch data", {}, slow_fetch), "fetch")
    graph.add_tool_node(Tool("compute", "compute data", {}, slow_compute), "compute")
    graph.add_join_node("all", "merge")
    graph.add_output_node(node_id="output")

    graph.connect("input", "fetch")
    graph.connect("input", "compute")
    graph.connect("fetch", "merge")
    graph.connect("compute", "merge")
    graph.connect("merge", "output")

    import time
    start = time.perf_counter()
    ctx = await graph.run("hello")
    elapsed = time.perf_counter() - start

    print(f"  总耗时: {elapsed:.2f}s (两个 0.3s 分支并行, 理论最小 0.3s)")
    print(f"  输出: {ctx.node_outputs.get('output')}")


async def demo_timeout():
    """演示节点超时。"""
    print("\n【节点超时演示】")

    async def very_slow(**kwargs):
        await asyncio.sleep(10)
        return "should not reach here"

    graph = GraphExecutionGraph()
    graph.add_input_node("input")
    graph.add_tool_node(Tool("slow", "slow tool", {}, very_slow), "slow")
    graph.add_output_node(node_id="output")
    graph.connect("input", "slow")
    graph.connect("slow", "output")
    graph.set_node_timeout("slow", 0.2)

    import time
    start = time.perf_counter()
    ctx = await graph.run("test")
    elapsed = time.perf_counter() - start

    print(f"  总耗时: {elapsed:.2f}s (超时设为 0.2s)")
    print(f"  slow 节点输出: {ctx.node_outputs.get('slow')}")
    print(f"  最终输出: {ctx.node_outputs.get('output')}")


async def demo_swarm_with_thinking():
    """演示 AgentSwarm + ThinkingGraph 的协作。"""
    print("\n【Swarm + ThinkingGraph 演示】")

    fetcher = LLMFetcher(
        api_url=os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1"),
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        model="deepseek-chat",
    )

    spec = SwarmSpec(
        name="demo_swarm",
        description="A helpful assistant swarm.",
    )
    swarm = AgentSwarm(fetcher, spec=spec)

    # 添加思维图谱工具
    thinking_tools = create_thinking_graph_tools(swarm.thinking_graph)
    for t in thinking_tools:
        swarm.tool_registry.register(t)

    # 添加执行图工具
    graph_tools = create_execution_graph_tools(swarm.execution_graph)
    for t in graph_tools:
        swarm.tool_registry.register(t)

    print(f"  Swarm: {swarm.name}")
    print(f"  执行图节点: {len(swarm.execution_graph.nodes)}")
    print(f"  工具池: {len(swarm.tool_registry.schemas)} 个工具")


async def main():
    print("=" * 50)
    print("Angelus + memory_graph llm_fetcher 集成示例")
    print("=" * 50)

    await demo_parallel_execution()
    await demo_timeout()
    await demo_swarm_with_thinking()

    print("\n" + "=" * 50)
    print("示例执行完毕")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
