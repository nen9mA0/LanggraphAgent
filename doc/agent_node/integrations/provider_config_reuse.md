# Provider Config Reuse

## Purpose

`workflow_agents` can reuse a minimal subset of provider-native configuration instead of copying full `.claude` or `.codex` directories into each agent workspace.

Current reusable fields:

- `model`
- `skills`
- `mcp`
- Codex-only `base_url`
- Codex-only `auth.json`

Public entry points:

- `build_reused_agent_config(...)`
- `materialize_reused_agent_config(...)`
- `AgentNodeConfig.from_provider_defaults(...)`

## Resolution Model

### Read path

`AgentNodeConfig.from_provider_defaults(...)` resolves provider settings in this order:

1. `provider_config_directory`, if given
2. `working_directory`, if the preferred directory yielded no reusable values
3. user-home provider defaults through that fallback path when supported

This keeps agent-local snapshots independent while preserving project-level defaults as fallback.

### Write path

`materialize_reused_agent_config(...)` writes only a minimal local snapshot:

- Claude and Claude SDK:
  - `.claude/settings.json`
- Codex:
  - `.codex/config.toml`
  - `.codex/auth.json`

The real-agent demo uses this to prepare stable per-node folders under `.workflow/agent/`.

## Claude Backends

Applies to:

- `agent_type="claude"`
- `agent_type="claude_sdk"`

### Reused model

- reused `model` becomes `AgentNodeConfig.model`
- the runtime then passes it through the normal backend startup path

### Reused skills

- reused `skills` are exposed as `runtime_options["reused_skills"]`
- each value is treated as a skill directory selector
- the runtime resolves each selector to a directory containing `SKILL.md`
- resolved skills are copied into the agent-local `CLAUDE_CONFIG_DIR/skills/`

Accepted selector forms:

- absolute skill directory path
- absolute `SKILL.md` path
- relative path under the working directory
- relative name under `~/.claude/skills/`

### Reused MCP

- reused `mcp` is exposed as `runtime_options["reused_mcp"]`
- the runtime writes it into `reused_mcp.json` under the agent workspace
- Claude CLI uses that file as MCP startup config
- Claude SDK passes the same file path through the worker into SDK client options

Expected structure:

- a mapping of server name to server config payload

## Codex Backend

Applies to:

- `agent_type="codex"`

### Reused model

- reused `model` becomes `AgentNodeConfig.model`
- reused `base_url`, `model_provider`, and `model_reasoning_effort` are preserved in runtime options

Minimal example:

```toml
# .codex/config.toml
model = "gpt-5-codex"
base_url = "https://your-codex-gateway.example/v1"
model_provider = "openai"
model_reasoning_effort = "high"
```

```json
{
  "refresh_token": "..."
}
```

Save the JSON file as `.codex/auth.json`.

### Reused skills

- reused `skills` are exposed as `runtime_options["reused_skills"]`
- the runtime converts them into a startup override:
  - `-c skills.config=<json>`

### Reused MCP

- reused `mcp` is exposed as `runtime_options["reused_mcp"]`
- the runtime converts it into a startup override:
  - `-c mcp_servers=<json>`

### Reused model extras

When available, the runtime also emits:

- local `CODEX_HOME/config.toml` with reused `base_url`
- `-c model_provider=<json>`
- `-c model_reasoning_effort=<json>`

### Reused auth

- reused `auth.json` is exposed as `runtime_options["reused_auth"]`
- when a local provider snapshot already exists, the runtime uses that `auth.json`
- otherwise the runtime writes a minimal local `CODEX_HOME/auth.json` before startup
- this keeps per-agent Codex auth state isolated from the global home directory

## Design Constraints

- config reuse is intentionally minimal
- agent-local snapshots are reviewable and editable
- full provider home directories are not copied
- downstream graph behavior does not change:
  - only `TurnResult.final_output` is forwarded by default

## Related Docs

- `../api_reference.md`
- `../examples/real_agent_demo.md`
- `../internals/runtime_and_state.md`
