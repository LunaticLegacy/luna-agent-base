from core import AgentNode, ExecutionGraph


def build_graph(core):
    graph = ExecutionGraph('deepseek_demo')

    # 1. requirement_analyst — single outgoing edge, no routing needed
    graph.add_node(
        AgentNode(
            node_id=1,
            node_name='requirement_analyst',
            metadata={'tool_execution_mode': 'external'},
            agent_id='requirement_analyst',
            additional_prompt=(
                'Phase: requirement analysis. Understand the user request, read the project '
                'structure and relevant files, search for related code, and produce a clear '
                'implementation plan. Output a JSON envelope with content (the plan) and '
                'tool_requests (file_reader, search, command_runner).'
            ),
        ),
    )

    # 2. coder — single outgoing edge, no routing needed
    graph.add_node(
        AgentNode(
            node_id=2,
            node_name='coder',
            metadata={'tool_execution_mode': 'external'},
            agent_id='coder',
            additional_prompt=(
                'Phase: implementation. You are a coding assistant similar to Claude Code. '
                'Read files before editing. Use file_editor for precise edits and file_writer for new files. '
                'Run commands (tests, build, lint) to verify your changes. If verification fails, '
                'fix the code and re-verify. Output a JSON envelope with tool_requests.'
            ),
        ),
    )

    # 3. reviewer — branch node: outputs branch "approve" or "revise"
    graph.add_node(
        AgentNode(
            node_id=3,
            node_name='reviewer',
            metadata={'tool_execution_mode': 'external'},
            agent_id='reviewer',
            additional_prompt=(
                'Phase: review. Review the implementation against the original requirements. '
                'Read the modified files, run verification commands (tests), and assess quality. '
                'Output a JSON envelope with verdict and branch. '
                'verdict=approve with branch="approve" routes to the Summarizer. '
                'verdict=revise with branch="revise" routes back to the Coder for fixes.'
            ),
        ),
    )

    # 4. summarizer — terminal node, no outgoing edges
    graph.add_node(
        AgentNode(
            node_id=4,
            node_name='summarizer',
            metadata={'tool_execution_mode': 'external'},
            agent_id='summarizer',
            additional_prompt=(
                'Phase: summary. You are the final summarizer. Read the original requirements, '
                'the implementation plan, modified files, and review verdict. Produce a clear, '
                'structured final report of what was done. Output a JSON envelope with content '
                '(the summary). This is the terminal node.'
            ),
        ),
    )

    # Static topology: all connections defined via add_edge only.
    # Nodes with a single outgoing edge do not need to output branch — the engine follows the edge automatically.
    # The reviewer node branches via branch="approve" / branch="revise" matched against edge.condition.
    graph.add_edge(1, 2, label='implement', condition=None, priority=10)
    graph.add_edge(2, 3, label='review', condition=None, priority=10)
    graph.add_edge(3, 2, label='revise', condition='revise', priority=10)
    graph.add_edge(3, 4, label='summarize', condition='approve', priority=10)

    graph.set_entry(1)
    graph.set_exit(4)
    return graph
