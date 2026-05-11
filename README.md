# Program Workflow

## Overview

This repository is moving toward a Node.js/TypeScript AI agent orchestration platform.

Current focus:

- LangGraph JS as the workflow runtime
- TypeScript backend as the primary server
- Frontend flow editor and playground UI
- Registry-backed tools and LLMs

## Current Status

- `npm run backend:dev` starts the minimal TypeScript backend
- `npm run studio` starts the same backend entrypoint
- `npm run frontend:dev` starts the Vite frontend
- `npm run build` succeeds
- Backend now supports:
  - `health`
  - flows CRUD
  - TypeScript code generation from graph state
  - `run` / `test` with structured execution traces
  - tools CRUD and code preview
  - remote/local LLM registry endpoints
  - chatbot chat and chat/stream endpoints
- Frontend base URL handling is centralized through `frontend/src/utils/serverUrl.ts`
- Flow canvas supports node and edge deletion through the left-top selection card
- Remaining cleanup is mostly legacy API/helper consistency and page-level polish

## Quick Start

```bash
npm install
npm run backend:dev
npm run frontend:dev
```

## Repository Architecture

1. Frontend provides visual flow editing, tool management, LLM management, and playground pages.
2. Backend provides flow persistence, execution, code generation, tool registry, LLM registry, and chatbot APIs.
3. LangGraph JS is the runtime target for generated workflows.

## Directory Structure

```text
.
|- frontend/                 Frontend app source and Vite entry
|- backend/                  TypeScript backend implementation
|- .langgraph_api/           Local LangGraph API state artifacts
|- doc/                      Project documentation and API contracts
|- package.json              Root scripts and merged frontend dependencies
|- tailwind.config.cjs       Root Tailwind config for frontend
|- postcss.config.cjs        Root PostCSS config for frontend
`- readme.md                 This document
```

## Backend Interfaces Required By Frontend

See [doc/frontend-backend-api.md](doc/frontend-backend-api.md).

## Important Integration Notes

- Most active frontend callers now use `getApiBaseUrl()` / `getServerUrl()`
- A few legacy helpers still exist and should be cleaned up later
- `run` / `test` are simulation-first and return structured execution data
- `POST /api/flows/generate/code` now emits TypeScript LangGraph code

## Suggested Next Steps

1. Finish removing legacy API helpers and unify the remaining URL conventions.
2. Replace simulated flow execution with real LangGraph JS execution.
3. Tighten tool and LLM registry behavior around the active UI flows.
