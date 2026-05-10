# Frontend Backend API Contract

## Purpose

This document lists the backend interfaces currently required by the frontend.

It is based on the actual frontend code in `frontend/src`, not on the older product PRD. If the new Node.js backend is meant to replace the original Python service without breaking the UI, these routes are the migration baseline.

## Base URL Conventions In Current Frontend

The current frontend uses multiple base URL sources:

- `ServerContext`: defaults to `http://localhost:8000`
- `VITE_API_URL`
- `VITE_API_BASE_URL`
- hardcoded `http://localhost:8000` in several `NodeSidebar` calls

### Recommended cleanup target

Use a single backend base URL and normalize all callers to it.

## Endpoint Inventory

### Health

#### `HEAD /api/health`

- Used by: `frontend/src/contexts/ServerContext.tsx`
- Purpose: determine backend online/offline status
- Expected behavior: return `2xx` when server is reachable

### Chat Playground

#### `POST /api/playground/chatbot/chat`

- Used by: `frontend/src/api/chatbot.ts`
- Purpose: non-streaming chat completion
- Request body:

```json
{
  "messages": [
    { "role": "system", "content": "You are a helpful AI assistant." },
    { "role": "user", "content": "Hello" }
  ],
  "llm_type": "remote",
  "llm_alias": "openai-main",
  "model": "gpt-4.1",
  "temperature": 0.7,
  "max_tokens": 1000,
  "top_p": 1,
  "frequency_penalty": 0,
  "presence_penalty": 0
}
```

- Expected response shape:

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 0,
  "model": "gpt-4.1",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

#### `POST /api/playground/chatbot/chat/stream`

- Used by: `frontend/src/api/chatbot.ts`, parsed in `frontend/src/hooks/useChat.ts`
- Purpose: streaming chat completion
- Request body: same as non-streaming chat
- Expected stream format: SSE-like lines beginning with `data: `

Example chunks:

```text
data: {"choices":[{"delta":{"content":"Hel"}}]}
data: {"choices":[{"delta":{"content":"lo"}}]}
data: [DONE]
```

### LLM Registry

#### `GET /api/llms/remote`

- Used by:
  - `frontend/src/api/chatbot.ts`
  - `frontend/src/api/llms.ts`
  - `frontend/src/services/llmService.ts`
  - `frontend/src/pages/ToolsPage.tsx`
  - `frontend/src/components/canvas/NodeSidebar.tsx`
- Purpose: list remote/API-backed LLM entries
- Expected response: array of providers/LLM entries

#### `GET /api/llms/local`

- Used by:
  - `frontend/src/api/chatbot.ts`
  - `frontend/src/api/llms.ts`
  - `frontend/src/services/llmService.ts`
  - `frontend/src/components/canvas/NodeSidebar.tsx`
- Purpose: list local LLM entries
- Expected response: array

#### `GET /api/llms/remote/:alias`

- Used by: `frontend/src/services/llmService.ts`
- Purpose: fetch one remote LLM config

#### `GET /api/llms/local/:alias`

- Used by: `frontend/src/services/llmService.ts`
- Purpose: fetch one local LLM config

#### `POST /api/llms/remote`

- Used by: `frontend/src/services/llmService.ts`
- Purpose: create remote LLM entry
- Typical request body:

```json
{
  "alias": "openai-main",
  "provider": "openai",
  "api_key": "sk-...",
  "base_url": "https://api.openai.com/v1",
  "type": "api"
}
```

#### `PUT /api/llms/remote/:alias`

- Used by: `frontend/src/services/llmService.ts`
- Purpose: update remote LLM entry
- Body is partial; only included fields should be updated

#### `DELETE /api/llms/remote/:alias`

- Used by: `frontend/src/services/llmService.ts`

#### `POST /api/llms/local`

- Used by: `frontend/src/services/llmService.ts`
- Purpose: create local LLM entry

#### `PUT /api/llms/local/:alias`

- Used by: `frontend/src/services/llmService.ts`

#### `DELETE /api/llms/local/:alias`

