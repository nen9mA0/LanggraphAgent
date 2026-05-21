# Architecture

## Purpose

`workflow_agents` provides a small orchestration layer around long-lived agent backends. It is designed to keep backend-native session continuity while exposing a simple LangGraph-facing interface.

Supported backends:

- `claude`
- `claude_sdk`
- `codex`

## Design Rules

- one runtime handles at most one active turn at a time
- each agent node owns a durable workspace under `.workflow/agent/<folder>`
- node-to-node communication carries only `TurnResult.final_output` by default
- backend-native streaming events stay inside the runtime unless runtime history persistence is enabled
- provider config reuse is minimal and reviewable rather than copying full provider directories
  - local provider snapshots can also carry reusable `skills` and `mcp` values

## Layered View

### Graph layer

`AgentNode` is the LangGraph-facing boundary.

Responsibilities:

- read mailbox messages for one node
- build a prompt from inbound messages and shared state
- execute one agent turn
- forward the final output to downstream targets
- write a summarized result into `agent_results`

### Runtime layer

Concrete runtimes encapsulate backend-specific session handling.

Responsibilities:

- start and stop the backing CLI process or worker
- preserve the backend session or thread identifier
- stream internal events into a normalized event model
- return a `TurnResult` for each turn

### Registry and workspace layer

`AgentRuntimeRegistry` owns runtime instances, while `AgentWorkspace` defines the durable filesystem boundary for one agent instance.

Responsibilities:

- reuse one runtime per `instance_key`
- allocate stable workspace folders
- persist `config.json` and `runtime.json`
- optionally persist runtime history and mailbox traffic

## Main Components

### `AgentNodeConfig`

The central configuration object shared across graph, runtime, and storage concerns.

Key concerns:

- backend selection
- working directory and executable path
- prompt and model configuration
- downstream routing targets
- persistence options
- backend-specific `runtime_options`

### `AgentGraphState`

The shared graph state has three fields:

- `mailboxes`
  - cross-node message queues
- `agent_results`
  - summarized result for each node's most recent turn
- `shared`
  - workflow-wide context injected by the graph

### `TurnResult`

A completed turn snapshot that contains:

- status
- session or thread identifier
- final output
- optional error text
- token usage
- normalized output events

Only `final_output` is forwarded automatically to downstream nodes.

## Execution Flow

Typical flow:

1. Build an `AgentNodeConfig`.
2. Ask `AgentRuntimeRegistry` for a runtime.
3. The registry allocates or reuses a workspace and starts the concrete runtime if needed.
4. `AgentNode` converts inbound mailbox messages into one prompt.
5. The runtime executes one backend turn.
6. The runtime returns a `TurnResult`.
7. `AgentNode` forwards `TurnResult.final_output` to downstream targets.

## Workspace Layout

Each agent workspace lives under:

```text
.workflow/agent/<folder>/
|- config.json
|- runtime.json
|- inbox.jsonl
|- outbox.jsonl
|- history.jsonl                 # only when persist_runtime_history=True
|- .claude/settings.json         # optional Claude snapshot
`- .codex/config.toml            # optional Codex snapshot
```

Notes:

- `config.json` stores the persisted `AgentNodeConfig`
- `runtime.json` stores the resumable backend identifier
- `inbox.jsonl` and `outbox.jsonl` are written only when mailbox persistence is enabled
- `history.jsonl` is written only when runtime history persistence is enabled
- provider-native snapshots are optional local inputs, not full backend state copies

## Backend Summary

### Claude CLI

- launches a long-lived `claude -p` stream-json session
- resumes later turns through `--resume <session_id>`

### Claude SDK

- launches a dedicated Python worker process
- the worker talks to the Claude SDK and streams JSON lines back to the parent runtime

### Codex

- launches `codex app-server --listen stdio://`
- uses JSON-RPC for thread lifecycle and turn execution
- persists the Codex thread id as `session_id`

## Further Reading

- `api_reference.md`
- `integrations/provider_config_reuse.md`
- `examples/real_agent_demo.md`
- `integrations/claude_sdk.md`
- `internals/runtime_and_state.md`
