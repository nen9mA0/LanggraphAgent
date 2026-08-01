# Real Agent Demo

## Purpose

`src/workflow_agents/examples/real_agent_demo.py` runs a real local workflow instead of fake CLI stubs.

Default graph:

```text
planner -> writer(claude or claude_sdk) -> reviewer(codex)
```

## Prepare Agent Folders

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
python -m workflow_agents.examples.real_agent_demo `
  --working-directory (Resolve-Path .) `
  --prepare-only
```

This creates:

- `.workflow/agent/claude_writer`
- `.workflow/agent/claude_sdk_writer`
- `.workflow/agent/codex_reviewer`

It can also write minimal provider snapshots into those folders:

- `claude_writer/.claude/settings.json`
- `claude_sdk_writer/.claude/settings.json`
- `codex_reviewer/.codex/config.toml`
- `codex_reviewer/.codex/auth.json`

Those snapshots can carry more than model selection when you opt into broader reuse fields, including reusable `skills` and `mcp` values. See `../integrations/provider_config_reuse.md`.

## Files To Edit

### `claude_writer`

- `system_prompt.txt`
  - prompt appended to the Claude CLI runtime
- `cli_args.json`
  - JSON array of extra CLI arguments
- `env.json`
  - JSON object of environment variables
- `.claude/settings.json`
  - optional local provider snapshot
  - commonly used for model selection
  - can also carry reusable `skills` and `mcp` values

### `claude_sdk_writer`

- `python_executable.txt`
  - required path to a Python interpreter that can import `claude_agent_sdk`
- `sdk_module.txt`
  - optional SDK import name, default `claude_agent_sdk`
- `cli_path.txt`
  - optional Claude CLI path used by the SDK
- `system_prompt.txt`
  - prompt passed into the SDK runtime
- `env.json`
  - worker-process environment variables
- `client_options.json`
  - JSON object forwarded into `ClaudeAgentOptions(...)`
- `.claude/settings.json`
  - optional local provider snapshot
  - can also carry reusable `skills` and `mcp` values

### `codex_reviewer`

- `system_prompt.txt`
  - reviewer instructions
- `cli_args.json`
  - JSON array of extra Codex CLI arguments
- `env.json`
  - JSON object of environment variables
- `.codex/config.toml`
  - optional local provider snapshot
  - can carry `model`, `base_url`, `model_reasoning_effort`
  - `base_url` may be either top-level or provider-scoped through `model_provider` and `[model_providers.<name>]`
  - can also carry reusable `skills` and `mcp` values
- `.codex/auth.json`
  - optional local auth snapshot
  - used when this reviewer node should run with isolated Codex auth state

## Run The Demo

Claude CLI writer:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
python -m workflow_agents.examples.real_agent_demo `
  --working-directory (Resolve-Path .) `
  --topic "Write a concise explanation, then hand it to the reviewer for final polish."
```

Claude SDK writer:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
python -m workflow_agents.examples.real_agent_demo `
  --working-directory (Resolve-Path .) `
  --claude-backend claude_sdk `
  --topic "Write a concise explanation, then hand it to the reviewer for final polish."
```

## Config Resolution Order

The demo constructs configs with the standalone reuse helpers:

1. `build_reused_agent_config(...)`
2. `apply_reused_agent_config(...)`

For each node, the demo currently reads reusable provider settings from that node's folder under `.workflow/agent/<folder>`, and it enables home-default fallback where the example code asks for it.

This keeps config reuse explicit: the caller chooses which directory to inspect, and the merged result is then passed into `AgentNodeConfig(...)`.

For Codex, there are two runtime styles:

- `isolated`
  - the runtime prepares an agent-local `CODEX_HOME`
  - local `.codex/config.toml` and `.codex/auth.json` snapshots become the effective provider config
- `lightweight`
  - the runtime keeps the normal Codex home configuration active
  - `AgentNodeConfig` and reuse-derived values become per-agent overrides on top of the system config

The simple `agent_example.py` uses `lightweight` by default so provider routing defined in the normal Codex home config continues to work.

## Generated Runtime Files

During execution, each agent folder may contain:

- `config.json`
- `runtime.json`
- `inbox.jsonl`
- `outbox.jsonl`
- `history.jsonl`
  - written only when `persist_runtime_history=True`

## Notes

- the demo intentionally reuses fixed folder names instead of auto-suffixed folders
- mailbox persistence is enabled by default
- runtime history persistence is disabled by default
