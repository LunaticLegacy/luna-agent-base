# 上下文图管理系统（Context Graph System）设计计划

## 1. 项目概述

### 1.1 目标
构建一个基于有向异构图的上下文管理系统，替代传统的扁平化上下文数组。系统通过上下文 ID、摘要、关系网络三个维度实现智能裁剪，确保在 Token 预算有限的情况下，保留与当前任务最相关的语义网络。

### 1.2 核心特性
- **图结构化存储**：上下文条目作为节点，语义关系作为有向边
- **分层裁剪**：基于摘要的低成本筛选 + 基于实际内容的精确核算
- **引用完整性**：级联保留与引用消解机制，避免逻辑断裂
- **动态子图提取**：从当前激活节点出发，按相关性传播提取工作记忆

---

## 2. 数据模型

### 2.1 ContextEntry（上下文节点）

```python
@dataclass
class ContextEntry:
    id: str                          # 全局唯一标识符
    summary: str                     # 语义摘要（用于低成本决策）
    content: str                     # 实际完整内容
    token_count: int                 # 内容 Token 数（缓存）
    timestamp: float                 # 创建时间戳
    entry_type: EntryType            # 节点类型枚举
    outgoing_refs: List[ContextReference]  # 出边引用列表
    is_retained: bool = False        # 裁剪标记（运行时）
```

### 2.2 Relation（关系类型枚举）

| 关系 | 语义 | 裁剪影响 |
|------|------|----------|
| `REFERENCES` | 当前条目引用了另一条目的具体内容 | **强依赖** — 被引用条目不可简单删除 |
| `SUMMARY_OF` | 当前条目是另一条目的摘要/压缩 | **可替代** — 保留摘要即可释放原节点 |
| `ELABORATION_OF` | 当前条目是对另一条目的详细展开 | **弱依赖** — 可独立存在 |
| `CONTRADICTS` | 当前条目否定了另一条目 | **成对保留** — 单独保留会导致逻辑断裂 |
| `CAUSED_BY` | 当前条目是另一条目导致的结果 | **因果链保留** — 需保留上游 |
| `VERSION_OF` | 当前条目是另一条目的更新版本 | **新旧替代** — 通常保留最新 |
| `MERGED_FROM` | 当前条目合并了其他节点 | **聚合关系** — 源节点可被替代 |

### 2.3 ContextReference（引用描述符）

```python
@dataclass
class ContextReference:
    target_id: str                   # 目标节点 ID
    relation: Relation               # 关系类型
    target_hash: str                 # 目标内容哈希（检测变化）
    fallback_inline: Optional[str]   # 目标缺失时的内联替代
    weight: float = 1.0              # 关系权重（用于相关性传播）
```

**设计 rationale**：不直接存储 `ContextEntry` 对象指针，而是存储引用描述符。这允许运行时懒解析，并在目标节点被裁剪后通过 `fallback_inline` 或摘要进行引用消解。

---

## 3. 系统架构

```
+-----------------------------------------------------+
|                  Context Graph Store                  |
|   +---------+      +---------+      +---------+     |
|   | Entry A |----->| Entry B |----->| Entry C |     |
|   |(激活节点)| REF  |(被引用) | SUM  |(摘要)   |     |
|   +---------+      +---------+      +---------+     |
+--------------+--------------------------------------+
               |
               v
+--------------------------+
|     Graph Query Engine     |
|  - 子图提取（BFS + 加权）  |
|  - 相关性传播计算          |
|  - 活跃节点扩散激活        |
+--------------+-----------+
               |
               v
+--------------------------+
|      Graph Pruner        |
|  - 级联保留（Cascade）    |
|  - 引用完整性检查         |
|  - 预算贪婪填充           |
+--------------+-----------+
               |
               v
+--------------------------+
|    Reference Resolver    |
|  - 悬空引用检测          |
|  - 摘要替代注入          |
|  - 内联回退生成          |
+--------------+-----------+
               |
               v
+--------------------------+
|     Prompt Assembler     |
|  - 拓扑排序/时序排序      |
|  - 最终上下文拼装         |
+--------------------------+
```

### 3.1 模块职责

