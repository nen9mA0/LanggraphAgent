import { createServer, IncomingMessage, ServerResponse } from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'HEAD' | 'OPTIONS';

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
type RecordMap = Record<string, JsonValue>;

interface FlowPayload {
  name: string;
  description?: string;
  graph: { nodes: JsonValue[]; edges: JsonValue[] };
  state: { fields: JsonValue[] };
}

interface StoredFlow extends FlowPayload {
  id: number;
  created_at: string;
  updated_at: string;
}

interface StoredTool {
  id: number;
  name: string;
  description?: string;
  type: string;
  config?: RecordMap;
  code?: string;
  is_active?: boolean;
  parameters?: JsonValue[];
  created_at: string;
  updated_at: string;
}

interface StoredLLM {
  alias: string;
  provider: string;
  type: 'api' | 'local';
  api_key?: string;
  base_url?: string;
  path?: string;
  model?: string;
  created_at: string;
  updated_at: string;
}

interface StoreData {
  flows: StoredFlow[];
  tools: StoredTool[];
  remoteLlms: StoredLLM[];
  localLlms: StoredLLM[];
  nextFlowId: number;
  nextToolId: number;
}

interface FlowNodeData {
  label?: string;
  description?: string;
  node?: {
    inputFormat?: string;
    outputMode?: 'text' | 'structured' | string;
    systemPrompt?: string;
    userPrompt?: string;
  };
  llm?: {
    alias?: string;
    provider?: string;
    model?: string;
    type?: 'api' | 'local' | string;
  };
  tool?: {
    id?: string | number;
    name?: string;
    description?: string;
  } | null;
}

interface FlowNodeRecord {
  id: string;
  type: string;
  data?: FlowNodeData;
}

interface FlowEdgeRecord {
  id?: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
}

interface FlowExecutionStep {
  index: number;
  node_id: string;
  label: string;
  type: string;
  input: unknown;
  output: Record<string, unknown>;
  next_node_id: string | null;
}

interface FlowExecutionSummary {
  mode: 'run' | 'test';
  completed: boolean;
  started_from: string | null;
  ended_at: string | null;
  visited_node_ids: string[];
  steps: FlowExecutionStep[];
  final_state: Record<string, unknown>;
  warnings: string[];
}

const PORT = Number(process.env.PORT || 8000);
const HOST = process.env.HOST || '0.0.0.0';
const DATA_DIR = join(process.cwd(), 'backend', 'data');
const DATA_FILE = join(DATA_DIR, 'store.json');

const DEFAULT_STORE: StoreData = {
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

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

const sanitizeIdentifier = (value: string) =>
  value
    .replace(/[^a-zA-Z0-9_]/g, '_')
    .replace(/^(\d)/, '_$1')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '') || 'flow';

const toPascalCase = (value: string) =>
  sanitizeIdentifier(value)
    .split('_')
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join('') || 'Flow';

let store: StoreData = clone(DEFAULT_STORE);
let saveQueue: Promise<void> = Promise.resolve();

