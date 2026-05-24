# workflow_agents Guide

此目录实现“Agent 作为 LangGraph Node”的能力。这里的重点不是画布，而是长生命周期 runtime、workspace、session/thread 复用、mailbox 驱动的节点执行。

## 先读哪些文件

按这个顺序即可，不要一次性扫完整目录：

1. `AGENT_GUIDE.md`
2. `types.py`
3. `node.py`
4. `registry.py`
5. `state.py`
6. `runtime/AGENTS.md`

如果是文档导向任务，再去 `doc/agent_node/README.md`。

## 任务到代码入口

- 改 LangGraph 节点的 graph-facing 行为
  - `node.py`
  - `state.py`
- 改 runtime 生命周期、turn bookkeeping、超时/中断/完成语义
  - `runtime/base.py`
- 改 runtime 复用、workspace 分配、持久化文件
  - `registry.py`
  - `storage.py`
- 改 provider config 复用
  - `config_reuse.py`
  - `doc/agent_node/integrations/provider_config_reuse.md`
- 改 Claude CLI 适配
  - `runtime/claude.py`
- 改 Claude SDK 适配
  - `runtime/claude_sdk.py`
  - `runtime/claude_sdk_worker.py`
  - `doc/agent_node/integrations/claude_sdk.md`
- 改 Codex app-server / JSON-RPC 适配
  - `runtime/codex.py`
  - `runtime/AGENTS.md`

## 关键概念

- `AgentNodeConfig`
  - 统一配置对象，定义在 `types.py`
- `AgentNode`
  - LangGraph 包装器，读取 mailbox，拼 prompt，执行 turn，只向下游转发 `final_output`
- `AgentRuntimeRegistry`
  - 按 `instance_key` 复用 runtime，分配 workspace
- `ManagedAgentRuntime`
  - runtime 抽象基类，统一 turn 生命周期

## 真正的数据流

1. graph 把消息放进 `mailboxes`
2. `AgentNode.__call__()` 取出本节点 inbox
3. `prompt_builder` 把 inbound message 变成 prompt
4. runtime 执行一轮 turn
5. 只把 `TurnResult.final_output` 转发给 `targets`
6. `agent_results` 里保留摘要，不保留完整协议流

## 修改时的约束

- 一个 runtime 同时只能有一个 active turn。
- 默认跨节点只传 `final_output`，不要把 thinking/tool 流量随手塞进 graph state。
- `session_id` 是后端原生可恢复标识：
  - Claude CLI session id
  - Claude SDK session id
  - Codex thread id
- workspace 下的 provider config snapshot 是最小复用快照，不是整目录复制。

## 深入索引

- 想看 runtime 层说明
  - `runtime/AGENTS.md`
- 想看正式文档
  - `doc/agent_node/README.md`
- 想看 Codex schema 定位方式
  - `runtime/AGENTS.md`
  - `runtime/codex_schema/AGENT_INDEX.md`

## 验证

- `python -m unittest -v`
- 重点测试：
  - `tests/test_workflow_agents.py`
  - `tests/test_runtime_cli_availability.py`
