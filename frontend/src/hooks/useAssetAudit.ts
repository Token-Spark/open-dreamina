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

import { useCallback, useRef, useState } from 'react'
import { submitAssetAudit, getAssetAudit, type AssetAuditStatus } from '@/api/assets'
import { isSparkHubSeedance, type ReferenceAsset } from '@/components/GenerationInputBar'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'

interface AuditState {
  status: AssetAuditStatus | undefined
  error: string | null
}

/**
 * Spark Hub Seedance 参考素材审核 hook。
 *
 * 画布中通过连线推导的参考素材不经过上传流程，缺少审核状态。
 * 此 hook 在 Spark Hub Seedance 供应商下自动为这些素材提审并轮询，
 * 并在生成前提供审核门禁校验。手动上传的素材审核状态由
 * GenerationInputBar 内联管理，此 hook 通过 augmentRefAssets 合并展示。
 */
export function useAssetAudit(providerSlug: string) {
  const [auditStates, setAuditStates] = useState<Record<string, AuditState>>({})
  // 已提审的 assetId 集合，避免 useEffect 重复触发提审
  const submittedRef = useRef<Set<string>>(new Set())

  const patchAudit = useCallback((assetId: string, patch: Partial<AuditState>) => {
    setAuditStates((prev) => ({
      ...prev,
      [assetId]: { status: prev[assetId]?.status, error: prev[assetId]?.error, ...patch },
    }))
  }, [])

  const pollAudit = useCallback(async (assetId: string) => {
    try {
      const asset = await getAssetAudit(assetId, providerSlug)
      patchAudit(assetId, {
        status: asset.audit_status ?? undefined,
        error: asset.audit_error,
      })
      if (asset.audit_status === 'pending') {
        window.setTimeout(() => pollAudit(assetId), 3000)
      }
    } catch {
      // 轮询失败（如网络抖动）静默忽略，下次上传/刷新时重新查询
    }
  }, [providerSlug, patchAudit])

  const startAudit = useCallback(async (assetId: string) => {
    try {
      const asset = await submitAssetAudit(assetId, providerSlug)
      patchAudit(assetId, {
        status: asset.audit_status ?? 'pending',
        error: asset.audit_error,
      })
      if (asset.audit_status === 'pending') {
        window.setTimeout(() => pollAudit(assetId), 3000)
      }
    } catch (e) {
      patchAudit(assetId, { status: 'failed', error: toApiError(e).message })
      toast(toApiError(e).message, 'error')
    }
  }, [providerSlug, patchAudit, pollAudit])

  /**
   * 为缺少审核状态的图片/视频参考素材自动提审。
   * 音频无需审核；已有 auditStatus（手动上传流程设置）或已提审的素材跳过。
   */
  const ensureAudited = useCallback(
    (refAssets: ReferenceAsset[]) => {
      if (!isSparkHubSeedance(providerSlug)) return
      for (const asset of refAssets) {
        const kind = asset.kind ?? 'image'
        if (kind === 'audio') continue
        if (asset.auditStatus) continue
        if (submittedRef.current.has(asset.assetId)) continue
        submittedRef.current.add(asset.assetId)
        patchAudit(asset.assetId, { status: 'pending', error: null })
        void startAudit(asset.assetId)
      }
    },
    [providerSlug, patchAudit, startAudit],
  )

  /** 将 hook 管理的审核状态合并到参考素材列表上（用于渲染审核徽标）。 */
  const augmentRefAssets = useCallback(
    (refAssets: ReferenceAsset[]): ReferenceAsset[] => {
      return refAssets.map((a) => {
        const state = auditStates[a.assetId]
        return state
          ? { ...a, auditStatus: state.status, auditError: state.error }
          : a
      })
    },
    [auditStates],
  )

  /**
   * 审核门禁：Spark Hub Seedance 下，图片/视频参考素材须全部审核通过才能生成。
   * 返回 false 时已弹出提示，调用方直接 return 即可。
   */
  const checkAuditGate = useCallback(
    (refAssets: ReferenceAsset[]): boolean => {
      if (!isSparkHubSeedance(providerSlug)) return true
      const auditable = refAssets.filter((a) => (a.kind ?? 'image') !== 'audio')
      const resolveStatus = (a: ReferenceAsset) =>
        auditStates[a.assetId]?.status ?? a.auditStatus
      const unaudited = auditable.filter((a) => resolveStatus(a) !== 'active')
      if (unaudited.length) {
        const pending = unaudited.some((a) => resolveStatus(a) === 'pending')
        toast(
          pending
            ? '参考素材正在审核中，请等待审核通过后再生成'
            : '参考素材未通过审核，无法生成',
          'error',
        )
        return false
      }
      return true
    },
    [providerSlug, auditStates],
  )

  return { ensureAudited, augmentRefAssets, checkAuditGate }
}