async function ensureStoreLoaded() {
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

async function writeStore(next: StoreData) {
  saveQueue = saveQueue.then(async () => {
    await mkdir(DATA_DIR, { recursive: true });
    await writeFile(DATA_FILE, JSON.stringify(next, null, 2), 'utf8');
  });
  await saveQueue;
}

async function persist() {
  await writeStore(store);
}

function now() {
  return new Date().toISOString();
}

function send(res: ServerResponse, status: number, body?: unknown, headers: Record<string, string> = {}) {
  res.writeHead(status, {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Accept, Authorization, X-Requested-With',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,HEAD,OPTIONS',
    ...headers,
  });
  if (body === undefined || body === null) {
    res.end();
    return;
  }
  if (typeof body === 'string') {
    res.end(body);
    return;
  }
  res.end(JSON.stringify(body));
}

function notFound(res: ServerResponse) {
  send(res, 404, { detail: 'Not found' }, { 'Content-Type': 'application/json' });
}

function parseUrl(req: IncomingMessage) {
  return new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
}

async function readJson(req: IncomingMessage) {
  const chunks: Array<{ toString(encoding?: string): string }> = [];
  const iterable = req as unknown as AsyncIterable<Uint8Array | string>;
  for await (const chunk of iterable) chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  if (!chunks.length) return undefined;
  const text = Buffer.concat(chunks).toString('utf8');
  return text ? JSON.parse(text) : undefined;
}

function health(_req: IncomingMessage, res: ServerResponse) {
  send(res, 200, { status: 'ok' }, { 'Content-Type': 'application/json' });
}

function listResponse<T>(res: ServerResponse, items: T[]) {
  send(res, 200, items, { 'Content-Type': 'application/json' });
}

function getFlowById(id: number) {
  return store.flows.find((flow) => flow.id === id) || null;
}

function getToolById(id: number) {
  return store.tools.find((tool) => tool.id === id) || null;
}

function getToolByName(name: string) {
  return store.tools.find((tool) => tool.name === name) || null;
}

function getRemoteLLM(alias: string) {
  return store.remoteLlms.find((llm) => llm.alias === alias) || null;
}

function getLocalLLM(alias: string) {
  return store.localLlms.find((llm) => llm.alias === alias) || null;
}

function findToolForNode(node: FlowNodeRecord) {
  const toolRef = node.data?.tool;
  if (!toolRef) return null;

  const byId = toolRef.id !== undefined
    ? store.tools.find((tool) => String(tool.id) === String(toolRef.id))
    : null;
  if (byId) return byId;

  if (toolRef.name) {
    return store.tools.find((tool) => tool.name === toolRef.name) || null;
  }

  return null;
}

function findLLMForNode(node: FlowNodeRecord) {
  const llmRef = node.data?.llm;
  if (!llmRef?.alias) return null;

  if (llmRef.type === 'local') {
    return getLocalLLM(llmRef.alias) || getRemoteLLM(llmRef.alias);
  }

  return getRemoteLLM(llmRef.alias) || getLocalLLM(llmRef.alias);
}

function toTypeScriptPropertyKey(value: string) {
  return /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(value) ? value : JSON.stringify(value);
}

function toTypeScriptFieldType(rawType: unknown, isOptional = false): string {
  const source = typeof rawType === 'string' ? rawType.trim() : '';
  const fallback = isOptional ? 'unknown | null' : 'unknown';
  if (!source) return fallback;

  const normalized = source.toLowerCase().replace(/\s+/g, '');
  const optionalMatch = normalized.match(/^optional\[(.+)\]$/);
  if (optionalMatch) {
    return `${toTypeScriptFieldType(optionalMatch[1], false)} | null`;
  }

  const listMatch = normalized.match(/^(list|array)\[(.+)\]$/);
  if (listMatch) {
    return `${toTypeScriptFieldType(listMatch[2], false)}[]${isOptional ? ' | null' : ''}`;
  }

  if (normalized.endsWith('[]')) {
    return `${toTypeScriptFieldType(normalized.slice(0, -2), false)}[]${isOptional ? ' | null' : ''}`;
  }

  switch (normalized) {
    case 'str':
    case 'string':
      return isOptional ? 'string | null' : 'string';
    case 'int':
    case 'float':
    case 'number':
      return isOptional ? 'number | null' : 'number';
    case 'bool':
    case 'boolean':
      return isOptional ? 'boolean | null' : 'boolean';
    case 'dict':
    case 'object':
    case 'json':
    case 'map':
    case 'record':
      return isOptional ? 'Record<string, unknown> | null' : 'Record<string, unknown>';
    case 'any':
    case 'unknown':
      return isOptional ? 'unknown | null' : 'unknown';
    default:
      return fallback;
  }
}

function renderStateAnnotation(field: any) {
  const annotation = field?.fieldMetadata?.langgraph_annotation;
  if (annotation === 'add_messages') {
    return 'Annotation<unknown[]>({ reducer: (left, right) => left.concat(Array.isArray(right) ? right : [right]), default: () => [] })';
  }

  return `Annotation<${toTypeScriptFieldType(field?.type, Boolean(field?.isOptional))}>`;
}

function codegen(flow: FlowPayload) {
  const className = toPascalCase(flow.name || 'Flow');
  const nodes = Array.isArray(flow.graph?.nodes) ? flow.graph.nodes : [];
  const edges = Array.isArray(flow.graph?.edges) ? flow.graph.edges : [];
  const fields = Array.isArray(flow.state?.fields) ? flow.state.fields : [];
  const nodeTypeById = new Map<string, string>();
  for (const node of nodes) {
    const nodeId = typeof (node as { id?: unknown }).id === 'string' ? (node as { id: string }).id : undefined;
    const nodeType = typeof (node as { type?: unknown }).type === 'string' ? (node as { type: string }).type : 'node';
    if (nodeId) nodeTypeById.set(nodeId, nodeType);
  }

  const nodeEntries = nodes.map((node: any, index: number) => {
    const nodeRecord = node as FlowNodeRecord;
    const nodeId = typeof node?.id === 'string' ? node.id : `node-${index + 1}`;
    const rawLabel = typeof node?.data?.label === 'string' && node.data.label.trim() ? node.data.label : nodeId;
    const fnName = `node_${sanitizeIdentifier(rawLabel)}`;
    return {
      nodeId,
      rawLabel,
      fnName,
      type: typeof node?.type === 'string' ? node.type : 'node',
      tool: findToolForNode(nodeRecord),
      llm: findLLMForNode(nodeRecord),
    };
  });
  const executableNodes = nodeEntries.filter((node) => node.type !== 'start' && node.type !== 'end');

  const lines: string[] = [
    'import { Annotation, END, START, StateGraph } from "@langchain/langgraph";',
    '',
    `// Generated for ${flow.name || 'Untitled Flow'}`,
    `const ${className}StateAnnotation = Annotation.Root({`,
  ];

  if (fields.length) {
    fields.forEach((field: any) => {
      const rawName = typeof field?.name === 'string' && field.name.trim() ? field.name.trim() : 'state';
      lines.push(`  ${toTypeScriptPropertyKey(rawName)}: ${renderStateAnnotation(field)},`);
    });
  }

  lines.push('});');
  lines.push('');
  lines.push(`export type ${className}State = typeof ${className}StateAnnotation.State;`);
  lines.push('');

  if (fields.length) {
    lines.push('// State schema');
    lines.push(`export type ${className}StateShape = {`);
    fields.forEach((field: any) => {
      const rawName = typeof field?.name === 'string' && field.name.trim() ? field.name.trim() : 'state';
      const isOptional = Boolean(field?.isOptional);
      const fieldType = toTypeScriptFieldType(field?.type, isOptional);
      lines.push(`  ${toTypeScriptPropertyKey(rawName)}${isOptional ? '?' : ''}: ${fieldType};`);
    });
    lines.push('};');
    lines.push('');
  }

  if (executableNodes.length) {
    lines.push('// Node stubs');
    executableNodes.forEach((node) => {
      lines.push(`async function ${node.fnName}(state: ${className}State): Promise<Partial<${className}State>> {`);
      lines.push(`  // ${node.rawLabel} (${node.nodeId})`);
      if (node.llm) {
        lines.push(`  // LLM: ${node.llm.alias} (${node.llm.provider}${node.llm.model ? ` / ${node.llm.model}` : ''})`);
      }
      if (node.tool) {
        lines.push(`  // Tool: ${node.tool.name}`);
      }
      lines.push('  void state;');
      lines.push('  return {};');
      lines.push('}');
      lines.push('');
    });
  }

  lines.push(`const workflow = new StateGraph(${className}StateAnnotation);`);
  lines.push('');
  lines.push('// Nodes');
  executableNodes.forEach((node) => {
    lines.push(`workflow.addNode(${JSON.stringify(node.nodeId)}, ${node.fnName});`);
  });

  if (edges.length) {
    lines.push('');
    lines.push('// Edges');
    edges.forEach((edge: any, index: number) => {
      const source = typeof edge?.source === 'string' ? edge.source : '';
      const target = typeof edge?.target === 'string' ? edge.target : '';
      const sourceType = nodeTypeById.get(source);
      const targetType = nodeTypeById.get(target);
      const fromRef = sourceType === 'start' ? 'START' : JSON.stringify(source);
      const toRef = targetType === 'end' ? 'END' : JSON.stringify(target);
      lines.push(`// edge ${index + 1}: ${JSON.stringify(edge)}`);
      if (source && target) {
        lines.push(`workflow.addEdge(${fromRef}, ${toRef});`);
      }
    });
  }

  lines.push('');
  lines.push('export const compiledGraph = workflow.compile();');
  return lines.join('\n');
}

function chatResponse(model: string) {
  return {
    id: `chatcmpl-${Date.now()}`,
    object: 'chat.completion',
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [
      {
        index: 0,
        message: { role: 'assistant', content: 'This is a minimal backend response.' },
        finish_reason: 'stop',
      },
    ],
    usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
  };
}

function paramsResponse() {
  return {
    temperature: { type: 'number', min: 0, max: 2, default: 0.7 },
    topP: { type: 'number', min: 0, max: 1, default: 1 },
    frequencyPenalty: { type: 'number', min: 0, max: 2, default: 0 },
    presencePenalty: { type: 'number', min: 0, max: 2, default: 0 },
    maxTokens: { type: 'number', min: 1, max: 8192, default: 1000 },
  };
}

function validateKeyResponse(apiKey?: string) {
  const valid = Boolean(apiKey?.trim());
  return {
    valid,
    message: valid ? 'API key is valid' : 'API key is required',
  };
}

async function streamChat(req: IncomingMessage, res: ServerResponse, model: string) {
  res.writeHead(200, {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Accept, Authorization, X-Requested-With',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,HEAD,OPTIONS',
    'Content-Type': 'text/event-stream; charset=utf-8',
    Connection: 'keep-alive',
    'Cache-Control': 'no-cache',
  });
  (res as ServerResponse & { flushHeaders?: () => void }).flushHeaders?.();
  const text = 'This is a minimal backend response.';
  const chunkId = `chatcmpl-${Date.now()}`;
  for (const chunk of [text.slice(0, 10), text.slice(10, 20), text.slice(20)]) {
    res.write(
      `data: ${JSON.stringify({
        choices: [{ delta: { content: chunk }, index: 0, finish_reason: null }],
        model,
        created: Math.floor(Date.now() / 1000),
        id: chunkId,
        object: 'chat.completion.chunk',
      })}\n\n`
    );
  }
  res.write('data: [DONE]\n\n');
  res.end();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function stringifyValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value === null || value === undefined) return '';
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function parseInitialValue(value: unknown): unknown {
  if (value === undefined || value === null) return null;
  if (typeof value !== 'string') return value;

  const trimmed = value.trim();
  if (!trimmed || trimmed === 'None' || trimmed === 'null') return null;
  if (trimmed === '[]' || trimmed === '{}') return JSON.parse(trimmed);
  if (trimmed === 'true') return true;
  if (trimmed === 'false') return false;
  if (/^-?\d+(?:\.\d+)?$/.test(trimmed)) return Number(trimmed);

  if ((trimmed.startsWith('[') && trimmed.endsWith(']')) || (trimmed.startsWith('{') && trimmed.endsWith('}'))) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return value;
    }
  }

  return value;
}

