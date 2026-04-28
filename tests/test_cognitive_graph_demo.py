#!/usr/bin/env python3
"""
Cognitive Graph (思维图谱) 端到端演示与验证测试。

覆盖能力：
- 构建与查询（子图、邻居、出入边）
- 冲突检测（supports/opposes 矛盾对）
- 无支持声明检测
- 图谱合并与去重（基于 Jaccard 相似度）
- 从 LLM 输出文本中提取结构化认知图谱
- 序列化 / 反序列化
- 导出为 LLM 上下文（含子图描述符）
"""

from __future__ import annotations

import json

from core.cognitive import (
    CognitiveGraph,
    CognitiveNode,
    CognitiveEdge,
    CognitiveNodeType,
    CognitiveRelationType,
    extract_cognitive_graph_from_text,
    merge_cognitive_graphs,
)


def test_build_and_query() -> None:
    cg = CognitiveGraph(graph_id="demo_production_decision")

    fact_perf = CognitiveNode(
        node_type=CognitiveNodeType.FACT,
        content="新版算法在基准测试中吞吐量提升了 40%",
        confidence=0.95,
        tags=["benchmark", "performance"],
    )
    fact_bugs = CognitiveNode(
        node_type=CognitiveNodeType.FACT,
        content="过去两周内该算法分支发现了 3 个高危 bug",
        confidence=0.90,
        tags=["quality", "risk"],
    )
    hyp_stable = CognitiveNode(
        node_type=CognitiveNodeType.HYPOTHESIS,
        content="如果增加灰度发布覆盖率，可以在生产环境稳定运行",
        confidence=0.60,
        tags=["deployment", "strategy"],
    )
    claim_deploy = CognitiveNode(
        node_type=CognitiveNodeType.CLAIM,
        content="应该立即全量切换到新版算法",
        confidence=0.50,
        tags=["decision", "deploy"],
    )
    risk_outage = CognitiveNode(
        node_type=CognitiveNodeType.RISK,
        content="全量切换可能导致服务不可用",
        confidence=0.80,
        tags=["risk", "outage"],
    )

    for n in (fact_perf, fact_bugs, hyp_stable, claim_deploy, risk_outage):
        cg.add_node(n)

    cg.add_edge(CognitiveEdge(fact_perf.node_id, hyp_stable.node_id, CognitiveRelationType.SUPPORTS, strength=0.8))
    cg.add_edge(CognitiveEdge(fact_bugs.node_id, risk_outage.node_id, CognitiveRelationType.SUPPORTS, strength=0.9))
    cg.add_edge(CognitiveEdge(hyp_stable.node_id, claim_deploy.node_id, CognitiveRelationType.LEADS_TO, strength=0.6))
    cg.add_edge(CognitiveEdge(risk_outage.node_id, claim_deploy.node_id, CognitiveRelationType.OPPOSES, strength=0.85))
    cg.add_edge(CognitiveEdge(fact_bugs.node_id, hyp_stable.node_id, CognitiveRelationType.OPPOSES, strength=0.5))

    assert len(cg.nodes) == 5
    assert len(cg.edges) == 5

    # 子图查询
    sub = cg.query_subgraph([fact_perf.node_id], max_hops=1)
    assert fact_perf.node_id in sub.nodes
    assert hyp_stable.node_id in sub.nodes
    assert claim_deploy.node_id not in sub.nodes  # 2 hops away

    # 邻居
    nbrs = cg.neighbors(hyp_stable.node_id)
    assert fact_perf.node_id in nbrs
    assert claim_deploy.node_id in nbrs
    assert fact_bugs.node_id in nbrs

    # 出入边
    assert len(cg.outgoing_edges(fact_perf.node_id)) == 1
    assert len(cg.incoming_edges(claim_deploy.node_id)) == 2

    print("test_build_and_query passed")


def test_conflict_detection() -> None:
    cg = CognitiveGraph()
    a = CognitiveNode(node_type=CognitiveNodeType.CLAIM, content="A")
    b = CognitiveNode(node_type=CognitiveNodeType.CLAIM, content="B")
    cg.add_node(a)
    cg.add_node(b)
    cg.add_edge(CognitiveEdge(a.node_id, b.node_id, CognitiveRelationType.SUPPORTS))
    cg.add_edge(CognitiveEdge(a.node_id, b.node_id, CognitiveRelationType.OPPOSES))

    conflicts = cg.find_conflicts()
    assert len(conflicts) == 1
    print("test_conflict_detection passed")


