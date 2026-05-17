# API Reference

本文是 `src/workflow_agents` 的详细 API 参考，重点补全：

- 关键字段含义
- 方法参数与返回值
- 副作用与持久化位置
- 运行时约束与常见异常

适用范围：

- `src/workflow_agents` 下的非示例实现
- 不覆盖 `examples/` 中的 demo 入口

## 模块概览

公开入口来自 [src/workflow_agents/__init__.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/__init__.py:1)：

- `AgentGraphState`
- `AgentNode`
- `AgentNodeConfig`
- `AgentOutputEvent`
- `AgentRuntimeRegistry`
- `InterNodeMessage`
- `TokenUsageSnapshot`
- `TurnResult`
- `build_agent_node`

推荐理解顺序：

1. `types.py`
2. `storage.py`
3. `runtime/base.py`
4. `runtime/claude.py` / `runtime/codex.py`
5. `registry.py`
6. `state.py`
7. `node.py`

---

## types.py

文件：

- [src/workflow_agents/types.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/types.py:1)

### 类型别名

#### `AgentKind`

```python
Literal["claude", "codex"]
```

含义：

- 指定当前 node 使用哪种 agent backend
- 当前仅支持 `claude` 和 `codex`

#### `TurnStatus`

```python
Literal["running", "completed", "failed", "aborted", "timeout"]
```

含义：

- `running`
  - turn 已开始但未完成
- `completed`
  - turn 成功完成
- `failed`
  - turn 执行失败，通常伴随 `error`
- `aborted`
  - turn 被主动中断或 runtime 关闭
- `timeout`
  - turn 超时

#### `EventType`

```python
Literal["text", "thinking", "tool_use", "tool_result", "status", "error", "log"]
```

含义：

- `text`
  - agent 的文本输出片段
- `thinking`
  - agent 的思考内容
- `tool_use`
  - agent 开始调用工具
- `tool_result`
  - 工具调用结果
- `status`
  - 运行状态事件
- `error`
  - 错误事件
- `log`
  - 普通日志事件

### `utc_now_iso() -> str`

用途：

- 生成统一的 UTC ISO 8601 时间戳

返回值：

- 例如 `2026-05-15T03:12:45.123456+00:00`

使用位置：

- `AgentOutputEvent.created_at`
- `InterNodeMessage.created_at`
- `TurnResult.started_at`

### `TokenUsageSnapshot`

用途：

- 表示一次 turn 的 token 使用统计

字段说明：

- `input_tokens: int`
  - 本轮输入 token 数
- `output_tokens: int`
  - 本轮输出 token 数
- `cache_read_tokens: int`
  - 来自缓存读取的 token 数
- `cache_write_tokens: int`
  - 写入缓存的 token 数
- `context_window_tokens: int | None`
  - 模型上下文窗口大小
  - 为 `None` 时无法计算使用比例

方法说明：

#### `total_tokens() -> int`

返回值：

- `input + output + cache_read + cache_write`

注意：

- 这是本实现定义的总量统计，不区分不同供应商对 cache token 的计费口径

#### `usage_ratio() -> float | None`

返回值：

- 如果设置了有效 `context_window_tokens`
  - 返回 `total_tokens / context_window_tokens`
- 否则返回 `None`

使用场景：

- UI 显示上下文压力
- 编排层做上下文水位判断

#### `to_dict() -> dict[str, Any]`

返回字段：

- `input_tokens`
- `output_tokens`
- `cache_read_tokens`
- `cache_write_tokens`
- `context_window_tokens`
- `total_tokens`
- `usage_ratio`

#### `from_dict(payload) -> TokenUsageSnapshot`

参数：

- `payload`
  - 可为空
  - 缺省字段按 `0` 或 `None` 处理

### `AgentOutputEvent`

用途：

- 表示 runtime 记录的一条流式事件

字段说明：

- `event_type: EventType`
  - 事件类型
- `content: str`
  - 文本内容
  - `tool_use` 时通常为空
- `created_at: str`
  - UTC ISO 时间戳
- `call_id: str`
  - 工具调用 ID
- `tool_name: str`
  - 工具名
- `payload: dict[str, Any]`
  - 额外原始结构
  - 常见于工具输入参数
- `index: int`
  - 在当前 turn 中的顺序号

方法说明：

#### `to_dict()`

返回值：

- 与字段同构的普通字典

#### `from_dict(payload)`

参数：

