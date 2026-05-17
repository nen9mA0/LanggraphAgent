# AgentNode Architecture

## 1. 总体结构

### 1.1 分层视图

```text
+--------------------------------------------------------------+
|                      LangGraph Workflow                      |
|                                                              |
|  AgentGraphState                                             |
|  - mailboxes                                                 |
|  - agent_results                                             |
|  - shared                                                    |
|                                                              |
|  +----------------+      +----------------+                  |
|  |   AgentNode A  | ---> |   AgentNode B  | ---> ...         |
|  +----------------+      +----------------+                  |
+-----------|----------------------|---------------------------+
            |                      |
            v                      v
+-----------------------+  +-----------------------+
| AgentRuntimeRegistry  |  | AgentRuntimeRegistry  |
| - instance_key -> rt  |  | - instance_key -> rt  |
+-----------|-----------+  +-----------|-----------+
            |                          |
            v                          v
+-----------------------+  +-----------------------+
| ManagedAgentRuntime   |  | ManagedAgentRuntime   |
| - current_turn        |  | - current_turn        |
| - last_turn           |  | - last_turn           |
| - session_id          |  | - session_id          |
+-----------|-----------+  +-----------|-----------+
            |                          |
            v                          v
+-----------------------+  +-----------------------+
| ClaudeCodeRuntime     |  | CodexRuntime          |
| Claude CLI            |  | codex app-server      |
+-----------|-----------+  +-----------|-----------+
            |                          |
            v                          v
+-----------------------+  +-----------------------+
| AgentWorkspace        |  | AgentWorkspace        |
| .workflow/agent/...   |  | .workflow/agent/...   |
+-----------------------+  +-----------------------+
```

### 1.2 核心设计原则

当前实现围绕以下原则组织：

- `AgentNode` 负责“编排边界”
  - 只处理来自其他 node 的外部消息
  - 只把最终输出发给其他 node
- `ManagedAgentRuntime` 负责“执行边界”
  - 管理 turn 生命周期
  - 管理底层 CLI 会话
  - 记录内部流式事件
- `AgentWorkspace` 负责“持久化边界”
  - 配置、会话信息、事件日志都写到独立目录
- `AgentGraphState` 负责“图状态边界”
  - 只存放 graph 编排需要的状态
  - 不直接承载 agent 内部工具细节

## 2. 关键组件与组合关系

### 2.1 AgentNode 的位置

代码位置：

- [src/workflow_agents/node.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/node.py:1)

`AgentNode` 是 LangGraph 可执行节点包装器。它并不直接实现 CLI 协议，而是组合以下对象：

- `AgentNodeConfig`
- `AgentRuntimeRegistry`
- `PromptBuilder`
- `ManagedAgentRuntime`（通过 registry 获取）

组合关系图：

```text
AgentNode
|- config: AgentNodeConfig
|- registry: AgentRuntimeRegistry
|- prompt_builder: PromptBuilder
|
`- get_runtime()
   `- registry.get_or_create(config)
      `- ManagedAgentRuntime subclass
```

### 2.2 AgentNodeConfig

代码位置：

- [src/workflow_agents/types.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/types.py:1)

`AgentNodeConfig` 是 `AgentNode` 和 `ManagedAgentRuntime` 共用的配置对象。

它同时被以下组件使用：

- `AgentNode`
  - 读取 `name`、`targets`、`prompt_prefix`
- `AgentRuntimeRegistry`
  - 读取 `instance_key`、`folder_name`
- `ManagedAgentRuntime`
  - 读取超时、上下文窗口等运行参数
- `ClaudeCodeRuntime` / `CodexRuntime`
  - 读取 `executable_path`、`system_prompt`、`model`、`cli_args`、`env`
- `AgentWorkspace`
  - 通过 `persist_config()` 写入 `config.json`

### 2.3 AgentRuntimeRegistry

代码位置：

- [src/workflow_agents/registry.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/registry.py:1)

`AgentRuntimeRegistry` 是 `AgentNode` 和 runtime 之间的桥梁。

职责：

- 按 `instance_key` 复用 runtime
- 创建 `AgentWorkspace`
- 持久化 `config.json`
- 创建具体 runtime 实现
- 统一关闭所有 runtime

组合关系：

```text
AgentNode
  -> AgentRuntimeRegistry
       -> AgentWorkspaceManager
       -> AgentWorkspace
       -> create_agent_runtime(...)
            -> ClaudeCodeRuntime / CodexRuntime
