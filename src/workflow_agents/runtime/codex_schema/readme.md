codex app-server generated schema.

Agent-facing index files in this directory:

- `AGENT_INDEX.md`: compact navigation guide with progressive-disclosure rules.
- `agent_index.json`: machine-readable lookup index for methods, classes, files, and lines.
- `build_agent_index.py`: regeneration script for the two files above.

The index now covers both:

- generated Python models in this directory
- raw aggregate protocol schemas under `json_schema/` for server requests, server notifications, and request-response mappings that do not have standalone generated Python files

Large aggregate generated files such as `codex_app_server_protocol.schemas.py` and `codex_app_server_protocol.v2.schemas.py` are intentionally not used as preferred index targets, because they duplicate the raw protocol sources and add substantial navigation noise.

Regenerate after refreshing the schema files:

```bash
python src/workflow_agents/runtime/codex_schema/build_agent_index.py
```
