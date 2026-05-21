# Quick Start

## Goal

`workflow_agents` lets you run long-lived agent backends either:

- behind LangGraph nodes with mailbox-style message passing, or
- directly as reusable runtimes

The core boundary is simple: downstream nodes receive only `TurnResult.final_output` unless you deliberately build something more detailed on top.

## Package Layout

```text
src/workflow_agents/
|- AGENT_GUIDE.md
|- config_reuse.py
|- examples/
|- runtime/
|- node.py
|- registry.py
|- state.py
|- storage.py
|- types.py
`- __init__.py
```

## Fastest Trial

Run the fake CLI demo first if you only want to verify the graph wiring:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
python -m workflow_agents.examples.langgraph_demo --use-fake-cli
```

Prepare the real local demo folders:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
python -m workflow_agents.examples.real_agent_demo `
  --working-directory (Resolve-Path .) `
  --prepare-only
```

This creates the reusable agent folders under `.workflow/agent/`. Fill in the generated configuration files, then run:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src)
python -m workflow_agents.examples.real_agent_demo `
  --working-directory (Resolve-Path .) `
  --topic "Write and review a short explanation of long-lived agent nodes."
```

For the full folder layout and editable files, see `examples/real_agent_demo.md`.

If you want a node to reuse provider-native defaults without copying full provider directories, see `integrations/provider_config_reuse.md`.

## Minimal LangGraph Integration

```python
from langgraph.graph import END, START, StateGraph

from workflow_agents import AgentGraphState, AgentNode, AgentNodeConfig, AgentRuntimeRegistry

registry = AgentRuntimeRegistry()

writer = AgentNode(
    config=AgentNodeConfig.from_provider_defaults(
        name="writer",
        folder_name="claude_writer",
        agent_type="claude",
        executable_path="claude",
        working_directory="E:/Project/program_workflow",
        provider_config_directory="E:/Project/program_workflow/.workflow/agent/claude_writer",
        targets=("reviewer",),
    ),
    registry=registry,
)

reviewer = AgentNode(
    config=AgentNodeConfig.from_provider_defaults(
        name="reviewer",
        folder_name="codex_reviewer",
        agent_type="codex",
        executable_path="codex",
        working_directory="E:/Project/program_workflow",
        provider_config_directory="E:/Project/program_workflow/.workflow/agent/codex_reviewer",
    ),
    registry=registry,
)

graph = StateGraph(AgentGraphState)
graph.add_node("writer", writer)
graph.add_node("reviewer", reviewer)
graph.add_edge(START, "writer")
graph.add_edge("writer", "reviewer")
graph.add_edge("reviewer", END)
app = graph.compile()
```

## Direct Runtime Usage

If you do not need LangGraph orchestration, call the runtime through a node or registry:

```python
runtime = writer.get_runtime()
result = runtime.run_turn("Draft a short summary.")
print(result.status)
print(result.final_output)
runtime.shutdown()
```

## Next Docs

- `architecture.md`
- `api_reference.md`
- `examples/real_agent_demo.md`
