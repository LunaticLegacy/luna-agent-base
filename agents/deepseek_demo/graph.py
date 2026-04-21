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
            node_name="spawn_auditor",
            tool_name="agent_manager",
            input_mapping={
                "action": "create_agent",
            },
            next_node_ids=[3],
        )
    )
    graph.add_node(
        ToolNode(
            node_id=3,
            node_name="insert_auditor_node",
            tool_name="graph_editor",
            input_mapping={
                "action": "add_agent_node",
            },
        )
    )
    graph.add_node(
        ToolNode(
            node_id=5,
            node_name="delete_auditor",
            tool_name="agent_manager",
            input_mapping={
                "action": "destroy_agent",
            },
            next_node_ids=[6],
        )
    )
    graph.add_node(
        ToolNode(
            node_id=6,
            node_name="remove_auditor_node",
            tool_name="graph_editor",
            input_mapping={
                "action": "remove_node",
            },
            next_node_ids=[7],
        )
    )
    graph.add_node(
        AgentNode(
            node_id=7,
            node_name="publisher",
            agent_id="publisher",
            next_node_ids=[8],
        )
    )
    graph.add_node(
        ToolNode(
            node_id=8,
            node_name="file_writer",
            tool_name="file_writer",
            input_mapping={
                "path": "outputs/deepseek_demo_final.txt",
            },
        )
    )

    graph.add_edge(1, 2, label="plan_to_spawn", priority=10)
    graph.add_edge(2, 3, label="spawn_to_insert", priority=10)
    graph.add_edge(5, 6, label="delete_to_remove", priority=10)
    graph.add_edge(6, 7, label="cleanup_to_publish", priority=10)
    graph.add_edge(7, 8, label="publish_to_write", priority=10)

    graph.set_entry(1)
    graph.set_exit(8)
    return graph
