import type { FlowEdgeRecord, FlowExecutionSummary, FlowNodeRecord, StoredFlow } from '../types.ts';
import { findLLMForNode, findToolForNode } from './registry.ts';
import { isRecord, sanitizeIdentifier, stringifyValue, parseInitialValue } from '../utils.ts';

function getFlowGraph(flow: StoredFlow) {
  const rawNodes = Array.isArray(flow.graph?.nodes) ? flow.graph.nodes : [];
  const nodes: FlowNodeRecord[] = rawNodes
    .filter(isRecord)
    .map((node, index) => {
      const record = node as Record<string, unknown>;
      return {
        id: typeof record.id === 'string' ? record.id : `node-${index + 1}`,
        type: typeof record.type === 'string' ? record.type : 'node',
        data: isRecord(record.data) ? (record.data as FlowNodeRecord['data']) : {},
      };
    });

  const rawEdges = Array.isArray(flow.graph?.edges) ? flow.graph.edges : [];
  const edges: FlowEdgeRecord[] = rawEdges
    .filter(isRecord)
    .map((edge: unknown, index: number) => {
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

export function executeFlow(flow: StoredFlow, mode: 'run' | 'test', input: Record<string, unknown>): FlowExecutionSummary {
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
  const steps: FlowExecutionSummary['steps'] = [];
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
