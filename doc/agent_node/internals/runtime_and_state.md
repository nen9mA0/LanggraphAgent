# Runtime And State Internals

This document covers implementation details that are intentionally kept out of the public API reference.

## Internal Boundaries

### `ManagedAgentRuntime`

The internal base runtime coordinates:

- active turn bookkeeping
- persisted session or thread restore
- normalized event recording
- turn completion and shutdown semantics

Internal design rules:

- one runtime can have only one active turn
- `session_id` is persisted in `runtime.json`
- runtime events stay in memory unless `persist_runtime_history=True`

### `AgentWorkspace`

Each runtime owns one workspace under `.workflow/agent/<folder>`.

Files:

```text
.workflow/agent/<folder>/
|- config.json
|- runtime.json
|- history.jsonl
|- inbox.jsonl
|- outbox.jsonl
|- .claude/settings.json         # optional local provider snapshot
|- .codex/config.toml           # optional local provider snapshot
`- reused_mcp.json              # optional Claude MCP materialization
```

Writers:

- `config.json`
  - written by the registry from `AgentNodeConfig`
- `runtime.json`
  - written by the runtime to store the resumable backend id
- `history.jsonl`
  - written by the runtime only when runtime history persistence is enabled
- `inbox.jsonl` and `outbox.jsonl`
  - written by `AgentNode` only when mailbox persistence is enabled

## Internal Execution Flow

### `AgentNode.__call__()`

High-level flow:

1. copy the mailbox state
2. read `mailboxes[config.name]`
3. clear that mailbox entry
4. if there is no inbound work, return `{"status": "idle", "skipped": True}`
5. obtain the runtime from the registry
6. optionally persist inbound mailbox records
7. build the prompt
8. execute one runtime turn
9. create outbound `InterNodeMessage` values from `TurnResult.final_output`
10. update downstream mailboxes and `agent_results`

Important consequence:

- the graph state is an orchestration summary, not a replayable transcript

### `merge_mailboxes`

Mailbox state uses right-hand overwrite semantics per key instead of append-only merge.

Reason:

- once a node consumes its mailbox, it returns an empty list for that key
- the reducer must preserve that empty list instead of restoring old messages

## Backend Adapters

### Claude CLI runtime

- starts a long-lived `claude -p --input-format stream-json --output-format stream-json` process
- sends each prompt as one JSON line to stdin
- maps stream-json output to normalized events
- resumes with `--resume <session_id>`
- if local Claude provider snapshots or reused skills exist, prepares an agent-local `CLAUDE_CONFIG_DIR`
- if reused MCP exists, writes `reused_mcp.json` and passes it during Claude startup

### Claude SDK runtime

- starts a Python worker process
- sends `turn`, `interrupt`, and `shutdown` commands over stdin
- the worker imports the configured SDK module and streams JSON back
- reuses the same local Claude config overlay model as the CLI runtime
- passes worker env and optional local MCP config through the worker bootstrap payload

### Codex runtime

- starts `codex app-server --listen stdio://`
- initializes a JSON-RPC session
- resumes or creates a thread
- executes turns with `turn/start`
- converts item notifications into normalized text, thinking, tool, and log events
- converts reused provider fields into startup `-c` overrides:
  - `skills.config=...`
  - `mcp_servers=...`
  - optional model-provider extras

## State Model

`AgentGraphState` contains:

```python
class AgentGraphState(TypedDict, total=False):
    mailboxes: dict[str, list[dict[str, Any]]]
    agent_results: dict[str, dict[str, Any]]
    shared: dict[str, Any]
```

Roles:

- `mailboxes`
  - cross-node task payloads only
- `agent_results`
  - summarized output for graph control and debugging
- `shared`
  - graph-wide context

The following runtime details are intentionally not copied into graph state by default:

- `thinking`
- `tool_use`
- `tool_result`
- raw CLI or RPC protocol messages
- streaming partial text beyond the final forwarded output

## Why Only `final_output` Crosses Node Boundaries

This separation keeps the system predictable:

- graph state stays compact
- backend-specific traces do not leak into unrelated nodes
- backend-native resume relies on `session_id`, not mailbox replay
- auditing and orchestration stay separate concerns

## Code Reading Order

If you need to change behavior, read files in this order:

1. `src/workflow_agents/types.py`
2. `src/workflow_agents/state.py`
3. `src/workflow_agents/storage.py`
4. `src/workflow_agents/runtime/base.py`
5. `src/workflow_agents/runtime/claude.py`
6. `src/workflow_agents/runtime/claude_sdk.py`
7. `src/workflow_agents/runtime/codex.py`
8. `src/workflow_agents/registry.py`
9. `src/workflow_agents/node.py`
