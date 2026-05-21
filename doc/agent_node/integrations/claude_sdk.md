# Claude SDK Integration

## Overview

`workflow_agents` supports two Claude backends:

- `agent_type="claude"`
  - uses the Claude CLI directly
- `agent_type="claude_sdk"`
  - uses a Python worker process that hosts the Claude SDK

Choose `claude_sdk` when the SDK is installed in a dedicated Python environment or when you prefer SDK-mediated session management over direct CLI invocation.

## Configuration

Set `AgentNodeConfig.agent_type` to `claude_sdk` and pass SDK-specific settings in `runtime_options`.

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

## Supported `runtime_options`

- `python_executable`
  - Python interpreter used to launch the SDK bridge worker
- `sdk_module`
  - SDK import name, default `claude_agent_sdk`
- `cli_path`
  - optional Claude CLI path used by the SDK
- `client_options`
  - extra keyword arguments forwarded into `ClaudeAgentOptions(...)`
- `reused_skills`
  - optional reused Claude skill selectors coming from provider config reuse
- `reused_mcp`
  - optional reused Claude MCP server mapping coming from provider config reuse

## Session Behavior

- the runtime persists `session_id` to `runtime.json`
- on the next startup, the saved `session_id` is passed back to the worker as a resume option
- downstream nodes still receive only `TurnResult.final_output`

## Process Model

The integration has two layers:

1. `ClaudeSDKRuntime`
   - the parent runtime used by `workflow_agents`
2. `claude_sdk_worker.py`
   - a separate Python worker process that imports the Claude SDK

The worker emits line-delimited JSON back to the parent runtime, which maps those messages into `AgentOutputEvent`, `TokenUsageSnapshot`, and `TurnResult`.

If provider config reuse is enabled, the parent runtime may also:

- prepare an agent-local Claude config overlay for reused skills
- materialize a local MCP config file and pass it through the worker config

## Troubleshooting

If startup fails with an import error, verify that the configured interpreter can import the SDK:

```powershell
E:\Python\envs\claude\python.exe -c "import claude_agent_sdk; print('ok')"
```

Then set that interpreter path in either:

- `AgentNodeConfig.runtime_options["python_executable"]`, or
- `AgentNodeConfig.executable_path`

## Related Docs

- `../api_reference.md`
- `provider_config_reuse.md`
- `../examples/real_agent_demo.md`
- `../internals/runtime_and_state.md`