function buildInitialState(flow: StoredFlow, input: Record<string, unknown>) {
  const state: Record<string, unknown> = {};
  const fields = Array.isArray(flow.state?.fields) ? flow.state.fields : [];

  for (const field of fields) {
    if (!isRecord(field)) continue;
    const name = typeof field.name === 'string' ? field.name : '';
    if (!name) continue;
    state[name] = parseInitialValue(field.initialValue);
  }

  const mergedInput = isRecord(input) ? input : {};
  for (const [key, value] of Object.entries(mergedInput)) {
    state[key] = value;
  }

  if (!Array.isArray(state.messages)) {
    state.messages = [];
  }

  return state;
}

function getFlowGraph(flow: StoredFlow) {
  const rawNodes = Array.isArray(flow.graph?.nodes) ? flow.graph.nodes : [];
  const nodes: FlowNodeRecord[] = rawNodes
    .filter(isRecord)
    .map((node, index) => {
      const record = node as Record<string, unknown>;
      return {
        id: typeof record.id === 'string' ? record.id : `node-${index + 1}`,
        type: typeof record.type === 'string' ? record.type : 'node',
        data: isRecord(record.data) ? (record.data as FlowNodeData) : {},
      };
    });

  const rawEdges = Array.isArray(flow.graph?.edges) ? flow.graph.edges : [];
  const edges: FlowEdgeRecord[] = rawEdges
    .filter(isRecord)
    .map((edge, index) => {
      const record = edge as Record<string, unknown>;
      return {
        id: typeof record.id === 'string' ? record.id : `edge-${index + 1}`,
        source: typeof record.source === 'string' ? record.source : '',
        target: typeof record.target === 'string' ? record.target : '',
        sourceHandle: typeof record.sourceHandle === 'string' ? record.sourceHandle : null,
        targetHandle: typeof record.targetHandle === 'string' ? record.targetHandle : null,
      };
    });

  return { nodes, edges };
}

