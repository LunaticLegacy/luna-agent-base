# 动态 Agent Swarm 容错与架构调节方案

## 1. 目标

动态 agent swarm 不是静态流水线，而是一个会在执行中改变节点、边和任务分配的在线系统。  
因此，失败不应只被视为“终止”，而应被视为“架构调节信号”。

本方案的目标是：

- 当节点、分支或整轮 run 失败时，系统能够结构化上报失败
- 架构调节器能够消费失败信息并分类处理
- 系统能够自动执行局部修复、降级、重路由或回退
- 只有在不可恢复时，才升级为人工介入或终止当前执行

---

## 2. 核心原则

### 2.1 Fail-Closed，但不 Fail-Silent

默认不允许失败后继续“盲跑”。

- 节点失败后，当前执行链路应立即进入安全态
- 失败必须显式记录、上报和分类
- 后续是否继续执行，必须由调节策略决定

### 2.2 失败应驱动架构变化

失败不是单纯的日志事件，而是输入给架构调节器的控制信号。

调节器应能基于失败信息：

- 切换备用节点或备用 agent
- 回退到上一图版本
- 禁用故障子图
- 改写路由边
- 降级为简化执行模式

### 2.3 局部修复优先

除非故障影响全局结构，否则优先只修复受影响的局部范围。

- 单节点错误优先局部替换
- 单分支错误优先分支级降级
- 图变更错误优先回滚局部修改

---

## 3. 运行语义

### 3.1 失败后的默认行为

当节点执行失败时：

1. 当前节点标记为失败
2. 当前 run 进入失败或暂停状态
3. 执行层停止继续调度后续节点
4. 失败事件上报给架构调节器
5. 架构调节器决定是否修复并恢复执行

### 3.2 不同失败层级

| 失败层级 | 含义 | 默认处理 |
|------|------|------|
| 节点失败 | 单个 agent/tool/node 执行异常 | 停当前 run，交给调节器 |
| 分支失败 | 并行分支中的某一路失败 | 局部中止或重路由 |
| 图失败 | 图结构、路由或动态变更不合法 | 回滚或暂停 |
| Swarm 失败 | 当前执行上下文无法继续 | 进入调节回路 |

---

## 4. 架构调节器职责

架构调节器是一个独立的控制层，不是普通日志消费者。

### 4.1 输入

调节器接收结构化失败事件，至少包括：

- `run_id`
- `swarm_name`
- `graph_revision`
- `node_id`
- `node_name`
- `node_type`
- `failure_kind`
- `error_message`
- `state_snapshot`
- `recent_changes`

### 4.2 决策

调节器需要对失败进行分类：

- **可恢复**：可重试、可切换备用节点
- **可绕过**：当前节点失败，但可走替代路径
- **需降级**：保留主流程，但降低功能
- **需回退**：恢复到上一个稳定图版本
- **需暂停**：等待人工确认或外部修复
- **不可恢复**：终止当前 run 并上报

### 4.3 输出

调节器输出一个架构动作，例如：

- `retry_node`
- `reroute_edge`
- `replace_node`
- `disable_subgraph`
- `rollback_graph`
- `degrade_mode`
- `pause_run`
- `abort_run`

---

## 5. 失败事件模型

建议所有失败统一使用结构化事件，而不是只写字符串日志。

```python
@dataclass
class FailureEvent:
    event_id: str
    run_id: str
    swarm_name: str
    graph_revision: int
    failure_scope: str         # node | branch | graph | swarm
    failure_kind: str          # tool_error | agent_error | routing_error | mutation_error | timeout
    node_id: Optional[int]
    node_name: Optional[str]
    node_type: Optional[str]
    message: str
    state_snapshot: Dict[str, Any]
    recent_changes: List[Dict[str, Any]]
    timestamp: str
```

### 5.1 失败类型建议

| failure_kind | 说明 |
|------|------|
| `tool_error` | 工具执行失败 |
| `agent_error` | agent 推理或输出失败 |
| `routing_error` | 路由结果非法或缺失 |
| `mutation_error` | 动态改图失败 |
| `timeout` | 超时 |
| `invariant_violation` | 结构不变量被破坏 |

---

## 6. 调节策略表

### 6.1 节点失败

| 场景 | 建议动作 |
|------|------|
| 工具短暂失败 | 重试当前节点 |
| agent 输出无效 | 重新提示或切换备用 prompt |
| 节点数据缺失 | 回退到上一个稳定输入 |
| 关键汇总节点失败 | 暂停并等待修复 |

### 6.2 分支失败

| 场景 | 建议动作 |
|------|------|
| 某一路分支失败 | 保留其他分支，丢弃失败分支 |
| 分支依赖不可满足 | 改写为单路执行 |
| 多分支都失败 | 进入降级或暂停 |

### 6.3 图失败

| 场景 | 建议动作 |
|------|------|
| 新增节点后图不合法 | 回滚到上一版本 |
| 删除节点导致断边 | 修补边或回退 |
| 路由边冲突 | 选择备用边或暂停 |

---

## 7. 推荐架构

```
Execution Layer
  -> emits node/branch/run failure events

Architecture Regulator
  -> classifies failure
  -> chooses repair strategy
  -> outputs architecture patch

Graph / Run Controller
  -> applies patch
  -> resumes or aborts execution
```

### 7.1 模块分工

| 模块 | 责任 |
|------|------|
| `Execution Layer` | 执行节点、捕获异常、发失败事件 |
| `Architecture Regulator` | 接收失败、分类、生成修复动作 |
| `Graph Controller` | 应用图补丁、回滚、恢复执行 |
| `Run Controller` | 控制当前 run 的暂停、重试、终止 |

---

## 8. 推荐运行流程

1. 节点执行失败
2. 执行层立刻停止当前调度
3. 生成结构化失败事件
4. 上报给架构调节器
5. 调节器判断可恢复性
6. 若可恢复，生成补丁并应用
7. 若不可恢复，暂停或终止当前 run
8. 将结果和原因写入可观察日志

---

## 9. 产品层语义建议

为了让系统语义清晰，建议把“失败处理”定义成以下三种状态：

- **暂停**：等待修复或人工决策
- **降级**：以更弱能力继续运行
- **终止**：当前 run 无法恢复

不要把所有失败都笼统称为“停机”，否则会模糊：

- 是停当前 run
- 还是停整个 swarm
- 还是只是停某个分支

---

## 10. 结论

对于动态 agent swarm，容错不应是附加功能，而应是架构本身的一部分。

最合适的默认策略是：

- 节点失败后立即进入安全态
- 失败信息交给架构调节器
- 调节器自动尝试局部修复、降级或回退
- 只有在不可恢复时，才终止当前 run

这会让 swarm 从“脆弱的流程图”升级为“可调节的在线系统”。
