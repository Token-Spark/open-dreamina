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
  markSaved: (version: number) => void
  reset: () => void
}

export const useCanvasStore = create<CanvasState>((set) => ({
  canvasId: null,
  version: 1,
  nodes: [],
  edges: [],
  viewport: { x: 0, y: 0, zoom: 1 },
  isDirty: false,

  setCanvas: (canvasId, doc, version) =>
    set(() => ({
      canvasId,
      version,
      nodes: doc.nodes ?? [],
      edges: doc.edges ?? [],
      viewport: doc.viewport ?? { x: 0, y: 0, zoom: 1 },
      isDirty: false,
    })),

  setNodes: (nodes) => set({ nodes, isDirty: true }),

  setEdges: (edges) => set({ edges, isDirty: true }),

  addNode: (node) =>
    set((s) => ({ nodes: [...s.nodes, node], isDirty: true })),

  removeNode: (nodeId) =>
    set((s) => ({
      nodes: s.nodes.filter((n) => n.id !== nodeId),
      edges: s.edges.filter(
        (e) => e.source !== nodeId && e.target !== nodeId,
      ),
      isDirty: true,
    })),

  updateNodeData: (nodeId, patch) =>
    set((s) => ({
      nodes: s.nodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...patch } } : n,
      ),
      isDirty: true,
    })),

  setNodePosition: (nodeId, position) =>
    set((s) => ({
      nodes: s.nodes.map((n) =>
        n.id === nodeId ? { ...n, position } : n,
      ),
      isDirty: true,
    })),

  addEdge: (edge) =>
    set((s) => ({ edges: [...s.edges, edge], isDirty: true })),

  removeEdge: (edgeId) =>
    set((s) => ({
      edges: s.edges.filter((e) => e.id !== edgeId),
      isDirty: true,
    })),

  setViewport: (viewport) => set({ viewport, isDirty: true }),

  markSaved: (version) => set({ version, isDirty: false }),

  reset: () =>
    set({
      canvasId: null,
      version: 1,
      nodes: [],
      edges: [],
      viewport: { x: 0, y: 0, zoom: 1 },
      isDirty: false,
    }),
}))
