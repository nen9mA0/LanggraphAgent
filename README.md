# Program Workflow

## 项目定位

`program_workflow` 目前的核心实现集中在 `langgraph_codegen/`。这里复用了原 AgentSmith 的前后端，作为一个 LangGraph 代码生成器使用：前端负责画布编辑、LLM/Tools 管理和 Sandbox，后端负责 Flow CRUD、代码生成、注册管理和聊天接口。

## 当前技术栈

- 前端：React + Vite + React Flow + Monaco
- 后端：Python + FastAPI + SQLAlchemy + LangGraph
- 默认后端地址：`http://127.0.0.1:8000`
- 前端默认端口：`http://127.0.0.1:5173`

## 主要能力

- Flow 画布编辑、state schema、保存/加载、节点/边删除
- 从当前 graph 生成 Python LangGraph scaffold
- 本地/远程 LLM 注册、校验和模型列表
- Tool CRUD、代码预览和默认 prompt
- Chatbot sandbox 的流式对话

## 目录

```text
.
|- langgraph_codegen/
|  |- backend/
|  |- frontend/
|  |- package.json
|  `- README.md
|- doc/
|  |- backend_structure.md
|  |- frontend_structure.md
|  `- typescript-langgraph-backend-reference.md
`- readme.md
```

## 启动

后端：

```bash
cd langgraph_codegen/backend
python main.py
```

前端：

```bash
cd langgraph_codegen
npm install
npm run frontend:dev
```

## 文档

- `doc/backend_structure.md`
- `doc/frontend_structure.md`
- `doc/typescript-langgraph-backend-reference.md`
