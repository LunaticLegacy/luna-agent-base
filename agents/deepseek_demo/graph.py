from core import AgentNode, ExecutionGraph, ToolNode


def build_graph(core):
    graph = ExecutionGraph("deepseek_demo")

    graph.add_node(
        AgentNode(
            node_id=1,
            node_name="planner",
            agent_id="planner",
            next_node_ids=[2, 3],
            metadata={
                "route_policy": "all",
                "join_node_id": 4,
            },
        )
    )
    graph.add_node(
        AgentNode(
            node_id=2,
            node_name="researcher",
            agent_id="researcher",
        )
    )
    graph.add_node(
        AgentNode(
            node_id=3,
            node_name="writer",
            agent_id="writer",
        )
    )
    graph.add_node(
        AgentNode(
            node_id=4,
            node_name="reviewer",
            agent_id="reviewer",
            next_node_ids=[5],
        )
    )
    graph.add_node(
        ToolNode(
            node_id=5,
            node_name="graph_editor",
            tool_name="graph_editor",
            next_node_ids=[6],
        )
    )
    graph.add_node(
        AgentNode(
            node_id=6,
            node_name="publisher",
            agent_id="publisher",
            next_node_ids=[7],
        )
    )
    graph.add_node(
        ToolNode(
            node_id=7,
            node_name="file_writer",
            tool_name="file_writer",
            input_mapping={
                "path": "outputs/deepseek_demo_final.txt",
            },
        )
    )

    graph.add_edge(1, 2, label="research", priority=10)
    graph.add_edge(1, 3, label="write", priority=5)
    graph.add_edge(4, 5, label="edit_graph", priority=10)
    graph.add_edge(5, 6, label="publish", priority=10)
    graph.add_edge(6, 7, label="write_file", priority=10)

    graph.set_entry(1)
    graph.set_exit(7)
    return graph
