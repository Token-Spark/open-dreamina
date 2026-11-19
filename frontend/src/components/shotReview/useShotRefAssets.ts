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

/**
 * 审片条目「被引用资产」→ 创作页 ReferenceAsset 的桥接。
 *
 * 后端只在审片卡片上保存 asset_id 列表与派生 URL（见 schemas_shot_review.py），
 * 不含素材类型 / 审核状态 / 时长。这里按 id 逐条补查素材详情，让审片页能复用
 * ReferenceAssetTray、PromptMentionOverlay 与 ImageLightbox，获得与创作页一致的
 * 参考素材陈列与预览体验。素材被删或后端不可达时回退为「参考图」，不阻塞编辑。
 */

import { useEffect, useMemo, useState } from 'react'
import { assetFileUrl, assetThumbnailUrl, getAsset, type AssetAuditStatus } from '@/api/assets'
import type { ShotReviewItem } from '@/api/shotReviews'
import type { LightboxItem } from '@/components/ImageLightbox'
import type { ReferenceKind } from '@/components/ReferenceSlot'
import type { ReferenceAsset } from '@/lib/promptMention'
import { refAssetThumbUrl } from '@/lib/assetPreview'

interface AssetMeta {
  kind: ReferenceKind
  auditStatus?: AssetAuditStatus
  auditError?: string | null
  duration?: number
}

const IMAGE_FALLBACK: AssetMeta = { kind: 'image' }

export interface ShotRefAssets {
  /** 与创作页输入条同构的参考素材列表，可直接喂给 ReferenceAssetTray。 */
  refAssets: ReferenceAsset[]
  /** 灯箱画廊：多张参考素材可左右切换。 */
  gallery: LightboxItem[]
  /** 素材详情补查中（列表已可用，仅元信息未到）。 */
  loading: boolean
  /** 详情补查已完成（无资产时直接为 true）：消费方可据此决定何时开始审核等后续动作。 */
  detailsReady: boolean
}

export function useShotRefAssets(item: ShotReviewItem | null): ShotRefAssets {
  const ids = useMemo(
    () => (item?.input_asset_ids ?? []).filter((id): id is string => typeof id === 'string' && !!id),
    [item?.input_asset_ids],
  )
  const urls = useMemo(() => item?.input_asset_urls ?? [], [item?.input_asset_urls])

  const [metas, setMetas] = useState<AssetMeta[]>([])
  const [detailsReady, setDetailsReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    setDetailsReady(false)
    if (ids.length === 0) {
      setMetas([])
      setDetailsReady(true)
      return
    }
    // 先按「参考图」占位，详情请求期间托盘不会空白
    setMetas(ids.map(() => IMAGE_FALLBACK))
    void Promise.all(
      ids.map(async (id): Promise<AssetMeta> => {
        try {
          const asset = await getAsset(id)
          const kind: ReferenceKind =
            asset.type === 'video' || asset.type === 'audio' ? asset.type : 'image'
          return {
            kind,
            auditStatus: asset.audit_status ?? undefined,
            auditError: asset.audit_error,
            duration: kind !== 'image' && asset.duration != null ? asset.duration : undefined,
          }
        } catch {
          // 素材可能已被删除；保留占位，预览时由图片的 onError 兜底
          return IMAGE_FALLBACK
        }
      }),
    ).then((next) => {
      if (cancelled) return
      setMetas(next)
      setDetailsReady(true)
    })
    return () => {
      cancelled = true
    }
  }, [ids])

  const refAssets = useMemo<ReferenceAsset[]>(
    () =>
      ids.map((id, i) => {
        const previewUrl = urls[i] || assetFileUrl(id)
        const kind = metas[i]?.kind ?? 'image'
        return {
          assetId: id,
          previewUrl,
          // 音频的 /thumbnail 返回的是音频原始字节，直接当图片会破图并被标成
          // 「素材不可用」；统一解析成专用音频封面。
          thumbUrl: refAssetThumbUrl({ kind, previewUrl, thumbUrl: assetThumbnailUrl(id) }),
          name: `参考 ${i + 1}`,
          kind,
          auditStatus: metas[i]?.auditStatus,
          auditError: metas[i]?.auditError,
          duration: metas[i]?.duration,
        }
      }),
    [ids, urls, metas],
  )

  const gallery = useMemo<LightboxItem[]>(
    () =>
      refAssets.map((asset, i) => ({
        url: asset.previewUrl,
        type: asset.kind === 'image' ? 'image' : asset.kind === 'video' ? 'video' : 'audio',
        title: asset.name ?? `参考 ${i + 1}`,
        meta: {
          素材类型: asset.kind === 'image' ? '参考图' : asset.kind === 'video' ? '参考视频' : '参考音频',
          '资产 ID': asset.assetId,
          ...(asset.duration != null ? { 时长: `${asset.duration}s` } : {}),
        },
      })),
    [refAssets],
  )

  return {
    refAssets,
    gallery,
    loading: ids.length > 0 && !detailsReady,
    detailsReady,
  }
}