function getNodeLabel(node: FlowNodeRecord) {
  return node.data?.label?.trim() || node.id;
}

function getNodeInputFormat(node: FlowNodeRecord) {
  return node.data?.node?.inputFormat || 'messages[-1]["content"]';
}

function resolveNodeInput(inputFormat: string, state: Record<string, unknown>) {
  if (inputFormat === 'messages') return state.messages || [];
  if (inputFormat === 'messages[-1]["content"]' || inputFormat === "messages[-1]['content']") {
    const messages = Array.isArray(state.messages) ? state.messages : [];
    const last = messages.length ? messages[messages.length - 1] : null;
    if (typeof last === 'string') return last;
    if (isRecord(last) && typeof last.content === 'string') return last.content;
    return last ?? '';
  }
  if (inputFormat === 'message_type' || inputFormat === 'next') return state[inputFormat] ?? null;
  return state[inputFormat] ?? null;
}

function appendMessage(state: Record<string, unknown>, content: string) {
  const messages = Array.isArray(state.messages) ? [...state.messages] : [];
  messages.push({ role: 'assistant', content });
  state.messages = messages;
}

function selectNextNode(
  current: FlowNodeRecord,
  outgoingEdges: Array<FlowEdgeRecord>,
  state: Record<string, unknown>,
  nodeById: Map<string, FlowNodeRecord>,
  warnings: string[]
) {
  if (!outgoingEdges.length) return null;

  const candidates = [state.next, state.message_type, getNodeLabel(current)]
    .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    .map((value) => value.trim());

  if (current.type === 'router') {
    for (const candidate of candidates) {
      const matchingEdge = outgoingEdges.find((edge) => {
        const targetNode = nodeById.get(edge.target);
        return (
          edge.target === candidate ||
          edge.sourceHandle === candidate ||
          edge.targetHandle === candidate ||
          targetNode?.id === candidate ||
          getNodeLabel(targetNode || { id: '', type: '', data: {} }) === candidate
        );
      });

      if (matchingEdge) return matchingEdge.target;
    }

    const defaultEdge = outgoingEdges.find((edge) => !edge.sourceHandle);
    if (defaultEdge) return defaultEdge.target;
    warnings.push(`Router node "${current.id}" had no matching route; using the first outgoing edge.`);
    return outgoingEdges[0]?.target ?? null;
  }

  return outgoingEdges[0]?.target ?? null;
}

