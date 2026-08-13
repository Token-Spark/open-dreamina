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

import { useEffect, useRef, useState } from 'react'
import type * as React from 'react'
import {
  Wand2,
  ChevronDown,
  ImageIcon,
  MonitorPlay,
  Clock,
  Film,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Dropdown, DropdownItem } from '@/components/ui/Dropdown'
import { ReferenceSlot, type ReferenceKind } from '@/components/ReferenceSlot'
import { ModelPicker } from '@/components/ModelPicker'
import { SizePicker } from '@/components/SizePicker'
import { uploadAsset, assetFileUrl, submitAssetAudit, getAssetAudit } from '@/api/assets'
import {
  CONTENT_MODES,
  sizeFromRatioResolution,
  type ContentMode,
  type AspectRatio,
  type Resolution,
} from '@/lib/generation'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { cn } from '@/lib/utils'

/** 一个参考素材（图片/视频/音频）：assetId 用于提交任务，previewUrl 用于本地预览。 */
export interface ReferenceAsset {
  assetId: string
  previewUrl: string
  /** 素材类型；旧数据缺省按图片处理。 */
  kind?: ReferenceKind
  /** Seedance 参考素材审核状态（仅 Spark Hub Seedance 需要）；undefined 表示未提交审核。 */
  auditStatus?: 'pending' | 'active' | 'failed'
  /** 审核失败原因。 */
  auditError?: string | null
}

/**
 * 视频模式多模态参考限制（火山方舟 Seedance 2.0 系列：参考图 0-9 + 参考视频 0-3 + 参考音频 0-3）。
 * 参考: 创建视频生成任务 API（.trae/docs/火山方舟 - 视频生成 API）。
 */
const MAX_REF_IMAGES = 9
const MAX_REF_VIDEOS = 3
const MAX_REF_AUDIOS = 3
const MAX_IMAGE_BYTES = 30 * 1024 * 1024 // 单张图片 < 30 MB
const MAX_VIDEO_BYTES = 200 * 1024 * 1024 // 单个视频 ≤ 200 MB
const MAX_AUDIO_BYTES = 15 * 1024 * 1024 // 单个音频 ≤ 15 MB
/** API 仅接受 mp4/mov 参考视频、wav/mp3 参考音频（按扩展名兑底，部分浏览器 MIME 缺失）。 */
const VIDEO_EXTS = ['.mp4', '.mov']
const AUDIO_EXTS = ['.wav', '.mp3']
const KIND_CAPS: Record<ReferenceKind, number> = {
  image: MAX_REF_IMAGES,
  video: MAX_REF_VIDEOS,
  audio: MAX_REF_AUDIOS,
}
const KIND_SIZE_CAPS: Record<ReferenceKind, number> = {
  image: MAX_IMAGE_BYTES,
  video: MAX_VIDEO_BYTES,
  audio: MAX_AUDIO_BYTES,
}
const KIND_LABELS: Record<ReferenceKind, string> = {
  image: '参考图',
  video: '参考视频',
  audio: '参考音频',
}
/** 视频模式下文件选择器接受：图片 + mp4/mov 视频 + wav/mp3 音频。 */
const ACCEPT_VIDEO_MODE =
  'image/*,video/mp4,video/quicktime,audio/wav,audio/mpeg,audio/mp3,audio/x-wav,.mp4,.mov,.wav,.mp3'

/**
 * Seedance 视频生成帧模式（需求1：文生视频与参考图合二为一）。
 * auto 为合并模式：无参考图时按文生视频生成，上传图片后自动按参考图模式生成；
 * 提交时由 effectiveFrameMode 解析为后端接受的 text / reference。
 */
export type FrameMode = 'auto' | 'first' | 'first_last'

/** 解析后的后端帧模式（text / reference 仅作为 auto 的解析结果，不直接存储）。 */
export type EffectiveFrameMode = 'text' | 'first' | 'first_last' | 'reference'

/** 合并模式解析：无参考图 → 文生视频（text）；有参考图 → 多模态参考（reference）。 */
export function effectiveFrameMode(frameMode: FrameMode, hasImage: boolean): EffectiveFrameMode {
  if (frameMode === 'auto') return hasImage ? 'reference' : 'text'
  return frameMode
}

/** 归一化历史/外部传入的 frame_mode：旧数据中的 text / reference 均映射为合并模式 auto。 */
export function normalizeFrameMode(v: unknown): FrameMode {
  return v === 'first' || v === 'first_last' ? v : 'auto'
}

