# Real Agent Demo

## 目标

这个 demo 不使用 mock 数据，而是直接启动当前命令行里的真实：

- `claude`
- 或者通过 Claude Python SDK 驱动的 `claude`
- `codex`

并通过刚实现的 `AgentNode` 做一次：

默认链路：

```text
planner -> writer(claude) -> reviewer(codex)
```

也支持：

```text
planner -> writer(claude_sdk) -> reviewer(codex)
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

它会创建三个目录：

- `E:\Project\program_workflow\.workflow\agent\claude_writer`
- `E:\Project\program_workflow\.workflow\agent\claude_sdk_writer`
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

### Claude SDK agent

目录：

- `E:\Project\program_workflow\.workflow\agent\claude_sdk_writer`

文件：

- `python_executable.txt`
  - 必填
  - 放“安装了 Claude SDK 的 Python 解释器绝对路径”
  - 例如：
    - `E:\Python\envs\claude\python.exe`
- `sdk_module.txt`
  - 可选
  - 默认 `claude_agent_sdk`
- `cli_path.txt`
  - 可选
  - 如果 SDK 需要显式指定底层 `claude` 命令路径，就写这里
- `system_prompt.txt`
  - 放 Claude writer 的系统提示词
- `env.json`
  - 放 worker 进程需要的环境变量
- `client_options.json`
  - 放一个 JSON 对象
  - 这些字段会透传给 `ClaudeAgentOptions(...)`

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

使用 Claude CLI backend：

```bash
$env:PYTHONPATH='E:\Project\program_workflow\src'
E:\Project\program_workflow\langgraph_codegen\backend\.venv\Scripts\python.exe -m workflow_agents.examples.real_agent_demo --working-directory E:\Project\program_workflow --topic "请先写一段短说明，再由 reviewer 做最终润色。"
```

使用 Claude SDK backend：

```bash
$env:PYTHONPATH='E:\Project\program_workflow\src'
E:\Project\program_workflow\langgraph_codegen\backend\.venv\Scripts\python.exe -m workflow_agents.examples.real_agent_demo --working-directory E:\Project\program_workflow --claude-backend claude_sdk --topic "请先写一段短说明，再由 reviewer 做最终润色。"
```

## 运行后会生成什么

每个 agent 目录下会自动产生：

- `config.json`
- `runtime.json`
- `history.jsonl`
- `inbox.jsonl`
- `outbox.jsonl`

## 注意

- `--claude-backend claude` 时，默认假设 `claude` 和 `codex` 在当前 PATH 中可直接调用
- `--claude-backend claude_sdk` 时：
  - `codex` 仍需可直接调用
  - `claude_sdk_writer/python_executable.txt` 必须填写正确
- 当前实现会复用固定目录：
  - `claude_writer`
  - `claude_sdk_writer`
  - `codex_reviewer`
- 所以你手动拷贝进去的配置会被实际 runtime 读取，不会再被重命名到 `_1`

## 可选：验证本机 Claude SDK runtime

如果你已经准备好了 Claude SDK 对应的 Python 解释器，还可以跑仓库里的真实 smoke test：

```bash
$env:WORKFLOW_AGENTS_RUN_REAL_CLAUDE_SDK_TESTS='1'
$env:WORKFLOW_AGENTS_CLAUDE_SDK_PYTHON='E:\Python\envs\claude\python.exe'
$env:WORKFLOW_AGENTS_CLAUDE_CLI_PATH='C:\Users\you\AppData\Roaming\npm\claude.cmd'
python -m unittest tests.test_runtime_cli_availability.ClaudeSDKRuntimeIntegrationTestCase -v
```

可选变量：

```bash
$env:WORKFLOW_AGENTS_CLAUDE_SDK_MODULE='claude_agent_sdk'
```
