// Copyright 2026 Open Dreamina Contributors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge as rfAddEdge,
  ReactFlowProvider,
  useReactFlow,
  type Node,
  type Edge,
  type Connection,
  type XYPosition,
  BackgroundVariant,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { ArrowLeft, Play, Plus, Loader2, Check } from 'lucide-react'
import {
  getCanvas,
  saveCanvasDocument,
  createRun,
  type CanvasNodeType,
  type CanvasNode as CanvasNodeData,
  type CanvasEdge as CanvasEdgeData,
} from '@/api/canvas'
import { useCanvasStore } from '@/stores/canvasStore'
import { Button } from '@/components/ui/Button'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { defaultParamsForType } from '@/lib/generation'
import { CanvasBasicNode } from '@/components/canvas/CanvasBasicNode'
import { CanvasGenerationNode } from '@/components/canvas/CanvasGenerationNode'

const nodeTypes = {
  canvasNode: CanvasBasicNode,
  canvasGenerationNode: CanvasGenerationNode,
}

// ---------------- 适配函数：CanvasNode <-> React Flow Node ----------------

function toRFNode(node: CanvasNodeData): Node {
  const isGenerationNode = node.type === 'image_gen' || node.type === 'video_gen'
  return {
    id: node.id,
    type: isGenerationNode ? 'canvasGenerationNode' : 'canvasNode',
    position: node.position,
    data: { ...node.data, nodeType: node.type, title: node.title },
  }
}

function toRFEdge(edge: CanvasEdgeData): Edge {
  return {
    id: edge.id,
    source: edge.source,
    sourceHandle: edge.source_port,
    target: edge.target,
    targetHandle: edge.target_port,
  }
}

function fromRFEdge(edge: Edge): CanvasEdgeData {
  return {
    id: edge.id,
    source: edge.source,
    source_port: edge.sourceHandle ?? '',
    target: edge.target,
    target_port: edge.targetHandle ?? '',
    order: 0,
  }
}

// ---------------- 编辑器页面 ----------------

export function CanvasEditorPage() {
  return (
    <ReactFlowProvider>
      <CanvasEditorInner />
    </ReactFlowProvider>
  )
}

