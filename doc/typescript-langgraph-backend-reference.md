# LangGraph Backend Reference

## Purpose

This document records the current Python FastAPI backend used by `langgraph_codegen`.

## Current implementation status

- Backend entrypoint is `langgraph_codegen/backend/main.py`
- Flow CRUD, code generation, tools, LLM registry, and chatbot routes are implemented
- `POST /api/flows/generate/code` returns Python LangGraph scaffold
- Flow execution is still simulation-first in `run` / `test`
- `start` / `end` map to `START` / `END` in the generated template
- Tool and LLM definitions remain registry-backed in the database

## Minimum HTTP surface

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

## Generated code shape

`POST /api/flows/generate/code` currently returns a Python LangGraph scaffold using:

- `StateGraph`
- `START`
- `END`
- node function stubs
- imported LLM and tool blocks

## Execution shape

`POST /api/flows/:id/run` and `POST /api/flows/:id/test` currently return:

- execution status
- result wrapper
- lightweight structured output

## Key implementation notes

- Keep graph persistence as JSON
- Generate code from templates or structured generators
- Do not store provider/model details inside the graph as source code
- Normalize state schema early

## Next backend step

Move `run` / `test` from simulation-first execution to actual LangGraph runtime execution.
