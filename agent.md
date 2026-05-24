# program_workflow Root Guide

本仓库现在有两条主线，不要混读：

1. `src/workflow_agents`
   - 把 `codex`、`claude`、`claude_sdk` 这类长生命周期 Agent 封装成可复用 runtime，并可作为 LangGraph node 使用。
2. `langgraph_codegen`
   - 一套可视化编排 LangGraph 的前后端系统；前端编辑 graph，后端保存 graph 并生成 Python LangGraph 代码。

## 先做任务分流

用户需求里如果出现这些关键词，优先进入对应目录，不要先扫全仓库：

- Agent runtime、Codex/Claude 接入、会话复用、thread/session、mailbox、Agent Node
  - 先读 `src/workflow_agents/AGENTS.md`
- 画布、节点编辑、拖拽、保存加载、代码侧栏、前端页面、React Flow
  - 先读 `langgraph_codegen/frontend/AGENTS.md`
- Flow CRUD、代码生成、FastAPI、LLM/Tool registry、后端接口
  - 先读 `langgraph_codegen/backend/AGENTS.md`
- 想看文档而不是代码入口
  - 先读 `doc/AGENTS.md`

## 渐进式披露规则

- 根目录只保留路由信息，不在这里堆实现细节。
- 确认任务属于哪条主线后，只继续读取那个子目录的 `AGENTS.md`。
- 只有当子目录索引明确指向更深文件时，才继续打开具体代码或文档。
- 对 Codex 协议细节，不要直接扫 `codex_schema/` 全目录；先读 `src/workflow_agents/runtime/AGENTS.md`，再按索引打开具体 schema。

## 目录地图

- `src/workflow_agents`
  - Agent runtime / LangGraph node 实现
- `langgraph_codegen/backend`
  - FastAPI 后端，负责 Flow/LLM/Tool CRUD、代码生成、sandbox 接口
- `langgraph_codegen/frontend`
  - React 前端，负责画布、节点配置、代码面板、各管理页
- `doc`
  - 结构说明、临时接口文档、`agent_node` 专项文档
- `tests`
  - `workflow_agents` 的单元测试

## 高频需求到文件

- “让 Codex/Claude 作为 LangGraph Node 的行为改变”
  - `src/workflow_agents/node.py`
  - `src/workflow_agents/state.py`
  - `src/workflow_agents/runtime/*.py`
- “改 Codex app-server / JSON-RPC 适配”
  - `src/workflow_agents/runtime/codex.py`
  - `src/workflow_agents/runtime/AGENTS.md`
- “改画布节点的数据结构或默认值”
  - `langgraph_codegen/frontend/src/store/useFlowStore.ts`
  - `langgraph_codegen/frontend/src/components/FlowCanvas.tsx`
  - `langgraph_codegen/frontend/src/components/canvas/NodeSidebar.tsx`
- “改生成的 LangGraph Python 代码”
  - `langgraph_codegen/backend/services/flows/codegen.py`
  - `langgraph_codegen/backend/templates/flows/langgraph_main.jinja2`
- “改 Flow 后端接口或执行逻辑”
  - `langgraph_codegen/backend/api/flows.py`
  - `langgraph_codegen/backend/services/flows/runner.py`
- “改 LLM/Tool 注册和配置页”
  - `langgraph_codegen/frontend/src/pages/LLMsPage.tsx`
  - `langgraph_codegen/frontend/src/pages/ToolsPage.tsx`
  - `langgraph_codegen/backend/api/llms.py`
  - `langgraph_codegen/backend/api/tools.py`

## 文档入口

- `doc/backend_structure.md`
  - 可视化编排后端结构说明
- `doc/frontend_structure.md`
  - 可视化编排前端结构说明
- `doc/typescript-langgraph-backend-reference.md`
  - 当前 Python FastAPI 后端接口快照，名字里有 typescript 但内容以现状接口为主
- `doc/multica-agent-adapter-reference.md`
  - `multica` 项目中 agent adapter/runtime 的参考思路
- `doc/agent_node/README.md`
  - `src/workflow_agents` 的正式文档入口

## 当前项目状态

- `langgraph_codegen` 是当前可运行主系统。
- `langgraph_codegen/backend` 的 `POST /api/flows/generate/code` 已实现，目标是生成 Python LangGraph scaffold。
- `langgraph_codegen/backend` 的 `run` / `test` 目前仍偏模拟执行，不是完整 LangGraph runtime。
- `src/workflow_agents` 是独立的 Agent Node/runtime 能力层，文档较完整，但还不是 `langgraph_codegen` 里的默认执行路径。

## 验证入口

- `python -m unittest -v`
  - 主要覆盖 `src/workflow_agents`
- 如果改的是前后端画布系统，优先做局部静态检查或构建，不要误以为根目录测试能覆盖它。
