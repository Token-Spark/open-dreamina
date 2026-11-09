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

import type { CanvasNode, CanvasEdge } from '@/api/canvas'
import type { ReferenceAsset } from '@/components/GenerationInputBar'
import { assetFileUrl } from '@/api/assets'

/** 可以作为参考素材来源的节点类型 */
const SOURCE_TYPES = new Set(['asset', 'image_gen', 'video_gen'])

/** 生成节点上承载参考素材的输入端口，与后端 NODE_SPECS 保持一致 */
const REF_PORTS = new Set(['ref', 'video', 'audio'])

/** 按 order 排序的入边，保证多参考素材的顺序稳定 */
function incomingToPort(
  edges: CanvasEdge[],
  targetNodeId: string,
  port: string,
): CanvasEdge[] {
  return edges
    .filter((e) => e.target === targetNodeId && (e.target_port === port || !e.target_port))
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
}

/**
 * 根据连线关系，为某个生成节点推导出由上游节点贡献的参考素材列表。
 *
 * 素材节点或图片/视频生成节点通过 ref / video / audio 端口连到生成节点时，
 * 下游节点的参考素材自动包含上游已产出或选中的内容。
 */
export function deriveEdgeRefAssets(
  edges: CanvasEdge[],
  nodes: CanvasNode[],
  targetNodeId: string,
): ReferenceAsset[] {
  const seen = new Set<CanvasEdge>()
  const incoming: CanvasEdge[] = []
  for (const port of REF_PORTS) {
    for (const edge of incomingToPort(edges, targetNodeId, port)) {
      if (!seen.has(edge)) {
        seen.add(edge)
        incoming.push(edge)
      }
    }
  }

  const result: ReferenceAsset[] = []
  for (const edge of incoming) {
    const source = nodes.find((n) => n.id === edge.source)
    if (!source || !SOURCE_TYPES.has(source.type)) continue
    const asset = extractRefAssetFromNode(source)
    if (asset) result.push(asset)
  }
  return result
}

/**
 * 读取连到生成节点 prompt 端口的上游提示词文本。
 * 存在时由连线提供提示词，本地 data.prompt 作为回退。
 */
export function deriveEdgePrompt(
  edges: CanvasEdge[],
  nodes: CanvasNode[],
  targetNodeId: string,
): string | null {
  const texts: string[] = []
  for (const edge of incomingToPort(edges, targetNodeId, 'prompt')) {
    const source = nodes.find((n) => n.id === edge.source)
    if (!source || (source.type !== 'prompt' && source.type !== 'note')) continue
    const text = source.data.text
    if (typeof text === 'string' && text.trim()) texts.push(text.trim())
  }
  return texts.length ? texts.join('\n') : null
}

/** 从上游节点数据中提取一条参考素材 */
function extractRefAssetFromNode(node: CanvasNode): ReferenceAsset | null {
  const d = node.data

  // 素材节点：直接使用已选中的 asset_id
  if (node.type === 'asset') {
    const assetId = d.asset_id as string | undefined
    if (!assetId) return null
    return {
      assetId,
      previewUrl: (d.asset_thumb as string) ?? assetFileUrl(assetId),
      kind: (d.asset_type as ReferenceAsset['kind']) ?? 'image',
    }
  }

  // 生成节点：使用已选中（或首张）生成结果作为参考素材
  if (node.type === 'image_gen' || node.type === 'video_gen') {
    const resultUrls = (d.result_urls as string[])?.length
      ? (d.result_urls as string[])
      : d.result_url
        ? [d.result_url as string]
        : []
    const selectedIndex = Math.min(
      (d.selected_result as number) ?? 0,
      Math.max(0, resultUrls.length - 1),
    )
    const selectedUrl = resultUrls[selectedIndex]
    if (!selectedUrl) return null
    // 生成结果以 asset 文件 URL 形式提供，从中解析 asset ID
    const assetId = extractAssetIdFromUrl(selectedUrl)
    if (!assetId) return null
    return {
      assetId,
      previewUrl: selectedUrl,
      kind: node.type === 'video_gen' ? 'video' : 'image',
    }
  }

  return null
}

/** 从 /api/v1/assets/{id}/file 或 /thumbnail URL 中提取 asset ID */
function extractAssetIdFromUrl(url: string): string | null {
  const m = url.match(/\/assets\/([^/]+)\/(?:file|thumbnail)/)
  return m?.[1] ?? null
}

/**
 * 合并由连线推导的参考素材与手动添加的参考素材，按 assetId 去重。
 * 连线推导的素材排在前面。
 */
export function mergeRefAssets(
  edgeAssets: ReferenceAsset[],
  manualAssets: ReferenceAsset[],
): ReferenceAsset[] {
  const seen = new Set(edgeAssets.map((a) => a.assetId))
  return [...edgeAssets, ...manualAssets.filter((a) => !seen.has(a.assetId))]
}