| 模块 | 职责 |
|------|------|
| `ContextGraphStore` | 节点存储、索引、持久化、CRUD |
| `GraphQueryEngine` | 从激活节点提取相关子图、计算节点中心性 |
| `GraphPruner` | 在 Token 预算约束下决定保留/淘汰哪些节点 |
| `ReferenceResolver` | 处理被淘汰节点但仍有入边的情况 |
| `PromptAssembler` | 将保留的子图线性化为 LLM 输入 |

---

## 4. 核心算法设计

### 4.1 级联保留算法（Cascade Retention）

当用户或系统标记某节点为必须保留时，自动保留其语义依赖链。

```python
def cascade_retain(
    entry: ContextEntry,
    graph: ContextGraph,
    depth: int = 2
) -> Set[str]:
    retained = set()
    queue = [(entry, depth)]
    
    while queue:
        node, remaining_depth = queue.pop(0)
        if node.id in retained or remaining_depth < 0:
            continue
            
        node.is_retained = True
        retained.add(node.id)
        
        for ref in node.outgoing_refs:
            target = graph.get_node(ref.target_id)
            if not target:
                continue
                
            depth_cost = {
                Relation.REFERENCES: 1,
                Relation.CAUSED_BY: 1,
                Relation.CONTRADICTS: 0,
                Relation.ELABORATION_OF: 2,
                Relation.SUMMARY_OF: 0,
            }.get(ref.relation, 1)
            
            new_depth = remaining_depth - depth_cost
            if new_depth >= 0:
                queue.append((target, new_depth))
    
    return retained
```

### 4.2 图裁剪算法（Graph Pruning）

```python
def prune_graph(
    graph: ContextGraph,
    anchor_id: str,
    token_budget: int
) -> ContextGraph:
    # Step 1: 提取活跃子图
    active_nodes = graph.extract_subgraph(
        anchor_id=anchor_id,
        max_hops=2,
        min_relevance=0.15
    )
    
    # Step 2: 级联保留活跃子图
    for node in active_nodes:
        cascade_retain(node, graph, depth=2)
    
    # Step 3: 计算全局重要性（PageRank 变体）
    importance = graph.compute_centrality()
    
    # Step 4: 对未保留节点按重要性贪婪填充剩余预算
    remaining = token_budget - sum(
        n.token_count for n in graph.nodes if n.is_retained
    )
    
    candidates = [
        n for n in graph.nodes 
        if not n.is_retained
    ]
    candidates.sort(key=lambda n: importance[n.id], reverse=True)
    
    for node in candidates:
        if node.token_count <= remaining:
            node.is_retained = True
            remaining -= node.token_count
        else:
            # 尝试降级：用摘要替代
            summary = graph.find_summary_for(node)
            if summary and summary.token_count <= remaining:
                summary.is_retained = True
                remaining -= summary.token_count
    
    # Step 5: 引用消解
    for node in graph.nodes:
        if not node.is_retained:
            resolve_references(graph, node)
    
    return graph
```

### 4.3 子图提取算法（Subgraph Extraction）

```python
def extract_subgraph(
    self,
    anchor_id: str,
    max_hops: int = 2,
    min_relevance: float = 0.1
) -> List[ContextEntry]:
    anchor = self.get_node(anchor_id)
    if not anchor:
        return []
    
    queue = [(anchor, 0, 1.0)]
    visited = {anchor_id}
    result = []
    
    while queue:
        node, hop, score = queue.pop(0)
        if score < min_relevance:
            continue
            
        result.append(node)
        
        for ref in node.outgoing_refs:
            if ref.target_id in visited:
                continue
                
            weight = ref.weight
            decay = 0.5 ** hop
            new_score = score * weight * decay
            
            if hop < max_hops:
                target = self.get_node(ref.target_id)
                if target:
                    queue.append((target, hop + 1, new_score))
                    visited.add(ref.target_id)
    
    return result
```

---

## 5. 引用消解策略

当某个节点被淘汰但仍有其他节点引用它时，必须执行引用消解（Reference Resolution）。

### 5.1 消解策略矩阵

