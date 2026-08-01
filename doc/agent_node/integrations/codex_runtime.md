## 接口实现

https://github.com/openai/codex/tree/main/codex-rs/app-server

### initialize

* ### thread

#### 启动

* thread/start  impl
* thread/resume  impl
* thread/fork  not

#### 管理

* thread/list not
* thread/loaded/list  not
* thread/read  not
* thread/turns/list  not  exp
* thread/turns/items/list  not  exp
* thread/metadata/update  not
* thread/settings/update  not exp
* thread/memoryMode/set  not exp
* memory/reset  not  exp
* thread/goal/set  not
* thread/goal/get  not
* thread/goal/clear  not
* thread/goal/updated  not  notify
* thread/goal/cleared  not  notify
* thread/status/changed  not  notify
* thread/archive  





## 线程生命周期（会话启动、恢复、分叉、归档等）

| API 名称                    | 类型  | 功能概括                                                 | 实验性                                              |
| ------------------------- | --- | ---------------------------------------------------- | ------------------------------------------------ |
| `thread/start`            | 请求  | 创建新线程，返回初始状态并自动订阅事件。支持权限覆盖、运行时工作区根、环境选择等参数。          | 部分字段实验性（`runtimeWorkspaceRoots`, `environments`） |
| `thread/resume`           | 请求  | 按 ID 恢复已有线程，后续 `turn/start` 将追加到该线程。                 | 否                                                |
| `thread/fork`             | 请求  | 复制现有线程历史为新线程，支持临时内存分叉或排除已有 turns。                    | `excludeTurns` 实验性                               |
| `thread/list`             | 请求  | 分页列出存储的线程，支持多种过滤条件。                                  | 否                                                |
| `thread/loaded/list`      | 请求  | 列出当前加载在内存中的线程 ID。                                    | 否                                                |
| `thread/read`             | 请求  | 读取线程（不恢复），可选择是否包含 turns。                             | 否                                                |
| `thread/turns/list`       | 请求  | 实验性：分页查询线程的 turn 历史，无需恢复线程。                          | 是                                                |
| `thread/turns/items/list` | 请求  | 实验性：保留分页获取 turn 内所有 items 的接口，但当前返回错误。               | 是                                                |
| `thread/metadata/update`  | 请求  | 更新 SQLite 中存储的线程元数据（如 gitInfo）。                      | 否                                                |
| `thread/archive`          | 请求  | 将线程及其衍生线程的 rollout 文件移到归档目录，发送 `thread/archived` 通知。 | 否                                                |
| `thread/unarchive`        | 请求  | 将归档的线程移回会话目录，返回恢复的线程并发送 `thread/unarchived`。         | 否                                                |
| `thread/name/set`         | 请求  | 设置或更新线程的用户友好名称，成功后发送 `thread/name/updated`。          | 否                                                |
| `thread/compact/start`    | 请求  | 触发线程对话历史的压缩压缩，进度通过标准 turn/item 通知流式返回。               | 否                                                |
| `thread/rollback`         | 请求  | 从 agent 内存上下文删除最后 N 个 turn，并在 rollout 中标记回滚点。        | 否                                                |
| `thread/unsubscribe`      | 请求  | 取消当前连接对线程事件的订阅；若无订阅者，30分钟后卸载线程并发送 `thread/closed`。   | 否                                                |

## 线程配置与状态管理（设置、内存模式、目标等）

| API 名称                    | 类型  | 功能概括                                           | 实验性 |
| ------------------------- | --- | ---------------------------------------------- | --- |
| `thread/settings/update`  | 请求  | 实验性：更新加载中线程的下次 turn 设置（不启动 turn）。              | 是   |
| `thread/memoryMode/set`   | 请求  | 实验性：启用/禁用线程的持久化记忆功能。                           | 是   |
| `memory/reset`            | 请求  | 实验性：清空记忆目录并重置 SQLite 中的记忆阶段数据，保留线程记忆模式。        | 是   |
| `thread/goal/set`         | 请求  | 创建或更新线程的持久化目标，返回当前目标并发送 `thread/goal/updated`。 | 否   |
| `thread/goal/get`         | 请求  | 获取线程的当前持久化目标。                                  | 否   |
| `thread/goal/clear`       | 请求  | 清除线程的持久化目标，若有变化则发送 `thread/goal/cleared`。      | 否   |
| `thread/status/changed`   | 通知  | 当加载中线程的状态改变时发送（包含 threadId 和新状态）。              | 否   |
| `thread/settings/updated` | 通知  | 实验性：当加载线程的有效 next-turn 设置发生变化时发送。              | 是   |
| `thread/goal/updated`     | 通知  | 线程目标变化时发送，包含完整当前目标。                            | 否   |
| `thread/goal/cleared`     | 通知  | 线程目标被清除时发送。                                    | 否   |

