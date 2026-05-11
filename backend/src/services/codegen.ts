import { Annotation, StateGraph } from '@langchain/langgraph';
import type { FlowPayload, FlowNodeRecord } from '../types.ts';
import { findLLMForNode, findToolForNode } from './registry.ts';
import { sanitizeIdentifier, toPascalCase } from '../utils.ts';

function toTypeScriptPropertyKey(value: string) {
  return /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(value) ? value : JSON.stringify(value);
}

function toSingleLineComment(value: string) {
  return value.replace(/\r?\n/g, ' ').replace(/\s+/g, ' ').trim();
}

function normalizeNodeLabel(value: unknown, fallback: string) {
  const label = typeof value === 'string' && value.trim() ? value.trim() : fallback;
  return label;
}

function getNodeMetadata(node: unknown) {
  const record = node as FlowNodeRecord & {
    data?: FlowNodeRecord['data'] & {
      router?: {
        routeBy?: string;
        defaultRoute?: string;
        branchMap?: Record<string, string>;
      };
    };
  };

  const data = record?.data || {};
  const router = data?.router || {};
  return {
    label: normalizeNodeLabel(data?.label, record?.id || 'node'),
    description: typeof data?.description === 'string' ? data.description : '',
    inputFormat: typeof data?.node?.inputFormat === 'string' && data.node.inputFormat.trim()
      ? data.node.inputFormat.trim()
      : 'messages[-1]["content"]',
    outputMode: typeof data?.node?.outputMode === 'string' ? data.node.outputMode : 'text',
    systemPrompt: typeof data?.node?.systemPrompt === 'string' ? data.node.systemPrompt : '',
    userPrompt: typeof data?.node?.userPrompt === 'string' ? data.node.userPrompt : '',
    router,
  };
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
  const record = field as { fieldMetadata?: { langgraph_annotation?: string }; type?: unknown; isOptional?: unknown };
  const annotation = record?.fieldMetadata?.langgraph_annotation;
  if (annotation === 'add_messages') {
    return 'Annotation<unknown[]>({ reducer: (left, right) => left.concat(Array.isArray(right) ? right : [right]), default: () => [] })';
  }

  return `Annotation<${toTypeScriptFieldType(record?.type, Boolean(record?.isOptional))}>`;
}

