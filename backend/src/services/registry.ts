import { getLocalLLM, getRemoteLLM, getStore } from '../store.ts';
import type { FlowNodeRecord, StoredTool } from '../types.ts';

export function findToolForNode(node: FlowNodeRecord): StoredTool | null {
  const toolRef = node.data?.tool;
  if (!toolRef) return null;

  const tools = getStore().tools;
  const byId = toolRef.id !== undefined
    ? tools.find((tool) => String(tool.id) === String(toolRef.id))
    : null;
  if (byId) return byId;

  if (toolRef.name) {
    return tools.find((tool) => tool.name === toolRef.name) || null;
  }

  return null;
}

export function findLLMForNode(node: FlowNodeRecord) {
  const llmRef = node.data?.llm;
  if (!llmRef?.alias) return null;

  if (llmRef.type === 'local') {
    return getLocalLLM(llmRef.alias) || getRemoteLLM(llmRef.alias);
  }

  return getRemoteLLM(llmRef.alias) || getLocalLLM(llmRef.alias);
}