## 对话管理（Turn 操作）

| API 名称                | 类型  | 功能概括                                                     | 实验性                                                   |
| --------------------- | --- | -------------------------------------------------------- | ----------------------------------------------------- |
| `turn/start`          | 请求  | 向线程添加用户输入并开始 Codex 生成，流式返回 turn/item 通知。支持权限覆盖、运行时工作区根等。 | 部分字段实验性（`runtimeWorkspaceRoots`, permissions profile） |
| `turn/steer`          | 请求  | 向已在飞行中的常规 turn 追加用户输入，不启动新 turn。                         | 否                                                     |
| `turn/interrupt`      | 请求  | 请求取消正在进行的 turn（返回空对象，turn 以 `interrupted` 状态结束）。         | 否                                                     |
| `thread/inject_items` | 请求  | 向加载线程的模型可见历史中追加原始 Responses API 条目（不启动用户 turn）。          | 否                                                     |

## 实时会话（实验性）

| API 名称                        | 类型  | 功能概括                                             | 实验性 |
| ----------------------------- | --- | ------------------------------------------------ | --- |
| `thread/realtime/start`       | 请求  | 启动线程范围的实时会话，支持文本或音频输出，可通过 WebSocket 或 WebRTC 传输。 | 是   |
| `thread/realtime/appendAudio` | 请求  | 向活跃实时会话追加音频块。                                    | 是   |
| `thread/realtime/appendText`  | 请求  | 向活跃实时会话追加文本输入。                                   | 是   |
| `thread/realtime/stop`        | 请求  | 停止线程的实时会话。                                       | 是   |

## 代码审查

| API 名称         | 类型  | 功能概括                                            | 实验性 |
| -------------- | --- | ----------------------------------------------- | --- |
| `review/start` | 请求  | 启动 Codex 自动化评审器，返回类似 turn/start 的流式通知，最终给出评审意见。 | 否   |

## 命令执行（沙箱内）

| API 名称                     | 类型  | 功能概括                                       | 实验性 |
| -------------------------- | --- | ------------------------------------------ | --- |
| `command/exec`             | 请求  | 在服务端沙箱中运行单条命令（不启动线程/turn），适用于工具验证等。        | 否   |
| `command/exec/write`       | 请求  | 向运行中的命令会话写入 base64 解码后的 stdin 字节或关闭 stdin。 | 否   |
| `command/exec/resize`      | 请求  | 调整 PTY 后端命令会话的终端大小。                        | 否   |
| `command/exec/terminate`   | 请求  | 终止运行中的命令会话。                                | 否   |
| `command/exec/outputDelta` | 通知  | 流式命令会话输出 stdout/stderr 块（base64 编码）。       | 否   |

## 进程管理（宿主机，无沙箱，实验性）

| API 名称                | 类型  | 功能概括                                   | 实验性 |
| --------------------- | --- | -------------------------------------- | --- |
| `process/spawn`       | 请求  | 在 app-server 所在宿主机上生成独立进程（无 Codex 沙箱）。 | 是   |
| `process/writeStdin`  | 请求  | 向运行中的进程写入 stdin 或关闭 stdin。             | 是   |
| `process/resizePty`   | 请求  | 调整 PTY 后端进程的终端大小。                      | 是   |
| `process/kill`        | 请求  | 终止运行中的进程。                              | 是   |
| `process/outputDelta` | 通知  | 进程的 stdout/stderr 块（base64 编码）。        | 是   |
| `process/exited`      | 通知  | 进程退出时发送。                               | 是   |

## 文件系统操作

