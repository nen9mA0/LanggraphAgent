type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
type RecordMap = Record<string, JsonValue>;

export type { JsonValue, RecordMap };

export interface FlowPayload {
  name: string;
  description?: string;
  graph: { nodes: JsonValue[]; edges: JsonValue[] };
  state: { fields: JsonValue[] };
}

export interface StoredFlow extends FlowPayload {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface StoredTool {
  id: number;
  name: string;
  description?: string;
  type: string;
  config?: RecordMap;
  code?: string;
  is_active?: boolean;
  parameters?: JsonValue[] | undefined;
  created_at: string;
  updated_at: string;
}

export interface StoredLLM {
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

export interface StoreData {
  flows: StoredFlow[];
  tools: StoredTool[];
  remoteLlms: StoredLLM[];
  localLlms: StoredLLM[];
  nextFlowId: number;
  nextToolId: number;
}

export interface FlowNodeData {
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

export interface FlowNodeRecord {
  id: string;
  type: string;
  data?: FlowNodeData;
}

export interface FlowEdgeRecord {
  id?: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
}

export interface FlowExecutionStep {
  index: number;
  node_id: string;
  label: string;
  type: string;
  input: unknown;
  output: Record<string, unknown>;
  next_node_id: string | null;
}

export interface FlowExecutionSummary {
  mode: 'run' | 'test';
  completed: boolean;
  started_from: string | null;
  ended_at: string | null;
  visited_node_ids: string[];
  steps: FlowExecutionStep[];
  final_state: Record<string, unknown>;
  warnings: string[];
}
