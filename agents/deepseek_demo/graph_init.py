from core import AgentNode, ExecutionGraph, ToolNode


def _spawn_control(agent_id: str, name: str, mission: str) -> dict:
    return {
        "agent_id": agent_id,
        "name": name,
        "skill_name": "researcher_prompt",
        "additional_prompt": mission,
        "replace_existing": True,
    }


def _graph_edit_control(
    *,
    node_id: int,
    node_name: str,
    agent_id: str,
    mission: str,
    next_node_ids: list[int],
) -> dict:
    return {
        "node_id": node_id,
        "node_name": node_name,
        "agent_id": agent_id,
        "additional_prompt": mission,
        "next_node_ids": list(next_node_ids),
        "replace_existing": True,
        "runtime_transient": True,
    }


def _add_research_branch(
    graph: ExecutionGraph,
    *,
    spawn_node_id: int,
    insert_node_id: int,
    destroy_node_id: int,
    remove_node_id: int,
    transient_node_id: int,
    transient_agent_id: str,
    transient_node_name: str,
    mission: str,
):
    graph.add_node(
        ToolNode(
            node_id=spawn_node_id,
            node_name=f"spawn_{transient_node_name}",
            tool_name="agent_manager",
            input_mapping={
                "action": "create_agent",
                "spawn": _spawn_control(transient_agent_id, transient_node_name, mission),
            },
            next_node_ids=[insert_node_id],
        )
    )
    graph.add_node(
        ToolNode(
            node_id=insert_node_id,
            node_name=f"insert_{transient_node_name}",
            tool_name="graph_editor",
            input_mapping={
                "action": "add_agent_node",
                "graph_edit": _graph_edit_control(
                    node_id=transient_node_id,
                    node_name=transient_node_name,
                    agent_id=transient_agent_id,
                    mission=mission,
                    next_node_ids=[destroy_node_id],
                ),
            },
            next_node_ids=[destroy_node_id],
        )
    )
    graph.add_node(
        ToolNode(
            node_id=destroy_node_id,
            node_name=f"destroy_{transient_node_name}",
            tool_name="agent_manager",
            input_mapping={
                "action": "destroy_agent",
                "destroy": {
                    "agent_id": transient_agent_id,
                },
            },
            next_node_ids=[remove_node_id],
        )
    )
    graph.add_node(
        ToolNode(
            node_id=remove_node_id,
            node_name=f"remove_{transient_node_name}",
            tool_name="graph_editor",
            input_mapping={
                "action": "remove_node",
                "graph_edit": {
                    "node_id": transient_node_id,
                },
            },
        )
    )


