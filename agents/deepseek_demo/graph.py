from core import AgentNode, ExecutionGraph, ToolNode


def build_graph(core):
    graph = ExecutionGraph("deepseek_demo")

    graph.add_node(
        AgentNode(
            node_id=1,
            node_name="planner",
            agent_id="planner",
            next_node_ids=[2],
        )
    )
    graph.add_node(
        ToolNode(
            node_id=2,
            node_name="echo",
            tool_name="echo",
        )
    )

    graph.set_entry(1)
    graph.set_exit(2)
    return graph