function executeFlow(flow: StoredFlow, mode: 'run' | 'test', input: Record<string, unknown>): FlowExecutionSummary {
  const { nodes, edges } = getFlowGraph(flow);
  const warnings: string[] = [];
  const nodeById = new Map(nodes.map((node) => [node.id, node] as const));
  const outgoingBySource = new Map<string, FlowEdgeRecord[]>();

  for (const edge of edges) {
    if (!edge.source) continue;
    const current = outgoingBySource.get(edge.source) || [];
    current.push(edge);
    outgoingBySource.set(edge.source, current);
  }

  const incomingCounts = new Map<string, number>();
  for (const edge of edges) {
    incomingCounts.set(edge.target, (incomingCounts.get(edge.target) || 0) + 1);
  }

  const startNode: FlowNodeRecord | null = nodes.find((node) => node.type === 'start')
    || nodes.find((node) => (incomingCounts.get(node.id) || 0) === 0 && node.type !== 'end')
    || nodes[0]
    || null;

  const state = buildInitialState(flow, input);
  const steps: FlowExecutionStep[] = [];
  const visitedNodeIds: string[] = [];
  let currentNode: FlowNodeRecord | null = startNode;
  let endedAt: string | null = null;
  const maxSteps = Math.max(nodes.length * 4, 1);

  if (!currentNode) {
    warnings.push('Flow has no nodes to execute.');
  }

  for (let index = 0; currentNode && index < maxSteps; index += 1) {
    const node = currentNode;
    const inputFormat = getNodeInputFormat(node);
    const nodeInput = resolveNodeInput(inputFormat, state);
    const outgoingEdges = outgoingBySource.get(node.id) || [];
    const label = getNodeLabel(node);
    const output: Record<string, unknown> = {
      mode,
      node_id: node.id,
      node_type: node.type,
      label,
      input_format: inputFormat,
      input: nodeInput,
    };

    visitedNodeIds.push(node.id);

    if (node.type === 'start') {
      output.kind = 'start';
    } else if (node.type === 'end') {
      output.kind = 'end';
      endedAt = node.id;
      steps.push({
        index,
        node_id: node.id,
        label,
        type: node.type,
        input: nodeInput,
        output,
        next_node_id: null,
      });
      break;
    } else if (node.type === 'router') {
      const chosenNext = selectNextNode(node, outgoingEdges, state, nodeById, warnings);
      state.next = chosenNext;
      output.kind = 'router';
      output.selected_next = chosenNext;
      steps.push({
        index,
        node_id: node.id,
        label,
        type: node.type,
        input: nodeInput,
        output,
        next_node_id: chosenNext,
      });
      currentNode = chosenNext ? nodeById.get(chosenNext) || null : null;
      continue;
    } else {
      const tool = findToolForNode(node);
      const llm = findLLMForNode(node);
      const toolName = tool?.name || node.data?.tool?.name;
      const llmAlias = llm?.alias || node.data?.llm?.alias;
      const outputMode = node.data?.node?.outputMode || 'text';
      const prompt = node.data?.node?.userPrompt || node.data?.node?.systemPrompt || label;
      const structuredOutput = outputMode === 'structured';
      let content = `${label} processed ${stringifyValue(nodeInput)}`;

      if (toolName) {
        content = `Tool ${toolName} handled ${stringifyValue(nodeInput)}`;
        if (tool?.is_active === false) {
          warnings.push(`Tool "${tool.name}" is marked inactive but was still simulated during ${mode}.`);
        }
        output.tool = tool
          ? {
              id: tool.id,
              name: tool.name,
              type: tool.type,
              description: tool.description || '',
              is_active: tool.is_active ?? true,
            }
          : {
              id: node.data?.tool?.id ?? null,
              name: toolName,
            };
      } else if (llmAlias) {
        const provider = llm?.provider || node.data?.llm?.provider || 'llm';
        const model = llm?.model || node.data?.llm?.model || 'unknown-model';
        const systemPrompt = node.data?.node?.systemPrompt || '';
        const userPrompt = node.data?.node?.userPrompt || '';
        content = `[${provider}:${llmAlias}:${model}] ${stringifyValue(nodeInput)}`;
        output.llm = {
          alias: llmAlias,
          provider,
          model,
          type: llm?.type || node.data?.llm?.type || null,
        };
        output.prompt = {
          system: systemPrompt,
          user: userPrompt,
        };
      } else if (prompt) {
        content = `${prompt} :: ${stringifyValue(nodeInput)}`;
      }

      if (structuredOutput) {
        const messageType = sanitizeIdentifier(label).toLowerCase();
        state.message_type = messageType;
        output.kind = 'structured';
        output.message_type = messageType;
        output.result = {
          message_type: messageType,
          input: nodeInput,
          label,
          node_kind: toolName ? 'tool' : llmAlias ? 'llm' : 'node',
          tool_name: toolName || null,
          llm_alias: llmAlias || null,
        };
      } else {
        appendMessage(state, content);
        if (toolName) {
          output.kind = 'tool';
          output.result = {
            tool_name: toolName,
            simulated_output: content,
            input: nodeInput,
            code: tool?.code || null,
          };
        } else if (llmAlias) {
          output.kind = 'llm';
          output.result = {
            llm_alias: llmAlias,
            model: llm?.model || node.data?.llm?.model || null,
            simulated_output: content,
            input: nodeInput,
          };
        } else {
          output.kind = 'text';
        }
        output.message = content;
      }

      if (typeof state.message_type !== 'string' || !state.message_type) {
        state.message_type = sanitizeIdentifier(label).toLowerCase();
      }
    }

    const nextNodeId = selectNextNode(node, outgoingEdges, state, nodeById, warnings);
    if (typeof state.next === 'string' && state.next === nextNodeId) {
      state.next = null;
    }

    steps.push({
      index,
      node_id: node.id,
      label,
      type: node.type,
      input: nodeInput,
      output,
      next_node_id: nextNodeId,
    });

    if (!nextNodeId) {
      endedAt = node.id;
      break;
    }

    currentNode = nodeById.get(nextNodeId) || null;
  }

  if (currentNode && steps.length >= maxSteps) {
    warnings.push(`Flow execution stopped after ${maxSteps} steps to avoid an infinite loop.`);
  }

  const completed = Boolean(endedAt) || (currentNode?.type === 'end');
  return {
    mode,
    completed,
    started_from: startNode?.id || null,
    ended_at: endedAt,
    visited_node_ids: visitedNodeIds,
    steps,
    final_state: state,
    warnings,
  };
}

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

  if (path === '/api/llms/remote' && method === 'GET') return listResponse(res, store.remoteLlms);
  if (path === '/api/llms/local' && method === 'GET') return listResponse(res, store.localLlms);

  if (path === '/api/llms/remote/validate-key' && method === 'POST') {
    const body = (await readJson(req)) as { api_key?: string } | undefined;
    return send(res, 200, validateKeyResponse(body?.api_key), { 'Content-Type': 'application/json' });
  }

  if (path === '/api/llms/remote' && method === 'POST') {
    const body = (await readJson(req)) as Partial<StoredLLM>;
    const next: StoredLLM = {
      alias: body?.alias || `remote-${store.remoteLlms.length + 1}`,
      provider: body?.provider || 'openai',
      type: 'api',
      api_key: body?.api_key,
      base_url: body?.base_url,
      model: body?.model,
      created_at: now(),
      updated_at: now(),
    };
    store.remoteLlms = [...store.remoteLlms.filter((item) => item.alias !== next.alias), next];
    await persist();
    return send(res, 200, next, { 'Content-Type': 'application/json' });
  }

  if (path === '/api/llms/local' && method === 'POST') {
    const body = (await readJson(req)) as Partial<StoredLLM>;
    const next: StoredLLM = {
      alias: body?.alias || `local-${store.localLlms.length + 1}`,
      provider: body?.provider || 'llama-cpp',
      type: 'local',
      path: body?.path,
      model: body?.model,
      created_at: now(),
      updated_at: now(),
    };
    store.localLlms = [...store.localLlms.filter((item) => item.alias !== next.alias), next];
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
      store.remoteLlms = store.remoteLlms.map((item) => (item.alias === alias ? updated : item));
      await persist();
      return send(res, 200, updated, { 'Content-Type': 'application/json' });
    }
    if (!segment && method === 'DELETE') {
      const current = getRemoteLLM(alias);
      if (!current) return notFound(res);
      store.remoteLlms = store.remoteLlms.filter((item) => item.alias !== alias);
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
      store.localLlms = store.localLlms.map((item) => (item.alias === alias ? updated : item));
      await persist();
      return send(res, 200, updated, { 'Content-Type': 'application/json' });
    }
    if (!segment && method === 'DELETE') {
      const current = getLocalLLM(alias);
      if (!current) return notFound(res);
      store.localLlms = store.localLlms.filter((item) => item.alias !== alias);
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
    if (method === 'GET') return listResponse(res, store.tools);
    if (method === 'POST') {
      const body = (await readJson(req)) as Partial<StoredTool>;
      const next: StoredTool = {
        id: store.nextToolId++,
        name: body?.name || `tool-${store.nextToolId}`,
        description: body?.description,
        type: body?.type || 'custom_code',
        config: body?.config || {},
        code: body?.code || '',
        is_active: body?.is_active ?? true,
        parameters: body?.parameters || [],
        created_at: now(),
        updated_at: now(),
      };
      store.tools = [...store.tools, next];
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
      store.tools = store.tools.map((item) => (item.id === id ? updated : item));
      await persist();
      return send(res, 200, updated, { 'Content-Type': 'application/json' });
    }
    if (method === 'DELETE') {
      store.tools = store.tools.filter((item) => item.id !== id);
      await persist();
      return send(res, 200, tool, { 'Content-Type': 'application/json' });
    }
  }

  const flowBaseMatch = path.match(/^\/api\/flows\/(\d+)$/);
  const flowActionMatch = path.match(/^\/api\/flows\/(\d+)\/(run|test)$/);

  if (path === '/api/flows' || path === '/api/flows/') {
    if (method === 'GET') {
      const limit = Number(url.searchParams.get('limit') || '');
      const items = Number.isFinite(limit) && limit > 0 ? store.flows.slice(0, limit) : store.flows;
      return listResponse(res, items);
    }
    if (method === 'POST') {
      const body = (await readJson(req)) as FlowPayload;
      const next: StoredFlow = {
        id: store.nextFlowId++,
        name: body?.name || `Flow ${store.nextFlowId}`,
        description: body?.description,
        graph: body?.graph || { nodes: [], edges: [] },
        state: body?.state || { fields: [] },
        created_at: now(),
        updated_at: now(),
      };
      store.flows = [...store.flows, next];
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
      store.flows = store.flows.map((item) => (item.id === id ? updated : item));
      await persist();
      return send(res, 200, updated, { 'Content-Type': 'application/json' });
    }
    if (method === 'DELETE') {
      store.flows = store.flows.filter((item) => item.id !== id);
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
