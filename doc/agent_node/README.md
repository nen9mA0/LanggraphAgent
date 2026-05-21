# Agent Node Docs

This directory documents `src/workflow_agents`, which wraps long-lived `claude`, `claude_sdk`, and `codex` backends as reusable runtimes and optional LangGraph nodes.

## Recommended Reading Order

1. `quickstart.md`
2. `architecture.md`
3. `api_reference.md`
4. `integrations/provider_config_reuse.md`
5. `examples/real_agent_demo.md`
6. `integrations/claude_sdk.md`
7. `internals/runtime_and_state.md`

For the shortest code-oriented orientation, read `src/workflow_agents/AGENT_GUIDE.md` first.

If you are updating these docs rather than consuming them, read `DOC_MAINTENANCE_GUIDE.md` first.

## Directory Layout

### Top-level docs

- `quickstart.md`
  - quickest path to a running graph or direct runtime call
- `architecture.md`
  - public architecture overview and design rules
- `api_reference.md`
  - public API only
- `DOC_MAINTENANCE_GUIDE.md`
  - agent-facing documentation maintenance rules and workflow

### Supporting docs

- `examples/`
  - runnable example walkthroughs
- `integrations/`
  - backend-specific integration notes
  - provider config reuse behavior by backend
- `internals/`
  - implementation details and internal contracts

## Key Constraints

- each runtime handles at most one active turn at a time
- `AgentNode` forwards only `TurnResult.final_output` to downstream nodes by default
- runtime history persistence is optional
- `session_id` is the backend-native resumable identifier:
  - Claude CLI session id
  - Claude SDK resume/session id
  - Codex thread id
- provider config reuse stays intentionally minimal:
  - Claude snapshots are written to `.claude/settings.json`
  - Codex snapshots are written to `.codex/config.toml`
