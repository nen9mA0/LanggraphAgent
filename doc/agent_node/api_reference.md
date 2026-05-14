# API Reference

本文整理 `src/workflow_agents` 的核心 API，重点说明：

- 哪些类型是公开入口
- 每个类和函数的职责
- 常用调用顺序
- runtime / node / storage / state 之间的边界

## 公开入口

来自 [src/workflow_agents/__init__.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/__init__.py:1)：

- `AgentGraphState`
- `AgentNode`
- `AgentNodeConfig`
- `AgentOutputEvent`
- `AgentRuntimeRegistry`
- `InterNodeMessage`
- `TokenUsageSnapshot`
- `TurnResult`
- `build_agent_node`

## types.py

文件：

- [src/workflow_agents/types.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/types.py:1)

### `utc_now_iso() -> str`

返回 UTC ISO 8601 时间字符串，用于事件、消息、turn 的时间戳。

### `TokenUsageSnapshot`

表示单轮 agent turn 的 token 使用情况。

字段：

- `input_tokens`
- `output_tokens`
- `cache_read_tokens`
- `cache_write_tokens`
- `context_window_tokens`

方法：

- `total_tokens() -> int`
  - 返回总 token 数
- `usage_ratio() -> float | None`
  - 基于 `context_window_tokens` 计算使用占比
- `to_dict() -> dict[str, Any]`
- `from_dict(payload) -> TokenUsageSnapshot`

### `AgentOutputEvent`

表示 agent runtime 记录的一条流式事件。

典型事件类型：

- `text`
- `thinking`
- `tool_use`
- `tool_result`
- `status`
- `error`
- `log`

方法：

- `to_dict()`
- `from_dict(payload)`

### `InterNodeMessage`

表示 node 之间通过 mailbox 传递的外部消息。

字段：

- `sender`
- `recipient`
- `content`
- `metadata`
- `message_id`
- `created_at`

方法：

- `to_dict()`
- `from_dict(payload)`

### `TurnResult`

表示 agent 一轮执行的最终结果。

字段：

- `turn_id`
- `status`
- `started_at`
- `completed_at`
- `session_id`
- `final_output`
- `error`
- `usage`
- `events`
- `prompt`

方法：

- `to_dict()`
- `from_dict(payload)`

### `AgentNodeConfig`

定义一个 agent node 的运行配置。

关键字段：

- `name`
- `agent_type`
- `working_directory`
- `executable_path`
- `system_prompt`
- `model`
- `cli_args`
- `env`
- `context_window_tokens`
- `max_turns`
- `turn_timeout_seconds`
- `startup_timeout_seconds`
- `semantic_inactivity_timeout_seconds`
- `auto_start`
- `targets`
- `prompt_prefix`
- `folder_name`
- `instance_key`

关键方法：

- `normalized_working_directory() -> Path`
- `to_persistable_dict() -> dict[str, Any]`

## storage.py

文件：

- [src/workflow_agents/storage.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/storage.py:1)

### `slugify_name(value: str) -> str`

把 node 名称转换成可落盘目录名。

### `AgentWorkspace`

代表单个 agent node 的工作目录。

典型目录结构：

