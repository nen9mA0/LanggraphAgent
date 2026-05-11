# Multica Agent Adapter Reference

## 目的

本文记录 `ref/multica` 中与“多种现有 AI agent 接入”相关的参考实现，供后续在本项目中设计 LangGraph 后端时复用。

重点不是复刻 multica 的业务，而是保留它的核心模式：

- 用统一抽象包住不同 agent CLI
- 用 agent 记录承载差异化配置
- 用 daemon 在本地拉起实际执行进程
- 用 provider 专属适配器处理启动参数、事件流、模型发现和上下文注入

## 结论先行

Multica 适合当作“本机 agent runtime + adapter”参考实现，不适合直接替代本项目的全部目标。

它已经覆盖：

- 本机多 agent CLI 探测
- 同 provider 下多个 agent 配置
- skills / model / env / mcp 的按 agent 定制
- 任务队列、轮询、执行、回传

它没有覆盖：

- 你这个项目当前设想的完整 flow editor / graph orchestration
- LangGraph 原生的 node/subgraph 编排
- 通用工作流持久化和可视化编排语义

因此更合理的用法是：

- 直接复用它的“agent adapter + runtime executor”思路
- 在本项目里把这层落成 LangGraph 的一个子图或执行服务

## Multica 的接入模型

### 1. 先探测本机可用 CLI

daemon 启动时会扫描 PATH，上到哪些 CLI，就把哪些 provider 注册为可用 runtime。

支持的 provider 不是“云模型”，而是本机已安装的 agent CLI，例如：

- `claude`
- `codex`
- `copilot`
- `opencode`
- `openclaw`
- `hermes`
- `gemini`
- `pi`
- `cursor-agent`
- `kimi`
- `kiro-cli`

### 2. agent 记录和 runtime 记录是两层

关键点：

- `runtime` 更像“这台机器上的某个 provider 运行实例”
- `agent` 更像“面向任务的配置实体”

agent 记录承载：

- `model`
- `custom_env`
- `custom_args`
- `mcp_config`
- `skills`

所以同一个 provider 下可以有多个 agent，每个 agent 配不同配置。

### 3. 任务执行时按 agent 配置注入

daemon 拉到任务后，会按 `agent_id` 取出该 agent 的配置，再把这些配置注入到实际 CLI 进程里。

注入内容包括：

- 任务工作目录
- issue / project / repo context
- skills 文件
- provider 特定 runtime config
- model / env / args / MCP config

## 执行链路

### 1. 服务端分发任务

服务端按 `agent_id` 和 `runtime_id` 组织任务队列。

daemon 通过轮询领取任务。

### 2. daemon 构建执行环境

每个任务会生成独立工作目录：

- `workdir`
- `output`
- `logs`

然后写入上下文文件：

- `issue_context.md`
- project resources
- skills
- provider runtime config

### 3. 选择 provider adapter

daemon 通过统一接口创建 backend：

- `agent.New(provider, cfg)`

外部只知道“执行一次任务”，内部按 provider 分派到不同 backend。

### 4. 拉起 CLI 并解析流

不同 provider 的输出协议不一样：

- stream-json / JSONL
- JSON-RPC / ACP
- session file
- provider 自定义 event stream

backend 负责把这些流统一成同一种消息/结果格式，再回传给 daemon 和服务端。

## provider 差异怎么收口

### A. 启动命令

每个 provider 都有自己的固定启动骨架，例如：

- `claude`: `claude ... --output-format stream-json`
- `codex`: `codex app-server --listen stdio://`
- `copilot`: `copilot -p ... --output-format json`
- `opencode`: `opencode run --format json`
- `gemini`: `gemini -o stream-json`
- `cursor`: `cursor-agent chat -p ... --output-format stream-json`
- `hermes/kimi/kiro`: `... acp`

### B. 参数过滤

daemon 会把协议关键参数固定住，避免用户通过 `custom_args` 覆盖：

- 输出格式
- 传输方式
- session / model 绑定参数
- sandbox 相关关键参数

### C. 模型发现

模型列表分两类：

- 静态 catalog
- 动态 CLI 探测 + 缓存

### D. skills 注入路径

不同 provider 读取 skills 的目录不同：

- Claude: `.claude/skills`
- Copilot: `.github/skills`
- OpenCode: `.opencode/skills`
- Pi: `.pi/skills`
- Cursor: `.cursor/skills`
- Kimi: `.kimi/skills`
- Kiro: `.kiro/skills`
- Codex: 走独立 `CODEX_HOME`
- 其他 fallback: `.agent_context/skills`

### E. runtime config 文件

Multica 会按 provider 写入不同文件：

- `CLAUDE.md`
- `AGENTS.md`
- `GEMINI.md`

目的是让 agent 用自己的原生约定读取上下文，而不是强行统一成一套格式。

## 同 provider 多 agent 是否支持

支持。

原因是：

- `agent` 表才是差异化配置载体
- `runtime` 只是本机 provider 运行实例
- 任务领取时会按 `agent_id` 取回 `skills/custom_env/custom_args/mcp_config/model`

因此可以有：

- 两个 `codex` agent
- 不同 `model`
- 不同 `skills`
- 不同 `custom_args`
- 不同 `mcp_config`

共享同一台机器、同一个 provider runtime。

## 对本项目的建议落点

如果把这套思路迁移到当前项目，建议拆成三层：

1. `LangGraph graph`
   - 只负责编排
2. `agent adapter service`
   - 负责 provider 差异
3. `agentExecutor subgraph`
   - 负责一次完整执行

推荐输入：

- `agentId`
- `provider`
- `model`
- `skills`
- `customEnv`
- `customArgs`
- `mcpConfig`
- `prompt`
- `workdir`

## 适配判断

Multica 可以直接复用的部分：

- agent 配置模型
- provider adapter 设计
- 本机 CLI 执行模式
- skills / env / mcp 的注入方式
- 任务结果收集模式

Multica 不能直接替代的部分：

- 你的 flow editor
- LangGraph 语义
- 通用图编排
- 你项目后端的 flow persistence / generation / orchestration