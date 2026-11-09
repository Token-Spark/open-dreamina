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
import { ArrowLeft, Plus, Loader2, Check, AlertCircle } from 'lucide-react'
import {
  getCanvas,
  saveCanvasDocument,
  type CanvasNodeType,
  type CanvasNode as CanvasNodeData,
  type CanvasEdge as CanvasEdgeData,
  type CanvasValidationItem,
} from '@/api/canvas'
import { useCanvasStore } from '@/stores/canvasStore'
import { Button } from '@/components/ui/Button'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { defaultParamsForType } from '@/lib/generation'
import { checkConnection, useNodeSpecs } from '@/lib/canvasNodeSpecs'
import { CanvasBasicNode } from '@/components/canvas/CanvasBasicNode'
import { CanvasGenerationNode } from '@/components/canvas/CanvasGenerationNode'

const nodeTypes = {
  canvasNode: CanvasBasicNode,
  canvasGenerationNode: CanvasGenerationNode,
}

interface SaveVars {
  /** 发起保存时的本地写操作序号，用于判断返回前是否又有新编辑 */
  revision: number
  baseVersion: number
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
  const specs = useNodeSpecs()

  const { data: canvas, isLoading, isError } = useQuery({
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
  const [saveIssues, setSaveIssues] = useState<CanvasValidationItem[]>([])
  const [saveBlocked, setSaveBlocked] = useState(false)

  const loadedCanvasIdRef = useRef<string | null>(null)
  const failedRevisionRef = useRef<number | null>(null)
  const conflictCountRef = useRef(0)
  const blockedRef = useRef(false)
  const lastFlushRef = useRef(0)
  const isPendingRef = useRef(false)
  const saveMutateRef = useRef<(vars: SaveVars) => void>(() => {})
  const flushRef = useRef<() => void>(() => {})

  function updateBlocked(value: boolean) {
    blockedRef.current = value
    setSaveBlocked(value)
  }

  // 只在首次载入 / 切换到另一张画布时同步。同一次编辑会话里的 query 更新
  // （含窗口聚焦后的后台 refetch）绝不能覆盖本地尚未保存的内容。
  useEffect(() => {
    if (!canvas) return
    if (loadedCanvasIdRef.current === canvas.id && store.canvasId === canvas.id) return
    const previous = useCanvasStore.getState()
    if (previous.isDirty && previous.canvasId && previous.canvasId !== canvas.id) {
      // 路由切换不会触发 pagehide，先尽力把上一张画布写回再载入新画布
      flushRef.current()
    }
    loadedCanvasIdRef.current = canvas.id
    store.setCanvas(canvas.id, canvas.document, canvas.version)
    setRfNodes(canvas.document.nodes.map(toRFNode))
    setRfEdges(canvas.document.edges.map(toRFEdge))
    setSaveIssues([])
    failedRevisionRef.current = null
    conflictCountRef.current = 0
    updateBlocked(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvas])

  const saveMut = useMutation({
    mutationFn: ({ baseVersion }: SaveVars) => {
      const state = useCanvasStore.getState()
      return saveCanvasDocument(canvasId!, {
        document: {
          schema_version: 1,
          viewport: state.viewport,
          nodes: state.nodes,
          edges: state.edges,
        },
        base_version: baseVersion,
      })
    },
    onSuccess: (res, variables) => {
      // 保存往返期间若有新编辑，revision 已变化，脏标记必须保留，
      // 否则这些编辑永远不会进入下一轮自动保存。
      useCanvasStore.getState().markSaved(res.version, variables.revision)
      setSaveIssues(res.issues ?? [])
      failedRevisionRef.current = null
      conflictCountRef.current = 0
      updateBlocked(false)
      // 只让列表页刷新。不要 invalidate ['canvas', canvasId]：那会触发
      // refetch，用服务端快照覆盖保存期间产生的新编辑。
      qc.invalidateQueries({ queryKey: ['canvases'] })
    },
    onError: (err, variables) => {
      const e = toApiError(err)
      if (e.statusCode === 409) {
        const detail = e.rawDetail as { current_version?: unknown } | undefined
        const current = detail?.current_version
        conflictCountRef.current += 1
        if (typeof current === 'number' && conflictCountRef.current <= 3) {
          // 以服务端最新版本为基线重试，本地文档保持不动，等下一轮自动保存。
          useCanvasStore.getState().setVersion(current)
          if (conflictCountRef.current === 1) {
            toast(`画布已在别处更新（v${current}），正在按最新版本重试保存`, 'warning')
          }
          return
        }
        updateBlocked(true)
        toast('版本冲突持续存在，请刷新页面后重试', 'error')
        return
      }
      // 其它失败：同一份文档不再反复重试，避免每 5 秒刷一次 toast。
      // 用户下一次编辑会推进 revision，届时自动再试。
      failedRevisionRef.current = variables.revision
      toast(e.message, 'error')
    },
  })
  saveMutateRef.current = saveMut.mutate
  isPendingRef.current = saveMut.isPending

  // 自动保存：定时器只建一次，状态全部从 store 实时读取，不依赖不稳定的 mutation 对象。
  const autoSave = useCallback(() => {
    if (!canvasId || blockedRef.current || isPendingRef.current) return
    const state = useCanvasStore.getState()
    if (!state.isDirty) return
    if (failedRevisionRef.current === state.revision) return
    saveMutateRef.current({ revision: state.revision, baseVersion: state.version })
  }, [canvasId])

  useEffect(() => {
    const timer = setInterval(autoSave, 5000)
    return () => clearInterval(timer)
  }, [autoSave])

  // 离开页面（刷新 / 关闭 / 路由切换）时尽力补一次保存。
  // keepalive 请求有体积上限，大画布可能发不出去，因此只是兜底而非保证。
  flushRef.current = () => {
    const state = useCanvasStore.getState()
    if (!state.isDirty || !state.canvasId || isPendingRef.current) return
    if (Date.now() - lastFlushRef.current < 1000) return
    lastFlushRef.current = Date.now()
    void fetch(`/api/v1/canvas/${encodeURIComponent(state.canvasId)}/document`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        document: {
          schema_version: 1,
          viewport: state.viewport,
          nodes: state.nodes,
          edges: state.edges,
        },
        base_version: state.version,
      }),
      keepalive: true,
    }).catch(() => {})
  }

