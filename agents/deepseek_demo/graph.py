from core import AgentNode, ExecutionGraph, ToolNode


def build_graph(core):
    graph = ExecutionGraph('deepseek_demo')
    graph.add_node(
        AgentNode(
            node_id=1,
            node_name='orchestrator',
            next_node_ids=[2],
            metadata={},
            agent_id='orchestrator',
            additional_prompt=None,
        ),
    )
    graph.add_node(
        AgentNode(
            node_id=2,
            node_name='organizer_preflight',
            next_node_ids=[3, 4],
            metadata={'phase': 'preflight'},
            agent_id='organizer',
            additional_prompt=('Phase: preflight. Inspect the incoming request and decide whether the branch '
 'tree should stay wide or be narrowed before dispatch. If the task is simple, '
 'you may route directly to the dispatcher. If the task is broad, keep the '
 'planner in the loop.'),
        ),
    )
    graph.add_node(
        AgentNode(
            node_id=3,
            node_name='planner',
            next_node_ids=[4],
            metadata={},
            agent_id='planner',
            additional_prompt=None,
        ),
    )
    graph.add_node(
        AgentNode(
            node_id=4,
            node_name='research_dispatcher',
            next_node_ids=[5, 9, 13],
            metadata={'join_node_id': 17, 'phase': 'dispatch', 'route_policy': 'all'},
            agent_id='organizer',
            additional_prompt=('Phase: dispatch. Fan out the active branches, but keep the shape adaptive. '
 'Use graph edits to widen or narrow the tree if the current situation '
 'requires it. The join point is node 17. Do not include next_node_id, '
 'next_node_ids, branch, or branches in your response. The runtime will handle '
 'routing automatically.'),
        ),
    )
    graph.add_node(
        ToolNode(
            node_id=5,
            node_name='spawn_architecture_researcher_runtime',
            next_node_ids=[6],
            metadata={},
            tool_name='agent_manager',
            input_mapping={'action': 'create_agent',
 'spawn': {'additional_prompt': 'Focus on graph topology, branching patterns, '
                                'loop design, and how the adaptive organizer '
                                'can permanently reshape the runtime '
                                'architecture.',
           'agent_id': 'architecture_researcher_runtime',
           'name': 'architecture_researcher_runtime',
           'replace_existing': True,
           'skill_name': 'researcher_prompt'}},
        ),
    )
    graph.add_node(
        ToolNode(
            node_id=6,
            node_name='insert_architecture_researcher_runtime',
            next_node_ids=[7],
            metadata={},
            tool_name='graph_editor',
            input_mapping={'action': 'add_agent_node',
 'graph_edit': {'additional_prompt': 'Focus on graph topology, branching '
                                     'patterns, loop design, and how the '
                                     'adaptive organizer can permanently '
                                     'reshape the runtime architecture.',
                'agent_id': 'architecture_researcher_runtime',
                'next_node_ids': [7],
                'node_id': 31,
                'node_name': 'architecture_researcher_runtime',
                'replace_existing': True,
                'runtime_transient': True}},
        ),
    )
    graph.add_node(
        ToolNode(
            node_id=7,
            node_name='destroy_architecture_researcher_runtime',
            next_node_ids=[8],
            metadata={},
            tool_name='agent_manager',
            input_mapping={'action': 'destroy_agent',
 'destroy': {'agent_id': 'architecture_researcher_runtime'}},
        ),
    )
    graph.add_node(
        ToolNode(
            node_id=8,
            node_name='remove_architecture_researcher_runtime',
            next_node_ids=[],
            metadata={},
            tool_name='graph_editor',
            input_mapping={'action': 'remove_node', 'graph_edit': {'node_id': 31}},
        ),
    )
    graph.add_node(
        ToolNode(
            node_id=9,
            node_name='spawn_evidence_researcher_runtime',
            next_node_ids=[10],
            metadata={},
            tool_name='agent_manager',
            input_mapping={'action': 'create_agent',
 'spawn': {'additional_prompt': 'Focus on implementation evidence, '
                                'configuration fidelity, runtime behavior, and '
                                'the parts of the demo that prove the '
                                'architecture is real rather than decorative.',
           'agent_id': 'evidence_researcher_runtime',
           'name': 'evidence_researcher_runtime',
           'replace_existing': True,
           'skill_name': 'researcher_prompt'}},
        ),
    )
    graph.add_node(
        ToolNode(
            node_id=10,
            node_name='insert_evidence_researcher_runtime',
            next_node_ids=[11],
            metadata={},
            tool_name='graph_editor',
            input_mapping={'action': 'add_agent_node',
 'graph_edit': {'additional_prompt': 'Focus on implementation evidence, '
                                     'configuration fidelity, runtime '
                                     'behavior, and the parts of the demo that '
                                     'prove the architecture is real rather '
                                     'than decorative.',
                'agent_id': 'evidence_researcher_runtime',
                'next_node_ids': [11],
                'node_id': 32,
                'node_name': 'evidence_researcher_runtime',
                'replace_existing': True,
                'runtime_transient': True}},
        ),
    )
    graph.add_node(
        ToolNode(
            node_id=11,
            node_name='destroy_evidence_researcher_runtime',
            next_node_ids=[12],
            metadata={},
            tool_name='agent_manager',
            input_mapping={'action': 'destroy_agent',
 'destroy': {'agent_id': 'evidence_researcher_runtime'}},
        ),
    )
    graph.add_node(
        ToolNode(
            node_id=12,
            node_name='remove_evidence_researcher_runtime',
            next_node_ids=[],
            metadata={},
            tool_name='graph_editor',
            input_mapping={'action': 'remove_node', 'graph_edit': {'node_id': 32}},
        ),
    )
    graph.add_node(
        ToolNode(
            node_id=13,
            node_name='spawn_risk_researcher_runtime',
            next_node_ids=[14],
            metadata={},
            tool_name='agent_manager',
            input_mapping={'action': 'create_agent',
 'spawn': {'additional_prompt': 'Focus on failure modes, invalid graph states, '
                                'cleanup hazards, and operational risks '
                                'introduced by loops, fanout, and live graph '
                                'surgery.',
           'agent_id': 'risk_researcher_runtime',
           'name': 'risk_researcher_runtime',
           'replace_existing': True,
           'skill_name': 'researcher_prompt'}},
        ),
    )
    graph.add_node(
        ToolNode(
            node_id=14,
            node_name='insert_risk_researcher_runtime',
            next_node_ids=[15],
            metadata={},
            tool_name='graph_editor',
            input_mapping={'action': 'add_agent_node',
 'graph_edit': {'additional_prompt': 'Focus on failure modes, invalid graph '
                                     'states, cleanup hazards, and operational '
                                     'risks introduced by loops, fanout, and '
                                     'live graph surgery.',
                'agent_id': 'risk_researcher_runtime',
                'next_node_ids': [15],
                'node_id': 33,
                'node_name': 'risk_researcher_runtime',
                'replace_existing': True,
                'runtime_transient': True}},
        ),
    )
    graph.add_node(
        ToolNode(
            node_id=15,
            node_name='destroy_risk_researcher_runtime',
            next_node_ids=[16],
            metadata={},
            tool_name='agent_manager',
            input_mapping={'action': 'destroy_agent', 'destroy': {'agent_id': 'risk_researcher_runtime'}},
        ),
    )
    graph.add_node(
        ToolNode(
            node_id=16,
            node_name='remove_risk_researcher_runtime',
            next_node_ids=[],
            metadata={},
            tool_name='graph_editor',
            input_mapping={'action': 'remove_node', 'graph_edit': {'node_id': 33}},
        ),
    )
    graph.add_node(
        AgentNode(
            node_id=17,
            node_name='organizer_checkpoint',
            next_node_ids=[18, 3],
            metadata={'phase': 'checkpoint'},
            agent_id='organizer',
            additional_prompt=('Phase: checkpoint. Read the merged branch results, decide whether the '
 'architecture needs another planning pass, and use graph edits if the tree '
 'shape should change before the final write.'),
        ),
    )
    graph.add_node(
        AgentNode(
            node_id=18,
            node_name='writer',
            next_node_ids=[19],
            metadata={},
            agent_id='writer',
            additional_prompt=('Synthesize the branch outputs into a single report. Treat the architecture '
 'notes, evidence notes, and risk notes as parallel inputs that must be merged '
 'cleanly.'),
        ),
    )
    graph.add_node(
        AgentNode(
            node_id=19,
            node_name='reviewer',
            next_node_ids=[20, 18, 2],
            metadata={},
            agent_id='reviewer',
            additional_prompt=('Return a verdict that also selects the next runtime node through '
 'next_node_ids. approve -> 20, revise -> 18, re_research -> 2.'),
        ),
    )
    graph.add_node(
        AgentNode(
            node_id=20,
            node_name='publisher',
            next_node_ids=[21],
            metadata={},
            agent_id='publisher',
            additional_prompt=None,
        ),
    )
    graph.add_node(
        ToolNode(
            node_id=21,
            node_name='file_writer',
            next_node_ids=[],
            metadata={},
            tool_name='file_writer',
            input_mapping={'path': 'outputs/deepseek_demo_final.txt'},
        ),
    )
    graph.add_node(
        AgentNode(
            node_id=32,
            node_name='evidence_researcher_runtime',
            next_node_ids=[11],
            metadata={'runtime_transient': True},
            agent_id='evidence_researcher_runtime',
            additional_prompt=('Focus on implementation evidence, configuration fidelity, runtime behavior, '
 'and the parts of the demo that prove the architecture is real rather than '
 'decorative.'),
        ),
    )
    graph.add_edge(1, 2, label='frame', condition=None, priority=10)
    graph.add_edge(2, 4, label='direct_dispatch', condition=None, priority=5)
    graph.add_edge(2, 3, label='plan', condition=None, priority=10)
    graph.add_edge(3, 4, label='dispatch', condition=None, priority=10)
    graph.add_edge(4, 13, label='risk', condition='branch_c', priority=10)
    graph.add_edge(4, 9, label='evidence', condition='branch_b', priority=20)
    graph.add_edge(4, 5, label='structure', condition='branch_a', priority=30)
    graph.add_edge(5, 6, label='insert_architecture', condition=None, priority=10)
    graph.add_edge(6, 7, label='cleanup_architecture_agent', condition=None, priority=10)
    graph.add_edge(7, 8, label='remove_architecture_node', condition=None, priority=10)
    graph.add_edge(9, 10, label='insert_evidence', condition=None, priority=10)
    graph.add_edge(10, 11, label='cleanup_evidence_agent', condition=None, priority=10)
    graph.add_edge(11, 12, label='remove_evidence_node', condition=None, priority=10)
    graph.add_edge(13, 14, label='insert_risk', condition=None, priority=10)
    graph.add_edge(14, 15, label='cleanup_risk_agent', condition=None, priority=10)
    graph.add_edge(15, 16, label='remove_risk_node', condition=None, priority=10)
    graph.add_edge(17, 3, label='replan', condition=None, priority=5)
    graph.add_edge(17, 18, label='write', condition=None, priority=10)
    graph.add_edge(18, 19, label='review', condition=None, priority=10)
    graph.add_edge(19, 2, label='re_research', condition='re_research', priority=10)
    graph.add_edge(19, 18, label='revise', condition='revise', priority=20)
    graph.add_edge(19, 20, label='approve', condition='approve', priority=30)
    graph.add_edge(20, 21, label='publish', condition=None, priority=10)
    graph.add_edge(32, 11, label=None, condition=None, priority=0)
    graph.set_entry(1)
    graph.set_exit(21)
    return graph
