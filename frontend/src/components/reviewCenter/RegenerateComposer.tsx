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

import { useEffect, useState } from 'react'
import { Info, X } from 'lucide-react'
import { GenerationInputBar } from '@/components/GenerationInputBar'
import { useProviders } from '@/hooks/useProviders'
import { useAssetAudit } from '@/hooks/useAssetAudit'
import { toast } from '@/stores/uiStore'
import {
  ASPECT_RATIOS_BY_MODE,
  defaultParamsForType,
  deriveTaskType,
  defaultResolutionForMode,
  modelsForCategory,
  sizeFromRatioResolution,
  type AspectRatio,
  type ContentMode,
} from '@/lib/generation'
import {
  MAX_AUDIO_TOTAL_DURATION,
  effectiveFrameMode,
  frameModeSpec,
  isSeedanceProvider,
  normalizeFrameMode,
  type ReferenceAsset,
} from '@/lib/promptMention'
import type { ShotRegenerationPayload, ShotReviewItem } from '@/api/shotReviews'

/**
 * 任务卡片内的返工生成模块。
 *
 * 直接复用创作页的 `GenerationInputBar`（提示词、@ 引用、参考素材、模型/画幅/时长
 * 选择、全屏编辑全部同源），因此审阅人不需要回创作页重建一次上下文：
 * 在卡片上改完提示词就能提交同一条生成管线。
 */
export interface RegenerateComposerProps {
  item: ShotReviewItem
  submitting: boolean
  atConcurrencyLimit: boolean
  onSubmit: (payload: ShotRegenerationPayload) => void
  onClose: () => void
}

/** 从成片反推画幅：短剧多为 9:16，若按默认 16:9 返工会把竖屏镜头改坏。 */
function seedAspectRatio(item: ShotReviewItem, mode: ContentMode): AspectRatio {
  const ratios = ASPECT_RATIOS_BY_MODE[mode].filter((r) => r.value !== 'auto')
  if (!item.width || !item.height || item.width <= 0 || item.height <= 0) {
    return ratios[0].value
  }
  const actual = item.width / item.height
  let best = ratios[0]
  for (const r of ratios) {
    if (Math.abs(r.ratio - actual) < Math.abs(best.ratio - actual)) best = r
  }
  return best.value
}

function seedParams(item: ShotReviewItem, mode: ContentMode): Record<string, number | string> {
  const type = deriveTaskType(mode, false)
  const params = defaultParamsForType(type)
  const ratio = seedAspectRatio(item, mode)
  const resolution = defaultResolutionForMode(mode)
  const { width, height } = sizeFromRatioResolution(ratio, resolution, mode)
  params.aspect_ratio = ratio
  params.resolution = resolution
  params.width = width
  params.height = height
  // 时长对齐原片（取整并交给模型的时长范围校验兜底夹紧）
  if (mode === 'video' && item.duration != null && item.duration > 0) {
    params.duration = Math.max(1, Math.round(item.duration))
  }
  return params
}

