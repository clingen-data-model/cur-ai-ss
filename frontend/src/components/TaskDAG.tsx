import { useMemo, useState } from 'react'
import {
  ReactFlow,
  Background,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  Handle,
  Position,
  BaseEdge,
  getStraightPath,
  type EdgeProps,
} from '@xyflow/react'
import dagre from '@dagrejs/dagre'
import '@xyflow/react/dist/style.css'
import type { TaskResp, TaskType } from '@/api/generated/types.gen'

const DAG_EDGES: [TaskType, TaskType][] = [
  ['PDF Parsing', 'Paper Classifier'],
  ['Paper Classifier', 'Paper Metadata'],
  ['Paper Classifier', 'Variant Extraction'],
  ['Paper Classifier', 'Pedigree Description'],
  ['Pedigree Description', 'Patient Extraction'],
  ['Patient Extraction', 'Phenotype Extraction'],
  ['Patient Extraction', 'Patient Variant Occurrences'],
  ['Variant Extraction', 'Variant Harmonization'],
  ['Variant Extraction', 'Patient Variant Occurrences'],
  ['Variant Harmonization', 'Variant Annotation'],
  ['Patient Variant Occurrences', 'Segregation Evidence Extraction'],
  ['Segregation Evidence Extraction', 'Segregation Analysis Computed'],
  ['Phenotype Extraction', 'HPO Linking'],
]

const ALL_TASK_TYPES: TaskType[] = [
  'PDF Parsing',
  'Paper Classifier',
  'Paper Metadata',
  'Variant Extraction',
  'Pedigree Description',
  'Patient Extraction',
  'Variant Harmonization',
  'Variant Annotation',
  'Patient Variant Occurrences',
  'Segregation Evidence Extraction',
  'Segregation Analysis Computed',
  'Phenotype Extraction',
  'HPO Linking',
]

const TASK_DESCRIPTIONS: Record<TaskType, string> = {
  'PDF Parsing': 'Parses PDF file and extract text, tables, and images',
  'Paper Classifier': 'Classifies paper sections by relevance and evaluates if paper contains extractable patient-variant pairs',
  'General Paper Question': 'Answers a general question using the full paper text and all extracted data',
  'Paper Metadata': 'Extracts paper title, authors, publication date, and other metadata; resolve to PubMed article',
  'Variant Extraction': 'Identifies genetic variants mentioned in the paper',
  'Pedigree Description': 'Analyzes the images in the paper to determine if there is a describable pedigree',
  'Patient Extraction': 'Extracts patient demographic and clinical information',
  'Segregation Evidence Extraction': 'Collects segregation analysis evidence within each family',
  'Segregation Analysis Computed': 'Computes segregation analysis results per family',
  'Variant Harmonization': 'Normalizes variants to standard genomic coordinates using ClinVar, dbSNP, ClinGen Allele Registry, and VariantValidator',
  'Variant Annotation': 'Adds annotations (SpliceAI, conservation scores, etc.) to variants',
  'Patient Variant Occurrences': 'Associates patients with their variants and inheritance patterns',
  'Phenotype Extraction': 'Extracts phenotype text spans per patient',
  'HPO Linking': 'Maps phenotypes to HPO ontology terms for standardization',
}

export type NodeStatus = 'idle' | 'pending' | 'running' | 'partial' | 'completed' | 'failed'

export function computeStatus(tasks: TaskResp[]): NodeStatus {
  if (!tasks || tasks.length === 0) return 'idle'
  const statuses = tasks.map(t => t.status)
  if (statuses.some(s => s === 'Running' || s === 'Queued')) return 'running'
  if (statuses.some(s => s === 'Failed')) return 'failed'
  if (statuses.every(s => s === 'Completed')) return 'completed'
  if (statuses.some(s => s === 'Completed')) return 'partial'
  return 'pending'
}

function statusCounts(tasks: TaskResp[], taskType: TaskType) {
  const matching = tasks.filter(t => t.type === taskType)
  if (matching.length === 0) return null
  const completed = matching.filter(t => t.status === 'Completed').length
  return { completed, total: matching.length }
}

const STATUS_STYLES: Record<NodeStatus, { bg: string; border: string; text: string; dot: string }> = {
  idle:      { bg: 'bg-slate-50',   border: 'border-slate-200', text: 'text-slate-400', dot: 'bg-slate-300' },
  pending:   { bg: 'bg-slate-50',   border: 'border-slate-300', text: 'text-slate-600', dot: 'bg-slate-400' },
  running:   { bg: 'bg-blue-50',    border: 'border-blue-400',  text: 'text-blue-700',  dot: 'bg-blue-500' },
  partial:   { bg: 'bg-amber-50',   border: 'border-amber-400', text: 'text-amber-700', dot: 'bg-amber-500' },
  completed: { bg: 'bg-green-50',   border: 'border-green-400', text: 'text-green-700', dot: 'bg-green-500' },
  failed:    { bg: 'bg-red-50',     border: 'border-red-400',   text: 'text-red-700',   dot: 'bg-red-500' },
}