function CanvasEditorInner() {
  const { canvasId } = useParams<{ canvasId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const reactFlow = useReactFlow()

  const store = useCanvasStore()

  const { data: canvas, isLoading } = useQuery({
    queryKey: ['canvas', canvasId],
    queryFn: () => getCanvas(canvasId!),
    enabled: !!canvasId,
  })

  // React Flow 本地状态（保留 measured/dimensions 等内部字段）
  const [rfNodes, setRfNodes] = useNodesState<Node>(
    useMemo(() => store.nodes.map(toRFNode), []) // eslint-disable-line react-hooks/exhaustive-deps
  )
  const [rfEdges, setRfEdges] = useEdgesState<Edge>(
    useMemo(() => store.edges.map(toRFEdge), []) // eslint-disable-line react-hooks/exhaustive-deps
  )

  // 同步加载的画布到 store + RF 本地状态（刷新/导航/重新挂载均触发）
  useEffect(() => {
    if (!canvas) return
    store.setCanvas(canvas.id, canvas.document, canvas.version)
    setRfNodes(canvas.document.nodes.map(toRFNode))
    setRfEdges(canvas.document.edges.map(toRFEdge))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvas])

  // 保存
  const saveMut = useMutation({
    mutationFn: () =>
      saveCanvasDocument(canvasId!, {
        document: {
          schema_version: 1,
          viewport: store.viewport,
          nodes: store.nodes,
          edges: store.edges,
        },
        base_version: store.version,
      }),
    onSuccess: (res) => {
      store.markSaved(res.version)
      qc.invalidateQueries({ queryKey: ['canvas', canvasId] })
      qc.invalidateQueries({ queryKey: ['canvases'] })
    },
    onError: (err) => {
      const e = toApiError(err)
      if (e.statusCode === 409) {
        toast('版本冲突，请刷新页面后重试', 'error')
      } else {
        toast(e.message, 'error')
      }
    },
  })

  // 自动保存：每 5 秒检查是否有未保存变更
  const isDirtyRef = useRef(false)
  isDirtyRef.current = store.isDirty

  const autoSave = useCallback(() => {
    if (isDirtyRef.current && canvasId && !saveMut.isPending) {
      saveMut.mutate()
    }
  }, [canvasId, saveMut])

  useEffect(() => {
    const timer = setInterval(autoSave, 5000)
    return () => clearInterval(timer)
  }, [autoSave])

  // 页面卸载/刷新前尝试同步保存
  useEffect(() => {
    function handleBeforeUnload(e: BeforeUnloadEvent) {
      if (isDirtyRef.current) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [])

  // 运行（P0 骨架）
  const runMut = useMutation({
    mutationFn: () => createRun(canvasId!, { scope: 'all' }),
    onSuccess: () => {
      toast('运行已创建（调度功能即将上线）')
    },
    onError: (err) => toast(toApiError(err).message, 'error'),
  })

  // React Flow 只管理视图态；持久数据通过 store 原子操作更新，避免旧快照覆盖节点输入。
  const handleNodesChange = useCallback(
    (changes: Parameters<typeof applyNodeChanges<Node>>[0]) => {
      setRfNodes((nodes) => applyNodeChanges(changes, nodes))
      for (const change of changes) {
        if (change.type === 'position' && change.position) {
          store.setNodePosition(change.id, change.position)
        } else if (change.type === 'remove') {
          store.removeNode(change.id)
        }
      }
    },
    [setRfNodes, store],
  )

  const handleEdgesChange = useCallback(
    (changes: Parameters<typeof applyEdgeChanges<Edge>>[0]) => {
      setRfEdges((edges) => applyEdgeChanges(changes, edges))
      for (const change of changes) {
        if (change.type === 'remove') store.removeEdge(change.id)
      }
    },
    [setRfEdges, store],
  )

  const onConnect = useCallback(
    (conn: Connection) => {
      const newEdge: Edge = {
        ...conn,
        id: `eg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      }
      setRfEdges((edges) => rfAddEdge(newEdge, edges))
      store.addEdge(fromRFEdge(newEdge))
    },
    [setRfEdges, store],
  )

  // 添加节点（position 可选，右键菜单传入点击位置的流坐标）
  const addNode = useCallback(
    (type: CanvasNodeType, position?: XYPosition) => {
      const id = `nd_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`
      const isGenerationNode = type === 'image_gen' || type === 'video_gen'
      const data = isGenerationNode
        ? {
            nodeType: type,
            prompt: '',
            params: defaultParamsForType(type === 'image_gen' ? 'text2img' : 'text2video'),
            ref_assets: [],
          }
        : { nodeType: type }
      const nodePosition = position ?? { x: 160 + Math.random() * 240, y: 100 + Math.random() * 180 }
      const rfNode: Node = {
        id,
        type: isGenerationNode ? 'canvasGenerationNode' : 'canvasNode',
        position: nodePosition,
        data,
      }
      setRfNodes((nodes) => [...nodes, rfNode])
      store.addNode({ id, type, position: nodePosition, data })
    },
    [setRfNodes, store],
  )

  // 右键上下文菜单
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; flowPos: XYPosition } | null>(null)
  const contextMenuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!contextMenu) return
    function onPointerDown(e: PointerEvent) {
      if (contextMenuRef.current && e.target instanceof Element && !contextMenuRef.current.contains(e.target)) {
        setContextMenu(null)
      }
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setContextMenu(null)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [contextMenu])

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-fg-secondary">
        加载画布...
      </div>
    )
  }

  if (!canvas) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <p className="text-sm text-fg-secondary">画布不存在</p>
        <Button variant="outline" onClick={() => navigate('/canvas')}>
          返回列表
        </Button>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4 border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate('/canvas')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-sm font-medium text-fg-primary">{canvas.name}</h1>
            <p className="text-xs text-fg-muted">v{store.version} · {rfNodes.length} 节点</p>
          </div>
          {store.isDirty && (
            <span className="rounded-full bg-warning/10 px-2 py-0.5 text-xs text-warning">
              未保存
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Add node menu */}
          <AddNodeButton onAdd={addNode} />

          {/* 自动保存状态指示 */}
          <AutoSaveStatus
            isDirty={store.isDirty}
            isSaving={saveMut.isPending}
            isError={saveMut.isError}
          />

          <Button
            variant="outline"
            size="sm"
            onClick={() => runMut.mutate()}
            disabled={runMut.isPending}
          >
            <Play className="h-3.5 w-3.5" />
            运行
          </Button>
        </div>
      </div>

      {/* React Flow canvas */}
      <div className="flex-1 overflow-hidden">
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onConnect={onConnect}
          onPaneContextMenu={(event) => {
            event.preventDefault()
            const flowPos = reactFlow.screenToFlowPosition({ x: event.clientX, y: event.clientY })
            setContextMenu({ x: event.clientX, y: event.clientY, flowPos })
          }}
          fitView
          className="bg-bg-primary"
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
          <Controls className="bg-bg-secondary" />
          <MiniMap
            className="rounded-card border border-border bg-bg-secondary"
            maskColor="rgba(0,0,0,0.6)"
          />
        </ReactFlow>
      </div>

      {/* 右键上下文菜单 */}
      {contextMenu && (
        <div
          ref={contextMenuRef}
          className="fixed z-30 flex min-w-[120px] flex-col gap-0.5 rounded-card border border-border bg-bg-secondary p-1 shadow-lg"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <NodeCreateMenuItems
            onSelect={(type) => {
              addNode(type, contextMenu.flowPos)
              setContextMenu(null)
            }}
          />
        </div>
      )}
    </div>
  )
}

// ---------------- 节点类型与创建菜单 ----------------

const NODE_TYPES: { type: CanvasNodeType; label: string }[] = [
  { type: 'asset', label: '素材' },
  { type: 'image_gen', label: '图片生成' },
  { type: 'video_gen', label: '视频生成' },
  { type: 'note', label: '备注' },
]

function NodeCreateMenuItems({ onSelect }: { onSelect: (type: CanvasNodeType) => void }) {
  return NODE_TYPES.map(({ type, label }) => (
    <button
      key={type}
      onClick={() => onSelect(type)}
      className="flex items-center rounded-btn px-3 py-1.5 text-xs whitespace-nowrap text-fg-primary hover:bg-bg-tertiary"
    >
      {label}
    </button>
  ))
}

// ---------------- 自动保存状态指示 ----------------

function AutoSaveStatus({
  isDirty,
  isSaving,
  isError,
}: {
  isDirty: boolean
  isSaving: boolean
  isError: boolean
}) {
  let icon = <Check className="h-3 w-3" />
  let text = '自动保存'
  let className = 'text-fg-muted'

  if (isSaving) {
    icon = <Loader2 className="h-3 w-3 animate-spin" />
    text = '保存中...'
    className = 'text-fg-secondary'
  } else if (isError) {
    icon = <Loader2 className="h-3 w-3" />
    text = '保存失败，重试中...'
    className = 'text-error'
  } else if (isDirty) {
    icon = <Loader2 className="h-3 w-3" />
    text = '编辑中...'
    className = 'text-fg-secondary'
  }

  return (
    <div className={`flex items-center gap-1.5 text-xs ${className}`}>
      {icon}
      {text}
    </div>
  )
}

function AddNodeButton({ onAdd }: { onAdd: (type: CanvasNodeType) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // 点击外部关闭下拉
  useEffect(() => {
    if (!open) return
    function onPointerDown(e: PointerEvent) {
      if (ref.current && e.target instanceof Element && !ref.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setOpen((v) => !v)}
      >
        <Plus className="h-3.5 w-3.5" />
        添加节点
      </Button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 flex min-w-[120px] flex-col gap-0.5 rounded-card border border-border bg-bg-secondary p-1 shadow-lg">
          <NodeCreateMenuItems onSelect={(type) => { onAdd(type); setOpen(false) }} />
        </div>
      )}
    </div>
  )
}