| API 名称               | 类型  | 功能概括                               | 实验性 |
| -------------------- | --- | ---------------------------------- | --- |
| `fs/readFile`        | 请求  | 读取绝对路径文件，返回 base64 数据。             | 否   |
| `fs/writeFile`       | 请求  | 将 base64 数据写入绝对路径文件。               | 否   |
| `fs/createDirectory` | 请求  | 创建绝对路径目录（默认递归）。                    | 否   |
| `fs/getMetadata`     | 请求  | 返回路径的元数据（类型、时间戳等）。                 | 否   |
| `fs/readDirectory`   | 请求  | 列出目录下直接子项（仅名称，非完整路径）。              | 否   |
| `fs/remove`          | 请求  | 删除文件或目录树（默认递归且强制）。                 | 否   |
| `fs/copy`            | 请求  | 在绝对路径间复制文件或目录（目录需递归）。              | 否   |
| `fs/watch`           | 请求  | 订阅文件/目录变更通知，返回规范化路径。               | 否   |
| `fs/unwatch`         | 请求  | 停止发送指定 watchId 的变更通知。              | 否   |
| `fs/changed`         | 通知  | 当被监视的路径发生变化时发送，包含 watchId 和变更路径列表。 | 否   |

## 模型与能力

| API 名称                            | 类型  | 功能概括                        | 实验性 |
| --------------------------------- | --- | --------------------------- | --- |
| `model/list`                      | 请求  | 列出可用模型，包含推理力度选项、服务层级、升级信息等。 | 否   |
| `modelProvider/capabilities/read` | 请求  | 读取当前配置的模型提供商的能力。            | 否   |

## 实验性功能与权限

| API 名称                               | 类型  | 功能概括                          | 实验性      |
| ------------------------------------ | --- | ----------------------------- | -------- |
| `experimentalFeature/list`           | 请求  | 列出功能标志及其阶段、启用状态，支持按线程计算配置。    | 是        |
| `permissionProfile/list`             | 请求  | Beta：列出可用的权限配置 ID 及描述。        | 是 (beta) |
| `experimentalFeature/enablement/set` | 请求  | 修改进程内运行时功能开关（优先级低于云要求和命令行标志）。 | 是        |
| `environment/add`                    | 请求  | 添加或替换命名的远程环境（用于后续线程/turn 选择）。 | 是        |

## 环境与远程控制

| API 名称                         | 类型  | 功能概括                     | 实验性 |
| ------------------------------ | --- | ------------------------ | --- |
| `collaborationMode/list`       | 请求  | 列出可用的协作模式预设（如 Plan 模式）。  | 是   |
| `remoteControl/enable`         | 请求  | 启用当前 app-server 进程的远程控制。 | 是   |
| `remoteControl/disable`        | 请求  | 禁用远程控制（不撤销已注册设备）。        | 是   |
| `remoteControl/status/read`    | 请求  | 读取当前远程控制状态快照。            | 是   |
| `remoteControl/pairing/start`  | 请求  | 启动短期配对凭证，返回配对码及过期时间。     | 是   |
| `remoteControl/client/list`    | 请求  | 列出已授权访问某个环境的控制器设备。       | 是   |
| `remoteControl/client/revoke`  | 请求  | 撤销指定控制器设备对环境的授权。         | 是   |
| `remoteControl/status/changed` | 通知  | 远程控制状态或环境 ID 变化时发送。      | 是   |

## 技能与钩子

| API 名称                  | 类型  | 功能概括                  | 实验性 |
| ----------------------- | --- | --------------------- | --- |
| `skills/list`           | 请求  | 列出指定工作目录中的技能（可选强制重载）。 | 否   |
| `skills/extraRoots/set` | 请求  | 替换运行时额外独立技能根目录（不持久化）。 | 否   |
| `hooks/list`            | 请求  | 列出指定工作目录中发现的钩子。       | 否   |
| `skills/config/write`   | 请求  | 写入用户级技能配置（按名称或绝对路径）。  | 否   |
| `skills/changed`        | 通知  | 当监视的本地技能文件发生变化时发送。    | 否   |

## 插件市场与插件管理

