# Program Workflow

## Overview

This repository is evolving toward a Node.js-based AI agent orchestration platform.

The intended target architecture is:

- LangGraph JS for workflow orchestration
- Node.js/TypeScript as the main backend runtime
- Pluggable runtime adapters for different agent runtimes or model providers
- A frontend flow editor and operations UI that was merged from an existing Python-backed project

At the moment, the frontend is the most concrete part of the repo. It already runs from the repository root and expects a backend that exposes the same HTTP API shape as the original Python service.

## Current Status

- Frontend runs from the repository root with `npm run dev`
- Frontend production build works with `npm run build`
- Root `studio` script still points to `langgraphjs dev`, but there is no usable `langgraph.json` yet
- `backend/` does not yet contain the Node.js reimplementation
- The current frontend still assumes the old Python API contract
- Some frontend requests already use configurable backend URLs, but a few places still hardcode `http://localhost:8000`

## Quick Start

```bash
npm install
npm run dev
```

Available scripts:

- `npm run dev`: start Vite frontend using `frontend/`
- `npm run build`: build frontend
- `npm run preview`: preview built frontend
- `npm run studio`: reserved for future LangGraph backend work, not ready yet

## Repository Architecture

Planned runtime architecture:

1. Frontend provides visual flow editing, tool management, LLM management, and playground pages.
2. Node.js backend will provide:
   - flow persistence
   - flow execution / testing
   - code generation from graph state
   - tool registry CRUD
   - LLM registry CRUD
   - chatbot / playground APIs
3. LangGraph JS should eventually power orchestration logic instead of the original Python backend.

## Directory Structure

```text
.
|- frontend/                 Frontend app source and Vite entry
|- backend/                  Reserved for Node.js backend implementation
|- .langgraph_api/           Local LangGraph API state artifacts
|- doc/                      Project documentation and API contracts
|- package.json              Root scripts and merged frontend dependencies
|- tailwind.config.cjs       Root Tailwind config for frontend
|- postcss.config.cjs        Root PostCSS config for frontend
`- README.md                 This document
```

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

## Backend Interfaces Required By Frontend

The frontend is not backend-agnostic. It expects specific REST endpoints and, for chat streaming, an SSE-like payload format.

See:

- [doc/frontend-backend-api.md](./doc/frontend-backend-api.md)

This document includes:

- endpoint groups
- callers in the frontend
- request and response expectations
- notes about streaming
- current inconsistencies in URL handling

## Important Integration Notes

### 1. Backend URL usage is not fully unified

The frontend currently uses three patterns:

- `ServerContext` with configurable `serverUrl`
- `import.meta.env.VITE_API_URL`
- hardcoded `http://localhost:8000` in some `NodeSidebar` calls

When building the Node.js backend, unifying all frontend calls around a single base URL should be treated as follow-up cleanup.

### 2. Sandbox is partly real, partly placeholder

- `sandbox/chatbot` is a real playground page with working API dependencies
- the other sandbox pages are static placeholders for future capabilities

### 3. Flow execution is already assumed by the UI

The frontend is not just a static editor. It already expects the backend to support:

- save flow
- load flow
- run flow
- test flow
- generate code from graph state

### 4. LLM management is relatively broad

The frontend expects both:

- remote/API-backed LLM providers
- local providers such as LM Studio and llama.cpp

The Node.js backend should treat this as an adapter layer, not as a single-provider implementation.

## Recommended Backend Reimplementation Direction

For the new Node.js backend, a practical first split would be:

- `health` routes
- `llms` routes and adapter layer
- `tools` routes and persistence
- `flows` routes and persistence
- `playground/chatbot` routes
- LangGraph orchestration layer behind `flows/run`, `flows/test`, and later agent execution APIs

## Known Gaps

- No Node.js backend implementation yet
- No finalized LangGraph runtime config in repo root
- `backend/` is still effectively empty
- Frontend still reflects the old Python backend contract
- Some frontend pages contain placeholder content rather than live functionality

## Suggested Next Steps

1. Define the Node.js backend API surface using the existing frontend contract as the migration baseline.
2. Implement `health`, `llms`, `tools`, `flows`, and `playground/chatbot` first.
3. Replace hardcoded frontend backend URLs with a single source of truth.
4. Move flow execution to LangGraph JS once persistence and adapters exist.
