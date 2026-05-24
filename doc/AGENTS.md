# Docs Guide

此目录放的是仓库说明文档，要修改实现时，文档用于定向

## 怎么读

- 想理解可视化编排系统结构
  - 先读 `backend_structure.md`
  - 再读 `frontend_structure.md`
- 想看当前后端 HTTP 面
  - 读 `typescript-langgraph-backend-reference.md`
- 想借鉴另一个项目如何接 Agent
  - 读 `multica-agent-adapter-reference.md`
- 想理解 `src/workflow_agents`
  - 进入 `agent_node/`
  - 先读 `agent_node/README.md`

## 文档分组

- `backend_structure.md`
  - `langgraph_codegen/backend` 的目录、接口、当前状态
- `frontend_structure.md`
  - `langgraph_codegen/frontend` 的路由、组件入口、页面说明
- `typescript-langgraph-backend-reference.md`
  - 当前后端接口快照
  - 这是临时参考文档，不是生成器实现说明
- `multica-agent-adapter-reference.md`
  - 关注 adapter/runtime 设计，不要把它误当成本项目现状
- `agent_node/`
  - `src/workflow_agents` 的正式文档集合

## 更新文档时的原则

- 接口类文档要和 `langgraph_codegen/backend/api/*.py` 保持一致。
- `agent_node` 文档要和 `src/workflow_agents` 保持一致。
- 临时参考文档可以保留结论，但不要让它们覆盖代码真相。
