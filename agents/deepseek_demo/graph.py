from core import AgentNode, ExecutionGraph


def build_graph(core):
    graph = ExecutionGraph('deepseek_demo')

    # 1. requirement_analyst
    graph.add_node(
        AgentNode(
            node_id=1,
            node_name='requirement_analyst',
            next_node_ids=[2],
            metadata={'tool_execution_mode': 'external'},
            agent_id='requirement_analyst',
            additional_prompt=(
                'Phase: requirement analysis. Understand the user request, read the project '
                'structure and relevant files, search for related code, and produce a clear '
                'implementation plan. Output a JSON envelope with content (the plan) and '
                'tool_requests (file_reader, search, command_runner). When done, set next_node_ids: [2].'
            ),
        ),
    )

    # 2. coder
    graph.add_node(
        AgentNode(
            node_id=2,
            node_name='coder',
            next_node_ids=[3],
            metadata={'tool_execution_mode': 'external'},
            agent_id='coder',
            additional_prompt=(
                'Phase: implementation. You are a coding assistant similar to Claude Code. '
                'Read files before editing. Use file_editor for precise edits and file_writer for new files. '
                'Run commands (tests, build, lint) to verify your changes. If verification fails, '
                'fix the code and re-verify. Output a JSON envelope with tool_requests. '
                'When implementation is complete and verified, set next_node_ids: [3].'
            ),
        ),
    )

    # 3. reviewer
    graph.add_node(
        AgentNode(
            node_id=3,
            node_name='reviewer',
            next_node_ids=[],
            metadata={'tool_execution_mode': 'external'},
            agent_id='reviewer',
            additional_prompt=(
                'Phase: review. Review the implementation against the original requirements. '
                'Read the modified files, run verification commands (tests), and assess quality. '
                'Output a JSON envelope with verdict and next_node_ids. '
                'verdict=approve with next_node_ids=[] ends the run. '
                'verdict=revise with next_node_ids:[2] sends back to coder for fixes.'
            ),
        ),
    )

    graph.add_edge(1, 2, label='implement', condition=None, priority=10)
    graph.add_edge(2, 3, label='review', condition=None, priority=10)
    graph.add_edge(3, 2, label='revise', condition='revise', priority=10)

    graph.set_entry(1)
    graph.set_exit(3)
    return graph
