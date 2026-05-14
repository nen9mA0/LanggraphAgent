# Real Agent Demo

## 目标

这个 demo 不使用 mock 数据，而是直接启动当前命令行里的真实：

- `claude`
- `codex`

并通过刚实现的 `AgentNode` 做一次：

```text
planner -> writer(claude) -> reviewer(codex)
```

## 入口

代码位置：

- `src/workflow_agents/examples/real_agent_demo.py`

## 第一步：生成 agent 配置目录

先执行：

```bash
$env:PYTHONPATH='E:\Project\program_workflow\src'
E:\Project\program_workflow\langgraph_codegen\backend\.venv\Scripts\python.exe -m workflow_agents.examples.real_agent_demo --working-directory E:\Project\program_workflow --prepare-only
```

它会创建两个目录：

- `E:\Project\program_workflow\.workflow\agent\claude_writer`
- `E:\Project\program_workflow\.workflow\agent\codex_reviewer`

## 你需要手动放入/修改的文件

### Claude agent

目录：

- `E:\Project\program_workflow\.workflow\agent\claude_writer`

文件：

- `system_prompt.txt`
  - 放 Claude writer 的系统提示词
- `cli_args.json`
  - 放一个 JSON 数组，例如 `[]`
  - 如果你想给 Claude 额外参数，就写到这里
- `env.json`
  - 放一个 JSON 对象，例如 `{}`
  - 如果你需要额外环境变量，就写到这里

### Codex agent

目录：

- `E:\Project\program_workflow\.workflow\agent\codex_reviewer`

文件：

- `system_prompt.txt`
  - 放 Codex reviewer 的系统提示词
- `cli_args.json`
  - 放一个 JSON 数组，例如 `[]`
- `env.json`
  - 放一个 JSON 对象，例如 `{}`

## 第二步：运行真实 demo

```bash
$env:PYTHONPATH='E:\Project\program_workflow\src'
E:\Project\program_workflow\langgraph_codegen\backend\.venv\Scripts\python.exe -m workflow_agents.examples.real_agent_demo --working-directory E:\Project\program_workflow --topic "请先写一段短说明，再由 reviewer 做最终润色。"
```

## 运行后会生成什么

每个 agent 目录下会自动产生：

- `config.json`
- `runtime.json`
- `history.jsonl`
- `inbox.jsonl`
- `outbox.jsonl`

## 注意

- 这个 demo 默认假设 `claude` 和 `codex` 在当前 PATH 中可直接调用
- 当前实现会复用固定目录：
  - `claude_writer`
  - `codex_reviewer`
- 所以你手动拷贝进去的配置会被实际 runtime 读取，不会再被重命名到 `_1`
