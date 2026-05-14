# LangGraph Demo

## 位置

示例代码在：

- `src/workflow_agents/examples/langgraph_demo.py`

## graph 结构

```text
START
  |
planner
  |
writer   (Claude node)
  |
reviewer (Codex node)
  |
 END
```

说明：

- `planner` 是普通 Python node，只负责往 `writer` 的 mailbox 塞一条初始消息
- `writer` 使用 Claude runtime
- `reviewer` 使用 Codex runtime
- `writer` 的最终输出会被转发给 `reviewer`
- `reviewer` 不再向下游转发，只把结果留在 `agent_results["reviewer"]`

## 直接运行

### 1. fake CLI 版本

```bash
python -m workflow_agents.examples.langgraph_demo --use-fake-cli
```

这个模式不依赖真实 agent，可用于验证：

- graph 编排是否通
- mailbox 是否正确流转
- `.workflow/agent/...` 是否正确落盘
- node 是否只转发最终输出

### 2. 真实 CLI 版本

```bash
python -m workflow_agents.examples.langgraph_demo ^
  --working-directory E:\\Project\\program_workflow\\.demo_workdir ^
  --claude-exec claude ^
  --codex-exec codex ^
  --topic "Write and review a short release summary."
```

前提：

- 本机 PATH 中可找到 `claude` 和 `codex`
- 两个 CLI 都已经完成登录或本地初始化

## 输出怎么看

命令完成后会打印一个 JSON，重点看：

- `agent_results["writer"]`
- `agent_results["reviewer"]`
- `mailboxes`

正常情况下：

- `writer` 会消耗 `planner -> writer` 的消息
- `writer` 会把 `final_output` 发给 `reviewer`
- `reviewer` 会消耗 `writer -> reviewer` 的消息
- 已消费的 mailbox 会被置为空列表；最终 `mailboxes` 一般会是空列表集合或只剩未被消费的其他消息

## 配置替换建议

如果你要把这个示例替换成真实业务节点，通常只需要改三类内容：

1. `planner_node`
   - 改成你自己的初始消息生成逻辑
2. `AgentNodeConfig`
   - 改 `agent_type`、`model`、`system_prompt`、`targets`
3. graph 拓扑
   - 改 `add_node` / `add_edge`