| API 名称                | 类型  | 功能概括                                    | 实验性                           |
| --------------------- | --- | --------------------------------------- | ----------------------------- |
| `marketplace/add`     | 请求  | 添加远程插件市场（Git URL 或 GitHub 缩写），持久化到用户配置。 | 否                             |
| `marketplace/remove`  | 请求  | 按名称移除配置的市场，并删除安装根目录。                    | 否                             |
| `marketplace/upgrade` | 请求  | 升级所有或指定的 Git 插件市场。                      | 否                             |
| `plugin/list`         | 请求  | 列出发现的市场和插件状态（含可用性、分类等）。                 | 部分字段实验性（`interface.category`） |
| `plugin/installed`    | 请求  | 列出已安装插件及本地建议安装的插件（不拉取远程目录）。             | 开发中（实验性）                      |
| `plugin/read`         | 请求  | 读取特定插件的详细信息，包含技能、钩子、应用、MCP 服务器等。        | 开发中（实验性）                      |
| `plugin/skill/read`   | 请求  | 按需读取未安装的远程插件技能 markdown 内容。             | 否                             |
| `plugin/install`      | 请求  | 从市场安装插件，返回认证策略和仍需认证的应用。                 | 开发中（实验性）                      |
| `plugin/uninstall`    | 请求  | 卸载本地或远程插件，删除缓存并清除配置。                    | 开发中（实验性）                      |

## MCP 服务器

| API 名称                    | 类型  | 功能概括                             | 实验性 |
| ------------------------- | --- | -------------------------------- | --- |
| `mcpServer/oauth/login`   | 请求  | 为已配置的 MCP 服务器启动 OAuth 登录流程。      | 否   |
| `config/mcpServer/reload` | 请求  | 从磁盘重载 MCP 服务器配置，并刷新已加载线程。        | 否   |
| `mcpServerStatus/list`    | 请求  | 枚举已配置的 MCP 服务器及其工具、认证状态、资源和资源模板。 | 否   |
| `mcpServer/resource/read` | 请求  | 读取 MCP 服务器的资源内容（文本或二进制）。         | 否   |
| `mcpServer/tool/call`     | 请求  | 调用线程已配置的 MCP 服务器上的工具。            | 否   |

## 工具与用户交互

| API 名称                  | 类型  | 功能概括                  | 实验性 |
| ----------------------- | --- | --------------------- | --- |
| `tool/requestUserInput` | 请求  | 向用户提出 1～3 个简短问题并返回答案。 | 是   |

## 配置管理

| API 名称                    | 类型  | 功能概括                             | 实验性 |
| ------------------------- | --- | -------------------------------- | --- |
| `config/read`             | 请求  | 读取磁盘上经过分层解析的有效配置。                | 否   |
| `config/value/write`      | 请求  | 写入单个配置键值到用户 config.toml（支持点分路径）。 | 否   |
| `config/batchWrite`       | 请求  | 原子性批量写入多个配置项，可选热重载线程。            | 否   |
| `configRequirements/read` | 请求  | 读取约束要求（如允许的策略、沙箱模式、网络权限等）。       | 否   |

## 外部 Agent 配置迁移

| API 名称                       | 类型  | 功能概括                                                      | 实验性 |
| ---------------------------- | --- | --------------------------------------------------------- | --- |
| `externalAgentConfig/detect` | 请求  | 检测可迁移的外部 agent 产物（插件、会话等）。                                | 否   |
| `externalAgentConfig/import` | 请求  | 应用选定的迁移项，完成后发送 `externalAgentConfig/import/completed` 通知。 | 否   |

## Windows 沙箱

| API 名称                      | 类型  | 功能概括                                                             | 实验性 |
| --------------------------- | --- | ---------------------------------------------------------------- | --- |
| `windowsSandbox/setupStart` | 请求  | 启动 Windows 沙箱设置（提升或非提升模式），完成后发送 `windowsSandbox/setupCompleted`。 | 否   |

## 反馈上报

| API 名称            | 类型  | 功能概括                                | 实验性 |
| ----------------- | --- | ----------------------------------- | --- |
| `feedback/upload` | 请求  | 提交反馈报告（分类、原因、日志、会话 ID 等），返回追踪线程 ID。 | 否   |

## 其他（应用列表）

| API 名称     | 类型  | 功能概括    | 实验性 |
| ---------- | --- | ------- | --- |
| `app/list` | 请求  | 列出可用应用。 | 否   |