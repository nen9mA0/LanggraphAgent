# 前端结构

`langgraph_codegen/frontend` 是 Vite + React 前端，默认连接 `http://127.0.0.1:8000/api`。

## 路由

- `/`：flow canvas editor
- `/llms`：LLM registry
- `/tools`：tool registry
- `/settings`：server URL settings
- `/about`：about page
- `/sandbox/chatbot`：chatbot playground
- `/sandbox/tool-tester`：placeholder
- `/sandbox/rag-lab`：placeholder
- `/sandbox/llm-finetuning`：placeholder

## 入口

- `src/main.tsx`：app entry
- `src/App.tsx`：router and layout
- `src/contexts/ServerContext.tsx`：backend URL and health check
- `src/utils/serverUrl.ts`：URL helper
- `src/store/useFlowStore.ts`：flow state store

## Flow editor

- `src/components/FlowCanvas.tsx`：React Flow canvas、节点/边删除、save/load、state 和 memory modal
- `src/components/canvas/NodeSidebar.tsx`：selected node editor
- `src/components/canvas/CodeSidebar.tsx`：向 `/api/flows/generate/code` 发送当前 graph
- `src/components/SaveLoadFlow.tsx`：save/load/run/test UI
- `src/components/StateModal.tsx`：state schema editor
- `src/components/MemoryModal.tsx`：memory settings modal

## Registry pages

- `src/pages/LLMsPage.tsx`：remote/local LLM management
- `src/pages/ToolsPage.tsx`：tool CRUD and code preview
- `src/pages/SettingsPage.tsx`：backend URL config
- `src/pages/AboutPage.tsx`：product/about page

## Sandbox

- `src/pages/ChatbotPage.tsx`：chatbot sandbox
- `src/components/chat/*`：chat UI and config panel

## 备注

- 默认后端地址来自 `src/utils/serverUrl.ts`，并可在 Settings 中覆盖。
- `CodeSidebar` 生成的是 Python LangGraph 代码，不是 TypeScript。
