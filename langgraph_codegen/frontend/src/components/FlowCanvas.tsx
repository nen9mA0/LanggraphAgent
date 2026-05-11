import React, { useRef, useCallback, useMemo, useState, memo, useEffect } from 'react';
import StateModal, { type StateField } from './StateModal';
import MemoryModal from './MemoryModal';
import SaveLoadFlow from './SaveLoadFlow';
import ReactFlow, {
  Background,
  Controls,
  type Node,
  type Edge,
  type MarkerType,
  type Connection,
  ConnectionLineType
} from 'reactflow';
import 'reactflow/dist/style.css';
import { FiTrash2 } from 'react-icons/fi';
import useFlowStore, { type NodeType } from '../store/useFlowStore';
import { nodeTypes } from './flow/nodeTypes';
import type { CustomNode } from './flow/NodeComponent';
import Toolbar from './flow/Toolbar';

// Memoized components to prevent unnecessary re-renders
const MemoizedBackground = memo(() => (
  <Background
    gap={16}
    color="#64748b"
    style={{ backgroundColor: 'rgb(15, 23, 42)' }}
  />
));

const MemoizedControls = memo(() => (
  <Controls
    style={{
      display: 'flex',
      gap: '8px',
      padding: '8px',
      backgroundColor: 'rgba(255, 255, 255, 0.1)',
      borderRadius: '4px',
    }}
  />
));

interface FlowCanvasProps {
  onNodeSelect?: (node: CustomNode | null) => void;
  className?: string;
  style?: React.CSSProperties;
}