```

### 2.4 AgentWorkspace

代码位置：

- [src/workflow_agents/storage.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/storage.py:1)

每个 runtime 对应一个 `AgentWorkspace`，负责该 agent node 的本地持久化目录。

目录结构：

```text
.workflow/agent/<folder_name>/
|- config.json
|- runtime.json
|- history.jsonl
|- inbox.jsonl
`- outbox.jsonl
```

这些文件与组件关系如下：

```text
config.json   <- AgentRuntimeRegistry / AgentNodeConfig
runtime.json  <- ManagedAgentRuntime
history.jsonl <- ManagedAgentRuntime
inbox.jsonl   <- AgentNode
outbox.jsonl  <- AgentNode
```

### 2.5 ManagedAgentRuntime

代码位置：

- [src/workflow_agents/runtime/base.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/runtime/base.py:1)

`ManagedAgentRuntime` 是底层 agent 执行层的统一抽象。

它维护：

- 当前活动 turn：`_current_turn`
- 最近完成 turn：`_last_turn`
- 当前 session / thread：`_session_id`
- 生命周期状态：`_started`、`_closed`

`AgentNode` 不关心 Claude 或 Codex 的协议细节，它只依赖以下统一接口：

- `run_turn(prompt, timeout=None)`
- `get_output_text()`
- `get_output_events()`
- `get_context_usage()`
- `get_context_usage_ratio()`
- `is_output_complete()`
- `shutdown()`

## 3. AgentNode 与状态数据结构的组合

### 3.1 AgentGraphState

代码位置：

- [src/workflow_agents/state.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/state.py:1)

定义：

```python
class AgentGraphState(TypedDict, total=False):
    mailboxes: dict[str, list[dict[str, Any]]]
    agent_results: dict[str, dict[str, Any]]
    shared: dict[str, Any]
```

### 3.2 三个核心状态槽位

#### `mailboxes`

用途：

- node 之间的外部通信通道

结构：

```python
{
    "writer": [InterNodeMessage.to_dict(), ...],
    "reviewer": [InterNodeMessage.to_dict(), ...],
}
```

说明：

- key 是接收方 node 名称
- value 是待消费消息列表
- `AgentNode.__call__()` 会消费 `mailboxes[config.name]`

#### `agent_results`

用途：

- 保存 node 最近一轮 turn 的摘要结果

结构示意：

```python
{
    "writer": {
        "status": "completed",
        "session_id": "...",
        "final_output": "...",
        "error": "",
        "usage": {...},
        "workspace": "...",
        "consumed_messages": [...],
        "forwarded_messages": [...],
    }
}
```

说明：

- 它面向 graph 编排层和调试层
- 不是原始事件流
- 不会替代 `history.jsonl`

#### `shared`

用途：

- graph 范围的共享输入

典型内容：

- 任务主题
- 用户输入
- 上层工作流注入的上下文

### 3.3 reducer 设计

`mailboxes` 使用 `merge_mailboxes`，不是简单追加，而是“右值覆盖同名 key”。

原因：

- 节点消费自己的 mailbox 后会将其置为空列表
- 如果使用简单追加，旧消息会重新回到状态里

图示：

```text
before:
  mailboxes["writer"] = [msg1]

AgentNode("writer") consumes msg1
returns:
  mailboxes["writer"] = []

reducer must keep []
instead of restoring [msg1]
```

## 4. AgentNode 间通信的数据结构

### 4.1 InterNodeMessage

代码位置：

- [src/workflow_agents/types.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/types.py:1)

定义：

