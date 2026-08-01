# Runtime Notes

This directory contains multiple runtime adapters. Keep this file high level.

## Scope

- `base.py`
  - shared runtime lifecycle and turn-state semantics
- `factory.py`
  - backend selection by `agent_type`
- backend files such as `claude.py`, `claude_sdk.py`, `codex.py`, `codex_sdk.py`
  - provider-specific runtime adapters

## Runtimes

### Codex

Start here:

1. `src/workflow_agents/runtime/codex.py`
2. `src/workflow_agents/runtime/base.py`
3. `src/workflow_agents/runtime/codex_schema/`

#### Codex Schema Workflow

Use this order:

1. Read `src/workflow_agents/runtime/codex_schema/AGENT_INDEX.md`
2. Use `src/workflow_agents/runtime/codex_schema/agent_index.json` to find:
   - `client_requests`
   - `client_request_responses`
   - `server_requests`
   - `server_notifications`
3. Open only the specific schema file and line the index points to
4. Only drop to raw protocol schemas under `codex_schema/json_schema/` when the index points there

#### Regeneration

If schema files change, regenerate the index with:

```bash
python src/workflow_agents/runtime/codex_schema/build_agent_index.py
```

#### Attension

- Keep adapter-specific details inside `codex_schema/` docs or next to the runtime code.

### Codex SDK

Start here:

1. `src/workflow_agents/runtime/codex_sdk.py`
2. `src/workflow_agents/runtime/codex_sdk_worker.py`
3. `src/workflow_agents/runtime/codex.py`

Notes:

- `codex_sdk.py` intentionally reuses the event-mapping helpers from `codex.py`
- `codex_sdk_worker.py` owns the `openai_codex` import boundary and turn stream loop

## Guidance

- Do not put Agent-specific protocol details in this file.