export const FlowCanvas: React.FC<FlowCanvasProps> = ({
  onNodeSelect,
  className = '',
  style,
}) => {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const { 
    nodes, 
    edges, 
    state: flowState,
    onNodesChange, 
    onEdgesChange, 
    addEdge,
    removeEdge,
    removeNode,
    addNode,
    setNodes,
    setEdges,
    setState
  } = useFlowStore();
  
  // State for the modals
  const [isStateModalOpen, setIsStateModalOpen] = useState(false);
  const [isMemoryModalOpen, setIsMemoryModalOpen] = useState(false);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);
  const [stateFields, setStateFields] = useState<StateField[]>(flowState || []);
  
  // Initialize state fields when component mounts
  useEffect(() => {
    if (flowState && flowState.length > 0) {
      setStateFields(flowState);
    } else {
      // Initialize with default fields if no state exists
      const defaultFields: StateField[] = [
        {
          id: '1',
          name: 'messages',
          type: 'List[str]',
          isOptional: false,
          initialValue: '[]',
          fieldMetadata: {
            langgraph_annotation: 'add_messages'
          },
          isInternal: false
        },
        {
          id: '2',
          name: 'message_type',
          type: 'str',
          isOptional: true,
          initialValue: 'None',
          fieldMetadata: {},
          isInternal: false
        },
        {
          id: '3',
          name: 'next',
          type: 'str',
          isOptional: true,
          initialValue: 'None',
          fieldMetadata: {},
          isInternal: false
        }
      ];
      setStateFields(defaultFields);
      setState(defaultFields);
    }
  }, [setState]);

  useEffect(() => {
    if (selectedEdge && !edges.some((edge) => edge.id === selectedEdge.id)) {
      setSelectedEdge(null);
    }
  }, [edges, selectedEdge]);
  
  // Log state changes
  useEffect(() => {
    console.log('State fields updated:', stateFields);
  }, [stateFields]);

  const handleStateButtonClick = useCallback(() => {
    setIsStateModalOpen(true);
  }, [stateFields]);

  const handleMemoryButtonClick = useCallback(() => {
    setIsMemoryModalOpen(true);
  }, []);

  const handleStateModalClose = useCallback(() => {
    setIsStateModalOpen(false);
  }, []);

  const handleMemoryModalClose = useCallback(() => {
    setIsMemoryModalOpen(false);
  }, []);

  const handleStateSave = useCallback((fields: StateField[]) => {
    console.log('Saving state fields:', fields);
    setState(fields); 
    setStateFields(fields);
    setIsStateModalOpen(false);
  }, [setState]);

  const handleMemorySave = useCallback((settings: any) => {
    console.log('Memory settings saved:', settings);
  }, []);

  const handleConnect = useCallback((connection: Connection) => {
    // Prevent connection from source to itself or invalid connections
    if (connection.source === connection.target || !connection.source || !connection.target) {
      return;
    }
    
    addEdge({
      ...connection,
      id: `edge-${connection.source}-${connection.target}-${Date.now()}`,
      type: 'smoothstep',
      animated: true,
      style: { stroke: '#94a3b8', strokeWidth: 2 },
      markerEnd: { type: 'arrowclosed' as MarkerType, color: '#94a3b8' },
    });
  }, [addEdge]);

  const handleNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setSelectedEdge(null);
    onNodeSelect?.(node as CustomNode);
  }, [onNodeSelect]);

  const handlePaneClick = useCallback((_event: React.MouseEvent) => {
    setSelectedEdge(null);
    onNodeSelect?.(null);
  }, [onNodeSelect]);

  const handleEdgeClick = useCallback((_event: React.MouseEvent, edge: Edge) => {
    setSelectedEdge(edge);
    onNodeSelect?.(null);
  }, [onNodeSelect]);

  const handleDeleteSelectedEdge = useCallback(() => {
    if (!selectedEdge) return;
    removeEdge(selectedEdge.id);
    setSelectedEdge(null);
    onNodeSelect?.(null);
  }, [onNodeSelect, removeEdge, selectedEdge]);

  const handleDeleteSelectedNode = useCallback(() => {
    const selectedNode = nodes.find((node) => node.selected);
    if (!selectedNode) return;
    removeNode(selectedNode.id);
    onNodeSelect?.(null);
  }, [nodes, onNodeSelect, removeNode]);

  const createNode = useCallback((type: NodeType, position: { x: number; y: number }): CustomNode => {
    const id = `${type}-${Date.now()}`;
    const baseNode: CustomNode = {
      id,
      type: type as any, // Type assertion for ReactFlow's Node type
      position,
      data: {
        label: type === 'router' ? 'Router' : type.charAt(0).toUpperCase() + type.slice(1),
        type,
        // Initialize node object with default values
        node: {
          inputFormat: 'messages[-1]["content"]',
          outputMode: 'text' as const,
          systemPrompt: '',
          userPrompt: ''
        }
      },
    };

    switch (type) {
      case 'node':
        return {
          ...baseNode,
          type: 'node',
          data: {
            ...baseNode.data,
            type: 'node',
            node: {
              ...baseNode.data.node,
              // Keep any existing node properties
            },
            tool: null,
          },
        } as unknown as CustomNode;
      case 'router':
        return {
          ...baseNode,
          type: 'router',
          data: {
            ...baseNode.data,
            type: 'router',
            node: {
              ...baseNode.data.node,
              // Router-specific node properties can go here
            },
            tool: null
          },
        } as unknown as CustomNode;
      case 'trigger':
      case 'start':
      case 'end':
      default:
        return {
          ...baseNode,
          type: type as NodeType,
          data: {
            ...baseNode.data,
            type: type as NodeType,
            node: {
              ...baseNode.data.node,
              // Node type-specific properties can go here
            },
            tool: null,
          },
        } as unknown as CustomNode;
    }
  }, []);

  // Get the current flow state as a serialized graph
  const getSerializedGraph = useCallback(() => {
    return {
      nodes,
      edges,
      state: stateFields,
    };
  }, [nodes, edges, stateFields]);

  // Load a flow from serialized data
  const loadFlow = useCallback((serializedGraph: any) => {
    if (serializedGraph?.nodes && serializedGraph?.edges) {
      setNodes(serializedGraph.nodes);
      setEdges(serializedGraph.edges);
      
      // Load state fields if they exist
      if (serializedGraph.state) {
        // Convert state to StateField[] format if needed
        const stateFields = (Array.isArray(serializedGraph.state) ? serializedGraph.state : []).map((field: any) => ({
          id: field.id || `field-${Math.random().toString(36).substr(2, 9)}`,
          name: field.name || field.id || '',
          type: field.type || 'str',
          isOptional: field.isOptional || false,
          initialValue: field.initialValue !== undefined ? String(field.initialValue) : '',
          isInternal: field.isInternal || false
        }));
        setStateFields(stateFields);
      }
    }
  }, [setNodes, setEdges]);

  const handleAddNode = useCallback((type: NodeType = 'node') => {
    if (!reactFlowWrapper.current) return;

    const { left, top } = reactFlowWrapper.current.getBoundingClientRect();
    const position = {
      x: window.innerWidth / 2 - left - 100,
      y: window.innerHeight / 2 - top - 50,
    };

    const newNode = createNode(type, position);
    addNode(newNode);
  }, [createNode, addNode]);

  // Memoize all ReactFlow props that don't need to change
  const flowProps = useMemo(() => ({
    nodeTypes,
    defaultEdgeOptions: {
      type: 'smoothstep',
      style: { stroke: '#94a3b8', strokeWidth: 2 },
      animated: true,
      markerEnd: { type: 'arrowclosed' as MarkerType, color: '#94a3b8' },
    },
    connectionLineStyle: {
      stroke: '#94a3b8',
      strokeWidth: 2,
    },
    connectionRadius: 30,
    fitView: true,
    minZoom: 0.1,
    maxZoom: 2,
    nodeOrigin: [0.5, 0.5] as [number, number],
    proOptions: { hideAttribution: true },
    snapToGrid: true,
    snapGrid: [15, 15] as [number, number],
    nodesDraggable: true,
    nodesConnectable: true,
    elementsSelectable: true,
    selectNodesOnDrag: true,
    connectionLineType: ConnectionLineType.SmoothStep,
  }), []);
  

  // Memoize all event handlers
  const eventHandlers = useMemo(() => ({
    onConnectStart: (_: any) => {
      // Connection start handler
    },
    onConnectEnd: () => {
      // Connection end handler
    },
    onError: (code: string, message: string) => {
      console.error('ReactFlow error:', code, message);
    },
    isValidConnection: (connection: Connection) => {
      return connection.source !== connection.target && 
             !!connection.source && 
             !!connection.target;
    }
  }), []);

  // Memoize the Toolbar to prevent unnecessary re-renders
  const memoizedToolbar = useMemo(() => (
    <Toolbar
      onAddNode={handleAddNode}
      onStateClick={handleStateButtonClick}
      onMemoryClick={handleMemoryButtonClick}
    />
  ), [handleAddNode, handleStateButtonClick, handleMemoryButtonClick]);

  // Memoize the ReactFlow component's children
  const reactFlowChildren = useMemo(() => (
    <>
      <MemoizedBackground />
      <MemoizedControls />
      {memoizedToolbar}

      {/* State Modal */}
      <StateModal
        isOpen={isStateModalOpen}
        onClose={handleStateModalClose}
        onSave={handleStateSave}
        initialFields={stateFields}
      />

      <MemoryModal
        isOpen={isMemoryModalOpen}
        onClose={handleMemoryModalClose}
        onSave={handleMemorySave}
        initialSettings={{}}
      />

      {/* Save/Load Flow Buttons */}
      <div className="absolute top-4 right-4 z-10">
        <SaveLoadFlow 
          key="save-load-flow"
          serializedGraph={getSerializedGraph()} 
          onLoad={loadFlow} 
        />
      </div>

      {(nodes.some((node) => node.selected) || selectedEdge) && (
        <div className="absolute top-4 left-4 z-10">
          <div className="flex items-center gap-3 rounded-lg border border-red-500/30 bg-gray-900/90 px-3 py-2 shadow-lg shadow-black/20 backdrop-blur">
            <div className="min-w-0">
              {selectedEdge ? (
                <>
                  <div className="text-xs font-medium text-red-300">Selected Edge</div>
                  <div className="text-[11px] text-gray-400 truncate max-w-[220px]">
                    {selectedEdge.source} {'->'} {selectedEdge.target}
                  </div>
                </>
              ) : (
                <>
                  <div className="text-xs font-medium text-red-300">Selected Node</div>
                  <div className="text-[11px] text-gray-400 truncate max-w-[220px]">
                    {nodes.find((node) => node.selected)?.data.label ?? 'Unnamed node'}
                  </div>
                </>
              )}
            </div>
            <button
              type="button"
              onClick={selectedEdge ? handleDeleteSelectedEdge : handleDeleteSelectedNode}
              className="inline-flex items-center gap-1 rounded-md bg-red-600/15 px-2.5 py-1 text-xs font-medium text-red-300 hover:bg-red-600 hover:text-white transition-colors"
              title={selectedEdge ? 'Delete edge' : 'Delete node'}
            >
              <FiTrash2 className="h-3.5 w-3.5" />
              Delete
            </button>
          </div>
        </div>
      )}
    </>
  ), [
    memoizedToolbar,
    isStateModalOpen,
    isMemoryModalOpen,
    handleStateModalClose,
    handleMemoryModalClose,
    handleStateSave,
    handleMemorySave,
    stateFields,
    getSerializedGraph,
    loadFlow,
    nodes,
    selectedEdge,
    handleDeleteSelectedEdge,
    handleDeleteSelectedNode
  ]);

  const optimizedNodes = useMemo(() => nodes, [nodes]);

  return (
    <div 
      className={`h-full w-full relative ${className}`} 
      ref={reactFlowWrapper} 
      style={style}
    >
      <ReactFlow
        nodes={optimizedNodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={handleConnect}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onPaneClick={handlePaneClick}
        {...flowProps}
        {...eventHandlers}
      >
        {reactFlowChildren}
      </ReactFlow>
    </div>
  );
};

export default FlowCanvas;

