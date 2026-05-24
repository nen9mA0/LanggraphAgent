codex app-server generated schema.

Agent-facing index files in this directory:

- `AGENT_INDEX.md`: compact navigation guide with progressive-disclosure rules.
- `agent_index.json`: machine-readable lookup index for methods, classes, files, and lines.
- `build_agent_index.py`: regeneration script for the two files above.

Regenerate after refreshing the schema files:

```bash
python src/workflow_agents/runtime/codex_schema/build_agent_index.py
```