interface TaskNodeData {
  label: string
  status: NodeStatus
  counts: { completed: number; total: number } | null
  errorMessage: string | null
  description: string
  [key: string]: unknown
}

function TaskNode({ data }: { data: TaskNodeData }) {
  const s = STATUS_STYLES[data.status]
  const [hovered, setHovered] = useState(false)

  return (
    <div
      className="relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className={`rounded-lg border-2 ${s.bg} ${s.border} px-3 py-2 min-w-[140px] shadow-sm cursor-grab active:cursor-grabbing`}>
        <Handle type="target" position={Position.Top} className="!bg-slate-300 !w-2 !h-2" />
        <div className="flex items-center gap-1.5">
          <span className={`size-2 rounded-full flex-shrink-0 ${s.dot} ${data.status === 'running' ? 'animate-pulse' : ''}`} />
          <span className={`text-[11px] font-medium leading-tight ${s.text}`}>{data.label}</span>
        </div>
        {data.counts && data.counts.total > 1 && (
          <div className={`text-[10px] mt-1 ml-3.5 ${s.text} opacity-75`}>
            {data.counts.completed}/{data.counts.total}
          </div>
        )}
        {data.errorMessage && data.status === 'failed' && (
          <div className="text-[10px] mt-1 ml-3.5 text-red-500 truncate max-w-[140px]" title={data.errorMessage}>
            {data.errorMessage}
          </div>
        )}
        <Handle type="source" position={Position.Bottom} className="!bg-slate-300 !w-2 !h-2" />
      </div>

      {hovered && (
        <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 z-50 w-56 rounded-md bg-popover border border-border px-3 py-2 shadow-md pointer-events-none">
          <p className="text-xs font-medium text-foreground mb-1">{data.label}</p>
          <p className="text-[11px] text-muted-foreground leading-snug">{data.description}</p>
        </div>
      )}
    </div>
  )
}

function SimpleEdge({ sourceX, sourceY, targetX, targetY, markerEnd, style }: EdgeProps) {
  const [edgePath] = getStraightPath({ sourceX, sourceY, targetX, targetY })
  return <BaseEdge path={edgePath} markerEnd={markerEnd} style={style} />
}

const NODE_W = 160
const NODE_H = 56

function layoutNodes(tasks: TaskResp[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 24, ranksep: 120 })

  for (const type of ALL_TASK_TYPES) {
    g.setNode(type, { width: NODE_W, height: NODE_H })
  }
  for (const [src, tgt] of DAG_EDGES) {
    g.setEdge(src, tgt)
  }

  dagre.layout(g)

  const nodes: Node[] = ALL_TASK_TYPES.map((type) => {
    const pos = g.node(type)
    const status = computeStatus(tasks.filter(t => t.type === type))
    const counts = statusCounts(tasks, type)
    const errorTask = tasks.find(t => t.type === type && t.status === 'Failed')
    return {
      id: type,
      type: 'taskNode',
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
      data: {
        label: type,
        status,
        counts,
        errorMessage: errorTask?.error_message ?? null,
        description: TASK_DESCRIPTIONS[type] ?? '',
      },
    }
  })

  const edges: Edge[] = DAG_EDGES.map(([src, tgt]) => ({
    id: `${src}->${tgt}`,
    source: src,
    target: tgt,
    type: 'simpleEdge',
    style: { stroke: '#cbd5e1', strokeWidth: 1.5 },
    markerEnd: { type: 'arrowclosed' as const, color: '#cbd5e1' },
  }))

  return { nodes, edges }
}

const nodeTypes = { taskNode: TaskNode }
const edgeTypes = { simpleEdge: SimpleEdge }

interface TaskDAGProps {
  tasks: TaskResp[]
}

export function TaskDAG({ tasks }: TaskDAGProps) {
  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => layoutNodes(tasks), [tasks])
  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges] = useEdgesState(initialEdges)

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange} // allows dragging to update node positions
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      fitView // zoom/pan on mount so all nodes are visible
      fitViewOptions={{ padding: 0.12 }} // 12% breathing room around the outermost nodes
      nodesDraggable={true}
      nodesConnectable={false} // prevent users from drawing new edges
      elementsSelectable={false} // no click-to-select highlight
      panOnDrag={true}
      zoomOnScroll={true}
      zoomOnPinch={true}
      zoomOnDoubleClick={false} // double-click would zoom in unexpectedly
      proOptions={{ hideAttribution: true }} // hide "Built by xyflow" watermark
    >
      <Background color="#e2e8f0" gap={16} size={1} />
    </ReactFlow>
  )
}
