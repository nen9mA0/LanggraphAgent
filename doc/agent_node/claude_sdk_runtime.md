# Claude SDK Runtime

## Overview

`workflow_agents` now supports two Claude backends:

- `agent_type="claude"`
  - uses the `claude` CLI directly
  - current implementation keeps a long-lived `claude -p --input-format stream-json --output-format stream-json` process alive
- `agent_type="claude_sdk"`
  - uses a Python interpreter that has the Claude Python SDK installed
  - the runtime starts a local Python bridge worker, and the worker talks to `ClaudeSDKClient`

The original CLI runtime is kept unchanged in purpose and is still available.

## When To Use

Choose `claude_sdk` when:

- your Claude SDK is installed in a dedicated Python environment
- you want to manage Claude from Python instead of shelling directly to `claude`
- you want a long-lived session without building your own async SDK bridge

Choose `claude` when:

- `claude` is already available on `PATH`
- you want the smallest dependency surface
- you prefer to inspect and replay the exact CLI invocation

## Configuration

Use `AgentNodeConfig.agent_type="claude_sdk"` and configure SDK-specific options through `runtime_options`.

Example:

```python
from workflow_agents import AgentNodeConfig

config = AgentNodeConfig(
    name="writer",
    agent_type="claude_sdk",
    working_directory="E:/Project/program_workflow",
    executable_path="E:/Python/envs/claude/python.exe",
    system_prompt="You are the writer node.",
    model="sonnet",
    context_window_tokens=200_000,
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

## Key Fields

### `AgentNodeConfig.agent_type`

Supported values now include:

- `"claude"`
- `"claude_sdk"`
- `"codex"`

### `AgentNodeConfig.runtime_options`

This is a backend-specific extension dictionary.

For `claude_sdk`, the supported keys are:

- `python_executable: str`
  - Python interpreter used to launch the SDK bridge worker
  - this interpreter must be able to import the Claude SDK
- `sdk_module: str`
  - SDK import name
  - default is `claude_agent_sdk`
- `cli_path: str`
  - optional path to the underlying `claude` CLI used by the SDK
- `client_options: dict[str, Any]`
  - extra keyword arguments forwarded into `ClaudeAgentOptions(...)`

## Important Behavior

- `claude_sdk` is still managed as a long-lived runtime.
- The runtime persists `session_id` into `runtime.json`.
- On the next startup, the saved `session_id` is forwarded back into the SDK client options as `resume`.
- Only `TurnResult.final_output` is forwarded to downstream agent nodes.
- Internal streaming events are still written into `history.jsonl`.

## Process Model

The runtime has two layers:

1. `ClaudeSDKRuntime`
   - synchronous runtime used by the current `ManagedAgentRuntime` abstraction
2. `claude_sdk_worker.py`
   - separate Python worker process
   - imports `claude_agent_sdk`
   - opens `ClaudeSDKClient`
   - converts async SDK events into line-delimited JSON for the parent runtime

This design avoids forcing the main runtime abstraction to become async.

## Installation Notes

The shell `python` used in this repository may be different from the Python where you installed the Claude SDK.

If runtime startup fails with an import error:

1. find the Python interpreter that can import `claude_agent_sdk`
2. put that interpreter path into:
   - `AgentNodeConfig.executable_path`, or
   - `AgentNodeConfig.runtime_options["python_executable"]`

Quick check:

```bash
E:\Python\envs\claude\python.exe -c "import claude_agent_sdk; print('ok')"
```

## Minimal Direct Test

```python
from workflow_agents import AgentNodeConfig, AgentRuntimeRegistry

registry = AgentRuntimeRegistry()
runtime = registry.get_or_create(
    AgentNodeConfig(
        name="writer",
        agent_type="claude_sdk",
        working_directory="E:/Project/program_workflow",
        executable_path="E:/Python/envs/claude/python.exe",
        runtime_options={"python_executable": "E:/Python/envs/claude/python.exe"},
    )
)

result = runtime.run_turn("Write one short paragraph about agent runtimes.")
print(result.status)
print(result.final_output)
print(result.session_id)
```

## Tests

Current repository tests cover:

- SDK runtime happy path with an injected fake SDK module
- startup failure path when the configured SDK module cannot be imported
- optional real SDK smoke test with your local Python interpreter and Claude CLI

Run:

```bash
python -m unittest tests.test_workflow_agents -v
python -m unittest tests.test_runtime_cli_availability.ClaudeSDKRuntimeErrorPathTestCase -v
```

Run the real SDK smoke test only when your local environment is ready:

```bash
$env:WORKFLOW_AGENTS_RUN_REAL_CLAUDE_SDK_TESTS='1'
$env:WORKFLOW_AGENTS_CLAUDE_SDK_PYTHON='E:\Python\envs\claude\python.exe'
$env:WORKFLOW_AGENTS_CLAUDE_CLI_PATH='C:\Users\you\AppData\Roaming\npm\claude.cmd'
python -m unittest tests.test_runtime_cli_availability.ClaudeSDKRuntimeIntegrationTestCase -v
```

Optional:

```bash
$env:WORKFLOW_AGENTS_CLAUDE_SDK_MODULE='claude_agent_sdk'
```