```python
@dataclass(slots=True)
class InterNodeMessage:
    sender: str
    recipient: str
    content: str
    metadata: dict[str, Any]
    message_id: str
    created_at: str
```

### 4.2 字段语义

- `sender`
  - 上游 node 名称
- `recipient`
  - 下游 node 名称
- `content`
  - 发送给下游 node 的正文
- `metadata`
  - 附加结构化信息
  - 当前实现常放：
    - `turn_id`
    - `session_id`
    - `status`
- `message_id`
  - 唯一消息 ID
- `created_at`
  - UTC 时间戳

### 4.3 通信语义

`InterNodeMessage` 只承载跨 node 的可消费结果，不承载 agent 内部中间状态。

也就是说，以下信息不会自动作为 node 通信内容：

- `thinking`
- `tool_use`
- `tool_result`
- 原始日志
- 增量文本片段

真正向下游传播的是：

- `TurnResult.final_output`

### 4.4 一个消息从上游到下游的路径

```text
upstream AgentNode completes turn
    |
    v
TurnResult.final_output
    |
    v
InterNodeMessage(
  sender=upstream_name,
  recipient=target_name,
  content=final_output,
  metadata={turn_id, session_id, status},
)
    |
    v
mailboxes[target_name].append(message.to_dict())
    |
    v
downstream AgentNode reads mailbox on next execution
```

## 5. AgentNode 的执行流程

### 5.1 单次 `AgentNode.__call__()` 流程

```text
AgentNode.__call__(state)
  |
  |-- copy mailboxes
  |-- inbound = mailboxes[config.name]
  |-- mailboxes[config.name] = []
  |
  |-- if no inbound:
  |     return idle/skipped agent_results
  |
  |-- runtime = get_runtime()
  |-- workspace.inbox.jsonl append
  |-- prompt = prompt_builder(config, inbound, state)
  |-- result = runtime.run_turn(prompt)
  |
  |-- build outbound InterNodeMessage list
  |-- write messages into downstream mailboxes
  |-- workspace.outbox.jsonl append
  |
  `-- return {
         "mailboxes": ...,
         "agent_results": ...,
       }
```

### 5.2 输入输出边界

输入：

- `state["mailboxes"][config.name]`
- `state["shared"]`
- `config`

输出：

- 更新后的 `mailboxes`
- 当前 node 的 `agent_results`

不会直接输出到 graph state 的内容：

- runtime 内部事件流
- CLI 原始协议事件
- stderr tail

这些都在 runtime/workspace 层处理。

## 6. AgentNode 与底层 CLI 的衔接方式

### 6.1 抽象边界

`AgentNode` 自己不关心 Claude / Codex 的协议格式。它只面向 `ManagedAgentRuntime` 的统一接口。

衔接关系：

```text
AgentNode
  -> ManagedAgentRuntime.run_turn(prompt)
       -> backend-specific runtime
            -> CLI process / RPC protocol
```

### 6.2 Claude 路径

代码位置：

- [src/workflow_agents/runtime/claude.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/runtime/claude.py:1)

工作模式：

- 每轮 turn 启动一次 Claude CLI
- 使用 `stream-json` 协议
- 通过 `--resume <session_id>` 复用对话

链路图：

```text
AgentNode
  -> runtime.run_turn(prompt)
     -> ClaudeCodeRuntime._send_input_impl(...)
        -> start process:
           claude -p --output-format stream-json --input-format stream-json ...
        -> write stdin JSON payload
        -> read stdout line by line
        -> convert stream-json events to AgentOutputEvent / TurnResult
```

协议映射：

- `system`
  - 更新 `session_id`
  - 记录 `status`
- `assistant`
  - 解析 `usage`
  - 解析 `text` / `thinking` / `tool_use`
- `user`
  - 解析 `tool_result`
- `result`
  - 生成最终 `final_output`

### 6.3 Codex 路径

代码位置：

- [src/workflow_agents/runtime/codex.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/runtime/codex.py:1)

工作模式：

- 先启动长期存活的 `codex app-server`
- 与之通过 JSON-RPC 交互
- 维护可复用 thread

链路图：

```text
AgentNode
  -> runtime.run_turn(prompt)
     -> CodexRuntime._send_input_impl(...)
        -> JSON-RPC turn/start
        -> app-server emits notifications
        -> runtime maps notifications to AgentOutputEvent / TurnResult