/**
 * 各帧模式对参考图片数量的要求（required 为提交任务所需张数）。
 * slots 为固定图片格子的角色标注（首帧/尾帧），用于在输入区渲染指定数量的上传格子；
 * auto（合并模式，含参考图状态）走多模态参考，不设固定格子，上限沿用 MAX_REF_IMAGES。
 * allowMultimodal 表示是否允许图片之外的视频/音频参考。
 */
const FRAME_MODES: {
  mode: FrameMode
  label: string
  hint: string
  maxImages: number
  required: number
  allowMultimodal: boolean
  slots?: string[]
}[] = [
  {
    mode: 'auto',
    label: '文生视频/参考图',
    hint: '无需图片可直接生成，上传图片自动转为参考图',
    maxImages: MAX_REF_IMAGES,
    required: 0,
    allowMultimodal: true,
  },
  { mode: 'first', label: '首帧', hint: '上传 1 张图片作为视频首帧', maxImages: 1, required: 1, allowMultimodal: false, slots: ['首帧'] },
  {
    mode: 'first_last',
    label: '首尾帧',
    hint: '上传 2 张图片，分别作为首帧与尾帧',
    maxImages: 2,
    required: 2,
    allowMultimodal: false,
    slots: ['首帧', '尾帧'],
  },
]

/** 当前帧模式配置；非 Seedance 视频/图片模式返回 null（走通用多模态限制）。 */
export function frameModeSpec(
  mode: ContentMode,
  isSeedance: boolean,
  frameMode: FrameMode,
): (typeof FRAME_MODES)[number] | null {
  if (mode !== 'video' || !isSeedance) return null
  return FRAME_MODES.find((m) => m.mode === frameMode) ?? null
}

/** 判断当前 provider 是否为 Seedance 系列（slug 含 seedance，或已知遗留别名 dreamina-cli）。 */
export function isSeedanceProvider(slug: string): boolean {
  const s = slug.toLowerCase()
  // dreamina-cli 是遗留 slug，后端实际使用 DreaminaSeedanceProvider（Seedance 系列），
  // 见 backend/app/providers/factory.py 中 "dreamina-cli" 注册项。
  return s.includes('seedance') || s === 'dreamina-cli'
}

/**
 * 判断是否为 Spark Hub Seedance 中转（唯一需要参考素材审核的 provider）。
 * 参考素材需先通过 seedance_asset_audit 审核，审核通过后才能用于视频生成。
 */
export function isSparkHubSeedance(slug: string): boolean {
  return slug === 'sparkhub-seedance'
}

export interface GenerationInputBarProps {
  /** 内容模式：图片 / 视频（需求1：合并文生图/图生图、文生视频/图生视频）。 */
  mode: ContentMode
  onModeChange: (mode: ContentMode) => void
  prompt: string
  negativePrompt: string
  onPromptChange: (v: string) => void
  onNegativeChange: (v: string) => void
  providerSlug: string
  modelId: string
  onProviderChange: (slug: string) => void
  onModelChange: (modelId: string) => void
  params: Record<string, number | string>
  onParamsChange: (params: Record<string, number | string>) => void
  /** 多张参考图（按上传顺序）。空数组表示无参考图。 */
  refAssets: ReferenceAsset[]
  onRefAssetsChange: (assets: ReferenceAsset[]) => void
  onGenerate: () => void
  submitting: boolean
  /** 是否已达并发上限：达到时仅禁用生成按钮，输入区仍可编辑以准备下一条任务。 */
  atConcurrencyLimit: boolean
}