- Used by: `frontend/src/services/llmService.ts`

#### `POST /api/llms/remote/validate-key`

- Used by: `frontend/src/pages/LLMsPage.tsx`
- Purpose: validate a user-supplied API key before saving
- Request body:

```json
{
  "provider": "openai",
  "api_key": "sk-..."
}
```

- Expected response:

```json
{
  "valid": true,
  "message": "API key is valid"
}
```

#### `GET /api/llms/remote/:alias/validate-key`

- Used by: `frontend/src/pages/LLMsPage.tsx`
- Purpose: validate stored remote credential for an existing alias
- Expected response:

```json
{
  "valid": true,
  "message": "API key is valid"
}
```

#### `GET /api/llms/remote/:alias/models`

- Used by:
  - `frontend/src/api/chatbot.ts`
  - `frontend/src/api/llms.ts`
  - `frontend/src/pages/LLMsPage.tsx`
  - `frontend/src/pages/ToolsPage.tsx`
  - `frontend/src/components/canvas/NodeSidebar.tsx`
- Expected response:

```json
{
  "models": ["gpt-4.1", "gpt-4.1-mini"]
}
```

#### `GET /api/llms/local/:alias/models`

- Used by same families of pages/components as above for local models
- Expected response:

```json
{
  "models": ["model-a", "model-b"]
}
```

#### `GET /api/llms/remote/:alias/embeddings_models`

- Used by: `frontend/src/pages/LLMsPage.tsx`
- Expected response:

```json
{
  "embeddings_models": ["text-embedding-3-large"]
}
```

#### `GET /api/llms/local/:alias/embeddings_models`

- Used by: `frontend/src/pages/LLMsPage.tsx`
- Expected response:

```json
{
  "embeddings_models": ["nomic-embed-text"]
}
```

#### `GET /api/llms/remote/:alias/parameters`

#### `GET /api/llms/local/:alias/parameters`

- Used by:
  - `frontend/src/api/chatbot.ts`
  - `frontend/src/api/llms.ts`
  - `frontend/src/components/chat/ConfigPanel.tsx`
- Purpose: fetch model parameter metadata for UI sliders/forms
- Expected response example:

```json
{
  "temperature": {
    "type": "number",
    "min": 0,
    "max": 2,
    "default": 0.7
  },
  "topP": {
    "type": "number",
    "min": 0,
    "max": 1,
    "default": 1
  }
}
```

#### `GET /api/llms/local/provider/lm-studio/models`

- Used by: `frontend/src/pages/LLMsPage.tsx`
- Purpose: query live LM Studio instance for available models
- Expected response:

```json
{
  "models": ["model-1", "model-2"]
}
```

#### `GET /api/llms/local/llama-cpp/recommended-path`

- Used by: `frontend/src/pages/LLMsPage.tsx`
- Purpose: suggest model directory path
- Expected response:

```json
{
  "path": "C:/models/llama"
}
```

### Tools

#### `GET /api/tools/`

- Used by:
  - `frontend/src/pages/ToolsPage.tsx`
- Purpose: list saved tools
- Expected response: array of tool objects

#### `GET /api/tools`

- Used by:
  - `frontend/src/components/canvas/NodeSidebar.tsx`
- Note: this is currently called without the trailing slash and is hardcoded to `http://localhost:8000`
- Purpose: list tools for node binding

#### `POST /api/tools/`

- Used by: `frontend/src/pages/ToolsPage.tsx`
- Purpose: create tool

#### `PUT /api/tools/:id`

- Used by: `frontend/src/pages/ToolsPage.tsx`
- Purpose: update tool

#### `DELETE /api/tools/:id`

- Used by: `frontend/src/pages/ToolsPage.tsx`
- Purpose: delete tool

#### `POST /api/tools/preview_code`

- Used by: `frontend/src/pages/ToolsPage.tsx`
- Purpose: preview generated implementation code for a tool definition
- Request body: tool form payload
- Expected response:

```json
{
  "code": "..."
}
```

