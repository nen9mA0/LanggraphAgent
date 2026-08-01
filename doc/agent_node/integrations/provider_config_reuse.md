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

- `apply_reused_agent_config(...)`
- `build_reused_agent_config(...)`
- `write_reused_agent_config(...)`

## Resolution Model

### Read path

`build_reused_agent_config(...)` reads from the `working_directory` you pass in, plus optional home defaults when `include_home_defaults=True`.

Common patterns:

1. read from `.workflow/agent/<folder>` when you want one node to follow its own local snapshot
2. read from the project root when you want to initialize a new node snapshot from project-level provider config
3. include home defaults only when you explicitly want that fallback merged in

The helper does not perform an automatic multi-directory fallback. The caller decides which directory should be inspected.

### Write path

`write_reused_agent_config(...)` writes only a minimal local snapshot:

- Claude and Claude SDK:
  - `.claude/settings.json`
- Codex:
  - `.codex/config.toml`
  - `.codex/auth.json`

The real-agent demo uses this to prepare stable per-node folders under `.workflow/agent/`.

### Apply path

`apply_reused_agent_config(...)` merges one `ReusedAgentConfig` into `AgentNodeConfig(...)` constructor kwargs.

Typical pattern:

```python
reused = build_reused_agent_config(
    agent_type="codex",
    working_directory="E:/Project/program_workflow/.workflow/agent/codex_reviewer",
    include_home_defaults=True,
    reuse_fields=("model",),
)

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
- reused `base_url`, and `model_reasoning_effort` are preserved in runtime options
- `base_url` may come from either:
  - top-level `base_url`
  - or `model_provider = "..."` plus `[model_providers.<name>].base_url`

Minimal example:

```toml
# .codex/config.toml
model = "gpt-5-codex"
base_url = "https://your-codex-gateway.example/v1"
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
- `-c model_reasoning_effort=<json>`

### Lightweight mode

If `runtime_options["codex_config_mode"] == "lightweight"`:

- the runtime does not override `CODEX_HOME`
- Codex continues using the normal home configuration
- `AgentNodeConfig` values act as per-agent overrides on top of that baseline
- this is useful when your real provider routing is defined in the default Codex home config, for example through `model_provider` and `[model_providers.<name>]`

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