- `payload`
  - 需包含 `event_type`

### `InterNodeMessage`

用途：

- 表示 node 间的 mailbox 消息

字段说明：

- `sender: str`
  - 上游 node 名称
- `recipient: str`
  - 目标 node 名称
- `content: str`
  - 发送给下游 node 的正文
- `metadata: dict[str, Any]`
  - 透传元信息
  - 典型值包括 `turn_id`、`session_id`、`status`
- `message_id: str`
  - 消息唯一标识
- `created_at: str`
  - UTC ISO 时间戳

约束：

- `content` 是跨 node 共享的上下文正文
- agent 内部 `thinking` / tool 明细不应直接塞进 `content`

### `TurnResult`

用途：

- 表示一轮 agent turn 的最终快照

字段说明：

- `turn_id: str`
  - 本轮唯一 ID
- `status: TurnStatus`
  - 本轮状态
- `started_at: str`
  - 开始时间
- `completed_at: str | None`
  - 完成时间，运行中时可能为空
- `session_id: str`
  - Claude session ID 或 Codex thread ID
- `final_output: str`
  - 当前实现向外传播的最终文本
- `error: str`
  - 失败或超时时的错误信息
- `usage: TokenUsageSnapshot`
  - token 使用统计
- `events: list[AgentOutputEvent]`
  - 该 turn 的流式事件快照
- `prompt: str`
  - 实际发送给 agent 的 prompt

关键语义：

- `final_output` 是给外部系统消费的最终结果
- `events` 是内部细粒度事件，不直接参与 node 间传播

### `AgentNodeConfig`

用途：

- 定义一个 agent node 的运行配置

字段说明：

#### 身份与后端

- `name: str`
  - node 逻辑名称
  - 用作 mailbox key
- `agent_type: AgentKind`
  - 运行时后端类型
- `instance_key: str`
  - runtime registry 的实例键
  - 相同 `instance_key` 会复用同一个 runtime

#### 目录与执行

- `working_directory: str`
  - agent 实际工作目录
  - CLI 在该目录下运行
- `folder_name: str | None`
  - agent workspace 目录名
  - 如果设置，会固定使用该目录
  - 适合你手工预放配置
- `executable_path: str | None`
  - CLI 可执行文件路径
  - 为空时使用默认命令名：`claude` 或 `codex`

#### Prompt / 模型

- `system_prompt: str`
  - 附加给 agent 的系统提示
- `prompt_prefix: str`
  - 由 `default_prompt_builder` 拼到 mailbox 内容前
- `model: str`
  - 指定模型名
  - Claude / Codex 的具体支持由各自 CLI 决定

#### CLI 扩展

- `cli_args: tuple[str, ...]`
  - 追加到命令行的参数
- `env: dict[str, str]`
  - 额外环境变量

#### 限制与超时

- `context_window_tokens: int | None`
  - 上下文窗口大小
- `max_turns: int | None`
  - 传给 Claude 的 `--max-turns`
  - 当前 Codex runtime 未使用
- `turn_timeout_seconds: float`
  - 等待 turn 完成的默认超时
- `startup_timeout_seconds: float`
  - 进程启动或握手请求的超时
- `semantic_inactivity_timeout_seconds: float`
  - 当前字段已保留，但当前 Python 版 runtime 尚未实际使用

#### 生命周期与路由

- `auto_start: bool`
  - `True` 时首次使用自动启动 runtime
  - `False` 时需手动调 `runtime.start()`
- `targets: tuple[str, ...]`
  - 当前 node 完成后要转发到的下游 node 名称列表

方法说明：

#### `normalized_working_directory() -> Path`

返回值：

- 绝对路径形式的 `working_directory`

#### `to_persistable_dict() -> dict[str, Any]`

用途：

- 写入 `config.json`

返回字段：

- 所有关键配置字段
- `cli_args` / `targets` 会转为 list

---

## storage.py

文件：

- [src/workflow_agents/storage.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/storage.py:1)

### `slugify_name(value: str) -> str`

用途：

- 把 node 名称转换为目录安全名称

处理规则：

- 非字母数字下划线字符替换为 `_`
- 连续 `_` 压缩
- 去掉首尾 `_`
- 空结果时回退为 `"agent"`

示例：

- `"writer"` -> `"writer"`
- `"My Writer"` -> `"My_Writer"`
- `"writer/reviewer"` -> `"writer_reviewer"`

### `AgentWorkspace`

