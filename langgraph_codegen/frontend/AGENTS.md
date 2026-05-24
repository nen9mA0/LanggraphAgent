# Frontend Guide

此目录是 `langgraph_codegen` 的 React 前端。重点是画布状态、节点编辑、代码生成面板、保存加载，以及 LLM/Tool 管理页面。

## 建议阅读顺序

1. `src/App.tsx`
2. `src/contexts/ServerContext.tsx`
3. `src/store/useFlowStore.ts`
4. `src/components/FlowCanvas.tsx`
5. `src/components/canvas/NodeSidebar.tsx`
6. `src/components/canvas/CodeSidebar.tsx`

## 任务到文件

- 改页面路由、整体布局、导航
  - `src/App.tsx`
- 改后端地址、健康检查、服务端上下文
  - `src/contexts/ServerContext.tsx`
  - `src/utils/serverUrl.ts`
- 改画布状态、节点/边增删改、默认 state
  - `src/store/useFlowStore.ts`
  - `src/components/FlowCanvas.tsx`
- 改节点 UI、节点类型、节点渲染
  - `src/components/flow/nodeTypes.ts`
  - `src/components/flow/NodeComponent.tsx`
  - `src/components/flow/nodeFactory.ts`
- 改节点配置表单
  - `src/components/canvas/NodeSidebar.tsx`
- 改代码生成面板或发给后端的 payload
  - `src/components/canvas/CodeSidebar.tsx`
- 改保存/加载/运行/测试交互
  - `src/components/SaveLoadFlow.tsx`
- 改 LLM / Tool 管理页
  - `src/pages/LLMsPage.tsx`
  - `src/pages/ToolsPage.tsx`
  - `src/api/llms.ts`
  - `src/services/flows.ts`
- 改 sandbox chat
  - `src/pages/ChatbotPage.tsx`
  - `src/components/chat/`
  - `src/hooks/useChat.ts`

## 节点数据结构

当前高频会用到三个层级：

- `node.data.node`
  - 节点自身运行配置
  - 例如 `systemPrompt`、`userPrompt`、`inputFormat`、`outputMode`
- `node.data.llm`
  - 选中的 LLM/provider/model
- `node.data.tool`
  - 选中的 tool 定义

改前后端联动时，先确认这三个对象在 store、表单、发包、后端 schema 里是否一致。

## 当前实现边界

- 代码侧栏调用后端 `/api/flows/generate/code`，展示的是生成后的 Python 代码。
- 多个 sandbox 页面仍是占位页或半成品。
- 前端是当前用户最先接触的系统，但它并不直接实现 `workflow_agents` 那套 runtime。

## 验证

- 改前端后，优先跑构建或最小手工验证。
- 如果是节点数据结构变更，务必联查：
  - `src/store/useFlowStore.ts`
  - `src/components/canvas/NodeSidebar.tsx`
  - `src/components/canvas/CodeSidebar.tsx`
  - `../backend/schemas/flows.py`