def build_graph(core):
    graph = ExecutionGraph("deepseek_demo")

    graph.add_node(
        AgentNode(
            node_id=1,
            node_name="orchestrator",
            agent_id="orchestrator",
            next_node_ids=[2],
        )
    )

    graph.add_node(
        AgentNode(
            node_id=2,
            node_name="organizer_preflight",
            agent_id="organizer",
            next_node_ids=[3, 4, 22],
            additional_prompt=(
                "Phase: preflight. Inspect the incoming request and decide whether the branch tree "
                "should stay wide or be narrowed before dispatch. If the task asks for an "
                "implementation artifact, route directly to the code writer. If the task is simple "
                "and research-oriented, you may route directly to the dispatcher. If the task is "
                "broad, keep the planner in the loop."
            ),
            metadata={"phase": "preflight"},
        )
    )

    graph.add_node(
        AgentNode(
            node_id=3,
            node_name="planner",
            agent_id="planner",
            next_node_ids=[4],
        )
    )

    graph.add_node(
        AgentNode(
            node_id=4,
            node_name="research_dispatcher",
            agent_id="organizer",
            next_node_ids=[5, 9, 13],
            additional_prompt=(
                "Phase: dispatch. Fan out the active branches, but keep the shape adaptive. "
                "Use graph edits to widen or narrow the tree if the current situation requires it. "
                "The join point is node 17. "
                "Do not include next_node_id, next_node_ids, branch, or branches in your response. "
                "The runtime will handle routing automatically."
            ),
            metadata={
                "route_policy": "all",
                "join_node_id": 17,
                "phase": "dispatch",
            },
        )
    )

    _add_research_branch(
        graph,
        spawn_node_id=5,
        insert_node_id=6,
        destroy_node_id=7,
        remove_node_id=8,
        transient_node_id=31,
        transient_agent_id="architecture_researcher_runtime",
        transient_node_name="architecture_researcher_runtime",
        mission=(
            "Focus on graph topology, branching patterns, loop design, and how the adaptive "
            "organizer can permanently reshape the runtime architecture."
        ),
    )
    _add_research_branch(
        graph,
        spawn_node_id=9,
        insert_node_id=10,
        destroy_node_id=11,
        remove_node_id=12,
        transient_node_id=32,
        transient_agent_id="evidence_researcher_runtime",
        transient_node_name="evidence_researcher_runtime",
        mission=(
            "Focus on implementation evidence, configuration fidelity, runtime behavior, and the "
            "parts of the demo that prove the architecture is real rather than decorative."
        ),
    )
    _add_research_branch(
        graph,
        spawn_node_id=13,
        insert_node_id=14,
        destroy_node_id=15,
        remove_node_id=16,
        transient_node_id=33,
        transient_agent_id="risk_researcher_runtime",
        transient_node_name="risk_researcher_runtime",
        mission=(
            "Focus on failure modes, invalid graph states, cleanup hazards, and operational risks "
            "introduced by loops, fanout, and live graph surgery."
        ),
    )

    graph.add_node(
        AgentNode(
            node_id=17,
            node_name="organizer_checkpoint",
            agent_id="organizer",
            next_node_ids=[18, 3, 22],
            additional_prompt=(
                "Phase: checkpoint. Read the merged branch results, decide whether the architecture "
                "needs another planning pass, and use graph edits if the tree shape should change "
                "before the final write. If the task is implementation-oriented, route directly to "
                "the code writer instead of the report writer."
            ),
            metadata={"phase": "checkpoint"},
        )
    )

    graph.add_node(
        AgentNode(
            node_id=18,
            node_name="writer",
            agent_id="writer",
            next_node_ids=[19],
            additional_prompt=(
                "Synthesize the branch outputs into a single report. Treat the architecture notes, "
                "evidence notes, and risk notes as parallel inputs that must be merged cleanly."
            ),
        )
    )

    graph.add_node(
        AgentNode(
            node_id=22,
            node_name="code_writer",
            agent_id="code_writer",
            next_node_ids=[23],
            additional_prompt=(
                "Write a single self-contained Python module that satisfies the implementation brief. "
                "Output only source code, no markdown, no report prose, and no extra commentary. "
                "Prefer a minimal but correct implementation with explicit shape checks, deterministic "
                "demo input, and a runnable __main__ block."
            ),
        )
    )

    graph.add_node(
        ToolNode(
            node_id=23,
            node_name="file_writer_code",
            tool_name="file_writer",
            input_mapping={"path": "code/transformer.py"},
        )
    )

    graph.add_node(
        AgentNode(
            node_id=19,
            node_name="reviewer",
            agent_id="reviewer",
            next_node_ids=[20, 18, 2],
            additional_prompt=(
                "Return a verdict that also selects the next runtime node through next_node_ids. "
                "approve -> 20, revise -> 18, re_research -> 2."
            ),
        )
    )

    graph.add_node(
        AgentNode(
            node_id=20,
            node_name="publisher",
            agent_id="publisher",
            next_node_ids=[21],
        )
    )

    graph.add_node(
        ToolNode(
            node_id=21,
            node_name="file_writer",
            tool_name="file_writer",
            input_mapping={"path": "outputs/deepseek_demo_final.txt"},
        )
    )

    graph.add_edge(1, 2, label="frame", priority=10)
    graph.add_edge(2, 22, label="implement", priority=15)
    graph.add_edge(2, 3, label="plan", priority=10)
    graph.add_edge(2, 4, label="direct_dispatch", priority=5)
    graph.add_edge(3, 4, label="dispatch", priority=10)

    graph.add_edge(4, 5, label="structure", condition="branch_a", priority=30)
    graph.add_edge(4, 9, label="evidence", condition="branch_b", priority=20)
    graph.add_edge(4, 13, label="risk", condition="branch_c", priority=10)

    graph.add_edge(5, 6, label="insert_architecture", priority=10)
    graph.add_edge(6, 7, label="cleanup_architecture_agent", priority=10)
    graph.add_edge(7, 8, label="remove_architecture_node", priority=10)

    graph.add_edge(9, 10, label="insert_evidence", priority=10)
    graph.add_edge(10, 11, label="cleanup_evidence_agent", priority=10)
    graph.add_edge(11, 12, label="remove_evidence_node", priority=10)

    graph.add_edge(13, 14, label="insert_risk", priority=10)
    graph.add_edge(14, 15, label="cleanup_risk_agent", priority=10)
    graph.add_edge(15, 16, label="remove_risk_node", priority=10)

    graph.add_edge(17, 3, label="replan", priority=5)
    graph.add_edge(17, 18, label="write", priority=10)
    graph.add_edge(17, 22, label="implement", priority=8)

    graph.add_edge(18, 19, label="review", priority=10)
    graph.add_edge(22, 23, label="write_code", priority=10)

    graph.add_edge(19, 20, label="approve", condition="approve", priority=30)
    graph.add_edge(19, 18, label="revise", condition="revise", priority=20)
    graph.add_edge(19, 2, label="re_research", condition="re_research", priority=10)

    graph.add_edge(20, 21, label="publish", priority=10)

    graph.set_entry(1)
    graph.set_exit(21)
    return graph