用途：

- 表示单个 agent node 的持久化工作目录

目录结构：

```text
.workflow/agent/<folder_name>/
|- config.json
|- runtime.json
|- history.jsonl
|- inbox.jsonl
`- outbox.jsonl
```

字段说明：

- `node_name: str`
  - 逻辑 node 名称
- `folder_name: str`
  - 实际目录名
- `root: Path`
  - 目录根路径

属性说明：

#### `config_path`

- 配置持久化文件
- 来自 `AgentNodeConfig.to_persistable_dict()`

#### `runtime_path`

- runtime 元数据文件
- 当前主要保存 `session_id`

#### `history_path`

- turn 历史与流式事件日志

典型记录：

- `{"kind": "turn_started", ...}`
- `{"kind": "event", ...}`
- `{"kind": "turn_completed", ...}`

#### `inbox_path`

- 记录该 node 消费的 mailbox 输入

#### `outbox_path`

- 记录该 node 发给下游的 mailbox 输出

方法说明：

#### `ensure() -> None`

副作用：

- 若目录不存在则创建

#### `write_json(path, payload) -> None`

参数：

- `path: Path`
- `payload: dict[str, Any]`

副作用：

- 以 UTF-8 和两空格缩进写入 JSON

#### `read_json(path) -> dict[str, Any]`

返回值：

- 文件存在时返回解析后的对象
- 文件不存在时返回空字典

#### `append_jsonl(path, payload) -> None`

副作用：

- 在目标文件末尾追加一行 JSON

#### `persist_config(config) -> None`

用途：

- 把 `AgentNodeConfig` 写到 `config.json`

#### `load_runtime_state() -> dict[str, Any]`

用途：

- 读取 `runtime.json`

#### `save_runtime_state(payload) -> None`

用途：

- 覆盖写入 `runtime.json`

### `AgentWorkspaceManager`

用途：

- 管理 workspace 目录分配

字段说明：

- `base_directory`
  - 默认是 `<cwd>/.workflow/agent`
- `_allocated`
  - 当前进程内已分配目录集合
  - 防止同一进程重复分配

方法说明：

#### `__init__(base_directory=None)`

参数：

- `base_directory: str | Path | None`
  - 空时使用默认 `.workflow/agent`

副作用：

- 确保 base 目录存在

#### `prepare_workspace(node_name, preferred_name=None) -> AgentWorkspace`

参数：

- `node_name: str`
  - 逻辑 node 名称
- `preferred_name: str | None`
  - 指定目录名

返回值：

- `AgentWorkspace`

行为：

- 如果设置了 `preferred_name`
  - 直接使用该目录名
  - 即使目录已存在，也会复用
- 如果未设置
  - 优先尝试 `<slug>`
  - 冲突时递增生成 `<slug>_1`、`<slug>_2`

适用场景：

- 固定目录复用：人工预放配置
- 自动编号目录：临时节点或测试场景

---

## state.py

文件：

- [src/workflow_agents/state.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/state.py:1)

### `merge_mailboxes(left, right)`

用途：

- LangGraph reducer，用于合并 `mailboxes`

参数：

- `left`
  - 旧状态
- `right`
  - 新状态

返回值：

- 合并后的 mailbox 字典

语义：

- 右侧同名 key 覆盖左侧
- 不做简单 list 追加

为什么这样设计：

- node 在消费 mailbox 后会把自己的 mailbox 置空
- 如果 reducer 采用追加，旧消息会被错误带回

### `merge_dicts(left, right)`

用途：

- LangGraph reducer，用于普通 dict merge

语义：

- `right` 覆盖 `left`

### `AgentGraphState`

用途：

- 整个 graph 的共享状态定义

字段说明：

#### `mailboxes: dict[str, list[dict[str, Any]]]`

含义：

- key 是 node 名称
- value 是待该 node 消费的消息列表

约束：

- 这里只放跨 node 外部消息
- 不直接放 agent 内部 tool 细节

#### `agent_results: dict[str, dict[str, Any]]`

含义：

- 保存每个 node 最近一轮执行的结果摘要

典型字段：

- `status`
- `session_id`
- `final_output`
- `error`
- `usage`
- `workspace`
- `consumed_messages`
- `forwarded_messages`

#### `shared: dict[str, Any]`

含义：

- graph 全局共享输入
- 例如任务主题、外部上下文、用户输入

---

## node.py

文件：

- [src/workflow_agents/node.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/node.py:1)

### `PromptBuilder`

定义：

```python
Callable[[AgentNodeConfig, Sequence[InterNodeMessage], Mapping[str, Any]], str]
```

参数说明：

- `AgentNodeConfig`
  - 当前 node 配置
- `Sequence[InterNodeMessage]`
  - 当前 node 收到的 mailbox 消息
- `Mapping[str, Any]`
  - 整个 graph 当前状态

返回值：

- 最终发给 agent 的 prompt 字符串

### `default_prompt_builder(config, messages, state) -> str`

参数：

- `config`
  - 当前 node 配置
- `messages`
  - 当前 node 的 inbound mailbox 消息
- `state`
  - graph 状态

返回值：

- 一个拼接后的 prompt

构造规则：

1. 写入 `Node: <config.name>`
2. 明确提示只处理外部消息
3. 若 `config.prompt_prefix` 非空则追加
4. 若无消息则写入 `No inbound messages.`
5. 否则逐条展开消息

### `AgentNode`

用途：

- 把 agent runtime 封装成 LangGraph node

字段说明：

- `config: AgentNodeConfig`
  - node 配置
- `registry: AgentRuntimeRegistry | None`
  - runtime 注册表
  - 为空时自动创建
- `prompt_builder: PromptBuilder`
  - prompt 生成器

方法说明：

#### `__post_init__()`

行为：

- 如果调用方未传 `registry`
  - 自动创建一个新的 `AgentRuntimeRegistry`

#### `get_runtime()`

返回值：

- 当前 node 对应的 runtime 实例

副作用：

- 若 runtime 不存在则会新建
- 可能触发 workspace 持久化
- 若 `auto_start=True` 可能触发启动

#### `invoke_direct(prompt) -> TurnResult`

用途：

- 绕过 LangGraph，直接跑一轮 agent

参数：

- `prompt: str`

返回值：

- `TurnResult`

适用场景：

- 独立调试
- 单轮调用测试

#### `__call__(state) -> AgentGraphState`

用途：

- LangGraph 执行入口

参数：

- `state: AgentGraphState`

返回值：

- 一个只包含“本节点本轮更新”的状态片段

内部流程：

1. 复制 `state["mailboxes"]`
2. 读取 `mailboxes[self.config.name]`
3. 将当前 node 的 mailbox 置为空列表
4. 若没有消息，返回：
   - `{"agent_results": {name: {"status": "idle", "skipped": True}}}`
5. 将 inbound 消息写入 `inbox.jsonl`
6. 用 `prompt_builder(...)` 构造 prompt
7. 执行 `runtime.run_turn(...)`
8. 将 `result.final_output` 转成多个 `InterNodeMessage`
9. 写入下游 mailbox
10. 若有 outbound，则追加到 `outbox.jsonl`
11. 返回：
   - 更新后的 `mailboxes`
   - 当前 node 的 `agent_results`

返回结果中的 `agent_results[config.name]` 字段：

- `status`
- `session_id`
- `final_output`
- `error`
- `usage`
- `workspace`
- `consumed_messages`
- `forwarded_messages`

重要边界：

- 传播给下游的只有 `final_output`
- 内部事件不会自动进入下游上下文

### `build_agent_node(config, registry=None, prompt_builder=...) -> AgentNode`

用途：

- 便捷构造 `AgentNode`

参数：

- `config: AgentNodeConfig`
- `registry: AgentRuntimeRegistry | None`
- `prompt_builder: PromptBuilder`

返回值：

- `AgentNode`

---

## registry.py

文件：

- [src/workflow_agents/registry.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/registry.py:1)

### `AgentRuntimeRegistry`

用途：

- 管理 runtime 生命周期
- 管理 workspace 分配

字段说明：

- `workspace_manager`
  - `AgentWorkspaceManager` 实例
- `_runtimes`
  - `instance_key -> runtime` 映射

方法说明：

#### `__init__(base_directory=None)`

参数：

- `base_directory: str | Path | None`
  - workspace 根目录

#### `get_or_create(config)`

参数：

- `config: AgentNodeConfig`

返回值：

- 具体 runtime 实例

流程：

1. 按 `config.instance_key` 查缓存
2. 不存在时分配 workspace
3. 持久化 `config.json`
4. 调用 `create_agent_runtime(...)`
5. 若 `config.auto_start=True`
   - 调用 `runtime.start()`
6. 缓存 runtime 并返回

异常：

- runtime 启动失败时会向外抛出异常

#### `shutdown_all() -> None`

行为：

- 关闭 registry 中所有 runtime
- 清空内部缓存

---

## runtime/base.py

文件：

- [src/workflow_agents/runtime/base.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/runtime/base.py:1)

### `_TurnContext`

用途：

- 仅供内部使用的活动 turn 上下文

字段说明：

- `result: TurnResult`
  - 当前 turn 的可变结果对象
- `completion: threading.Event`
  - 用于等待 turn 完成

### `ManagedAgentRuntime`

用途：

- 所有具体 runtime 的抽象基类

职责：

- 管理 turn 生命周期
- 提供统一查询接口
- 负责 session/thread 持久化
- 负责事件记录与结果封口

构造参数：

- `config: AgentNodeConfig`
- `workspace: AgentWorkspace`

重要内部状态：

- `_current_turn`
  - 当前正在执行的 turn
- `_last_turn`
  - 最近一次完成的 turn
- `_started`
  - runtime 是否已经启动
- `_closed`
  - runtime 是否已经关闭
- `_session_id`
  - 当前可复用的会话标识

公开属性：

#### `session_id`

返回值：

- 当前 session/thread ID

说明：

- Claude 下通常是 session ID
- Codex 下通常是 thread ID

公开方法说明：

#### `start() -> None`

用途：

- 启动底层 runtime

行为：

- 已启动则直接返回
- 已关闭则抛 `RuntimeError`

异常：

- `_start_impl()` 的异常会直接抛出

#### `send_input(prompt) -> str`

用途：

- 新开一轮 turn

参数：

- `prompt: str`

返回值：

- 新建 turn 的 `turn_id`

副作用：

- 若 `auto_start=True` 会先启动 runtime
- 写入 `history.jsonl` 的 `turn_started`
- 调用后端 `_send_input_impl(...)`

约束：

- 若已有未完成 turn，会抛 `RuntimeError`

#### `wait_for_completion(timeout=None) -> TurnResult`

用途：

- 等待当前 turn 完成

参数：

- `timeout: float | None`
  - 为空时使用 `config.turn_timeout_seconds`

返回值：

- 完成态的 `TurnResult` 拷贝

行为：

- 当前有活动 turn：等待其完成
- 当前无活动 turn 但有 `_last_turn`：直接返回 `_last_turn`
- 两者都没有：抛 `RuntimeError`

超时行为：

- 超时后调用 `_cancel_active_turn("turn timed out", "timeout")`

#### `run_turn(prompt, timeout=None) -> TurnResult`

用途：

- `send_input(...)` + `wait_for_completion(...)` 的组合封装

#### `is_output_complete() -> bool`

返回值：

- `True`
  - 当前无活动 turn 且有最近结果
  - 或当前 turn 已完成
- `False`
  - 当前 turn 仍在运行

#### `get_output_events(after_index=0) -> list[AgentOutputEvent]`

参数：

- `after_index: int`
  - 只返回 `event.index >= after_index` 的事件

返回值：

- 当前活动 turn 或最近完成 turn 的事件快照

#### `get_output_text() -> str`

返回值：

- 当前活动 turn 或最近完成 turn 的 `final_output`
- 如果还没有 turn，返回空串

#### `get_context_usage() -> TokenUsageSnapshot`

返回值：

- 当前活动 turn 或最近完成 turn 的 token 使用快照
- 如果还没有 turn，返回空 usage，但会保留 `context_window_tokens`

#### `get_context_usage_ratio() -> float | None`

返回值：

- 当前上下文使用占比

#### `shutdown() -> None`

用途：

- 关闭 runtime

行为：

- 幂等
- 首次调用会转入 `_shutdown_impl()`

内部辅助方法说明：

#### `_load_runtime_state()`

- 从 `runtime.json` 恢复 session 信息

#### `_persist_runtime_state()`

- 把当前 `session_id` 写回 `runtime.json`

#### `_record_event(...)`

参数：

- `turn_id`
- `event_type`
- `content`
- `call_id`
- `tool_name`
- `payload`

副作用：

- 追加一条 `AgentOutputEvent`
- 若 `event_type == "text"`，自动拼接到 `final_output`
- 写入 `history.jsonl`

#### `_replace_usage(turn_id, usage)`

- 直接覆盖当前 turn usage

#### `_merge_usage(turn_id, usage)`

- 将 usage 增量合并到当前 turn

#### `_set_session_id(session_id)`

- 更新内存 session ID
- 同时写入 `runtime.json`

#### `_set_final_output(turn_id, final_output)`

- 强制覆盖当前 turn 的 `final_output`

#### `_complete_turn(...)`

参数：

- `turn_id`
- `status`
- `final_output`
- `error`
- `session_id`
- `usage`

副作用：

- 标记 turn 完成
- 写入 `completed_at`
- 更新 `_last_turn`
- 清空 `_current_turn`
- 写入 `history.jsonl`
- 触发 `completion.set()`

抽象方法说明：

#### `_start_impl()`

- 后端启动逻辑

#### `_send_input_impl(prompt, turn_id)`

- 后端发送输入逻辑

#### `_cancel_active_turn(reason, status)`

- 后端取消逻辑

#### `_shutdown_impl()`

- 后端关闭逻辑

---

## runtime/claude.py

文件：

- [src/workflow_agents/runtime/claude.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/runtime/claude.py:1)

### `ClaudeCodeRuntime`

用途：

- 通过 Claude Code CLI 执行 agent turn

工作模式：

- 每轮 turn 启动一个新的 `claude -p`
- 使用 `--resume <session_id>` 尝试复用会话

重要内部字段：

- `_active_process`
  - 当前活动 Claude 子进程
- `_stderr_tail`
  - 最近若干行 stderr
- `_worker`
  - 当前 turn 的后台工作线程

方法说明：

#### `__init__(config, workspace)`

- 初始化运行时状态

#### `_start_impl()`

行为：

- 检查 `claude` 可执行文件是否存在

异常：

- 找不到可执行文件时抛 `FileNotFoundError`

#### `_build_args() -> list[str]`

返回值：

- Claude CLI 的完整参数列表

包含项：

- `-p`
- `--output-format stream-json`
- `--input-format stream-json`
- `--verbose`
- `--strict-mcp-config`
- `--permission-mode bypassPermissions`
- 可选 `--model`
- 可选 `--max-turns`
- 可选 `--append-system-prompt`
- 可选 `--resume`
- 额外 `cli_args`

#### `_send_input_impl(prompt, turn_id)`

行为：

- 清空 stderr tail
- 启动子进程
- 创建后台 worker 线程处理 stdout/stderr

#### `_run_turn_worker(process, turn_id, prompt)`

职责：

- 写入 stdin 的 JSON payload
- 逐行读取 stdout
- 解析 Claude stream-json 事件
- 转为内部 event / usage / final_output
- 最终调用 `_complete_turn(...)`

会处理的消息类型：

- `system`
- `assistant`
- `user`
- `log`
- `result`

#### `_drain_stderr(process)`

职责：

- 收集 stderr 的尾部文本
- 用于失败诊断

#### `_cancel_active_turn(reason, status)`

行为：

- 杀掉活动进程
- 将当前 turn 标记为指定状态

#### `_shutdown_impl()`

行为：

- 取消当前 turn
- 等待 worker 线程退出

---

## runtime/codex.py

文件：

- [src/workflow_agents/runtime/codex.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/runtime/codex.py:1)

### `CodexRuntime`

用途：

- 通过 `codex app-server` 的 JSON-RPC 接口执行 agent turn

工作模式：

- 启动长期存活的 app-server 子进程
- 维护一个可复用 thread
- 每轮通过 `turn/start` 发起任务

重要内部字段：

- `_process`
  - Codex app-server 进程
- `_reader_thread`
  - stdout 读取线程
- `_stderr_thread`
  - stderr 读取线程
- `_stderr_tail`
  - stderr 尾部缓存
- `_request_id`
  - JSON-RPC 递增请求号
- `_pending`
  - 等待响应的请求映射
- `_rpc_lock`
  - RPC 写入和 pending 管理锁
- `_thread_id`
  - 当前 thread ID
- `_active_turn_id`
  - 当前活动 turn ID

方法说明：

#### `__init__(config, workspace)`

- 初始化进程和 RPC 相关状态

#### `_start_impl()`

流程：

1. 校验 `codex` 可执行文件
2. 启动 `codex app-server --listen stdio://`
3. 启动 stdout / stderr 辅助线程
4. 发送 `initialize`
5. 发送 `initialized`
6. 若已有 `_thread_id`
   - 尝试 `thread/resume`
