## Frontend Route Map

- `/`: flow canvas editor
- `/llms`: remote/local LLM registry management
- `/tools`: tool CRUD and code preview
- `/settings`: backend server URL configuration
- `/about`: static product/about page
- `/sandbox/chatbot`: working chatbot playground
- `/sandbox/tool-tester`: placeholder page
- `/sandbox/rag-lab`: placeholder page
- `/sandbox/llm-finetuning`: placeholder page

## Frontend Code Map

### Root frontend files

- `frontend/index.html`: Vite HTML entry
- `frontend/vite.config.ts`: frontend Vite config, root/env settings, chunk splitting
- `frontend/tsconfig.json`: TypeScript project references
- `frontend/tsconfig.app.json`: app TypeScript config
- `frontend/tsconfig.node.json`: Node-side TypeScript config for Vite config
- `frontend/eslint.config.js`: frontend lint configuration

### `frontend/src/`

#### App bootstrap

- `frontend/src/main.tsx`: React entry, mounts app and wraps `ReactFlowProvider`
- `frontend/src/App.tsx`: app shell, router, header navigation, lazy-loaded pages
- `frontend/src/index.css`: global styles, Tailwind layers, React Flow base styles
- `frontend/src/App.css`: legacy app styles, low importance
- `frontend/src/vite-env.d.ts`: Vite env type definitions

#### API wrappers

- `frontend/src/api/chatbot.ts`: chatbot playground API wrapper, includes streaming chat requests
- `frontend/src/api/llms.ts`: basic LLM listing/model/parameter APIs used by some UI parts

#### Service wrappers

- `frontend/src/services/flows.ts`: flow CRUD, run, test APIs
- `frontend/src/services/llmService.ts`: richer LLM CRUD service abstraction for `/llms`

#### Context and hooks

- `frontend/src/contexts/ServerContext.tsx`: configurable backend base URL, health checks, localStorage persistence
- `frontend/src/hooks/useChat.ts`: chat state machine, streaming handling, metrics

#### Store and shared types

- `frontend/src/store/useFlowStore.ts`: Zustand store for nodes, edges, and flow state
- `frontend/src/types/index.ts`: shared frontend types for nodes and graph-related objects
- `frontend/src/utils/nodeUtils.ts`: node-related helper utilities

#### Pages

- `frontend/src/pages/ChatbotPage.tsx`: working sandbox chat playground page
- `frontend/src/pages/ToolsPage.tsx`: tool management page with preview/save/delete flows
- `frontend/src/pages/LLMsPage.tsx`: remote/local model provider management UI
- `frontend/src/pages/SettingsPage.tsx`: backend server URL settings page
- `frontend/src/pages/AboutPage.tsx`: marketing/about page
- `frontend/src/pages/ToolTesterPage.tsx`: placeholder sandbox page
- `frontend/src/pages/RAGLabPage.tsx`: placeholder sandbox page
- `frontend/src/pages/LLMFinetuningPage.tsx`: placeholder sandbox page

#### Canvas and graph editor

- `frontend/src/components/FlowCanvas.tsx`: main React Flow canvas, modal orchestration, save/load integration
- `frontend/src/components/FlowCanvas.module.css`: canvas-specific CSS module
- `frontend/src/components/SaveLoadFlow.tsx`: save/load/run/test dialog for flows
- `frontend/src/components/StateModal.tsx`: edit graph state schema
- `frontend/src/components/MemoryModal.tsx`: memory settings modal

#### Canvas sidebars

- `frontend/src/components/canvas/NodeSidebar.tsx`: selected node editor, LLM/tool binding, prompt loading, model selection
- `frontend/src/components/canvas/CodeSidebar.tsx`: generate backend code from current graph

#### Flow node rendering

- `frontend/src/components/flow/NodeComponent.tsx`: node renderer for React Flow
- `frontend/src/components/flow/nodeTypes.ts`: React Flow node type registry
- `frontend/src/components/flow/nodeFactory.ts`: node creation helpers
- `frontend/src/components/flow/Toolbar.tsx`: add-node / state / memory toolbar

#### Chat UI

- `frontend/src/components/chat/ConfigPanel.tsx`: model config panel for chatbot sandbox
- `frontend/src/components/chat/ChatInput.tsx`: chat input box with file upload UI
- `frontend/src/components/chat/ChatMessage.tsx`: message renderer and code block display

#### Tool configuration forms

- `frontend/src/components/tools/APICallConfig.tsx`: API-call tool config form
- `frontend/src/components/tools/CodeEditorConfig.tsx`: Monaco-backed code editor config
- `frontend/src/components/tools/RAGConfig.tsx`: RAG tool config form
- `frontend/src/components/tools/WebSearchConfig.tsx`: web search tool config form

#### Assets

- `frontend/src/assets/logo.png`: app asset
- `frontend/src/assets/react.svg`: default asset
