# Architecture

## 分层

### 1. runtime

`src/workflow_agents/runtime/`

职责：

- 拉起真实 CLI 进程
- 维护长生命周期 session / thread
- 提供统一的 turn 接口
- 记录流式事件
- 计算 token 使用情况
- 暴露完成态、输出、关闭等控制接口

当前实现：

- `ClaudeCodeRuntime`
- `CodexRuntime`

两者都继承 `ManagedAgentRuntime`。

### 2. storage

`src/workflow_agents/storage.py`

职责：

- 默认在 `<working_directory>/.workflow/agent/` 下创建 agent 根目录
- 为每个 node 分配独立目录
- 重名时自动追加 `_1`、`_2`
- 保存配置、会话信息、history、inbox、outbox

### 3. registry

`src/workflow_agents/registry.py`

职责：

- 负责 runtime 单例复用
- 一个 `AgentNodeConfig.instance_key` 对应一个 runtime 实例
- 统一管理关闭

### 4. node

`src/workflow_agents/node.py`

职责：

- 从 `mailboxes[node_name]` 读取跨 node 消息
- 构造 prompt 发给 agent runtime
- 将最终输出转发到目标 node 的 mailbox
- 把本轮结果写到 `agent_results`

## 状态模型

`src/workflow_agents/state.py`

```python
class AgentGraphState(TypedDict, total=False):
    mailboxes: dict[str, list[dict[str, Any]]]
    agent_results: dict[str, dict[str, Any]]
    shared: dict[str, Any]
```

语义：

- `mailboxes`
  - 只承载 node 之间的外部消息
- `agent_results`
  - 保存每个 node 最近一轮 turn 的摘要结果
- `shared`
  - graph 级共享输入

## 为什么不把内部流式输出塞回 graph state

这是当前实现最重要的边界：

- `tool_use`
- `tool_result`
- `thinking`
- `log`
- 流式 `text`

这些都保存在当前 agent 的 `history.jsonl` 中，便于审计和调试；但 node 向其他 node 转发时，只转发 `TurnResult.final_output`。

这样做的好处：

- graph state 不会被 agent 内部噪声污染
- 不同 agent 的上下文边界更清晰
- LangGraph 编排层只处理可消费的外部结果
- 后续要做持久化、可视化或回放时，更容易拆分“编排上下文”和“agent 原始事件”

## Claude / Codex 差异处理

### Claude

- 单次 turn 使用 `claude -p --output-format stream-json`
- runtime 保持 session id，并在后续 turn 中通过 `--resume` 复用

### Codex

- 启动 `codex app-server --listen stdio://`
- runtime 通过 JSON-RPC 初始化并创建或恢复 thread
- 后续 turn 都在同一个 thread 内执行

## 当前限制

- 现在只实现了 `claude` 和 `codex`
- prompt builder 还是简单文本拼接
- 还没有做中断恢复策略、turn 排队、多路并发调度
- 还没有对接 `langgraph_codegen` 前后端节点定义