7. 否则 `thread/start`
8. 持久化 thread ID

异常：

- 找不到可执行文件：`FileNotFoundError`
- 初始化超时：`TimeoutError`
- `thread/start` 无 thread id：`RuntimeError`

#### `_send_input_impl(prompt, turn_id)`

行为：

- 设置 `_active_turn_id`
- 发送 `turn/start`

异常：

- 没有初始化 thread 时抛 `RuntimeError`

#### `_rpc_notify(method, params=None)`

用途：

- 发送 JSON-RPC notification

#### `_rpc_request(method, params, timeout) -> dict[str, Any]`

参数：

- `method: str`
- `params: dict[str, Any]`
- `timeout: float`

返回值：

- RPC `result` 对象

异常：

- 超时：`TimeoutError`
- 远端返回错误：`RuntimeError`

#### `_write_rpc(payload)`

用途：

- 把 JSON-RPC 数据写入 Codex stdin

异常：

- 进程未运行时抛 `RuntimeError`

#### `_reader_loop()`

职责：

- 读取 stdout 的 JSON 行
- 分发到：
  - `_handle_response(...)`
  - `_handle_notification(...)`

退出行为：

- 若进程退出，会给所有 pending 请求返回错误

#### `_stderr_loop()`

职责：

- 持续读取 stderr
- 只保留最近若干行

