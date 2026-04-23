# Backend Docs

这组文档按当前后端代码的真实实现拆分为若干模块。

## 模块索引

- [App and Routes](./app-and-routes.md)
- [Runtime](./runtime.md)
- [Runs](./runs.md)
- [Workflow Hardening Plan](./workflow-hardening.md)
- [Catalog and Content](./catalog-and-content.md)
- [Errors and Health](./errors-and-health.md)

## 说明

- 这些文档只描述当前实现，不保留旧版“规划中 API”的口径。
- 如果某个接口是 app-level 和 blueprint 两层并存，会在对应文档里明确说明。
- 路由、运行时、执行链路、内容持久化和错误处理都分别独立说明，方便排查 404、405、SSE 和运行时冲突问题。
