# API Reference

This document covers the public surface exported by `workflow_agents`.

## Public Exports

`workflow_agents.__init__` exports:

- `AgentGraphState`
- `AgentNode`
- `AgentNodeConfig`
- `AgentOutputEvent`
- `AgentRuntimeRegistry`
- `InterNodeMessage`
- `ReusedAgentConfig`
- `ReusedConfigSnapshot`
- `TokenUsageSnapshot`
- `TurnResult`
- `apply_reused_agent_config`
- `build_agent_node`
- `build_reused_agent_config`
- `write_reused_agent_config`

Internal runtime classes and backend adapters are intentionally documented under `internals/` and `integrations/`, not here.

## `AgentNodeConfig`

Configuration for one reusable agent runtime and its optional graph node wrapper.

### Required fields

- `name`
  - logical node name
  - also used as the mailbox key
- `agent_type`
  - one of `claude`, `claude_sdk`, or `codex`
- `working_directory`
  - execution directory used by the backend

### Common execution fields

- `executable_path`
  - explicit backend executable or Python interpreter path
- `system_prompt`
  - backend-level system or developer instructions
- `model`
  - explicit model override
- `cli_args`
  - extra backend CLI arguments
- `env`
  - extra environment variables
- `context_window_tokens`
  - optional context window used for usage reporting
- `max_turns`
  - optional backend turn limit
- `turn_timeout_seconds`
  - max time to wait for one turn
- `startup_timeout_seconds`
  - max time to wait for backend startup
- `semantic_inactivity_timeout_seconds`
  - reserved backend timeout knob carried in config
- `auto_start`
  - start the runtime automatically on first use

### Graph-facing fields

- `targets`
  - downstream node names that should receive `final_output`
- `prompt_prefix`
  - extra prompt text added by the default prompt builder

### Persistence fields

- `folder_name`
  - fixed workspace folder name under `.workflow/agent`
- `persist_runtime_history`
  - whether to append raw turn history to `history.jsonl`
- `persist_node_mailboxes`
  - whether to append mailbox traffic to `inbox.jsonl` and `outbox.jsonl`
- `instance_key`
  - identity used by the registry to reuse a runtime instance

### Extension field

- `runtime_options`
  - backend-specific options such as Claude SDK worker settings or reused provider config values
  - reused provider values currently include:
    - `reused_skills`
    - `reused_mcp`
    - Codex config values such as `reused_base_url`, and `reused_model_reasoning_effort`
    - Codex auth payload as `reused_auth`
    - Codex config mode as `codex_config_mode`, with `isolated` and `lightweight`

Agent config reuse is handled by the standalone helpers documented below:

1. `build_reused_agent_config(...)`
2. `apply_reused_agent_config(...)`
3. `write_reused_agent_config(...)`

This keeps reusable provider settings separate from plain `AgentNodeConfig` construction.

## `AgentNode`

LangGraph-compatible wrapper around one managed runtime.

### Constructor

```python
AgentNode(
    config: AgentNodeConfig,
    registry: AgentRuntimeRegistry | None = None,
    prompt_builder: PromptBuilder = default_prompt_builder,
)
```

### Main methods

- `get_runtime()`
  - lazily create or reuse the backing runtime
- `invoke_direct(prompt)`
  - run one prompt directly and return a `TurnResult`
- `__call__(state)`
  - consume mailbox messages, run one turn, and return graph state updates

### Behavior

- reads inbound messages from `state["mailboxes"][config.name]`
- builds one prompt
- runs one backend turn
- forwards only `TurnResult.final_output` to `config.targets`
- writes a summarized entry to `agent_results`

### `build_agent_node(...)`

Convenience constructor equivalent to instantiating `AgentNode` directly.

## `AgentRuntimeRegistry`

Owns runtime instances and their workspaces.

### Constructor

```python
AgentRuntimeRegistry(base_directory: str | Path | None = None)
```

If `base_directory` is omitted, the default workspace root is `./.workflow/agent`.

### Main methods

- `get_or_create(config)`
  - allocate or reuse the workspace
  - persist `config.json`
  - create the backend runtime
  - auto-start it when `config.auto_start` is true
- `shutdown_all()`
  - shut down every runtime currently owned by the registry

## Runtime Handle

`AgentNode.get_runtime()` and `AgentRuntimeRegistry.get_or_create(...)` return a runtime handle suitable for direct execution.

Stable operations used by the package examples:

- `start()`
- `send_input(prompt)`
- `wait_for_completion(timeout=None)`
- `run_turn(prompt, timeout=None)`
- `get_output_events(after_index=0)`
- `get_output_text()`
- `get_context_usage()`
- `get_context_usage_ratio()`
- `is_output_complete()`
- `shutdown()`

For the internal runtime contract and backend adapter details, see `internals/runtime_and_state.md`.

## Graph State and Message Types

### `AgentGraphState`

Shared LangGraph state with these keys:

- `mailboxes`
  - `dict[str, list[dict[str, Any]]]`
- `agent_results`
  - `dict[str, dict[str, Any]]`
- `shared`
  - `dict[str, Any]`

### `InterNodeMessage`

Represents one mailbox message between nodes.

Key fields:

- `sender`
- `recipient`
- `content`
- `metadata`
- `message_id`
- `created_at`

### `TurnResult`

Represents the completed result of one turn.

Key fields:

- `turn_id`
- `status`
- `started_at`
- `completed_at`
- `session_id`
- `final_output`
- `error`
- `usage`
- `events`
- `prompt`

`final_output` is the only field automatically forwarded across agent nodes.

### `AgentOutputEvent`

Normalized runtime event.

Key fields:

- `event_type`
  - `text`, `thinking`, `tool_use`, `tool_result`, `status`, `error`, or `log`
- `content`
- `call_id`
- `tool_name`
- `payload`
- `index`

### `TokenUsageSnapshot`

Token accounting for one turn.

Key fields:

- `input_tokens`
- `output_tokens`
- `cache_read_tokens`
- `cache_write_tokens`
- `context_window_tokens`

Helper methods:

- `total_tokens()`
- `usage_ratio()`
- `to_dict()`
- `from_dict(...)`

## Provider Config Reuse

Typical flow:

1. call `build_reused_agent_config(...)` to read a minimal reusable subset from provider-native config files
2. call `apply_reused_agent_config(...)` to merge those values into `AgentNodeConfig(...)` constructor kwargs
3. call `write_reused_agent_config(...)` when you want to persist a minimal agent-local snapshot under `.workflow/agent/<folder>`

### `build_reused_agent_config(...)`

Reads a minimal reusable subset from provider-native config files.

Supported reusable fields:

- `model`
- `skills`
- `mcp`
- Codex-only `base_url`
- Codex-only `auth.json`

Return value:

- `ReusedAgentConfig`

Important output fields:

- `model`
- `skills`
- `mcp`
- `auth`
- `runtime_options`
- `metadata`

For Codex, base URL reuse supports both:

- top-level `base_url`
- provider-scoped `model_provider = "..."`
  plus `[model_providers.<name>].base_url`

### `apply_reused_agent_config(...)`

Merges one `ReusedAgentConfig` into `AgentNodeConfig(...)` keyword arguments.

Behavior:

- sets `model` only when the caller did not already provide one
- exposes reused `skills` as `runtime_options["reused_skills"]`
- exposes reused `mcp` as `runtime_options["reused_mcp"]`
- exposes Codex auth as `runtime_options["reused_auth"]` only when `reuse_fields` includes `auth`
- lets explicit `runtime_options` provided by the caller win

Typical usage:

```python
config = AgentNodeConfig(
    **apply_reused_agent_config(
        reused_config=reused,
        name="reviewer",
        folder_name="codex_reviewer",
        agent_type="codex",
        executable_path="codex",
        working_directory="E:/Project/program_workflow",
    )
)
```

For Codex, you can also keep the default home configuration active and use `AgentNodeConfig` as a lightweight overlay:

```python
config = AgentNodeConfig(
    **apply_reused_agent_config(
        reused_config=reused,
        name="reviewer",
        folder_name="codex_reviewer",
        agent_type="codex",
        executable_path="codex",
        working_directory="E:/Project/program_workflow",
        runtime_options={"codex_config_mode": "lightweight"},
    )
)
```

### `write_reused_agent_config(...)`

Writes a minimal agent-local provider snapshot into a target directory.

Output locations:

- Claude and Claude SDK:
  - `.claude/settings.json`
- Codex:
  - `.codex/config.toml`
  - `.codex/auth.json`

Return value:

- `ReusedConfigSnapshot`

Important output fields:

- `written_files`
- `skipped_fields`

This function writes only the minimal reusable snapshot. It does not copy a full provider home directory.

## Related Docs

- `architecture.md`
- `integrations/provider_config_reuse.md`
- `examples/real_agent_demo.md`
- `integrations/claude_sdk.md`
- `internals/runtime_and_state.md`