  useEffect(() => {
    // 有未保存内容时提示用户，避免误以为已经落库
    function handleBeforeUnload(e: BeforeUnloadEvent) {
      if (!useCanvasStore.getState().isDirty) return
      e.preventDefault()
      e.returnValue = ''
    }
    function handlePageHide() {
      flushRef.current()
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    window.addEventListener('pagehide', handlePageHide)
    return () => {
      flushRef.current()
      window.removeEventListener('beforeunload', handleBeforeUnload)
      window.removeEventListener('pagehide', handlePageHide)
    }
  }, [])

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

  // 连线校验与后端 canvas_validate 同规则：端口存在、类型兼容、容量、去重、不成环。
  const isValidConnection = useCallback(
    (conn: Connection | Edge) => {
      const state = useCanvasStore.getState()
      return checkConnection(conn as Connection, specs, state.nodes, state.edges).ok
    },
    [specs],
  )

  const onConnect = useCallback(
    (conn: Connection) => {
      const state = useCanvasStore.getState()
      const check = checkConnection(conn, specs, state.nodes, state.edges)
      if (!check.ok || !check.connection) {
        toast(check.reason ?? '连线不合法', 'error')
        return
      }
      const edge = check.connection
      const targetPort = edge.targetHandle ?? ''
      const order = state.edges.filter(
        (e) => e.target === edge.target && e.target_port === targetPort,
      ).length
      const newEdge: Edge = {
        ...edge,
        id: `eg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      }
      setRfEdges((edges) => rfAddEdge(newEdge, edges))
      state.addEdge({
        id: newEdge.id,
        source: newEdge.source,
        source_port: edge.sourceHandle ?? '',
        target: newEdge.target,
        target_port: targetPort,
        order,
      })
    },
    [setRfEdges, specs],
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
        : type === 'prompt' || type === 'note'
          ? { nodeType: type, text: '' }
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

  if (isError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <p className="text-sm text-fg-secondary">画布加载失败，请检查网络或后端服务</p>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => qc.invalidateQueries({ queryKey: ['canvas', canvasId] })}>
            重试
          </Button>
          <Button variant="ghost" onClick={() => navigate('/canvas')}>
            返回列表
          </Button>
        </div>
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

  const errorIssues = saveIssues.filter((issue) => issue.level === 'error')
  const issueTitle = errorIssues.slice(0, 6).map((issue) => `· ${issue.message}`).join('\n')

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4 px-4 py-2.5">
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
            isBlocked={saveBlocked}
            issueCount={errorIssues.length}
            issueTitle={issueTitle}
          />

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
          isValidConnection={isValidConnection}
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
  { type: 'prompt', label: '提示词' },
  { type: 'image_gen', label: '图片生成' },
  { type: 'video_gen', label: '视频生成' },
  { type: 'preview', label: '预览' },
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
  isBlocked,
  issueCount,
  issueTitle,
}: {
  isDirty: boolean
  isSaving: boolean
  isError: boolean
  isBlocked: boolean
  issueCount: number
  issueTitle: string
}) {
  let icon = <Check className="h-3 w-3" />
  let text = '自动保存'
  let className = 'text-fg-muted'

  if (isSaving) {
    icon = <Loader2 className="h-3 w-3 animate-spin" />
    text = '保存中...'
    className = 'text-fg-secondary'
  } else if (isBlocked) {
    icon = <AlertCircle className="h-3 w-3" />
    text = '保存已暂停，请刷新页面'
    className = 'text-error'
  } else if (isError) {
    icon = <AlertCircle className="h-3 w-3" />
    text = '保存失败，修改后重试'
    className = 'text-error'
  } else if (issueCount > 0) {
    icon = <Check className="h-3 w-3" />
    text = `已保存 · ${issueCount} 项待完善`
    className = 'text-warning'
  } else if (isDirty) {
    icon = <Loader2 className="h-3 w-3" />
    text = '编辑中...'
    className = 'text-fg-secondary'
  }

  return (
    <div className={`flex items-center gap-1.5 text-xs ${className}`} title={issueTitle || undefined}>
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
