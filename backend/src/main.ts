import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { ensureStoreLoaded, getStore, nextFlowId, nextToolId, persist, getFlowById, getToolById, getRemoteLLM, getLocalLLM, upsertRemoteLLM, upsertLocalLLM, upsertTool, upsertFlow, removeRemoteLLM, removeLocalLLM, removeTool, removeFlow } from './store.ts';
import { PORT, HOST } from './config.ts';
import { health, listResponse, notFound, parseUrl, readJson, send, type HttpMethod } from './http.ts';
import { chatResponse, paramsResponse, streamChat, validateKeyResponse } from './services/chat.ts';
import { codegen } from './services/codegen.ts';
import { executeFlow } from './services/execution.ts';
import { now } from './utils.ts';
import type { FlowPayload, StoredFlow, StoredLLM, StoredTool } from './types.ts';

async function router(req: IncomingMessage, res: ServerResponse) {
  const url = parseUrl(req) as {
    pathname: string;
    searchParams: { get(name: string): string | null };
  };
  const path = url.pathname;
  const method = (req.method || 'GET').toUpperCase() as HttpMethod;

  if (method === 'OPTIONS') return send(res, 204, undefined);

  if (path === '/api/health' && (method === 'GET' || method === 'HEAD')) return health(req, res);

  if (path === '/api/playground/chatbot/chat' && method === 'POST') {
    const body = (await readJson(req)) as { model?: string } | undefined;
    return send(res, 200, chatResponse(body?.model || 'gpt-4.1'), { 'Content-Type': 'application/json' });
  }

  if (path === '/api/playground/chatbot/chat/stream' && method === 'POST') {
    const body = (await readJson(req)) as { model?: string } | undefined;
    return streamChat(req, res, body?.model || 'gpt-4.1');
  }

  if (path === '/api/llms/remote' && method === 'GET') return listResponse(res, getStore().remoteLlms);
  if (path === '/api/llms/local' && method === 'GET') return listResponse(res, getStore().localLlms);

  if (path === '/api/llms/remote/validate-key' && method === 'POST') {
    const body = (await readJson(req)) as { api_key?: string } | undefined;
    return send(res, 200, validateKeyResponse(body?.api_key), { 'Content-Type': 'application/json' });
  }

  if (path === '/api/llms/remote' && method === 'POST') {
    const body = (await readJson(req)) as Partial<StoredLLM>;
    const next: StoredLLM = {
      alias: body?.alias || `remote-${getStore().remoteLlms.length + 1}`,
      provider: body?.provider || 'openai',
      type: 'api',
      api_key: body?.api_key,
      base_url: body?.base_url,
      model: body?.model,
      created_at: now(),
      updated_at: now(),
    };
    upsertRemoteLLM(next);
    await persist();
    return send(res, 200, next, { 'Content-Type': 'application/json' });
  }

  if (path === '/api/llms/local' && method === 'POST') {
    const body = (await readJson(req)) as Partial<StoredLLM>;
    const next: StoredLLM = {
      alias: body?.alias || `local-${getStore().localLlms.length + 1}`,
      provider: body?.provider || 'llama-cpp',
      type: 'local',
      path: body?.path,
      model: body?.model,
      created_at: now(),
      updated_at: now(),
    };
    upsertLocalLLM(next);
    await persist();
    return send(res, 200, next, { 'Content-Type': 'application/json' });
  }

  const remoteMatch = path.match(/^\/api\/llms\/remote\/([^/]+)(?:\/([^/]+))?(?:\/([^/]+))?$/);
  const localMatch = path.match(/^\/api\/llms\/local\/([^/]+)(?:\/([^/]+))?(?:\/([^/]+))?$/);

  if (remoteMatch) {
    const alias = decodeURIComponent(remoteMatch[1]);
    const segment = remoteMatch[2];
    if (!segment && method === 'GET') {
      const llm = getRemoteLLM(alias);
      return llm ? send(res, 200, llm, { 'Content-Type': 'application/json' }) : notFound(res);
    }
    if (!segment && method === 'PUT') {
      const body = (await readJson(req)) as Partial<StoredLLM>;
      const current = getRemoteLLM(alias);
      if (!current) return notFound(res);
      const updated = { ...current, ...body, alias: body?.alias || current.alias, updated_at: now() };
      upsertRemoteLLM(updated);
      await persist();
      return send(res, 200, updated, { 'Content-Type': 'application/json' });
    }
    if (!segment && method === 'DELETE') {
      const current = getRemoteLLM(alias);
      if (!current) return notFound(res);
      removeRemoteLLM(alias);
      await persist();
      return send(res, 200, current, { 'Content-Type': 'application/json' });
    }
    if (segment === 'models' && method === 'GET') return send(res, 200, { models: ['gpt-4.1', 'gpt-4.1-mini'] }, { 'Content-Type': 'application/json' });
    if (segment === 'embeddings_models' && method === 'GET') return send(res, 200, { embeddings_models: ['text-embedding-3-large'] }, { 'Content-Type': 'application/json' });
    if (segment === 'parameters' && method === 'GET') return send(res, 200, paramsResponse(), { 'Content-Type': 'application/json' });
    if (segment === 'validate-key' && method === 'GET') {
      const llm = getRemoteLLM(alias);
      return send(res, 200, validateKeyResponse(llm?.api_key), { 'Content-Type': 'application/json' });
    }
  }

  if (localMatch) {
    const alias = decodeURIComponent(localMatch[1]);
    const segment = localMatch[2];
    if (!segment && method === 'GET') {
      const llm = getLocalLLM(alias);
      return llm ? send(res, 200, llm, { 'Content-Type': 'application/json' }) : notFound(res);
    }
    if (!segment && method === 'PUT') {
      const body = (await readJson(req)) as Partial<StoredLLM>;
      const current = getLocalLLM(alias);
      if (!current) return notFound(res);
      const updated = { ...current, ...body, alias: body?.alias || current.alias, updated_at: now() };
      upsertLocalLLM(updated);
      await persist();
      return send(res, 200, updated, { 'Content-Type': 'application/json' });
    }
    if (!segment && method === 'DELETE') {
      const current = getLocalLLM(alias);
      if (!current) return notFound(res);
      removeLocalLLM(alias);
      await persist();
      return send(res, 200, current, { 'Content-Type': 'application/json' });
    }
    if (segment === 'models' && method === 'GET') return send(res, 200, { models: ['model-a', 'model-b'] }, { 'Content-Type': 'application/json' });
    if (segment === 'embeddings_models' && method === 'GET') return send(res, 200, { embeddings_models: ['nomic-embed-text'] }, { 'Content-Type': 'application/json' });
    if (segment === 'parameters' && method === 'GET') return send(res, 200, paramsResponse(), { 'Content-Type': 'application/json' });
    if (segment === 'provider' && localMatch[3] === 'models' && method === 'GET') return send(res, 200, { models: ['model-a', 'model-b'] }, { 'Content-Type': 'application/json' });
  }

  if (path === '/api/llms/local/provider/lm-studio/models' && method === 'GET') {
    return send(res, 200, { models: ['model-a', 'model-b'] }, { 'Content-Type': 'application/json' });
  }

  if (path === '/api/llms/local/llama-cpp/recommended-path' && method === 'GET') {
    return send(res, 200, { path: 'C:/models/llama' }, { 'Content-Type': 'application/json' });
  }

  if (path === '/api/tools' || path === '/api/tools/') {
    if (method === 'GET') return listResponse(res, getStore().tools);
    if (method === 'POST') {
      const body = (await readJson(req)) as Partial<StoredTool>;
      const id = nextToolId();
      const next: StoredTool = {
        id,
        name: body?.name || `tool-${id}`,
        description: body?.description,
        type: body?.type || 'custom_code',
        config: body?.config || {},
        code: body?.code || '',
        is_active: body?.is_active ?? true,
        parameters: body?.parameters || [],
        created_at: now(),
        updated_at: now(),
      };
      upsertTool(next);
      await persist();
      return send(res, 200, next, { 'Content-Type': 'application/json' });
    }
  }

  if (path === '/api/tools/preview_code' && method === 'POST') {
    const body = (await readJson(req)) as Partial<StoredTool> | undefined;
    const code = `def ${String(body?.name || 'tool').replace(/[^a-zA-Z0-9_]/g, '_')}(query):\n    return {"query": query}`;
    return send(res, 200, { code }, { 'Content-Type': 'application/json' });
  }

  const toolDefaultMatch = path.match(/^\/api\/tools\/([^/]+)\/default_agent_prompts$/);
  if (toolDefaultMatch && method === 'GET') {
    return send(
      res,
      200,
      {
        system_prompt: 'You are a helpful assistant.',
        user_prompt: `Use the ${decodeURIComponent(toolDefaultMatch[1])} tool carefully.`,
      },
      { 'Content-Type': 'application/json' }
    );
  }

  const toolMatch = path.match(/^\/api\/tools\/(\d+)$/);
  if (toolMatch) {
    const id = Number(toolMatch[1]);
    const tool = getToolById(id);
    if (!tool) return notFound(res);
    if (method === 'GET') return send(res, 200, tool, { 'Content-Type': 'application/json' });
    if (method === 'PUT') {
      const body = (await readJson(req)) as Partial<StoredTool>;
      const updated = { ...tool, ...body, updated_at: now() };
      upsertTool(updated);
      await persist();
      return send(res, 200, updated, { 'Content-Type': 'application/json' });
    }
    if (method === 'DELETE') {
      removeTool(id);
      await persist();
      return send(res, 200, tool, { 'Content-Type': 'application/json' });
    }
  }

  const flowBaseMatch = path.match(/^\/api\/flows\/(\d+)$/);
  const flowActionMatch = path.match(/^\/api\/flows\/(\d+)\/(run|test)$/);

  if (path === '/api/flows' || path === '/api/flows/') {
    if (method === 'GET') {
      const limit = Number(url.searchParams.get('limit') || '');
      const items = Number.isFinite(limit) && limit > 0 ? getStore().flows.slice(0, limit) : getStore().flows;
      return listResponse(res, items);
    }
    if (method === 'POST') {
      const body = (await readJson(req)) as FlowPayload;
      const id = nextFlowId();
      const next: StoredFlow = {
        id,
        name: body?.name || `Flow ${id}`,
        description: body?.description,
        graph: body?.graph || { nodes: [], edges: [] },
        state: body?.state || { fields: [] },
        created_at: now(),
        updated_at: now(),
      };
      upsertFlow(next);
      await persist();
      return send(res, 200, next, { 'Content-Type': 'application/json' });
    }
  }

  if (path === '/api/flows/generate/code' && method === 'POST') {
    const body = (await readJson(req)) as FlowPayload;
    return send(res, 200, { code: codegen(body) }, { 'Content-Type': 'application/json' });
  }

  if (flowBaseMatch) {
    const id = Number(flowBaseMatch[1]);
    const flow = getFlowById(id);
    if (!flow) return notFound(res);
    if (method === 'GET') return send(res, 200, flow, { 'Content-Type': 'application/json' });
    if (method === 'PUT') {
      const body = (await readJson(req)) as FlowPayload;
      const updated = { ...flow, ...body, id, updated_at: now() };
      upsertFlow(updated);
      await persist();
      return send(res, 200, updated, { 'Content-Type': 'application/json' });
    }
    if (method === 'DELETE') {
      removeFlow(id);
      await persist();
      return send(res, 200, flow, { 'Content-Type': 'application/json' });
    }
  }

  if (flowActionMatch && method === 'POST') {
    const id = Number(flowActionMatch[1]);
    const action = flowActionMatch[2];
    const flow = getFlowById(id);
    if (!flow) return notFound(res);
    const input = ((await readJson(req)) || {}) as Record<string, unknown>;
    const execution = executeFlow(flow, action as 'run' | 'test', input);
    return send(
      res,
      200,
      {
        status: 'success',
        result: {
          flow_id: id,
          action,
          name: flow.name,
          input,
          message: `${action.toUpperCase()} flow completed`,
          execution,
        },
      },
      { 'Content-Type': 'application/json' }
    );
  }

  notFound(res);
}

await ensureStoreLoaded();

createServer((req: IncomingMessage, res: ServerResponse) => {
  void router(req, res).catch((error) => {
    send(res, 500, { detail: error instanceof Error ? error.message : 'Internal server error' }, { 'Content-Type': 'application/json' });
  });
}).listen(PORT, HOST, () => {
  console.log(`Minimal backend listening on http://${HOST}:${PORT}`);
});
