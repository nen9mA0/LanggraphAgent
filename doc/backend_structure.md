# 后端结构

`langgraph_codegen/backend` 是一个 Python FastAPI 后端，负责 flow 持久化、LLM/Tool registry、代码生成和聊天 playground。

## 目录概览

```text
backend/
|- main.py                 # FastAPI 入口，挂载 /api 路由和 health
|- api/                    # HTTP 路由
|- core/                   # 配置、启动、auth、加密
|- crud/                   # 数据库读写封装
|- db/                     # SQLAlchemy session/base/init
|- models/                 # ORM models
|- schemas/                # Pydantic request/response models
|- services/               # 业务服务
|  |- flows/               # codegen / runner / parser
|  |- llms/                # 远程与本地 LLM 适配
|  |- sandbox/chatbot/     # chatbot playground service
|  `- tools/               # Tool 工厂、校验与生成
|- templates/              # Jinja2 templates
|- tests/                  # tests
`- utils/                  # helpers
```

## 关键入口

- `main.py`：FastAPI app，CORS，`/api/health`，挂载 `llms`、`flows`、`tools`、`chatbot`
- `api/flows.py`：Flow CRUD，`/generate/code`，`/run`，`/test`
- `services/flows/codegen.py`：读取 graph，拉取 DB 中的 LLM/Tool 定义，渲染模板
- `templates/flows/langgraph_main.jinja2`：生成 Python LangGraph scaffold
- `services/tools/generator.py`：tool 工厂，按配置实例化 RAG / web search / API call
- `services/llms/factory.py`：remote/local provider factory
- `services/sandbox/chatbot/llm_service.py`：sandbox 聊天服务

## API 面

### Flow

- `GET /api/flows`
- `POST /api/flows`
- `GET /api/flows/{id}`
- `PUT /api/flows/{id}`
- `DELETE /api/flows/{id}`
- `POST /api/flows/generate/code`
- `POST /api/flows/{id}/run`
- `POST /api/flows/{id}/test`

### Tool

- `GET /api/tools`
- `POST /api/tools`
- `GET /api/tools/{id}`
- `PUT /api/tools/{id}`
- `DELETE /api/tools/{id}`
- `POST /api/tools/preview_code`
- `GET /api/tools/{name}/default_agent_prompts`

### LLM

- `GET /api/llms/remote`
- `POST /api/llms/remote`
- `GET /api/llms/remote/{alias}`
- `PUT /api/llms/remote/{alias}`
- `DELETE /api/llms/remote/{alias}`
- `POST /api/llms/remote/validate-key`
- `GET /api/llms/remote/{alias}/validate-key`
- `GET /api/llms/remote/{alias}/models`
- `GET /api/llms/remote/{alias}/embeddings_models`
- `GET /api/llms/remote/{alias}/parameters`
- `GET /api/llms/local`
- `POST /api/llms/local`
- `GET /api/llms/local/{alias}`
- `PUT /api/llms/local/{alias}`
- `DELETE /api/llms/local/{alias}`
- `GET /api/llms/local/{alias}/models`
- `GET /api/llms/local/{alias}/embeddings_models`
- `GET /api/llms/local/{alias}/parameters`
- `GET /api/llms/local/provider/{provider}/models`
- `GET /api/llms/local/{provider}/recommended-path`

### Playground

- `POST /api/playground/chatbot/chat`
- `POST /api/playground/chatbot/chat/stream`

## 当前状态

- `generate/code` 已经是当前的代码生成主路径，输出 Python LangGraph 代码。
- `run` 和 `test` 目前仍是模拟执行，尚未接入完整 LangGraph runtime。
- 启动时会创建数据库和加密 key。
