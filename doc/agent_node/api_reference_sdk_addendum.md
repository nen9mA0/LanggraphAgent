# API Reference Addendum

## Scope

This addendum documents the new Claude SDK runtime support added on top of the existing agent node implementation.

It complements, rather than replaces, `api_reference.md`.

## New `AgentKind`

`src/workflow_agents/types.py`

```python
AgentKind = Literal["claude", "claude_sdk", "codex"]
```

Meaning:

- `claude`
  - use the existing Claude CLI runtime
- `claude_sdk`
  - use the new Python SDK-based Claude runtime
- `codex`
  - use the existing Codex JSON-RPC runtime

## New `AgentNodeConfig` Field

`src/workflow_agents/types.py`

### `runtime_options: dict[str, Any]`

Purpose:

- backend-specific runtime options
- avoids polluting the generic config with provider-specific fields

Persistence:

- serialized by `AgentNodeConfig.to_persistable_dict()`
- written into the workspace `config.json`

Current `claude_sdk` keys:

- `python_executable: str`
  - Python interpreter path used to launch the SDK bridge worker
  - use this when the repository shell `python` is not the one that has the Claude SDK installed
- `sdk_module: str`
  - import name of the SDK module
  - default: `claude_agent_sdk`
- `cli_path: str`
  - optional path to the underlying Claude CLI used by the SDK
- `client_options: dict[str, Any]`
  - extra keyword arguments forwarded to `ClaudeAgentOptions(...)`

## New Runtime

`src/workflow_agents/runtime/claude_sdk.py`

### `ClaudeSDKRuntime`

Role:

- concrete `ManagedAgentRuntime` implementation for Claude Python SDK usage

Process model:

1. parent runtime stays synchronous and matches the existing runtime abstraction
2. parent starts a separate Python worker process
3. worker imports the Claude SDK and opens `ClaudeSDKClient`
4. worker streams JSON lines back to the parent runtime
5. parent converts those lines into `AgentOutputEvent`, `TokenUsageSnapshot`, and `TurnResult`

Important methods:

- `_start_impl()`
  - validates the configured Python interpreter
  - launches the worker
  - waits for a `ready` event or raises a startup error
- `_send_input_impl(prompt, turn_id)`
  - sends one turn request to the worker over stdin
- `_cancel_active_turn(reason, status)`
  - sends an interrupt request to the worker
  - finalizes the current turn if needed
- `_shutdown_impl()`
  - shuts down the worker process and joins helper threads

Session behavior:

- `session_id` is persisted in `runtime.json`
- the saved session id is forwarded into the next worker launch as a resume option

## New Worker

`src/workflow_agents/runtime/claude_sdk_worker.py`

Role:

- bridge the async Claude SDK into the current synchronous runtime framework

Responsibilities:

- import `claude_agent_sdk` from the configured interpreter
- construct `ClaudeAgentOptions`
- open `ClaudeSDKClient`
- accept stdin commands:
  - `turn`
  - `interrupt`
  - `shutdown`
- emit stdout events:
  - `ready`
  - `system`
  - `assistant`
  - `user`
  - `log`
  - `result`
  - `error`

## Factory Mapping

`src/workflow_agents/runtime/factory.py`

`create_agent_runtime(config, workspace)` now resolves:

- `claude` -> `ClaudeCodeRuntime`
- `claude_sdk` -> `ClaudeSDKRuntime`
- `codex` -> `CodexRuntime`

## Example Configuration

```python
from workflow_agents import AgentNodeConfig

config = AgentNodeConfig(
    name="writer",
    agent_type="claude_sdk",
    working_directory="E:/Project/program_workflow",
    executable_path="E:/Python/envs/claude/python.exe",
    model="sonnet",
    runtime_options={
        "python_executable": "E:/Python/envs/claude/python.exe",
        "sdk_module": "claude_agent_sdk",
        "cli_path": "C:/Users/you/AppData/Roaming/npm/claude.cmd",
        "client_options": {
            "permission_mode": "bypassPermissions",
        },
    },
)
```

## Testing

Repository coverage added for:

- successful SDK runtime turn handling with a fake injected SDK module
- startup failure path when the configured SDK module is missing

Commands:

```bash
python -m unittest tests.test_workflow_agents -v
python -m unittest tests.test_runtime_cli_availability.ClaudeSDKRuntimeErrorPathTestCase -v
```