| 关系类型 | 消解方式 |
|----------|----------|
| `REFERENCES` | 将被引用节点的摘要内联到引用处，或替换为 `fallback_inline` |
| `SUMMARY_OF` | 反向关系，摘要被保留时原节点淘汰无需消解 |
| `CONTRADICTS` | 双方必须同时保留，若预算不足则都淘汰并记录矛盾摘要 |
| `CAUSED_BY` | 将因节点的摘要加入果节点的内容前缀 |
| `VERSION_OF` | 旧版本直接淘汰，新版本已包含完整信息 |

### 5.2 消解器实现

```python
def resolve_references(graph: ContextGraph, evicted_node: ContextEntry):
    referencers = graph.get_incoming_refs(evicted_node.id)
    
    for ref in referencers:
        source = graph.get_node(ref.source_id)
        if not source or not source.is_retained:
            continue
            
        if ref.relation == Relation.REFERENCES:
            # 在 source 内容中插入被引用节点的摘要
            inline = ref.fallback_inline or evicted_node.summary
            source.content = f"[引用: {inline}]\n{source.content}"
            source.token_count = estimate_tokens(source.content)
            
        elif ref.relation == Relation.CONTRADICTS:
            # 标记矛盾对的一方缺失
            source.content += f"\n[注: 与原观点 {evicted_node.id} 的矛盾论证已因空间限制移除]"
```

---

## 6. Prompt 拼装策略

图结构最终需要线性化为 LLM 的输入文本。拼装时应遵循以下优先级：

1. **系统级节点**（EntryType.SYSTEM）始终置于最前
2. **当前激活节点**（anchor）及其直接邻居紧随其后
3. **时间序**：同层级节点按时间戳升序排列
4. **分隔符**：用清晰的标记区分不同上下文来源

```
[SYSTEM]
<系统指令内容>

[CONTEXT: ctx_001]
<当前激活上下文>

[CONTEXT: ctx_003 | 引用自: ctx_002]
<相关上下文，标注引用关系>

[CONTEXT: ctx_005 | 摘要替代原: ctx_004]
<摘要替代的上下文>
```

---

## 7. 实现路线图

### Phase 1: 基础图结构（Week 1）
- [ ] 实现 `ContextEntry`、`ContextReference`、`Relation` 数据类
- [ ] 实现 `ContextGraphStore` 的内存存储与基本 CRUD
- [ ] 实现简单的子图提取（BFS，无权重）

### Phase 2: 裁剪引擎（Week 2）
- [ ] 实现 `GraphPruner` 的级联保留逻辑
- [ ] 实现基于 Token 预算的贪婪填充
- [ ] 实现 `REFERENCES` 和 `SUMMARY_OF` 两种关系的消解

### Phase 3: 查询与拼装（Week 3）
- [ ] 实现加权 BFS 子图提取
- [ ] 实现节点重要性评分（PageRank）
- [ ] 实现 `PromptAssembler` 的线性化策略

### Phase 4: 优化与持久化（Week 4）
- [ ] 图结构的 JSON/数据库持久化
- [ ] 摘要质量评估与自动修正
- [ ] 完整的单元测试与集成测试

---

## 8. 关键设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 引用存储方式 | `ContextReference` 描述符而非直接指针 | 支持懒解析、引用消解、目标变更检测 |
| 关系方向 | 有向边 | 语义关系天然不对称（A 引用 B 不等于 B 引用 A） |
| 裁剪粒度 | 节点级 | 比块级更灵活，比 token 级更易维护一致性 |
| 摘要角色 | 元数据 + 降级替代 | 既用于快速筛选，又用于内容替代 |
| PageRank vs 时序 | 混合权重 | 纯 PageRank 会丢失对话的因果递进，纯时序会丢失关联深度 |

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 摘要与内容不一致 | 裁剪错误 | 定期用 LLM 校验摘要准确性，偏差大时重新生成 |
| 图过于稠密 | 子图提取膨胀 | 设置单节点最大出度限制（如 5），超限时合并弱关系 |
| 循环引用 | 级联保留死循环 | 所有遍历算法维护 `visited` 集合 |
| 引用消解后 Token 膨胀 | 超出预算 | 消解后重新核算，必要时二次裁剪 |
| 关系类型过度设计 | 系统复杂 | Phase 1 仅实现 REF/SUM/ELAB 三种核心关系 |

---

*文档版本: v1.0*
*创建日期: 2026-04-23*
