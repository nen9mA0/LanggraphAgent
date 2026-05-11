# TypeScript LangGraph Backend Reference

## Purpose

This document tracks the Node.js/TypeScript backend direction for the current repo.

It is both a target architecture note and a status reference for what is already implemented.

## Current Implementation Status

- Minimal TypeScript backend is running from `backend/src/main.ts`
- Health, flows CRUD, code generation, run/test, tools, LLM registry, and chatbot routes are implemented
- Flow execution is simulation-first and returns structured trace data
- Generated flow code is TypeScript LangGraph code
- Visual `start` / `end` nodes map to `START` / `END` in generated code
- Tool and LLM data are still registry-backed and not embedded into graph JSON

## Minimum HTTP Surface

### Health

- `HEAD /api/health`
- `GET /api/health`

### Flows

- `GET /api/flows`
- `POST /api/flows`
- `GET /api/flows/:id`
- `PUT /api/flows/:id`
- `DELETE /api/flows/:id`
- `POST /api/flows/generate/code`
- `POST /api/flows/:id/run`
- `POST /api/flows/:id/test`

### Tools

- `GET /api/tools`
- `POST /api/tools`
- `GET /api/tools/:id`
- `PUT /api/tools/:id`
- `DELETE /api/tools/:id`
- `POST /api/tools/preview_code`
- `GET /api/tools/:name/default_agent_prompts`

### LLM Registry

- `GET /api/llms/remote`
- `POST /api/llms/remote`
- `GET /api/llms/remote/:alias`
- `PUT /api/llms/remote/:alias`
- `DELETE /api/llms/remote/:alias`
- `POST /api/llms/remote/validate-key`
- `GET /api/llms/remote/:alias/validate-key`
- `GET /api/llms/remote/:alias/models`
- `GET /api/llms/remote/:alias/embeddings_models`
- `GET /api/llms/remote/:alias/parameters`
- `GET /api/llms/local`
- `POST /api/llms/local`
- `GET /api/llms/local/:alias`
- `PUT /api/llms/local/:alias`
- `DELETE /api/llms/local/:alias`
- `GET /api/llms/local/:alias/models`
- `GET /api/llms/local/:alias/embeddings_models`
- `GET /api/llms/local/:alias/parameters`
- `GET /api/llms/local/provider/:provider/models`
- `GET /api/llms/local/:provider/recommended-path`

### Playground

- `POST /api/playground/chatbot/chat`
- `POST /api/playground/chatbot/chat/stream`

## Generated Code Shape

`POST /api/flows/generate/code` currently returns a TypeScript LangGraph scaffold using:

- `Annotation`
- `StateGraph`
- `START`
- `END`

Node stubs are emitted as `async function` blocks and the graph is compiled as TypeScript output.

## Execution Shape

`POST /api/flows/:id/run` and `POST /api/flows/:id/test` return:

- execution status
- result wrapper
- structured execution trace
- warnings

## Key Implementation Notes

- Keep graph persistence as JSON
- Generate code from templates or structured generators
- Do not store provider/model details inside the graph as source code
- Normalize state schema early

## Next Backend Step

Move `run` / `test` from simulation-first execution to actual LangGraph JS runtime execution.