#### `GET /api/tools/:toolName/default_agent_prompts`

- Used by: `frontend/src/components/canvas/NodeSidebar.tsx`
- Purpose: fetch default system/user prompts after selecting a tool
- Expected response:

```json
{
  "system_prompt": "...",
  "user_prompt": "..."
}
```

### Flows

#### `GET /api/flows/`

- Used by: `frontend/src/services/flows.ts`, `frontend/src/components/SaveLoadFlow.tsx`
- Purpose: list flows

#### `GET /api/flows/:id`

- Used by: `frontend/src/services/flows.ts`
- Purpose: fetch single flow

#### `POST /api/flows/`

- Used by: `frontend/src/services/flows.ts`, `frontend/src/components/SaveLoadFlow.tsx`
- Purpose: create flow
- Typical request shape:

```json
{
  "name": "My Flow",
  "description": "Example",
  "graph": {
    "nodes": [],
    "edges": []
  },
  "state": {
    "fields": []
  }
}
```

#### `PUT /api/flows/:id`

- Used by: `frontend/src/services/flows.ts`, `frontend/src/components/SaveLoadFlow.tsx`
- Purpose: update flow

#### `DELETE /api/flows/:id`

- Used by: `frontend/src/services/flows.ts`, `frontend/src/components/SaveLoadFlow.tsx`

#### `POST /api/flows/:id/run`

- Used by: `frontend/src/services/flows.ts`, `frontend/src/components/SaveLoadFlow.tsx`
- Purpose: execute flow
- Request body: optional input object

#### `POST /api/flows/:id/test`

- Used by: `frontend/src/services/flows.ts`, `frontend/src/components/SaveLoadFlow.tsx`
- Purpose: test flow
- Request body: optional input object

#### `POST /api/flows/generate/code`

- Used by: `frontend/src/components/canvas/CodeSidebar.tsx`
- Purpose: generate backend code from current graph state
- Request body example:

```json
{
  "name": "Untitled Flow",
  "description": "Generated on ...",
  "graph": {
    "nodes": [],
    "edges": []
  },
  "state": {
    "fields": []
  }
}
```

- Expected response:

```json
{
  "code": "..."
}
```

## Frontend Call Site Notes

### `NodeSidebar` uses hardcoded localhost

Current file: `frontend/src/components/canvas/NodeSidebar.tsx`

These requests do not use `ServerContext`:

- `GET http://localhost:8000/api/tools`
- `GET http://localhost:8000/api/llms/local`
- `GET http://localhost:8000/api/llms/remote`
- `GET http://localhost:8000/api/llms/remote/:alias/models`
- `GET http://localhost:8000/api/llms/local/:alias/models`

This should be normalized when integrating the new backend.

### `flows.ts` uses a hardcoded base URL

Current file: `frontend/src/services/flows.ts`

It uses:

- `const API_BASE_URL = 'http://localhost:8000/api';`

This should also be migrated to a shared configurable base URL.

### `llmService.ts` uses `VITE_API_BASE_URL`

Current file: `frontend/src/services/llmService.ts`

This differs from `VITE_API_URL` used elsewhere.

## Suggested Node.js Route Groups

To recreate the current frontend behavior, a good initial route split would be:

- `routes/health`
- `routes/llms`
- `routes/tools`
- `routes/flows`
- `routes/playground`

With internal service layers such as:

- `services/llmRegistry`
- `services/toolRegistry`
- `services/flowStore`
- `services/flowExecutor`
- `services/codeGenerator`
- `services/runtimeAdapters`

## Minimum Viable Compatibility Target

If the goal is to get the current frontend usable as quickly as possible with a Node.js backend, the minimum path is:

1. Implement `HEAD /api/health`
2. Implement LLM list/model/parameter APIs
3. Implement tool CRUD + preview APIs
4. Implement flow CRUD + run/test + code generation APIs
5. Implement chatbot `chat` and `chat/stream`

Once those exist, the current frontend can function as the migration surface while LangGraph orchestration is introduced behind the API.