def test_unsupported_claims() -> None:
    cg = CognitiveGraph()
    supported = CognitiveNode(node_type=CognitiveNodeType.CLAIM, content="Supported claim")
    unsupported = CognitiveNode(node_type=CognitiveNodeType.CLAIM, content="Unsupported claim")
    evidence = CognitiveNode(node_type=CognitiveNodeType.EVIDENCE, content="Some evidence")
    cg.add_node(supported)
    cg.add_node(unsupported)
    cg.add_node(evidence)
    cg.add_edge(CognitiveEdge(evidence.node_id, supported.node_id, CognitiveRelationType.SUPPORTS))

    unsupported_list = cg.find_unsupported_claims()
    assert unsupported in unsupported_list
    assert supported not in unsupported_list
    print("test_unsupported_claims passed")


def test_merge_and_dedup() -> None:
    g1 = CognitiveGraph(graph_id="merge_a")
    n1 = CognitiveNode(node_type=CognitiveNodeType.FACT, content="Python 3.12 引入了 PEP 695 类型参数语法", confidence=0.95)
    g1.add_node(n1)

    g2 = CognitiveGraph(graph_id="merge_b")
    n2 = CognitiveNode(node_type=CognitiveNodeType.FACT, content="Python 3.12 引入了 PEP 695 类型参数语法", confidence=0.90)
    n3 = CognitiveNode(node_type=CognitiveNodeType.EVIDENCE, content="该语法在 Typing Summit 2023 上讨论通过", confidence=0.85)
    g2.add_node(n2)
    g2.add_node(n3)
    g2.add_edge(CognitiveEdge(n2.node_id, n3.node_id, CognitiveRelationType.EVIDENCE_FOR))

    merge_cognitive_graphs(g1, g2)

    assert len(g1.nodes) == 2  # n1/n2 合并为一个，n3 新增
    assert len(g1.edges) == 1

    merged_node = g1.nodes.get(n1.node_id)
    assert merged_node is not None
    assert merged_node.version == 2
    assert abs(merged_node.confidence - 0.925) < 0.01
    print("test_merge_and_dedup passed")


def test_extract_from_text() -> None:
    simulated_llm_output = """
<cognitive_graph>
{
  "cognitive_graph": {
    "nodes": [
      {"node_id": "n1", "node_type": "fact", "content": "数据库连接池当前最大连接数为 100", "confidence": 0.95},
      {"node_id": "n2", "node_type": "hypothesis", "content": "连接数不足是高峰期超时的主因", "confidence": 0.70},
      {"node_id": "n3", "node_type": "decision", "content": "将连接池上限提升至 200 并启用连接预热", "confidence": 0.85}
    ],
    "edges": [
      {"source_id": "n1", "target_id": "n2", "relation": "supports", "strength": 0.8},
      {"source_id": "n2", "target_id": "n3", "relation": "leads_to", "strength": 0.75}
    ]
  }
}
</cognitive_graph>
"""
    cg = extract_cognitive_graph_from_text(simulated_llm_output, source_agent_id="agent_analyst")
    assert cg is not None
    assert len(cg.nodes) == 3
    assert len(cg.edges) == 2
    assert all(n.source == "agent_analyst" for n in cg.nodes.values())
    print("test_extract_from_text passed")


def test_serde() -> None:
    cg = CognitiveGraph(graph_id="serde_test")
    n = CognitiveNode(node_type=CognitiveNodeType.GOAL, content="实现认知图谱持久化", confidence=1.0)
    cg.add_node(n)

    data = cg.to_dict()
    restored = CognitiveGraph.from_dict(data)
    assert restored.graph_id == cg.graph_id
    assert len(restored.nodes) == 1
    assert restored.nodes[n.node_id].content == n.content
    print("test_serde passed")


def test_export_for_llm() -> None:
    cg = CognitiveGraph()
    n1 = CognitiveNode(node_type=CognitiveNodeType.FACT, content="Fact A", confidence=0.9)
    n2 = CognitiveNode(node_type=CognitiveNodeType.REASONING, content="Reasoning B", confidence=0.7)
    cg.add_node(n1)
    cg.add_node(n2)
    cg.add_edge(CognitiveEdge(n1.node_id, n2.node_id, CognitiveRelationType.SUPPORTS))

    export = cg.export_for_llm()
    assert "Fact A" in export
    assert "Reasoning B" in export
    assert "supports" in export
    print("test_export_for_llm passed")


if __name__ == "__main__":
    test_build_and_query()
    test_conflict_detection()
    test_unsupported_claims()
    test_merge_and_dedup()
    test_extract_from_text()
    test_serde()
    test_export_for_llm()
    print("\nAll cognitive graph tests passed.")
