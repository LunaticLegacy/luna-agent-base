from core import AgentNode, ExecutionGraph, ToolNode


def build_graph(core):
    graph = ExecutionGraph('docs_verifier')

    # Node 1: orchestrator - 制定核对计划并分解任务
    graph.add_node(
        AgentNode(node_id=1,
            node_name='orchestrator',
            metadata={'route_policy': 'all', 'join_node_id': 5},
            agent_id='orchestrator',
            additional_prompt=None),
    )

    # Node 2: backend_verifier - 核对后端文档与代码一致性
    graph.add_node(
        AgentNode(node_id=2,
            node_name='backend_verifier',
            metadata={},
            agent_id='backend_verifier',
            additional_prompt=None),
    )

    # Node 3: frontend_verifier - 核对前端文档与代码一致性
    graph.add_node(
        AgentNode(node_id=3,
            node_name='frontend_verifier',
            metadata={},
            agent_id='frontend_verifier',
            additional_prompt=None),
    )

    # Node 4: structure_verifier - 核对结构/API/元数据文档与代码一致性
    graph.add_node(
        AgentNode(node_id=4,
            node_name='structure_verifier',
            metadata={},
            agent_id='structure_verifier',
            additional_prompt=None),
    )

    # Node 5: reviewer - 汇总审核所有核对结果
    graph.add_node(
        AgentNode(node_id=5,
            node_name='reviewer',
            metadata={},
            agent_id='reviewer',
            additional_prompt=None),
    )

    # Node 6: publisher - 生成最终核对报告
    graph.add_node(
        AgentNode(node_id=6,
            node_name='publisher',
            metadata={},
            agent_id='publisher',
            additional_prompt=None),
    )

    # Node 7: file_writer - 将报告写入 outputs/docs_verifier_report.txt
    graph.add_node(
        ToolNode(
            node_id=7,
            node_name='file_writer',
            next_node_ids=[],
            metadata={},
            tool_name='file_writer',
            input_mapping={'path': 'outputs/docs_verifier_report.txt'},
        ),
    )

    # Edges
    graph.add_edge(1, 2, label='verify_backend', condition=None, priority=10)
    graph.add_edge(1, 3, label='verify_frontend', condition=None, priority=10)
    graph.add_edge(1, 4, label='verify_structure', condition=None, priority=10)
    graph.add_edge(2, 5, label='backend_done', condition=None, priority=10)
    graph.add_edge(3, 5, label='frontend_done', condition=None, priority=10)
    graph.add_edge(4, 5, label='structure_done', condition=None, priority=10)
    graph.add_edge(5, 6, label='review_complete', condition=None, priority=10)
    graph.add_edge(6, 7, label='publish', condition=None, priority=10)

    graph.set_entry(1)
    graph.set_exit(7)
    return graph
