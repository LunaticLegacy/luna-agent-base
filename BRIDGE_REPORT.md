=== 桥接 + 执行全部模块 — 完成报告 ===

时间: 2026-05-05 18:33 (Asia/Shanghai)
最后更新: 2026-05-05 19:10

一、已完成的桥接工作
----------------------
1. memory_graph llm_fetcher 全量复制到 angelus
2. angelus modules/__init__.py 扩展导出新组件 (AgentSwarm, SwarmSpec, ThinkingGraph 等)
3. angelus core/__init__.py 桥接 lightweight 组件 (Legacy + New 共存)
4. angelus load_sk.sh API key 同步为有效 key
5. main_swarm.py 复制到 angelus 并运行正常

二、执行全部模块验证结果
--------------------------
- core/ 全部 32 个模块: 导入正常
- web/ 层全部模块: 导入正常
- tools/ 全部 11 个工具模块: 导入正常
- agents/ 全部 5 个 swarm 包: 导入正常 (2 个成功加载, 3 个因缺少 MOONSHOT_API_KEY 跳过)
- FastAPI app: 创建成功 (angelus v0.1.0, 49 个路由)
- pytest 测试套件: 127 passed, 3 failed (与桥接无关)

三、运行时 bug 修复
-------------------
- 问题: `'LLMContext' object has no attribute 'get'` (novelist swarm 运行时错误)
- 根因: angelus core/agent.py 传递 LLMContext 对象给 llm_handler.fetch(), llm_fetcher 直接传递给 litellm SDK
- 修复: llm_fetcher.py _build_messages() 添加 duck typing 转换
- 同步: 修复已同时应用到 memory_graph 原始项目

四、首个保守替换完成 — CognitiveGraph ↔ ThinkingGraph 适配器
-------------------------------------------------------------
- 文件: core/cognitive_parts/llm_adapter.py
- 功能: 双向转换 CognitiveGraph ↔ ThinkingGraph
- 测试: test_cognitive_adapter.py 通过 (round-trip 3 节点 2 边, 内容完整保留)
- 修改: core/cognitive_parts/graph.py 添加 to_thinking_graph() 和 from_thinking_graph() 方法
- 修改: core/cognitive_parts/__init__.py 导出适配器函数

五、demo_llm_graph.py 运行成功
-------------------------------
- 并行分支演示: 0.30s (两个 0.3s 分支并行, JoinNode 汇聚)
- 节点超时演示: 0.20s (超时 0.2s, 正确返回超时错误)
- Swarm + ThinkingGraph 演示: Swarm 创建成功, 17 个工具注册

六、轻量 vs 重量对比
---------------------
| 项目 | 代码量 | 架构特点 |
|------|--------|----------|
| memory_graph llm_fetcher | ~4,187 行 | Agent + ExecutionGraph + Swarm + ThinkingGraph, 紧凑内聚 |
| angelus core/ | ~16,126 行 | 认知图 + 记忆系统 + 工作空间 + 故障分类 + 策略层 + 架构管理 |

七、已完成的实际替换（不只是桥接）
----------------------------------
1. **GraphExecutor 分支并行执行 → ExecutionGraph 引擎** 🗑️旧代码已删除
   - 文件: core/executor_llm_adapter.py
   - 功能: 使用 llm_fetcher ExecutionGraph 的事件驱动调度替换手动 asyncio.gather
   - 修改: core/executor_parts/engine.py — `_route_to_next()` 直接调用 v2
   - 删除: `_execute_parallel_branches()` (v1) 和 `_run_branch_with_retry()` 已彻底删除
   - 测试: ✅ 全部 7 个 cognitive graph 测试通过 + round-trip 测试通过

2. **CognitiveGraph ↔ ThinkingGraph 双向转换**
   - 文件: core/cognitive_parts/llm_adapter.py
   - 状态: ✅ round-trip 测试通过

八、下一步候选替换
------------------
1. core/policy.py ExecutionGraph → llm_fetcher/swarm/execution_graph.py (数据模型适配)
2. core/tool_contract.py ToolContract → llm_fetcher/tool.py Tool (工具定义适配)
3. web/ API 路由 → 使用新组件暴露 endpoints

架构现状: 
- angelus core/ ~16,126 行 (重量级)
- llm_fetcher  ~4,187 行 (轻量级内聚)
- 替换策略: 保留旧接口, 内部实现逐步迁移到新组件
