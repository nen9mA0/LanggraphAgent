# workflow_agents Agent Guide

## Purpose

`workflow_agents` wraps long-lived agent backends as reusable Python runtimes and optional LangGraph nodes.

Current supported backends:

- `claude`
- `claude_sdk`
- `codex`

Primary goals:

- keep one long-lived runtime per agent node
- persist session/thread state across turns
- keep runtime transcript persistence optional
- only forward `final_output` across agent nodes
- support minimal reuse of provider-native config snapshots under each agent workspace

## Main Concepts

- `AgentNodeConfig`
  - runtime/node config object
  - defined in `types.py`
- `ManagedAgentRuntime`
  - abstract runtime lifecycle in `runtime/base.py`
  - concrete backends implement `_start_impl`, `_send_input_impl`, `_cancel_active_turn`, `_shutdown_impl`
- `AgentRuntimeRegistry`
  - owns runtime instances and workspace allocation
- `AgentNode`
  - LangGraph-compatible wrapper around a runtime
- `AgentWorkspace`
  - durable filesystem boundary for one agent instance

## Important Design Rules

- one runtime can only have one active turn at a time
- internal events stay in runtime memory and are only persisted when explicitly enabled
- downstream nodes only receive `TurnResult.final_output`
- `session_id` means:
  - Claude session id
  - Claude SDK resume/session id
  - Codex thread id
- `folder_name` means “reuse this exact workspace folder”
- without `folder_name`, workspace names auto-suffix on collision

## Directory Map

- `types.py`
  - shared datatypes: config, turn result, output events, mailbox message
- `config_reuse.py`
  - reads minimal reusable provider config
  - can materialize local `.claude/settings.json` or `.codex/config.toml` snapshots under agent folders
- `storage.py`
  - workspace paths and folder allocation
- `registry.py`
  - runtime creation/reuse entry
- `state.py`
  - LangGraph state and reducers
- `node.py`
  - `AgentNode` and prompt builder
- `runtime/base.py`
  - common runtime lifecycle and turn bookkeeping
- `runtime/factory.py`
  - backend dispatch by `agent_type`
- `runtime/claude.py`
  - Claude CLI runtime
- `runtime/claude_sdk.py`
  - Claude Python SDK runtime via worker process
- `runtime/claude_sdk_worker.py`
  - async SDK bridge worker
- `runtime/codex.py`
  - Codex app-server JSON-RPC runtime
- `examples/`
  - manual usage and demo entrypoints

## Execution Path

Typical flow:

1. build `AgentNodeConfig`
2. call `AgentRuntimeRegistry.get_or_create(config)`
3. registry allocates `AgentWorkspace`
4. runtime factory creates concrete runtime
5. runtime `send_input()` starts a turn
6. backend emits events and usage
7. runtime finalizes `TurnResult`
8. `AgentNode` forwards only `final_output`

## Workspace Files

Each runtime writes into:

```text
.workflow/agent/<folder>/
|- config.json
|- .claude/settings.json        # optional local Claude snapshot
|- .codex/config.toml           # optional local Codex snapshot
|- runtime.json
|- inbox.jsonl
`- outbox.jsonl
```

Meaning:

- `config.json`
  - persisted config snapshot
- `.claude/settings.json` / `.codex/config.toml`
  - optional minimal provider-native config snapshots
  - preferred when `AgentNodeConfig.from_provider_defaults(..., provider_config_directory=...)` is used
  - intended for reusing only the smallest useful subset such as model selection
- `runtime.json`
  - persisted session/thread id
- `history.jsonl`
  - optional
  - only written when `persist_runtime_history=True`
- `inbox.jsonl`, `outbox.jsonl`
  - node-to-node message persistence
  - written only when `persist_node_mailboxes=True`

## Backend Notes

### Claude CLI

- long-lived `claude -p` stream-json process
- session reuse via `--resume`

### Claude SDK

- sync parent runtime + async worker process
- worker imports `claude_agent_sdk`
- use `runtime_options["python_executable"]` when shell Python is not the SDK Python

### Codex

- talks to `codex app-server --listen stdio://`
- uses JSON-RPC
- supports thread resume, turn start, turn interrupt, item streaming, and basic server-initiated request handling

## Safe Modification Points

If changing behavior, start here:

- change protocol/backend behavior:
  - `runtime/claude.py`
  - `runtime/claude_sdk.py`
  - `runtime/codex.py`
- change shared lifecycle semantics:
  - `runtime/base.py`
- change workspace naming/persistence:
  - `storage.py`
  - `registry.py`
- change graph-facing behavior:
  - `node.py`
  - `state.py`

## Common Pitfalls

- do not instantiate `ManagedAgentRuntime` directly
- do not bypass `wait_for_completion()` after `send_input()`
- do not forward internal tool/thinking events through graph mailboxes unless intentionally changing the design
- do not assume runtime history is persisted by default
- do not break `folder_name` reuse semantics
- do not copy full provider config directories into agent workspaces unless intentionally expanding the scope
- local provider snapshots are meant to stay minimal and reviewable
- be careful with status races around timeout vs interrupt vs shutdown

## Fast Sanity Checks

Use:

```bash
python -m unittest -v
```

Important tests:

- `tests.test_workflow_agents`
- `tests.test_runtime_cli_availability`

Real CLI / real SDK tests are opt-in by environment variable.
