from core import AgentNode, ExecutionGraph, ToolNode


def build_graph(core):
    graph = ExecutionGraph("deepseek_demo")

    # === 静态节点 ===

    # 1. Orchestrator: 分析请求，输出研究计划
    graph.add_node(
        AgentNode(
            node_id=1,
            node_name="orchestrator",
            agent_id="orchestrator",
            next_node_ids=[2],
        )
    )

    # 2. Planner: 生成控制计划 + content
    graph.add_node(
        AgentNode(
            node_id=2,
            node_name="planner",
            agent_id="planner",
            next_node_ids=[3],
        )
    )

    # 3. Spawn Researcher: 动态创建 researcher agent
    graph.add_node(
        ToolNode(
            node_id=3,
            node_name="spawn_researcher",
            tool_name="agent_manager",
            input_mapping={"action": "create_agent"},
            next_node_ids=[4],
        )
    )

    # 4. Insert Researcher Node: 将 researcher 插入图
    graph.add_node(
        ToolNode(
            node_id=4,
            node_name="insert_researcher_node",
            tool_name="graph_editor",
            input_mapping={"action": "add_agent_node"},
            next_node_ids=[5],
        )
    )

    # 5. Researcher: 执行深度搜索（带 web_search 工具）
    graph.add_node(
        AgentNode(
            node_id=5,
            node_name="researcher_runtime",
            agent_id="researcher_runtime",
            next_node_ids=[6],
            metadata={"runtime_transient": True},
        )
    )

    # 6. Delete Researcher: 清理临时 agent
    graph.add_node(
        ToolNode(
            node_id=6,
            node_name="delete_researcher",
            tool_name="agent_manager",
            input_mapping={"action": "destroy_agent"},
            next_node_ids=[7],
        )
    )

    # 7. Remove Researcher Node: 从图中移除
    graph.add_node(
        ToolNode(
            node_id=7,
            node_name="remove_researcher_node",
            tool_name="graph_editor",
            input_mapping={"action": "remove_node"},
            next_node_ids=[8],
        )
    )

    # 8. Writer: 基于研究笔记撰写报告
    graph.add_node(
        AgentNode(
            node_id=8,
            node_name="writer",
            agent_id="writer",
            next_node_ids=[9],
        )
    )

    # 9. Reviewer: 审核，输出条件分支
    graph.add_node(
        AgentNode(
            node_id=9,
            node_name="reviewer",
            agent_id="reviewer",
            next_node_ids=[10, 8],  # 10=publisher, 8=writer (revise)
        )
    )

    # 10. Publisher: 最终润色
    graph.add_node(
        AgentNode(
            node_id=10,
            node_name="publisher",
            agent_id="publisher",
            next_node_ids=[11],
        )
    )

    # 11. File Writer: 写入文件
    graph.add_node(
        ToolNode(
            node_id=11,
            node_name="file_writer",
            tool_name="file_writer",
            input_mapping={"path": "outputs/deepseek_demo_final.txt"},
        )
    )

    # === 边定义 ===
    graph.add_edge(1, 2, label="plan", priority=10)
    graph.add_edge(2, 3, label="spawn", priority=10)
    graph.add_edge(3, 4, label="insert", priority=10)
    graph.add_edge(4, 5, label="research", priority=10)
    graph.add_edge(5, 6, label="cleanup_agent", priority=10)
    graph.add_edge(6, 7, label="cleanup_node", priority=10)
    graph.add_edge(7, 8, label="write", priority=10)
    graph.add_edge(8, 9, label="review", priority=10)

    # Reviewer 条件边
    graph.add_edge(9, 10, label="approve", condition="approve", priority=20)
    graph.add_edge(9, 8, label="revise", condition="revise", priority=10)

    graph.add_edge(10, 11, label="publish", priority=10)

    graph.set_entry(1)
    graph.set_exit(11)
    return graph