#### `_handle_response(payload)`

职责：

- 用响应结果唤醒对应 pending 请求

#### `_handle_notification(payload)`

职责：

- 把 Codex 原始通知转换成 runtime 内部事件

处理范围：

- `turn/started`
- `turn/completed`
- `item/started`
- `item/completed`

当前映射规则：

- `commandExecution`
  - 转为 `tool_use` / `tool_result`
- `fileChange`
  - 转为 `tool_use` / `tool_result`
- `agentMessage`
  - 转为 `text`
  - 同时更新 `final_output`

#### `_cancel_active_turn(reason, status)`

行为：

- 关闭 stdin
- 杀掉活动进程
- 完成当前 turn

#### `_shutdown_impl()`

行为：

- 取消当前 turn
- 尝试优雅终止进程
- 必要时强杀
- 关闭 stdio
- join 辅助线程

---

## runtime/factory.py

文件：

- [src/workflow_agents/runtime/factory.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/runtime/factory.py:1)

### `create_agent_runtime(config, workspace) -> ManagedAgentRuntime`

用途：

- 根据 `config.agent_type` 创建具体 runtime

参数：

- `config: AgentNodeConfig`
- `workspace: AgentWorkspace`

返回值：

- `ClaudeCodeRuntime`
- 或 `CodexRuntime`

