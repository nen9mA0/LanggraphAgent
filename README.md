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
- Frontend runs from the repository root with `npm run frontend:dev`
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

- `npm run frontend:dev`: start Vite frontend using `frontend/`
- `npm run build`: build frontend
- `npm run preview`: preview built frontend
- `npm run studio`: start the minimal TypeScript backend
- `npm run backend:dev`: start the minimal TypeScript backend

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

## Frontend Code Structure

See doc/frontend_structure.md

## Backend Interfaces Required By Frontend

The frontend is not backend-agnostic. It expects specific REST endpoints and, for chat streaming, an SSE-like payload format.

See doc/frontend-backend-api.md

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
