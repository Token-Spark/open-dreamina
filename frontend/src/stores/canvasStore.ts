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

import { create } from 'zustand'
import type { CanvasDocumentPayload, CanvasNode, CanvasEdge } from '@/api/canvas'

interface CanvasState {
  /** 当前编辑的画布 ID */
  canvasId: string | null
  /** 当前文档版本号（乐观锁基准） */
  version: number
  /** 节点列表（React Flow 格式） */
  nodes: CanvasNode[]
  /** 边列表（React Flow 格式） */
  edges: CanvasEdge[]
  /** 视口状态 */
  viewport: { x: number; y: number; zoom: number }
  /** 是否有未保存的修改 */
  isDirty: boolean
  /** 每次本地写操作递增；保存返回时用它判断期间是否又产生了新编辑 */
  revision: number

  setCanvas: (canvasId: string, doc: CanvasDocumentPayload, version: number) => void
  setNodes: (nodes: CanvasNode[]) => void
  setEdges: (edges: CanvasEdge[]) => void
  addNode: (node: CanvasNode) => void
  removeNode: (nodeId: string) => void
  updateNodeData: (nodeId: string, patch: Record<string, unknown>) => void
  setNodePosition: (nodeId: string, position: { x: number; y: number }) => void
  addEdge: (edge: CanvasEdge) => void
  removeEdge: (edgeId: string) => void
  setViewport: (viewport: { x: number; y: number; zoom: number }) => void
  /** 保存成功：只有发起保存后没有新编辑时才清脏标记 */
  markSaved: (version: number, savedRevision: number) => void
  /** 409 冲突后把基线对齐到服务端最新版本，不动本地文档 */
  setVersion: (version: number) => void
  reset: () => void
}

export const useCanvasStore = create<CanvasState>((set) => ({
  canvasId: null,
  version: 1,
  nodes: [],
  edges: [],
  viewport: { x: 0, y: 0, zoom: 1 },
  isDirty: false,
  revision: 0,

  setCanvas: (canvasId, doc, version) =>
    set(() => ({
      canvasId,
      version,
      nodes: doc.nodes ?? [],
      edges: doc.edges ?? [],
      viewport: doc.viewport ?? { x: 0, y: 0, zoom: 1 },
      isDirty: false,
    })),

  setNodes: (nodes) => set((s) => ({ nodes, isDirty: true, revision: s.revision + 1 })),

  setEdges: (edges) => set((s) => ({ edges, isDirty: true, revision: s.revision + 1 })),

  addNode: (node) =>
    set((s) => ({ nodes: [...s.nodes, node], isDirty: true, revision: s.revision + 1 })),

  removeNode: (nodeId) =>
    set((s) => ({
      nodes: s.nodes.filter((n) => n.id !== nodeId),
      edges: s.edges.filter(
        (e) => e.source !== nodeId && e.target !== nodeId,
      ),
      isDirty: true,
      revision: s.revision + 1,
    })),

  updateNodeData: (nodeId, patch) =>
    set((s) => ({
      nodes: s.nodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...patch } } : n,
      ),
      isDirty: true,
      revision: s.revision + 1,
    })),

  setNodePosition: (nodeId, position) =>
    set((s) => ({
      nodes: s.nodes.map((n) =>
        n.id === nodeId ? { ...n, position } : n,
      ),
      isDirty: true,
      revision: s.revision + 1,
    })),

  addEdge: (edge) =>
    set((s) => ({ edges: [...s.edges, edge], isDirty: true, revision: s.revision + 1 })),

  removeEdge: (edgeId) =>
    set((s) => ({
      edges: s.edges.filter((e) => e.id !== edgeId),
      isDirty: true,
      revision: s.revision + 1,
    })),

  setViewport: (viewport) =>
    set((s) => ({ viewport, isDirty: true, revision: s.revision + 1 })),

  markSaved: (version, savedRevision) =>
    set((s) => ({
      version,
      isDirty: s.revision === savedRevision ? false : s.isDirty,
    })),

  setVersion: (version) => set({ version }),

  reset: () =>
    set({
      canvasId: null,
      version: 1,
      nodes: [],
      edges: [],
      viewport: { x: 0, y: 0, zoom: 1 },
      isDirty: false,
      revision: 0,
    }),
}))