```text
.workflow/agent/<folder_name>/
|- config.json
|- runtime.json
|- history.jsonl
|- inbox.jsonl
`- outbox.jsonl
```

关键属性：

- `config_path`
- `runtime_path`
- `history_path`
- `inbox_path`
- `outbox_path`

关键方法：

- `ensure()`
- `write_json(path, payload)`
- `read_json(path)`
- `append_jsonl(path, payload)`
- `persist_config(config)`
- `load_runtime_state()`
- `save_runtime_state(payload)`

### `AgentWorkspaceManager`

负责分配和复用 agent 工作目录。

关键方法：

- `prepare_workspace(node_name, preferred_name=None) -> AgentWorkspace`

行为说明：

- 如果传了 `preferred_name`
  - 直接复用固定目录名
  - 适合需要人工预放配置的场景
- 如果没有传
  - 默认按 `node_name` 创建
  - 如重名则自动追加 `_1`、`_2`

## state.py

文件：

- [src/workflow_agents/state.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/state.py:1)

### `merge_mailboxes(left, right) -> dict[...]`

用于 LangGraph state reducer。

语义：

- 不是简单追加
- 同名 mailbox 以右侧最新值覆盖

这是为了避免 node 已消费的 mailbox 在图状态合并时又被带回来。

### `merge_dicts(left, right) -> dict[...]`

普通字典 merge，右侧覆盖左侧。

### `AgentGraphState`

`TypedDict`，定义 graph 的共享状态结构。

字段：

- `mailboxes`
  - node 之间的外部消息
- `agent_results`
  - 每个 node 最近一轮执行结果摘要
- `shared`
  - graph 共享输入

## node.py

文件：

- [src/workflow_agents/node.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/node.py:1)

### `PromptBuilder`

类型别名：

```python
Callable[[AgentNodeConfig, Sequence[InterNodeMessage], Mapping[str, Any]], str]
```

用于把 mailbox 消息和 graph state 转成发给 agent 的 prompt。

### `default_prompt_builder(config, messages, state) -> str`

默认 prompt 构造器。

特性：

- 自动写入 `Node: <name>`
- 明确提示“只处理外部消息，不传播内部工具细节”
- 追加 `prompt_prefix`
- 逐条展开 inbound mailbox 消息

### `AgentNode`

LangGraph node 包装器，负责把 mailbox 输入转成 agent turn，并把最终输出继续发给下游 node。

关键字段：

- `config`
- `registry`
- `prompt_builder`

关键方法：

- `__post_init__()`
  - 未传 registry 时自动创建默认 registry
- `get_runtime()`
  - 获取或创建 runtime
- `invoke_direct(prompt) -> TurnResult`
  - 不经过 graph，直接对 agent 发一轮输入
- `__call__(state) -> AgentGraphState`
  - LangGraph 执行入口

`__call__` 的行为：

1. 读取 `mailboxes[config.name]`
2. 清空该 mailbox
3. 记录 `inbox.jsonl`
4. 构造 prompt
5. 调用 runtime 执行一轮
6. 把 `final_output` 转成 `InterNodeMessage`
7. 发到 `config.targets`
8. 记录 `outbox.jsonl`
9. 返回新的 `mailboxes` 和 `agent_results`

边界说明：

- 内部 `thinking` / `tool_use` / `tool_result` 只留在 runtime history
- 对其他 node 只转发 `final_output`

### `build_agent_node(config, registry=None, prompt_builder=...) -> AgentNode`

创建 `AgentNode` 的便捷函数。

## registry.py

文件：

- [src/workflow_agents/registry.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/registry.py:1)

### `AgentRuntimeRegistry`

负责 runtime 生命周期和 workspace 分配。

关键方法：

- `get_or_create(config)`
  - 根据 `config.instance_key` 返回已存在 runtime，或新建 runtime
- `shutdown_all()`
  - 关闭 registry 管理的所有 runtime

工作流程：

1. 调用 `workspace_manager.prepare_workspace(...)`
2. 把 `config` 持久化到 `config.json`
3. 用 `create_agent_runtime(...)` 创建具体 runtime
4. 若 `auto_start=True` 则立即启动

## runtime/base.py

文件：

- [src/workflow_agents/runtime/base.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/runtime/base.py:1)

### `_TurnContext`

内部 dataclass。

职责：

- 保存当前 turn 的 `TurnResult`
- 保存完成事件 `completion`

### `ManagedAgentRuntime`

所有具体 runtime 的抽象基类。

公开方法：

- `start()`
- `send_input(prompt) -> str`
- `wait_for_completion(timeout=None) -> TurnResult`
- `run_turn(prompt, timeout=None) -> TurnResult`
- `is_output_complete() -> bool`
- `get_output_events(after_index=0) -> list[AgentOutputEvent]`
- `get_output_text() -> str`
- `get_context_usage() -> TokenUsageSnapshot`
- `get_context_usage_ratio() -> float | None`
- `shutdown()`

关键内部方法：

- `_record_event(...)`
- `_replace_usage(...)`
- `_merge_usage(...)`
- `_set_session_id(session_id)`
- `_set_final_output(turn_id, final_output)`
- `_complete_turn(...)`

抽象方法：

- `_start_impl()`
- `_send_input_impl(prompt, turn_id)`
- `_cancel_active_turn(reason, status)`
- `_shutdown_impl()`

典型调用顺序：

1. `start()`
2. `send_input(prompt)`
3. runtime 内部异步执行
4. `wait_for_completion()`
5. 查询 `get_output_text()` / `get_output_events()` / `get_context_usage()`
6. `shutdown()`

## runtime/claude.py

文件：

- [src/workflow_agents/runtime/claude.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/runtime/claude.py:1)

### `ClaudeCodeRuntime`

基于 Claude Code CLI 的 runtime。

实现方式：

- 每轮 turn 拉起一次 `claude -p`
- 使用 `--output-format stream-json`
- 使用 `--resume <session_id>` 复用对话

关键内部方法：

- `_start_impl()`
  - 检查可执行文件
- `_build_args()`
  - 生成 Claude 命令行参数
- `_send_input_impl(prompt, turn_id)`
  - 拉起进程并启动 worker
- `_run_turn_worker(process, turn_id, prompt)`
  - 写 stdin，读 stdout，解析事件
- `_drain_stderr(process)`
  - 收集 stderr tail
- `_cancel_active_turn(reason, status)`
- `_shutdown_impl()`

## runtime/codex.py

文件：

- [src/workflow_agents/runtime/codex.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/runtime/codex.py:1)

### `CodexRuntime`

基于 Codex app-server JSON-RPC 协议的 runtime。

实现方式：

- 启动 `codex app-server --listen stdio://`
- 初始化 JSON-RPC
- 恢复或新建 thread
- 每轮 turn 调用 `turn/start`

关键内部方法：

- `_start_impl()`
  - 启动 app-server，初始化，resume 或 start thread
- `_send_input_impl(prompt, turn_id)`
  - 发起新 turn
- `_rpc_notify(method, params=None)`
- `_rpc_request(method, params, timeout)`
- `_write_rpc(payload)`
- `_reader_loop()`
- `_stderr_loop()`
- `_handle_response(payload)`
- `_handle_notification(payload)`
- `_cancel_active_turn(reason, status)`
- `_shutdown_impl()`

## runtime/factory.py

文件：

- [src/workflow_agents/runtime/factory.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/runtime/factory.py:1)

### `create_agent_runtime(config, workspace) -> ManagedAgentRuntime`

按 `config.agent_type` 分派 runtime：

- `claude` -> `ClaudeCodeRuntime`
- `codex` -> `CodexRuntime`

## 常见组合方式

### 1. 直接用 runtime

```python
registry = AgentRuntimeRegistry()
runtime = registry.get_or_create(config)
result = runtime.run_turn("draft a short summary")
print(result.final_output)
```

### 2. 作为 LangGraph node

```python
node = AgentNode(config=config, registry=registry)
updated_state = node(state)
```

### 3. 自定义 prompt builder

```python
def my_prompt_builder(config, messages, state) -> str:
    return "\\n".join(message.content for message in messages)

node = build_agent_node(config, registry=registry, prompt_builder=my_prompt_builder)
```