export function GenerationInputBar({
  mode,
  onModeChange,
  prompt,
  onPromptChange,
  providerSlug,
  modelId,
  onProviderChange,
  onModelChange,
  params,
  onParamsChange,
  refAssets,
  onRefAssetsChange,
  onGenerate,
  submitting,
  atConcurrencyLimit,
}: GenerationInputBarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  // 镜像 refAssets，供异步审核轮询读取最新列表，避免闭包捕获过期状态。
  const refAssetsRef = useRef(refAssets)
  useEffect(() => {
    refAssetsRef.current = refAssets
  }, [refAssets])

  const aspectRatio = (params.aspect_ratio as AspectRatio) ?? '1:1'
  const resolution = (params.resolution as Resolution) ?? '2K'
  const duration = (params.duration as number) ?? 5
  const frameMode = normalizeFrameMode(params.frame_mode)
  const isSeedance = isSeedanceProvider(providerSlug)

  // 切回图片模式时移除视频/音频参考（图片模式不支持多模态参考）。
  useEffect(() => {
    if (mode === 'image' && refAssets.some((a) => (a.kind ?? 'image') !== 'image')) {
      onRefAssetsChange(refAssets.filter((a) => (a.kind ?? 'image') === 'image'))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  // Seedance 帧模式：合并模式（auto）无参考图时即文生视频，清空参考素材；
  // 首帧/首尾帧仅保留图片参考，视频/音频不适用。
  useEffect(() => {
    if (mode !== 'video' || !isSeedance) return
    const hasImage = refAssets.some((a) => (a.kind ?? 'image') === 'image')
    if (frameMode === 'auto') {
      if (!hasImage && refAssets.length > 0) onRefAssetsChange([])
      return
    }
    const cleaned = refAssets.filter((a) => (a.kind ?? 'image') === 'image')
    if (cleaned.length !== refAssets.length) {
      onRefAssetsChange(cleaned)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, frameMode, isSeedance, refAssets])

  // 首帧/首尾帧模式限制图片数量（首帧 1 张、首尾帧 2 张），超出部分按上传顺序裁剪并提醒。
  useEffect(() => {
    const spec = frameModeSpec(mode, isSeedance, frameMode)
    if (!spec) return
    const images = refAssets.filter((a) => (a.kind ?? 'image') === 'image')
    if (images.length > spec.maxImages) {
      onRefAssetsChange(images.slice(0, spec.maxImages))
      toast(`${spec.label}模式最多保留 ${spec.maxImages} 张参考图`, 'error')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, frameMode, isSeedance, refAssets])

  // 视频模式智能默认：未上传图片时自动回落到合并模式（文生视频）；
  // 上传图片后合并模式由 effectiveFrameMode 自动解析为参考图，无需改写 frame_mode。
  useEffect(() => {
    if (mode !== 'video' || !isSeedance) return
    const hasImage = refAssets.some((a) => (a.kind ?? 'image') === 'image')
    if (!hasImage && frameMode !== 'auto') {
      updateFrameMode('auto')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, isSeedance, refAssets])

  /** 识别文件类型；不支持的类型返回 null。 */
  function kindOfFile(file: File): ReferenceKind | null {
    const ext = '.' + (file.name.split('.').pop() ?? '').toLowerCase()
    if (file.type.startsWith('image/')) return 'image'
    if (file.type.startsWith('video/') || VIDEO_EXTS.includes(ext)) return 'video'
    if (file.type.startsWith('audio/') || AUDIO_EXTS.includes(ext)) return 'audio'
    return null
  }

  /** 更新单个参考素材的审核状态（基于 ref 镜像，避免闭包过期）。 */
  function patchAudit(assetId: string, patch: Partial<ReferenceAsset>) {
    const next = refAssetsRef.current.map((r) =>
      r.assetId === assetId ? { ...r, ...patch } : r,
    )
    refAssetsRef.current = next
    onRefAssetsChange(next)
  }

  /** 轮询 Spark Hub Seedance 参考素材审核状态，pending 时定时重查直到终态。 */
  async function pollAudit(assetId: string) {
    try {
      const asset = await getAssetAudit(assetId, providerSlug)
      const status = asset.audit_status
      patchAudit(assetId, {
        auditStatus: status ?? undefined,
        auditError: asset.audit_error,
      })
      if (status === 'pending') {
        window.setTimeout(() => pollAudit(assetId), 3000)
      }
    } catch {
      // 轮询失败（如网络抖动）静默忽略，下次上传/刷新时重新查询
    }
  }

  /** 提交 Spark Hub Seedance 参考素材审核，并异步轮询进度。 */
  async function startAudit(assetId: string) {
    patchAudit(assetId, { auditStatus: 'pending', auditError: null })
    try {
      const asset = await submitAssetAudit(assetId, providerSlug)
      patchAudit(assetId, {
        auditStatus: asset.audit_status ?? 'pending',
        auditError: asset.audit_error,
      })
      if (asset.audit_status === 'pending') {
        window.setTimeout(() => pollAudit(assetId), 3000)
      }
    } catch (e) {
      patchAudit(assetId, { auditStatus: 'failed', auditError: toApiError(e).message })
      toast(toApiError(e).message, 'error')
    }
  }

  // 串行上传多个素材，逐个追加到参考列表（避免并发状态竞争）。
  // 视频模式支持图片/视频/音频；图片模式仅支持图片。按文档限制数量与大小。
  async function handleUploadFiles(files: FileList | File[]) {
    const next: ReferenceAsset[] = [...refAssets]
    const added: ReferenceAsset[] = []
    for (const file of Array.from(files)) {
      const kind = kindOfFile(file)
      if (!kind) {
        toast(`不支持的文件类型：${file.name}`, 'error')
        continue
      }
      if (mode === 'image' && kind !== 'image') {
        toast('图片模式仅支持上传图片参考，视频/音频参考请在视频模式下使用', 'error')
        continue
      }
      if (kind === 'video' && !VIDEO_EXTS.includes('.' + (file.name.split('.').pop() ?? '').toLowerCase())) {
        toast(`参考视频仅支持 ${VIDEO_EXTS.join(' / ')} 格式：${file.name}`, 'error')
        continue
      }
      if (kind === 'audio' && !AUDIO_EXTS.includes('.' + (file.name.split('.').pop() ?? '').toLowerCase())) {
        toast(`参考音频仅支持 ${AUDIO_EXTS.join(' / ')} 格式：${file.name}`, 'error')
        continue
      }
      // Seedance 首帧/首尾帧模式仅接受图片参考，并按帧模式限制图片数量
      const spec = frameModeSpec(mode, isSeedance, frameMode)
      if (spec && !spec.allowMultimodal) {
        if (kind !== 'image') {
          toast(`${spec.label}模式仅支持上传图片参考`, 'error')
          continue
        }
        const imageCount = next.filter((a) => (a.kind ?? 'image') === 'image').length
        if (imageCount >= spec.maxImages) {
          toast(`${spec.label}模式最多上传 ${spec.maxImages} 张参考图`, 'error')
          continue
        }
      }
      // 合并模式：无参考图时即文生视频，视频/音频参考需先有参考图才作为参考图模式使用
      if (spec?.mode === 'auto' && kind !== 'image' && !next.some((a) => (a.kind ?? 'image') === 'image')) {
        toast('请先上传参考图，再上传视频/音频参考', 'error')
        continue
      }
      const cap = KIND_CAPS[kind]
      if (next.filter((a) => (a.kind ?? 'image') === kind).length >= cap) {
        toast(`${KIND_LABELS[kind]}最多 ${cap} 个`, 'error')
        continue
      }
      if (file.size > KIND_SIZE_CAPS[kind]) {
        toast(
          `${KIND_LABELS[kind]}超出大小限制（${Math.round(KIND_SIZE_CAPS[kind] / 1024 / 1024)} MB）：${file.name}`,
          'error',
        )
        continue
      }
      try {
        const asset = await uploadAsset(file)
        const ref: ReferenceAsset = {
          assetId: asset.id,
          previewUrl: assetFileUrl(asset.id),
          kind,
        }
        next.push(ref)
        added.push(ref)
        // Spark Hub Seedance：参考素材需先审核，上传后自动提审并异步轮询进度
        if (isSparkHubSeedance(providerSlug)) {
          startAudit(asset.id)
        }
      } catch (e) {
        toast(toApiError(e).message, 'error')
      }
    }
    if (added.length) {
      onRefAssetsChange(next)
      toast(`已上传 ${added.length} 个参考素材`, 'success')
    }
  }

  function removeRef(index: number) {
    onRefAssetsChange(refAssets.filter((_, i) => i !== index))
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    const files = Array.from(e.dataTransfer.files ?? [])
    if (files.length) handleUploadFiles(files)
  }

  function onPaste(e: React.ClipboardEvent) {
    const items = e.clipboardData.items
    const files: File[] = []
    for (let i = 0; i < items.length; i++) {
      const t = items[i].type
      // 粘贴通常只有图片；视频模式下兼容剪贴板中的视频/音频文件
      const allowed = t.startsWith('image/') || (mode === 'video' && (t.startsWith('video/') || t.startsWith('audio/')))
      if (allowed) {
        const file = items[i].getAsFile()
        if (file) files.push(file)
      }
    }
    if (files.length) {
      e.preventDefault()
      handleUploadFiles(files)
    }
  }

  function updateRatioResolution(nextRatio: AspectRatio, nextResolution: Resolution) {
    const { width, height } = sizeFromRatioResolution(nextRatio, nextResolution, mode)
    onParamsChange({ ...params, aspect_ratio: nextRatio, resolution: nextResolution, width, height })
  }

  function updateDuration(next: number) {
    onParamsChange({ ...params, duration: next })
  }

  function updateFrameMode(next: FrameMode) {
    onParamsChange({ ...params, frame_mode: next })
  }

  /** 当前模式下的参考素材提示文案。 */
  function refHint(): string {
    if (mode !== 'video' || !isSeedance) return ''
    return FRAME_MODES.find((m) => m.mode === frameMode)?.hint ?? ''
  }

  // 首帧/首尾帧模式：用带角色标注的固定格子渲染（首帧 1 格、首尾帧 2 格），
  // 已上传图片按上传顺序填充到格子中，让用户直观看到“还差哪一帧”。
  const activeFrameSpec = frameModeSpec(mode, isSeedance, frameMode)
  const frameSlots = activeFrameSpec?.slots ?? null
  const frameImages = frameSlots ? refAssets.filter((a) => (a.kind ?? 'image') === 'image') : []

  /** 移除固定格子中第 slotIndex 张图片（对应 frameImages 的下标）。 */
  function removeFrameImage(slotIndex: number) {
    const target = frameImages[slotIndex]
    if (!target) return
    onRefAssetsChange(refAssets.filter((a) => a.assetId !== target.assetId))
  }

  return (
    <div className="bg-transparent p-4">
      <div className="mx-auto max-w-4xl">
        <div
          className="relative rounded-2xl border border-border/60 bg-bg-secondary/70 p-4 shadow-xl backdrop-blur-md"
          onPaste={onPaste}
          onDrop={onDrop}
          onDragOver={(e) => e.preventDefault()}
        >
          {/* 已上传的参考素材列表（图片/视频/音频）；首帧/首尾帧模式下图片在下方固定格子中展示 */}
          {refAssets.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {refAssets.map((ref, i) =>
                frameSlots && (ref.kind ?? 'image') === 'image' ? null : (
                  <ReferenceSlot
                    key={ref.assetId}
                    previewUrl={ref.previewUrl}
                    kind={ref.kind ?? 'image'}
                    auditStatus={ref.auditStatus}
                    auditError={ref.auditError}
                    onPick={() => {}}
                    onClear={() => removeRef(i)}
                  />
                ),
              )}
            </div>
          )}

          {/* 输入区：参考图槽 + 提示词 */}
          <div className="flex gap-3">
            {frameSlots ? (
              // 首帧/首尾帧：渲染指定数量的角色格子；全部填满后不再显示上传按钮，
              // 需先移除已有图片才能重新上传。
              <div className="flex gap-2">
                {frameSlots.map((label, i) => (
                  <ReferenceSlot
                    key={label}
                    label={label}
                    previewUrl={frameImages[i]?.previewUrl ?? null}
                    auditStatus={frameImages[i]?.auditStatus}
                    auditError={frameImages[i]?.auditError}
                    onPick={() => fileInputRef.current?.click()}
                    onClear={() => removeFrameImage(i)}
                  />
                ))}
              </div>
            ) : (
              <ReferenceSlot
                previewUrl={null}
                onPick={() => fileInputRef.current?.click()}
                onClear={() => {}}
              />
            )}
            <div className="flex flex-1 flex-col gap-2">
              <textarea
                value={prompt}
                onChange={(e) => onPromptChange(e.target.value)}
                disabled={submitting}
                placeholder={
                  mode === 'video'
                    ? isSeedance
                      ? `${refHint()}，输入文字描述你想生成的视频。`
                      : '上传参考图/视频/音频、输入文字或 @主体，描述你想生成的视频。支持最多 9 张参考图、3 个参考视频、3 段参考音频。'
                    : '上传参考图、输入文字或 @主体，描述你想生成的图片。支持上传多张参考图融合生成。'
                }
                rows={3}
                className={cn(
                  'w-full resize-none bg-transparent text-base text-fg-primary placeholder:text-fg-muted',
                  'focus-visible:outline-none',
                )}
              />
              <input
                ref={fileInputRef}
                type="file"
                accept={mode === 'video' ? ACCEPT_VIDEO_MODE : 'image/*'}
                multiple
                className="hidden"
                onChange={(e) => {
                  if (e.target.files?.length) handleUploadFiles(e.target.files)
                  e.target.value = ''
                }}
              />
            </div>
          </div>

          {/* 底部工具栏 */}
          <div className="mt-3 flex flex-wrap items-center gap-2 pr-32">
            <ModeDropdown mode={mode} onChange={onModeChange} disabled={submitting} placement="top" />
            <ModelPicker
              mode={mode}
              providerSlug={providerSlug}
              modelId={modelId}
              onProviderChange={onProviderChange}
              onModelChange={onModelChange}
              disabled={submitting}
              placement="top"
            />
            <SizePicker
              mode={mode}
              aspectRatio={aspectRatio}
              resolution={resolution}
              onChange={updateRatioResolution}
              disabled={submitting}
              placement="top"
            />
            {mode === 'video' && (
              <DurationPicker duration={duration} onChange={updateDuration} disabled={submitting} />
            )}
            {mode === 'video' && isSeedance && (
              <FrameModePicker frameMode={frameMode} onChange={updateFrameMode} disabled={submitting} />
            )}

            <Button
              size="md"
              onClick={onGenerate}
              disabled={submitting || atConcurrencyLimit}
              className="absolute bottom-4 right-4"
            >
              <Wand2 className="h-4 w-4" />
              {submitting ? '提交中…' : atConcurrencyLimit ? '并发已满' : '生成'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

function ModeDropdown({
  mode,
  onChange,
  disabled,
  placement = 'bottom',
}: {
  mode: ContentMode
  onChange: (mode: ContentMode) => void
  disabled?: boolean
  placement?: 'top' | 'bottom'
}) {
  const current = CONTENT_MODES.find((m) => m.mode === mode) ?? CONTENT_MODES[0]
  return (
    <Dropdown
      placement={placement}
      trigger={
        <button
          type="button"
          disabled={disabled}
          className="flex h-9 items-center gap-1.5 rounded-btn border border-border bg-bg-tertiary/70 px-3 text-sm text-fg-secondary transition-colors hover:text-fg-primary disabled:opacity-50"
        >
          {mode === 'image' ? <ImageIcon className="h-4 w-4" /> : <MonitorPlay className="h-4 w-4" />}
          {current.label}生成
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
      }
    >
      {CONTENT_MODES.map((m) => (
        <DropdownItem key={m.mode} active={mode === m.mode} onClick={() => onChange(m.mode)}>
          {m.mode === 'image' ? <ImageIcon className="h-3.5 w-3.5" /> : <MonitorPlay className="h-3.5 w-3.5" />}
          {m.label}生成
        </DropdownItem>
      ))}
    </Dropdown>
  )
}

function DurationPicker({
  duration,
  onChange,
  disabled,
}: {
  duration: number
  onChange: (duration: number) => void
  disabled?: boolean
}) {
  // 本地文本态，允许自由输入；失焦/回车时校验并提交。
  const [text, setText] = useState(String(duration))
  useEffect(() => {
    setText(String(duration))
  }, [duration])

  function commit() {
    const n = Number(text)
    if (Number.isFinite(n) && n > 0) onChange(n)
    else setText(String(duration))
  }

  return (
    <div className="flex h-9 items-center gap-1.5 rounded-btn border border-border bg-bg-tertiary/70 px-3 text-sm text-fg-secondary">
      <Clock className="h-4 w-4" />
      <input
        type="number"
        min={1}
        step={1}
        value={text}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur()
        }}
        className="w-10 bg-transparent text-fg-primary focus-visible:outline-none disabled:opacity-50"
      />
      <span className="text-fg-muted">秒</span>
    </div>
  )
}

function FrameModePicker({
  frameMode,
  onChange,
  disabled,
}: {
  frameMode: FrameMode
  onChange: (mode: FrameMode) => void
  disabled?: boolean
}) {
  const current = FRAME_MODES.find((m) => m.mode === frameMode) ?? FRAME_MODES[0]
  return (
    <Dropdown
      placement="top"
      trigger={
        <button
          type="button"
          disabled={disabled}
          className="flex h-9 items-center gap-1.5 rounded-btn border border-border bg-bg-tertiary/70 px-3 text-sm text-fg-secondary transition-colors hover:text-fg-primary disabled:opacity-50"
        >
          <Film className="h-4 w-4" />
          {current.label}
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
      }
    >
      {FRAME_MODES.map((m) => (
        <DropdownItem key={m.mode} active={frameMode === m.mode} onClick={() => onChange(m.mode)}>
          <Film className="h-3.5 w-3.5" />
          <div className="flex flex-col">
            <span>{m.label}</span>
            <span className="text-xs text-fg-muted">{m.hint}</span>
          </div>
        </DropdownItem>
      ))}
    </Dropdown>
  )
}

