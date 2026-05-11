# TypeScript LangGraph Backend Reference

## Purpose

This document defines a minimal TypeScript backend for a visual LangGraph-based agent builder.

Target capabilities:

- visual graph orchestration
- custom state definition
- code export
- enough registry support for tools and LLMs to make exported graphs usable

This is a migration reference, not a product spec.

Companion structure map:

- [`ref/agent-smith/backend-structure.md`](../ref/agent-smith/backend-structure.md)

## Minimum HTTP Surface

### Health

- `HEAD /api/health`
- `GET /api/health`

Purpose:

- backend readiness check

### Flows

- `GET /api/flows`
- `POST /api/flows`
- `GET /api/flows/:id`
- `PUT /api/flows/:id`
- `DELETE /api/flows/:id`
- `POST /api/flows/generate/code`
- `POST /api/flows/:id/run`
- `POST /api/flows/:id/test`

Purpose:

- persist visual graphs
- load existing drafts
- export runnable code
- execute or dry-run a saved graph

### Tools

- `GET /api/tools`
- `POST /api/tools`
- `GET /api/tools/:id`
- `PUT /api/tools/:id`
- `DELETE /api/tools/:id`
- `POST /api/tools/preview_code`
- `GET /api/tools/:name/default_agent_prompts`

Purpose:

- store reusable tool definitions
- preview generated tool code
- provide default prompts for node binding

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

Purpose:

- keep model/provider configuration out of graph JSON
- support both remote and local backends
- support parameter discovery for UI forms

## Internal TypeScript Interfaces

### Flow DTO

```ts
type FlowGraph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

type FlowState = {
  fields: StateField[];
};

type FlowPayload = {
  name: string;
  description?: string;
  graph: FlowGraph;
  state: FlowState;
};
```

### Graph Compiler

```ts
interface FlowCompiler {
  generateCode(flow: FlowPayload): Promise<string>;
  compile(flow: FlowPayload): Promise<CompiledGraph>;
  sanitizeNodeName(name: string): string;
}
```

### Flow Executor

```ts
interface FlowExecutor {
  run(flowId: string, input?: Record<string, unknown>): Promise<unknown>;
  test(flowId: string, input?: Record<string, unknown>): Promise<unknown>;
}
```

### Tool Adapter

```ts
interface ToolAdapter {
  toCode(): string;
  toNode(): Record<string, unknown>;
  defaultAgentPrompts(): { system_prompt: string; user_prompt: string };
}
```

### LLM Adapter

```ts
interface LLMAdapter {
  listModels(): Promise<string[]>;
  listEmbeddingModels(): Promise<string[]>;
  validateKey(apiKey?: string): Promise<boolean>;
  getTunableParameters(model?: string): Record<string, unknown>;
  toCode(model: string): string;
}
```

### Persistence Layer

```ts
interface FlowRepository {
  create(flow: FlowPayload): Promise<FlowRecord>;
  update(id: string, flow: FlowPayload): Promise<FlowRecord | null>;
  findById(id: string): Promise<FlowRecord | null>;
  list(limit?: number): Promise<FlowRecord[]>;
  delete(id: string): Promise<FlowRecord | null>;
}
```

## LangGraph JS Integration Notes

- use `StateGraph` as the runtime compiler target
- map visual `start` and `end` nodes to `START` and `END`
- generate node function names from labels with sanitization
- keep graph persistence as JSON, not as generated source
- render code from templates or structured generators, not by mutating stored graph state
- treat state fields as schema metadata, then derive the LangGraph state type from them

## Key Implementation Risks

- node labels may not be valid TypeScript identifiers
- graph JSON and generated code can drift if codegen mutates stored data
- state schema can contain unsupported types unless normalized early
- secrets must not be stored in plaintext
- provider/model discovery is backend-specific and may fail offline
- streaming and non-streaming responses should share one response contract
- the frontend currently assumes multiple base URL styles, so the backend should not hardcode a single origin

## Recommended Minimum Build Order

1. health
2. flow persistence
3. state schema validation
4. code generation
5. tool registry
6. LLM registry
7. run/test execution

## Reference Mapping From AgentSmith

The Python reference implements the same split:

- `api/flows.py`
- `api/tools.py`
- `api/llms.py`
- `services/flows/codegen.py`
- `services/tools/*`
- `services/llms/*`

This document is the TypeScript adaptation target for that architecture.
