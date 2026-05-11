# LangGraph Codegen

`langgraph_codegen` 是当前可运行的 LangGraph 代码生成器。它复用了原 AgentSmith 的画布和管理界面，但后端已经切换为 Python FastAPI，生成目标是 Python LangGraph 代码。

## 组成

- Flow canvas：React Flow 画布
- LLM / Tools：registry 管理
- Generated code：Jinja 模板输出 Python LangGraph scaffold
- Sandbox：chatbot playground

## 默认配置

- Backend：`http://127.0.0.1:8000`
- Frontend：`http://127.0.0.1:5173`

## 运行

后端：

```bash
cd backend
python main.py
```

前端：

```bash
npm install
npm run frontend:dev
```
