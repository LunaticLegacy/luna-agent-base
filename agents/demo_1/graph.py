from core import AgentNode, ExecutionGraph


def build_graph(core):
    graph = ExecutionGraph("demo_1")
    graph.add_node(
        AgentNode(
            node_id=1,
            node_name="hello_writer",
            metadata={"tool_execution_mode": "external"},
            agent_id="hello_writer",
        )
    )
    graph.set_entry(1)
    graph.set_exit(1)
    return graph
