// Copyright 2026 Open Dreamina Contributors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0

import { useQuery } from '@tanstack/react-query'
import type { Connection } from '@xyflow/react'
import {
  getNodeSpecs,
  type CanvasEdge,
  type CanvasNode,
  type NodeSpecPort,
  type NodeSpecs,
} from '@/api/canvas'

/**
 * 与后端 `canvas_specs.NODE_SPECS` 对齐的兜底规格。
 * 单一真源是后端 `/canvas/node-specs`；这里只用于首屏与接口不可用时不至于
 * 连端口都渲染不出来，端口 id / types 必须与后端保持一致。
 */
export const FALLBACK_NODE_SPECS: NodeSpecs = {
  asset: {
    inputs: [],
    outputs: [{ id: 'out', types: ['image', 'video', 'audio'], multi: false, max: null }],
  },
  prompt: {
    inputs: [{ id: 'in', types: ['text'], multi: true, max: null }],
    outputs: [{ id: 'out', types: ['text'], multi: false, max: null }],
  },
  image_gen: {
    inputs: [
      { id: 'ref', types: ['image'], multi: true, max: 14 },
      { id: 'prompt', types: ['text'], multi: false, max: null },
    ],
    outputs: [{ id: 'out', types: ['image'], multi: false, max: null }],
  },
  video_gen: {
    inputs: [
      { id: 'ref', types: ['image'], multi: true, max: 9 },
      { id: 'video', types: ['video'], multi: true, max: 3 },
      { id: 'audio', types: ['audio'], multi: true, max: 3 },
      { id: 'prompt', types: ['text'], multi: false, max: null },
    ],
    outputs: [{ id: 'out', types: ['video'], multi: false, max: null }],
  },
  preview: {
    inputs: [{ id: 'in', types: ['image', 'video', 'audio', 'text'], multi: false, max: null }],
    outputs: [],
  },
  note: { inputs: [], outputs: [] },
}

export const NODE_SPECS_QUERY_KEY = ['canvas', 'node-specs'] as const

/**
 * 读取后端节点规格。多个节点组件与编辑器共用同一个 queryKey，
 * React Query 会去重，只会发一次请求。
 */
export function useNodeSpecs(): NodeSpecs {
  const { data } = useQuery({
    queryKey: NODE_SPECS_QUERY_KEY,
    queryFn: getNodeSpecs,
    staleTime: Infinity,
    retry: 1,
  })
  return data ?? FALLBACK_NODE_SPECS
}

export function inputPorts(specs: NodeSpecs, nodeType: string): NodeSpecPort[] {
  return specs[nodeType]?.inputs ?? []
}

export function outputPorts(specs: NodeSpecs, nodeType: string): NodeSpecPort[] {
  return specs[nodeType]?.outputs ?? []
}

/** 连线落到节点主体而非具体端口时，补上该侧第一个端口，避免产生无端口边。 */
export function normalizeConnection(
  conn: Connection,
  specs: NodeSpecs,
  nodes: CanvasNode[],
): Connection | null {
  const source = nodes.find((n) => n.id === conn.source)
  const target = nodes.find((n) => n.id === conn.target)
  if (!source || !target) return null
  const sourceHandle = conn.sourceHandle || outputPorts(specs, source.type)[0]?.id || null
  const targetHandle = conn.targetHandle || inputPorts(specs, target.type)[0]?.id || null
  return { ...conn, sourceHandle, targetHandle }
}

/** 加入 source → target 后是否会成环：从 target 出发能否沿现有边走回 source。 */
function wouldCreateCycle(edges: CanvasEdge[], source: string, target: string): boolean {
  const adjacency = new Map<string, string[]>()
  for (const edge of edges) {
    const list = adjacency.get(edge.source) ?? []
    list.push(edge.target)
    adjacency.set(edge.source, list)
  }
  const visited = new Set<string>([target])
  const queue = [target]
  while (queue.length) {
    const current = queue.shift()!
    if (current === source) return true
    for (const next of adjacency.get(current) ?? []) {
      if (!visited.has(next)) {
        visited.add(next)
        queue.push(next)
      }
    }
  }
  return false
}

export interface ConnectionCheck {
  ok: boolean
  reason?: string
  /** 规范化后的连接（sourceHandle / targetHandle 已补齐），可直接生成边 */
  connection?: Connection
}

/**
 * 前端连线校验，规则与后端 canvas_validate 对齐：
 * 端口存在 → 类型兼容 → 不重复 → 不超容量 → 不成环 → 不自连。
 * 这样用户能拉出来的边，后端保存时一定不会被判为非法。
 */
export function checkConnection(
  raw: Connection,
  specs: NodeSpecs,
  nodes: CanvasNode[],
  edges: CanvasEdge[],
): ConnectionCheck {
  if (!raw.source || !raw.target) return { ok: false, reason: '连线缺少端点' }
  if (raw.source === raw.target) return { ok: false, reason: '不能连接到自身' }

  const connection = normalizeConnection(raw, specs, nodes)
  if (!connection) return { ok: false, reason: '连线的节点不存在' }

  const sourceNode = nodes.find((n) => n.id === connection.source)
  const targetNode = nodes.find((n) => n.id === connection.target)
  if (!sourceNode || !targetNode) return { ok: false, reason: '连线的节点不存在' }

  const outPort = outputPorts(specs, sourceNode.type).find((p) => p.id === connection.sourceHandle)
  const inPort = inputPorts(specs, targetNode.type).find((p) => p.id === connection.targetHandle)
  if (!outPort || !inPort) {
    return { ok: false, reason: '端口不存在，请连接到具体的输入 / 输出端口' }
  }
  if (!outPort.types.some((type) => inPort.types.includes(type))) {
    return {
      ok: false,
      reason: `端口类型不兼容（${outPort.types.join('/')} → ${inPort.types.join('/')}）`,
    }
  }

  const sourcePort = connection.sourceHandle ?? ''
  const targetPort = connection.targetHandle ?? ''
  if (
    edges.some(
      (e) =>
        e.source === connection.source &&
        e.target === connection.target &&
        e.source_port === sourcePort &&
        e.target_port === targetPort,
    )
  ) {
    return { ok: false, reason: '这条连线已存在' }
  }

  const existing = edges.filter((e) => e.target === connection.target && e.target_port === targetPort)
  const limit = inPort.multi ? (inPort.max ?? Infinity) : 1
  if (existing.length >= limit) {
    return { ok: false, reason: `该端口最多允许 ${limit} 条连线` }
  }

  if (wouldCreateCycle(edges, connection.source, connection.target)) {
    return { ok: false, reason: '这条连线会形成环' }
  }

  return { ok: true, connection }
}
