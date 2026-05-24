# Backend Guide

此目录是 `langgraph_codegen` 的 Python FastAPI 后端。关注点是 HTTP API、数据库模型、代码生成、LLM/Tool registry，以及 sandbox 接口。

## 建议阅读顺序

1. `main.py`
2. `api/flows.py`
3. `schemas/flows.py`
4. `crud/flows.py`
5. `services/flows/codegen.py`
6. `templates/flows/langgraph_main.jinja2`

如果改的不是 Flow，再转向对应的 `api/`、`schemas/`、`crud/`、`services/` 分组。

## 任务到文件

- 改 Flow CRUD 或 HTTP 行为
  - `api/flows.py`
  - `crud/flows.py`
  - `schemas/flows.py`
  - `models/flows.py`
- 改 graph -> Python LangGraph scaffold 的生成规则
  - `services/flows/codegen.py`
  - `templates/flows/langgraph_main.jinja2`
- 改 Flow 执行或测试逻辑
  - `api/flows.py`
  - `services/flows/runner.py`
  - 注意：当前 `run` / `test` 还是偏占位实现
- 改 LLM registry
  - `api/llms.py`
  - `crud/llms.py`
  - `schemas/llms.py`
  - `models/llms.py`
  - `services/llms/`
- 改 Tool registry 或新 Tool 类型
  - `api/tools.py`
  - `crud/tools.py`
  - `schemas/tools.py`
  - `models/tools.py`
  - `services/tools/`
  - `templates/tools/`
- 改 chatbot sandbox
  - `api/chatbot.py`
  - `services/sandbox/chatbot/llm_service.py`
- 改启动、配置、鉴权、加密、数据库
  - `core/`
  - `db/`

## 当前代码真相

- `generate/code` 读取前端传来的 graph/state，拉取数据库里的 LLM/Tool 定义，再渲染 Jinja 模板。
- 生成目标是 Python LangGraph scaffold。
- `run` / `test` 还没有接上完整 runtime；如果用户要“真正执行 graph”，通常需要先补这部分。
- Flow、Tool、LLM 定义目前是 registry + DB 驱动，不是直接写进 graph 源码。

## 改代码生成时重点看

- 节点数据来源
  - `schemas/flows.py`
- 生成逻辑
  - `services/flows/codegen.py`
- 模板输出
  - `templates/flows/langgraph_main.jinja2`
- 前端发包形状
  - `../frontend/src/components/canvas/CodeSidebar.tsx`

## 验证

- 后端目前的测试覆盖不完整。
- 已有显式测试主要在 `tests/tools/test_chroma_rag_generator.py`。
- 改 Flow/LLM/Tool API 后，最好至少做局部接口验证或启动检查。