```

协议映射：

- `initialize` / `initialized`
  - 完成会话初始化
- `thread/resume` / `thread/start`
  - 确定工作 thread
- `turn/start`
  - 发起一轮任务
- `turn/started`
  - 记录运行状态
- `turn/completed`
  - 生成完成态 `TurnResult`
- `item/started` / `item/completed`
  - 转换为工具调用事件或文本事件

### 6.4 两者的共同输出

无论底层协议如何不同，最终都统一成：

- `TurnResult`
- `AgentOutputEvent`
- `TokenUsageSnapshot`

这就是 `AgentNode` 可以不感知具体 CLI 协议的原因。

## 7. 一次完整 turn 的时序图

### 7.1 从 mailbox 到 CLI 再回到 mailbox

```text
Upstream Node         AgentNode(writer)       Runtime          Agent CLI        AgentNode(reviewer)
     |                       |                  |                  |                    |
     |-- final_output ------>|                  |                  |                    |
     |   as mailbox msg      |                  |                  |                    |
     |                       |-- read mailbox ->|                  |                    |
     |                       |-- build prompt --|                  |                    |
     |                       |                  |-- send prompt --->|                    |
     |                       |                  |<-- stream events -|                    |
     |                       |                  |-- build result ---|                    |
     |                       |<-- TurnResult ---|                  |                    |
     |                       |-- write outbox                      |                    |
     |                       |-- append mailbox[reviewer] ----------------------------->|
     |                       |                                                         |
```

### 7.2 与本地文件的同步关系

```text
AgentNode consumes inbound
  -> inbox.jsonl append

Runtime starts turn
  -> history.jsonl append(turn_started)

Runtime receives internal events
  -> history.jsonl append(event)

Runtime completes turn
  -> history.jsonl append(turn_completed)
  -> runtime.json update(session_id/thread_id if changed)

AgentNode emits outbound
  -> outbox.jsonl append
```

## 8. 当前实现的边界与约束

### 8.1 一个 runtime 同时只处理一个活动 turn

约束位置：

- `ManagedAgentRuntime.send_input()`

行为：

- 如果当前已有未完成 turn，则抛出 `RuntimeError`

影响：

- 当前不是并发多 turn runtime
- 需要上层编排保证同一 node 不被并发驱动

### 8.2 AgentNode 不是 message bus

`AgentNode` 不做：

- 多路消息队列调度
- 优先级排序
- 重试队列
- 持久化恢复后的自动重放

它只做：

- 消费自己的 mailbox
- 调用自己的 runtime
- 将最终输出写回下游 mailbox

### 8.3 graph state 与 agent history 明确分层

graph state 面向：

- 编排
- 路由
- 结果摘要

agent history 面向：

- 审计
- 调试
- 运行时诊断

### 8.4 CLI 结合方式仍是轻量适配

当前实现是“最小可用适配层”，并不包含：

- 更复杂的中断恢复
- 多 provider 插件化注册
- 模型能力自动发现
- 多运行时池化调度

## 9. 建议阅读路径

如果你要继续扩展当前架构，建议按这个顺序看代码：

1. [src/workflow_agents/types.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/types.py:1)
2. [src/workflow_agents/state.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/state.py:1)
3. [src/workflow_agents/storage.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/storage.py:1)
4. [src/workflow_agents/runtime/base.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/runtime/base.py:1)
5. [src/workflow_agents/runtime/claude.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/runtime/claude.py:1)
6. [src/workflow_agents/runtime/codex.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/runtime/codex.py:1)
7. [src/workflow_agents/registry.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/registry.py:1)
8. [src/workflow_agents/node.py](/abs/path/E:/Project/program_workflow/src/workflow_agents/node.py:1)