export function codegen(flow: FlowPayload) {
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

  const nodeEntries = nodes.map((node: unknown, index: number) => {
    const record = node as FlowNodeRecord & { type?: string };
    const nodeId = typeof record?.id === 'string' ? record.id : `node-${index + 1}`;
    const meta = getNodeMetadata(record);
    const rawLabel = meta.label;
    const fnName = `node_${sanitizeIdentifier(rawLabel)}`;
    return {
      nodeId,
      rawLabel,
      description: meta.description,
      fnName,
      type: typeof record?.type === 'string' ? record.type : 'node',
      tool: findToolForNode(record as FlowNodeRecord),
      llm: findLLMForNode(record as FlowNodeRecord),
      meta,
    };
  });
  const executableNodes = nodeEntries.filter((node) => node.type !== 'start' && node.type !== 'end');
  const routerNodes = nodeEntries.filter((node) => node.type === 'router');

  const outgoingBySource = new Map<string, Array<{ sourceHandle?: unknown; target?: unknown; targetHandle?: unknown }>>();
  edges.forEach((edge: unknown) => {
    const record = edge as { source?: unknown; sourceHandle?: unknown; target?: unknown; targetHandle?: unknown };
    const source = typeof record?.source === 'string' ? record.source : '';
    if (!source) return;
    const current = outgoingBySource.get(source) || [];
    current.push(record);
    outgoingBySource.set(source, current);
  });

  const routeKeyFor = (value: unknown) => {
    const text = typeof value === 'string' ? value.trim() : '';
    return text ? sanitizeIdentifier(text).toLowerCase() : '';
  };
  const lines: string[] = [
    'import { Annotation, END, START, StateGraph } from "@langchain/langgraph";',
    '',
    `// Generated for ${flow.name || 'Untitled Flow'}`,
    `const ${className}StateAnnotation = Annotation.Root({`,
  ];

  if (fields.length) {
    fields.forEach((field: unknown) => {
      const record = field as { name?: unknown };
      const rawName = typeof record?.name === 'string' && record.name.trim() ? record.name.trim() : 'state';
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
    fields.forEach((field: unknown) => {
      const record = field as { name?: unknown; type?: unknown; isOptional?: unknown };
      const rawName = typeof record?.name === 'string' && record.name.trim() ? record.name.trim() : 'state';
      const isOptional = Boolean(record?.isOptional);
      const fieldType = toTypeScriptFieldType(record?.type, isOptional);
      lines.push(`  ${toTypeScriptPropertyKey(rawName)}${isOptional ? '?' : ''}: ${fieldType};`);
    });
    lines.push('};');
    lines.push('');
  }

  if (executableNodes.length) {
    lines.push('// Node stubs');
    executableNodes.forEach((node: {
      rawLabel: string;
      nodeId: string;
      fnName: string;
      description: string;
      llm: any;
      tool: any;
      meta: {
        inputFormat: string;
        outputMode: string;
        systemPrompt: string;
        userPrompt: string;
      };
    }) => {
      lines.push(`async function ${node.fnName}(state: ${className}State): Promise<Partial<${className}State>> {`);
      lines.push(`  // Node: ${toSingleLineComment(node.rawLabel)} (${node.nodeId})`);
      if (node.description) {
        lines.push(`  // Description: ${toSingleLineComment(node.description)}`);
      }
      lines.push(`  // Input: ${toSingleLineComment(node.meta.inputFormat)}`);
      lines.push(`  // Output mode: ${toSingleLineComment(node.meta.outputMode)}`);
      if (node.meta.systemPrompt) {
        lines.push(`  // System prompt: ${toSingleLineComment(node.meta.systemPrompt)}`);
      }
      if (node.meta.userPrompt) {
        lines.push(`  // User prompt: ${toSingleLineComment(node.meta.userPrompt)}`);
      }
      if (node.llm) {
        lines.push(`  // LLM: ${node.llm.alias} (${node.llm.provider}${node.llm.model ? ` / ${node.llm.model}` : ''})`);
        lines.push('  // Replace this stub with a real LLM invocation.');
      }
      if (node.tool) {
        lines.push(`  // Tool: ${node.tool.name}`);
        lines.push('  // Replace this stub with a real tool invocation.');
      }
      if (!node.llm && !node.tool) {
        lines.push('  // Replace this stub with real node logic.');
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
  executableNodes.forEach((node: { nodeId: string; fnName: string }) => {
    lines.push(`workflow.addNode(${JSON.stringify(node.nodeId)}, ${node.fnName});`);
  });

  if (routerNodes.length) {
    lines.push('');
    lines.push('// Conditional routing');
    routerNodes.forEach((node) => {
      const outgoing = outgoingBySource.get(node.nodeId) || [];
      const usedBranchKeys = new Set<string>();
      const branches = outgoing.map((edge, index) => {
        const target = typeof edge.target === 'string' ? edge.target : '';
        const targetNode = nodeEntries.find((entry) => entry.nodeId === target);
        const targetLabel = targetNode?.rawLabel || target || `route_${index + 1}`;
        const preferredKey = routeKeyFor(targetLabel) || `route_${index + 1}`;
        const routeKey = usedBranchKeys.has(preferredKey) ? `route_${index + 1}` : preferredKey;
        usedBranchKeys.add(routeKey);
        const aliases = [
          routeKey,
          target,
          targetLabel,
          routeKeyFor(edge.sourceHandle),
          routeKeyFor(edge.targetHandle),
          routeKeyFor(targetLabel),
        ].filter((value): value is string => Boolean(value));
        return { routeKey, target, targetLabel, aliases };
      });

      const aliasEntries = branches.flatMap((branch) =>
        branch.aliases.map((alias) => `    ${JSON.stringify(alias)}: ${JSON.stringify(branch.routeKey)},`)
      );
      const pathMapEntries = branches
        .map((branch) => `    ${JSON.stringify(branch.routeKey)}: ${branch.target && nodeTypeById.get(branch.target) === 'end' ? 'END' : JSON.stringify(branch.target)},`)
        .join('\n');
      const defaultRouteKey = branches[0]?.routeKey || 'route_1';

      lines.push(`const routeLookup_${sanitizeIdentifier(node.nodeId)} = {`);
      if (aliasEntries.length) {
        lines.push(...aliasEntries);
      }
      lines.push('} as const;');
      lines.push('');
      lines.push(`const route_${sanitizeIdentifier(node.nodeId)} = (state: ${className}State) => {`);
      lines.push('  const context = state as Record<string, unknown>;');
      lines.push('  const candidates = [context.next, context.message_type, context.route, context.branch, context.current_route];');
      lines.push('  for (const candidate of candidates) {');
      lines.push('    const normalized = String(candidate ?? "").trim().toLowerCase().replace(/\\s+/g, "_");');
      lines.push(`    const mapped = routeLookup_${sanitizeIdentifier(node.nodeId)}[normalized as keyof typeof routeLookup_${sanitizeIdentifier(node.nodeId)}];`);
      lines.push('    if (mapped) return mapped;');
      lines.push('  }');
      lines.push(`  return ${JSON.stringify(defaultRouteKey)};`);
      lines.push('};');
      lines.push('');
      lines.push(`workflow.addConditionalEdges(${JSON.stringify(node.nodeId)}, route_${sanitizeIdentifier(node.nodeId)}, {`);
      if (pathMapEntries) {
        lines.push(pathMapEntries);
      }
      lines.push('  });');
    });
  }

  if (edges.length) {
    lines.push('');
    lines.push('// Edges');
    edges.forEach((edge: unknown, index: number) => {
      const record = edge as { source?: unknown; target?: unknown; sourceHandle?: unknown; targetHandle?: unknown };
      const source = typeof record?.source === 'string' ? record.source : '';
      const target = typeof record?.target === 'string' ? record.target : '';
      const sourceType = nodeTypeById.get(source);
      const targetType = nodeTypeById.get(target);
      const fromRef = sourceType === 'start' ? 'START' : JSON.stringify(source);
      const toRef = targetType === 'end' ? 'END' : JSON.stringify(target);
      lines.push(`// edge ${index + 1}: ${JSON.stringify(record)}`);
      if (source && target && sourceType !== 'router') {
        lines.push(`workflow.addEdge(${fromRef}, ${toRef});`);
      }
    });
  }

  lines.push('');
  lines.push('export const compiledGraph = workflow.compile();');
  return lines.join('\n');
}
