# Docs Index

这是 Angelus 项目的文档索引页。

## 总览

- [API 结构说明](./api_structure.md)
  - 当前 Flask API 的总体结构、路由、错误处理和运行时绑定关系
- [Metadata Reference](./metadata_reference.md)
  - 图节点、运行态、Agent、Tool、Skill 的 metadata 约定

## 后端

- [Backend API Map](./backend_api_map.md)
  - 后端 API 的调度方式、接口职责与运行时流转
- [Backend Reference](./backend_reference.md)
  - 后端所有类、函数、方法的功能与行为说明
- [Backend Live Execution](./backend_live_execution.md)
  - 实时执行图、异步 run session、SSE 事件流说明

## 前端

- [Frontend API Map](./frontend_api_map.md)
  - 前端如何消费后端 API、状态如何组织
- [Frontend Reference](./frontend_reference.md)
  - 前端所有主要组件、服务、模板与样式的行为说明
- [Frontend Receive Examples](./frontend_receive_examples.md)
  - 前端接收数据的示例格式，便于渲染和调试

## 结构

- [Agent Structure](./agent_structure.md)
  - 当前 swarm / agent / skill / tool / graph 的目录与结构约定

## 使用建议

- 如果你想先看“接口怎么用”，先看 `api_structure.md`
- 如果你想看“后端怎么跑”，先看 `backend_api_map.md` 和 `backend_live_execution.md`
- 如果你想看“前端怎么接”，先看 `frontend_api_map.md` 和 `frontend_reference.md`
- 如果你想看“图谱和 metadata 怎么解释”，先看 `metadata_reference.md`
- 如果你想看“业务包怎么组织”，先看 `agent_structure.md`

