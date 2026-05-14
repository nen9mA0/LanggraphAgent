# Quick Start

## 目标

`src/workflow_agents` 提供一套把 `claude` 和 `codex` 这类 CLI agent 封装成 LangGraph node 的最小实现。

核心约束：

- 每个 agent node 对应一个长生命周期 runtime
- node 只负责跨 node 的消息编排
- agent 内部的 tool 输出、thinking、状态事件只保存在 agent 自己的历史里，不直接传播给其他 node
- 每个 agent node 都有自己的 `.workflow/agent/<node_name>` 目录

## 目录

```text
src/workflow_agents/
|- examples/
|  `- langgraph_demo.py
|- runtime/
|  |- base.py
|  |- claude.py
|  `- codex.py
|- node.py
|- registry.py
|- state.py
|- storage.py
`- types.py
```

## 直接试跑

不依赖真实 `claude` / `codex`，可以先跑 fake CLI 示例：

```bash
python -m workflow_agents.examples.langgraph_demo --use-fake-cli
```

如果要换成真实 CLI：

```bash
python -m workflow_agents.examples.langgraph_demo ^
  --working-directory E:\\Project\\program_workflow\\.demo_workdir ^
  --claude-exec claude ^
  --codex-exec codex ^
  --topic "Write and review a short release summary."
```

运行后会输出最终 graph state，并在工作目录下生成：

```text
.workflow/
`- agent/
   |- writer/
   |  |- config.json
   |  |- runtime.json
   |  |- history.jsonl
   |  |- inbox.jsonl
   |  `- outbox.jsonl
   `- reviewer/
      ...
```

## 最小集成代码

```python
from langgraph.graph import END, START, StateGraph

from workflow_agents import AgentNode, AgentNodeConfig, AgentRuntimeRegistry, AgentGraphState

registry = AgentRuntimeRegistry()

writer = AgentNode(
    config=AgentNodeConfig(
        name="writer",
        agent_type="claude",
        executable_path="claude",
        working_directory="E:/Project/program_workflow",
        targets=("reviewer",),
    ),
    registry=registry,
)

reviewer = AgentNode(
    config=AgentNodeConfig(
        name="reviewer",
        agent_type="codex",
        executable_path="codex",
        working_directory="E:/Project/program_workflow",
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

## runtime 接口

通过 `node.get_runtime()` 可直接拿到 runtime：

```python
runtime = writer.get_runtime()
turn_id = runtime.send_input("draft a summary")
done = runtime.is_output_complete()
result = runtime.wait_for_completion()
text = runtime.get_output_text()
events = runtime.get_output_events()
usage = runtime.get_context_usage()
ratio = runtime.get_context_usage_ratio()
runtime.shutdown()
```
