# langgraph_codegen Guide

此目录是可视化编排系统本体，是“前端画布 + 后端接口 + 代码生成”的完整应用。

## 子系统分工

- `backend/`
  - FastAPI 后端
  - Flow/LLM/Tool CRUD
  - 代码生成
  - sandbox 聊天接口
- `frontend/`
  - React + Vite + React Flow 前端
  - 画布、节点配置、代码侧栏、管理页

## 先判断你在改哪一边

- 后端接口、生成代码、LLM/Tool provider、数据库
  - 读 `backend/AGENTS.md`
- 前端画布、节点表单、保存加载、页面路由、代码面板
  - 读 `frontend/AGENTS.md`

## 当前实现边界

- 这里生成的是 Python LangGraph 代码，不是 TypeScript LangGraph 代码。
- `POST /api/flows/generate/code` 是当前主路径。
- `POST /api/flows/{id}/run` 和 `POST /api/flows/{id}/test` 仍然偏模拟执行。
- `workflow_agents` 目前不是这个子系统里的默认执行引擎。

## 高概率修改路径

- “改画布上的节点数据怎么映射到后端 payload”
  - 前端：`frontend/src/store/useFlowStore.ts`
  - 前端：`frontend/src/components/canvas/CodeSidebar.tsx`
  - 后端：`backend/schemas/flows.py`
  - 后端：`backend/api/flows.py`
- “改生成出来的 Python scaffold”
  - `backend/services/flows/codegen.py`
  - `backend/templates/flows/langgraph_main.jinja2`
- “改 LLM 或 Tool 注册系统”
  - `backend/api/llms.py`
  - `backend/api/tools.py`
  - `frontend/src/pages/LLMsPage.tsx`
  - `frontend/src/pages/ToolsPage.tsx`
