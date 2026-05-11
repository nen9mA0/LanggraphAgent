import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { clone, now } from './utils.ts';
import { DATA_FILE, DATA_DIR } from './config.ts';
import type { StoreData, StoredFlow, StoredLLM, StoredTool } from './types.ts';

export const DEFAULT_STORE: StoreData = {
  flows: [],
  tools: [
    {
      id: 1,
      name: 'web_search',
      description: 'Default web search tool',
      type: 'web_search',
      config: { library: 'duckduckgo' },
      code: 'def tool(query):\n    return {"query": query}',
      is_active: true,
      parameters: [],
      created_at: new Date(0).toISOString(),
      updated_at: new Date(0).toISOString(),
    },
  ],
  remoteLlms: [
    {
      alias: 'openai-main',
      provider: 'openai',
      type: 'api',
      model: 'gpt-4.1',
      created_at: new Date(0).toISOString(),
      updated_at: new Date(0).toISOString(),
    },
  ],
  localLlms: [
    {
      alias: 'llama-local',
      provider: 'llama-cpp',
      type: 'local',
      path: 'C:/models/llama',
      model: 'model.gguf',
      created_at: new Date(0).toISOString(),
      updated_at: new Date(0).toISOString(),
    },
  ],
  nextFlowId: 1,
  nextToolId: 2,
};

let store: StoreData = clone(DEFAULT_STORE);
let saveQueue: Promise<void> = Promise.resolve();

export async function ensureStoreLoaded() {
  await mkdir(DATA_DIR, { recursive: true });
  if (!existsSync(DATA_FILE)) {
    await writeStore(DEFAULT_STORE);
    store = clone(DEFAULT_STORE);
    return;
  }

  try {
    const raw = await readFile(DATA_FILE, 'utf8');
    store = { ...clone(DEFAULT_STORE), ...JSON.parse(raw) };
  } catch {
    store = clone(DEFAULT_STORE);
  }
}

export async function writeStore(next: StoreData) {
  saveQueue = saveQueue.then(async () => {
    await mkdir(DATA_DIR, { recursive: true });
    await writeFile(DATA_FILE, JSON.stringify(next, null, 2), 'utf8');
  });
  await saveQueue;
}

export async function persist() {
  await writeStore(store);
}

export function getStore() {
  return store;
}

export function setStore(next: StoreData) {
  store = next;
}

export function getFlowById(id: number) {
  return store.flows.find((flow: StoredFlow) => flow.id === id) || null;
}

export function getToolById(id: number) {
  return store.tools.find((tool: StoredTool) => tool.id === id) || null;
}

export function getToolByName(name: string) {
  return store.tools.find((tool: StoredTool) => tool.name === name) || null;
}

export function getRemoteLLM(alias: string) {
  return store.remoteLlms.find((llm: StoredLLM) => llm.alias === alias) || null;
}

export function getLocalLLM(alias: string) {
  return store.localLlms.find((llm: StoredLLM) => llm.alias === alias) || null;
}

export function upsertRemoteLLM(next: StoredLLM) {
  store.remoteLlms = [...store.remoteLlms.filter((item: StoredLLM) => item.alias !== next.alias), next];
}

export function upsertLocalLLM(next: StoredLLM) {
  store.localLlms = [...store.localLlms.filter((item: StoredLLM) => item.alias !== next.alias), next];
}

export function upsertTool(next: StoredTool) {
  store.tools = [...store.tools.filter((item: StoredTool) => item.id !== next.id), next];
}

export function upsertFlow(next: StoredFlow) {
  store.flows = [...store.flows.filter((item: StoredFlow) => item.id !== next.id), next];
}

export function removeRemoteLLM(alias: string) {
  store.remoteLlms = store.remoteLlms.filter((item: StoredLLM) => item.alias !== alias);
}

export function removeLocalLLM(alias: string) {
  store.localLlms = store.localLlms.filter((item: StoredLLM) => item.alias !== alias);
}

export function removeTool(id: number) {
  store.tools = store.tools.filter((item: StoredTool) => item.id !== id);
}

export function removeFlow(id: number) {
  store.flows = store.flows.filter((item: StoredFlow) => item.id !== id);
}

export function nextFlowId() {
  return store.nextFlowId++;
}

export function nextToolId() {
  return store.nextToolId++;
}

export function timestamped<T extends { created_at?: string; updated_at?: string }>(value: T): T {
  return { ...value, created_at: value.created_at || now(), updated_at: now() };
}