export function RegenerateComposer({
  item,
  submitting,
  atConcurrencyLimit,
  onSubmit,
  onClose,
}: RegenerateComposerProps) {
  const mode: ContentMode = item.content_type === 'image' ? 'image' : 'video'
  // 初始提示词：优先审阅人已改写的精修提示词，其次分镜底稿
  const [prompt, setPrompt] = useState(item.revised_prompt || item.source_prompt || '')
  // 参考素材（首帧图、参考视频/音频）留空：审阅人可按需追加，空即纯文本生成
  const [refAssets, setRefAssets] = useState<ReferenceAsset[]>([])
  const [providerSlug, setProviderSlug] = useState('')
  const [modelId, setModelId] = useState('')
  const [params, setParams] = useState<Record<string, number | string>>(() => seedParams(item, mode))

  const { data: providers } = useProviders()
  const { ensureAudited, augmentRefAssets, checkAuditGate } = useAssetAudit(providerSlug)
  const auditedRefAssets = augmentRefAssets(refAssets)
  useEffect(() => {
    ensureAudited(refAssets)
  }, [refAssets, ensureAudited])

  // 默认服务：优先选原条目所用模型所在的服务，其次任一支持该内容模式的服务
  useEffect(() => {
    if (providerSlug || !providers) return
    const active = providers.filter((p) => p.is_active)
    const byModel = item.model
      ? active.find((p) => modelsForCategory(p, mode).some((m) => m.id === item.model))
      : undefined
    const target =
      byModel ??
      active.find((p) => modelsForCategory(p, mode).length > 0) ??
      active[0]
    if (target) setProviderSlug(target.slug)
  }, [providers, providerSlug, mode, item.model])

  // 模型兜底：当前模型不在该服务的可选列表中时，优先回落到原条目所用模型
  useEffect(() => {
    if (!providers) return
    const provider = providers.find((p) => p.slug === providerSlug && p.is_active)
    const available = modelsForCategory(provider, mode)
    if (!available.length) {
      setModelId('')
      return
    }
    if (available.some((m) => m.id === modelId)) return
    const sameAsSource = item.model ? available.find((m) => m.id === item.model) : undefined
    setModelId((sameAsSource ?? available[0]).id)
  }, [providers, providerSlug, mode, modelId, item.model])

  function handleGenerate() {
    if (!providerSlug) return toast('请先在设置中启用一个服务提供商', 'error')
    if (!prompt.trim()) return toast('请输入提示词', 'error')

    const hasRef = auditedRefAssets.length > 0
    const taskType = deriveTaskType(mode, hasRef)
    if (!hasRef && (taskType === 'img2img' || taskType === 'img2video')) {
      return toast('请上传参考素材', 'error')
    }
    const seedance = isSeedanceProvider(providerSlug)
    const frameMode = normalizeFrameMode(params.frame_mode)
    const spec = frameModeSpec(mode, seedance, frameMode)
    if (spec) {
      const imageCount = auditedRefAssets.filter((a) => (a.kind ?? 'image') === 'image').length
      if (imageCount < spec.required) {
        return toast(`${spec.label}模式需上传 ${spec.required} 张参考图`, 'error')
      }
    }
    if (!checkAuditGate(auditedRefAssets)) return
    if (seedance && mode === 'video') {
      const audioTotal = auditedRefAssets
        .filter((a) => (a.kind ?? 'image') === 'audio')
        .reduce((sum, a) => sum + (a.duration ?? 0), 0)
      if (audioTotal > MAX_AUDIO_TOTAL_DURATION) {
        return toast(`参考音频总时长 ${audioTotal.toFixed(1)} 秒，超过 ${MAX_AUDIO_TOTAL_DURATION} 秒上限`, 'error')
      }
    }

    onSubmit({
      prompt: prompt.trim(),
      provider: providerSlug,
      model_id: modelId || undefined,
      task_type: taskType,
      // 与创作页一致：Seedance 把合并模式解析为 text/reference 再上送
      params: seedance
        ? { ...params, frame_mode: effectiveFrameMode(frameMode, hasRef) }
        : params,
      input_asset_ids: auditedRefAssets.map((a) => a.assetId),
    })
  }

  return (
    <div className="mt-3 border-t border-border pt-3">
      <div className="mb-2 flex items-start justify-between gap-3">
        <p className="flex items-center gap-1.5 text-[11px] text-fg-muted">
          <Info className="h-3 w-3 shrink-0" />
          复用创作页生成模块：改提示词、加参考图、换模型或画幅后重新生成，结果会作为该镜的新版本回到本卡片
        </p>
        <button
          type="button"
          onClick={onClose}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-btn text-fg-muted transition-colors hover:bg-bg-tertiary hover:text-fg-primary"
          aria-label="收起返工面板"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <GenerationInputBar
        variant="compact"
        mode={mode}
        onModeChange={() => {}}
        prompt={prompt}
        onPromptChange={setPrompt}
        providerSlug={providerSlug}
        modelId={modelId}
        onProviderChange={setProviderSlug}
        onModelChange={setModelId}
        params={params}
        onParamsChange={setParams}
        refAssets={auditedRefAssets}
        onRefAssetsChange={setRefAssets}
        onGenerate={handleGenerate}
        submitting={submitting}
        atConcurrencyLimit={atConcurrencyLimit}
      />
    </div>
  )
}