异常：

- 未支持的 `agent_type` 抛 `ValueError`

---

## 常见调用路径

### 1. 直接调用 runtime

```python
registry = AgentRuntimeRegistry()
runtime = registry.get_or_create(config)

turn_id = runtime.send_input("draft a short summary")
result = runtime.wait_for_completion()

print(turn_id)
print(result.final_output)
print(runtime.get_context_usage_ratio())
runtime.shutdown()
```

### 2. 作为 LangGraph node 使用

```python
node = AgentNode(config=config, registry=registry)
updated_state = node(state)
```

输入依赖：

- `state["mailboxes"][config.name]`

输出更新：

- `mailboxes`
- `agent_results`

### 3. 自定义 prompt builder

```python
def my_prompt_builder(config, messages, state) -> str:
    return "\n".join(message.content for message in messages)

node = build_agent_node(
    config,
    registry=registry,
    prompt_builder=my_prompt_builder,
)
```

适用场景：

- 需要自定义提示格式
- 需要引入 `state["shared"]` 中的额外上下文

---

## 关键约束总结

### 1. node 间只传最终输出

当前设计中：

- `thinking`
- `tool_use`
- `tool_result`
- `log`

这些都会记录到 `history.jsonl`，但不会自动传播到下游 mailbox。

### 2. 同一 runtime 同时只允许一个活动 turn

如果调用：

- `send_input(...)`

时已有未完成 turn，会抛 `RuntimeError`。

### 3. workspace 是状态持久化边界

关键文件：

- `config.json`
- `runtime.json`
- `history.jsonl`
- `inbox.jsonl`
- `outbox.jsonl`

### 4. `folder_name` 会影响目录复用策略

- 不设置：
  - 自动编号防冲突
- 设置：
  - 直接复用该目录

适合人工预放配置。
