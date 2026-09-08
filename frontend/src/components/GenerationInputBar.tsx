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
  Images,
  MonitorPlay,
  Clock,
  Film,
  Music,
  Video,
  Clapperboard,
  Maximize2,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Dropdown, DropdownItem } from '@/components/ui/Dropdown'
import { ReferenceSlot, type ReferenceKind } from '@/components/ReferenceSlot'
import { ModelPicker } from '@/components/ModelPicker'
import { SizePicker } from '@/components/SizePicker'
import { DirectorDeskDialog } from '@/components/DirectorDeskDialog'
import { ImageLightbox, type LightboxItem } from '@/components/ImageLightbox'
import { PromptFullscreenEditor } from '@/components/PromptFullscreenEditor'
import { usePromptMention } from '@/hooks/usePromptMention'
import {
  uploadAsset,
  assetFileUrl,
  submitAssetAudit,
  getAssetAudit,
} from '@/api/assets'
import {
  CONTENT_MODES,
  sizeFromRatioResolution,
  imageResolutionsForModel,
  isSeedreamImageProvider,
  videoResolutionsForModel,
  videoDurationRangeForModel,
  type ContentMode,
  type AspectRatio,
  type Resolution,
} from '@/lib/generation'
import {
  ACCEPT_VIDEO_MODE,
  FRAME_MODES,
  KIND_CAPS,
  KIND_LABELS,
  KIND_SIZE_CAPS,
  MAX_AUDIO_TOTAL_DURATION,
  VIDEO_EXTS,
  AUDIO_EXTS,
  frameModeSpec,
  isSeedanceProvider,
  isSparkHubSeedance,
  normalizeFrameMode,
  type FrameMode,
  type ReferenceAsset,
} from '@/lib/promptMention'
import { toast, useUIStore } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { cn } from '@/lib/utils'

/**
 * 向后兼容 re-export：这些符号已迁至 lib/promptMention.ts，
 * 但 CreatePage / CanvasGenerationNode / useAssetAudit 等模块仍从本组件导入。
 */
export {
  effectiveFrameMode,
  frameModeSpec,
  isSeedanceProvider,
  isSparkHubSeedance,
  MAX_AUDIO_TOTAL_DURATION,
  normalizeFrameMode,
  type EffectiveFrameMode,
  type FrameMode,
  type ReferenceAsset,
} from '@/lib/promptMention'

export interface GenerationInputBarProps {
  /** 内容模式：图片 / 视频（需求1：合并文生图/图生图、文生视频/图生视频）。 */
  mode: ContentMode
  onModeChange: (mode: ContentMode) => void
  prompt: string
  onPromptChange: (v: string) => void
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
  /** 3D 导演台 iframe 地址（空则不显示导演台入口）。 */
  directorDeskUrl?: string
  /** 画布节点内使用的紧凑布局。 */
  variant?: 'default' | 'compact'
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
  directorDeskUrl,
  variant = 'default',
}: GenerationInputBarProps) {
  const compact = variant === 'compact'
  const fileInputRef = useRef<HTMLInputElement>(null)
  // 导演台弹窗开关 & 当前主题（传给 iframe）
  const [directorOpen, setDirectorOpen] = useState(false)
  // 素材预览灯箱：点击参考素材缩略图时打开
  const [previewItem, setPreviewItem] = useState<LightboxItem | null>(null)
  // 全屏沉浸式提示词编辑器开关
  const [fullscreenOpen, setFullscreenOpen] = useState(false)
  const theme = useUIStore((s) => s.theme)
  // 镜像 refAssets，供异步审核轮询读取最新列表，避免闭包捕获过期状态。
  const refAssetsRef = useRef(refAssets)
  useEffect(() => {
    refAssetsRef.current = refAssets
  }, [refAssets])

  // 帧模式 / Seedance 判定（@ 引用与上传流程共用）
  const frameMode = normalizeFrameMode(params.frame_mode)
  const isSeedance = isSeedanceProvider(providerSlug)

  // @ 引用：在提示词中键入 @ 触发悬浮选择器，引用已上传参考素材作为生成提示词。
  // 内联输入条与全屏沉浸式编辑器共用同一份状态逻辑，保证交互一致。
  const {
    textareaRef,
    mentionRef,
    mention,
    mentionItems,
    hasLibraryAssets,
    handlePromptInputChange,
    handlePromptKeyDown,
    insertMention,
  } = usePromptMention({
    prompt,
    onPromptChange,
    refAssets,
    onRefAssetsChange,
    mode,
    providerSlug,
    params,
  })

  const aspectRatio = (params.aspect_ratio as AspectRatio) ?? '1:1'
  const resolution = (params.resolution as Resolution) ?? '2K'
  const duration = (params.duration as number) ?? 5
  const count = (params.count as number) ?? 1

  // 切回图片模式时移除视频/音频参考（图片模式不支持多模态参考）。
  useEffect(() => {
    if (mode === 'image' && refAssets.some((a) => (a.kind ?? 'image') !== 'image')) {
      onRefAssetsChange(refAssets.filter((a) => (a.kind ?? 'image') === 'image'))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  // Seedance 帧模式：合并模式（auto）允许图片/视频/音频任意组合参考，无需因缺少参考图而清空；
  // 首帧/首尾帧仅保留图片参考，视频/音频不适用。
  useEffect(() => {
    if (mode !== 'video' || !isSeedance) return
    if (frameMode === 'auto') return
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

  // 视频模式：模型切换后，若当前分辨率不被新模型支持，自动回落到 720p（所有视频模型通用）。
  useEffect(() => {
    if (mode !== 'video') return
    const supported = videoResolutionsForModel(modelId).map((r) => r.value)
    if (!supported.includes(resolution as Resolution)) {
      updateRatioResolution(aspectRatio, '720p')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId, mode])

  // 视频模式：模型切换后，若当前时长超出新模型范围，自动夹紧到范围内。
  useEffect(() => {
    if (mode !== 'video') return
    const range = videoDurationRangeForModel(modelId)
    if (duration < range.min || duration > range.max) {
      updateDuration(range.default)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId, mode])

  // Seedream 图片模式：模型切换后，若当前分辨率不被新模型支持，自动回落到该模型支持的档位。
  useEffect(() => {
    if (mode !== 'image' || !isSeedreamImageProvider(providerSlug)) return
    const supported = imageResolutionsForModel(modelId).map((r) => r.value)
    if (!supported.includes(resolution as Resolution)) {
      updateRatioResolution(aspectRatio, supported[0])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId, mode, providerSlug])

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

  /** 提交 Spark Hub Seedance 参考素材审核，并异步轮询进度。
   *  审核初始状态（pending）已在上传时预设到素材对象中，这里直接发起提审。 */
  async function startAudit(assetId: string) {
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
        // 音频参考无需审核；图片/视频在 Spark Hub Seedance 下需审核，上传时立即标记为审核中。
        const needsAudit = isSparkHubSeedance(providerSlug) && kind !== 'audio'
        const ref: ReferenceAsset = {
          assetId: asset.id,
          previewUrl: assetFileUrl(asset.id),
          kind,
          auditStatus: needsAudit ? 'pending' : undefined,
          duration: (kind === 'audio' || kind === 'video') && asset.duration != null
            ? asset.duration
            : undefined,
        }
        next.push(ref)
        added.push(ref)
      } catch (e) {
        toast(toApiError(e).message, 'error')
      }
    }
    if (added.length) {
      onRefAssetsChange(next)
      // 仅对需要审核的图片/视频素材提审；审核状态已在上面预设为 pending，提交后立即展示。
      added.filter((r) => r.auditStatus === 'pending').forEach((r) => startAudit(r.assetId))
      toast(`已上传 ${added.length} 个参考素材`, 'success')
    }
  }

  /** 导演台采集回调：上传截图并作为参考图添加。 */
  async function handleDirectorImage(file: File) {
    try {
      const asset = await uploadAsset(file)
      const needsAudit = isSparkHubSeedance(providerSlug)
      const ref: ReferenceAsset = {
        assetId: asset.id,
        previewUrl: assetFileUrl(asset.id),
        kind: 'image',
        auditStatus: needsAudit ? 'pending' : undefined,
      }
      onRefAssetsChange([...refAssets, ref])
      if (needsAudit) startAudit(ref.assetId)
    } catch (e) {
      toast(toApiError(e).message, 'error')
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

  function updateCount(next: number) {
    onParamsChange({ ...params, count: next })
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
    <div className={cn('bg-transparent', compact ? 'p-0' : 'p-4')}>
      <div className={cn(!compact && 'mx-auto max-w-5xl')}>
        <div
          className={cn(
            'relative border border-border/60 bg-bg-secondary/70 backdrop-blur-md transition-all duration-200 focus-within:border-border',
            compact ? 'rounded-card p-3 shadow-none' : 'rounded-2xl p-5 shadow-elevated',
          )}
          onPaste={onPaste}
          onDrop={onDrop}
          onDragOver={(e) => e.preventDefault()}
        >
          {/* 已上传的参考素材列表（图片/视频/音频）；首帧/首尾帧模式下图片在下方固定格子中展示 */}
          {refAssets.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-2">
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
                    onPreview={() =>
                      setPreviewItem({
                        url: ref.previewUrl,
                        type: (ref.kind ?? 'image') === 'image' ? 'image' : (ref.kind ?? 'image') === 'video' ? 'video' : 'audio',
                        title: KIND_LABELS[ref.kind ?? 'image'],
                      })
                    }
                  />
                ),
              )}
            </div>
          )}

          {/* 输入区：参考素材槽（含导演台）+ 提示词 */}
          <div className={cn('flex', compact ? 'flex-col gap-2' : 'gap-4')}>
            <div className="flex gap-2">
              {frameSlots ? (
                // 首帧/首尾帧：渲染指定数量的角色格子；全部填满后不再显示上传按钮，
                // 需先移除已有图片才能重新上传。
                frameSlots.map((label, i) => (
                  <ReferenceSlot
                    key={label}
                    label={label}
                    previewUrl={frameImages[i]?.previewUrl ?? null}
                    auditStatus={frameImages[i]?.auditStatus}
                    auditError={frameImages[i]?.auditError}
                    onPick={() => fileInputRef.current?.click()}
                    onClear={() => removeFrameImage(i)}
                    onPreview={
                      frameImages[i]
                        ? () =>
                            setPreviewItem({
                              url: frameImages[i]!.previewUrl,
                              type: 'image',
                              title: `${label} · 参考图`,
                            })
                        : undefined
                    }
                  />
                ))
              ) : (
                <ReferenceSlot
                  previewUrl={null}
                  onPick={() => fileInputRef.current?.click()}
                  onClear={() => {}}
                />
              )}
              {/* 导演台：本质是一种参考素材来源，与参考槽位并排展示 */}
              {mode === 'video' && directorDeskUrl && (
                <div className="flex w-16 shrink-0 flex-col items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setDirectorOpen(true)}
                    disabled={submitting}
                    title="打开 3D 导演台，采集运镜参考"
                    aria-label="导演台"
                    className="flex h-16 w-16 shrink-0 flex-col items-center justify-center gap-1 rounded-btn border border-dashed border-border text-fg-muted transition-colors hover:border-fg-muted hover:text-fg-secondary disabled:opacity-50"
                  >
                    <Clapperboard className="h-5 w-5" />
                  </button>
                  <span className="text-xs text-fg-muted">导演台</span>
                </div>
              )}
            </div>
            <div className="relative flex flex-1 flex-col gap-2">
              {/* @ 引用悬浮选择器：在提示词中键入 @ 时弹出，可选择已上传参考素材或素材库已有素材 */}
              {mention.open && (
                <div
                  ref={mentionRef}
                  className="absolute bottom-full left-0 z-50 mb-2 w-80 animate-slide-up rounded-card border border-border bg-bg-secondary p-1.5 shadow-elevated"
                >
                  {refAssets.length === 0 && !hasLibraryAssets ? (
                    <div className="px-3 py-2 text-sm text-fg-muted">
                      暂无可引用的素材，请先上传或在素材库中新建资产
                    </div>
                  ) : mentionItems.length === 0 ? (
                    <div className="px-3 py-2 text-sm text-fg-muted">无匹配的素材</div>
                  ) : (
                    <>
                      <div className="px-2 pb-1 pt-1 text-[11px] font-medium text-fg-muted">
                        选择要引用的素材
                      </div>
                      <div className="flex max-h-60 flex-col gap-0.5 overflow-auto scrollbar-thin">
                        {mentionItems.map((item, i) => (
                          <button
                            key={item.source + item.asset.assetId}
                            type="button"
                            onClick={() => insertMention(item)}
                            className={cn(
                              'flex items-center gap-2 rounded-btn px-2 py-1.5 text-sm transition-colors',
                              i === mention.activeIndex
                                ? 'bg-accent text-bg-primary'
                                : 'text-fg-secondary hover:bg-bg-tertiary hover:text-fg-primary',
                            )}
                          >
                            <span className="relative h-6 w-6 shrink-0 overflow-hidden rounded border border-border">
                              {item.kind === 'image' ? (
                                <img
                                  src={item.thumbUrl}
                                  alt=""
                                  className="h-full w-full object-cover"
                                />
                              ) : item.kind === 'video' ? (
                                <span className="flex h-full w-full items-center justify-center bg-bg-tertiary">
                                  <Video className="h-3.5 w-3.5" />
                                </span>
                              ) : item.thumbUrl ? (
                                <>
                                  <img
                                    src={item.thumbUrl}
                                    alt=""
                                    className="h-full w-full object-cover"
                                  />
                                  <span className="absolute bottom-0 right-0 flex h-3 w-3 items-center justify-center rounded-tl bg-accent text-bg-primary">
                                    <Music className="h-2 w-2" />
                                  </span>
                                </>
                              ) : (
                                <span className="flex h-full w-full items-center justify-center bg-bg-tertiary">
                                  <Music className="h-3.5 w-3.5" />
                                </span>
                              )}
                            </span>
                            <span className="truncate">{item.label}</span>
                            {item.source === 'library' && (
                              <span className="shrink-0 rounded bg-bg-tertiary px-1 py-0.5 text-[10px] text-fg-muted">
                                素材库
                              </span>
                            )}
                            <span className="ml-auto shrink-0 text-xs text-fg-muted">
                              {item.tokens.join(' ')}
                            </span>
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}
              <textarea
                ref={textareaRef}
                value={prompt}
                onChange={handlePromptInputChange}
                onKeyDown={(e) =>
                  handlePromptKeyDown(e, onGenerate, submitting, atConcurrencyLimit)
                }
                disabled={submitting}
                placeholder={
                  mode === 'video'
                    ? isSeedance
                      ? `${refHint()}。支持上传图片、视频、音频作为参考素材（参考视频/音频单个时长 2-15 秒，各最多 3 个）。输入文字或 @ 引用素材，描述你想生成的视频。`
                      : '上传参考图/视频/音频、输入文字或 @ 引用素材，描述你想生成的视频。支持最多 9 张参考图、3 个参考视频、3 段参考音频。'
                    : '上传参考图、输入文字或 @ 引用素材，描述你想生成的图片。支持上传多张参考图融合生成。'
                }
                rows={compact ? 3 : 4}
                className={cn(
                  'w-full resize-none bg-transparent leading-relaxed text-fg-primary placeholder:text-fg-muted',
                  'transition-[height] duration-200 focus-visible:outline-none',
                  compact ? 'min-h-20 text-sm' : 'min-h-[120px] text-base',
                )}
              />
              {/* 全屏沉浸式编辑入口：点击后进入全屏大字号编辑提示词 */}
              <button
                type="button"
                onClick={() => setFullscreenOpen(true)}
                title="全屏编辑"
                aria-label="全屏编辑提示词"
                className="absolute bottom-2 right-2 z-10 flex h-7 w-7 items-center justify-center rounded-btn text-fg-muted transition-colors hover:bg-bg-tertiary hover:text-fg-primary"
              >
                <Maximize2 className="h-4 w-4" />
              </button>
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
          <div className={cn('mt-4 flex flex-wrap items-center gap-2', !compact && 'pr-36')}>
            {!compact && <ModeDropdown mode={mode} onChange={onModeChange} disabled={submitting} placement="top" />}
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
              modelId={modelId}
              providerSlug={providerSlug}
              aspectRatio={aspectRatio}
              resolution={resolution}
              onChange={updateRatioResolution}
              disabled={submitting}
              placement="top"
            />
            {mode === 'image' && !compact && (
              <CountPicker count={count} onChange={updateCount} disabled={submitting} />
            )}
            {mode === 'video' && (
              <DurationPicker duration={duration} onChange={updateDuration} modelId={modelId} disabled={submitting} />
            )}
            {mode === 'video' && isSeedance && (
              <FrameModePicker frameMode={frameMode} onChange={updateFrameMode} disabled={submitting} />
            )}

            <Button
              size="md"
              onClick={onGenerate}
              disabled={submitting || atConcurrencyLimit}
              className={cn(
                'transition-transform duration-200 hover:scale-[1.02] active:scale-[0.98]',
                compact ? 'ml-auto' : 'absolute bottom-5 right-5',
              )}
            >
              <Wand2 className="h-4 w-4" />
              {submitting ? '提交中…' : atConcurrencyLimit ? '并发已满' : '生成'}
            </Button>
          </div>
        </div>
      </div>
      <DirectorDeskDialog
        open={directorOpen}
        onClose={() => setDirectorOpen(false)}
        url={directorDeskUrl ?? ''}
        theme={theme}
        onCaptureImage={handleDirectorImage}
      />
      <ImageLightbox
        item={previewItem}
        open={previewItem != null}
        onClose={() => setPreviewItem(null)}
      />
      <PromptFullscreenEditor
        open={fullscreenOpen}
        onClose={() => setFullscreenOpen(false)}
        prompt={prompt}
        onPromptChange={onPromptChange}
        refAssets={refAssets}
        onRefAssetsChange={onRefAssetsChange}
        mode={mode}
        providerSlug={providerSlug}
        params={params}
        onGenerate={onGenerate}
        submitting={submitting}
        atConcurrencyLimit={atConcurrencyLimit}
      />
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
          className="flex h-9 items-center gap-1.5 rounded-btn border border-border bg-bg-tertiary/70 px-3 text-sm font-medium text-fg-secondary transition-all hover:text-fg-primary disabled:opacity-50"
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
  modelId,
  disabled,
}: {
  duration: number
  onChange: (duration: number) => void
  modelId: string
  disabled?: boolean
}) {
  const range = videoDurationRangeForModel(modelId)
  // 本地文本态，允许自由输入；失焦/回车时按模型范围校验并提交。
  const [text, setText] = useState(String(duration))
  useEffect(() => {
    setText(String(duration))
  }, [duration])

  function commit() {
    const n = Number(text)
    if (Number.isFinite(n) && n >= range.min && n <= range.max) {
      onChange(n)
    } else {
      // 超出范围时回退到当前值（模型切换的 clamp effect 会修正）
      setText(String(duration))
    }
  }

  return (
    <div className="flex h-9 items-center gap-1.5 rounded-btn border border-border bg-bg-tertiary/70 px-3 text-sm font-medium text-fg-secondary">
      <Clock className="h-4 w-4" />
      <input
        type="number"
        min={range.min}
        max={range.max}
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
      <span className="text-xs text-fg-muted">{range.min}~{range.max}s</span>
    </div>
  )
}

function CountPicker({
  count,
  onChange,
  disabled,
}: {
  count: number
  onChange: (count: number) => void
  disabled?: boolean
}) {
  const MIN = 1
  const MAX = 4
  return (
    <div className="flex h-9 items-center gap-1.5 rounded-btn border border-border bg-bg-tertiary/70 px-3 text-sm font-medium text-fg-secondary">
      <Images className="h-4 w-4" />
      <button
        type="button"
        disabled={disabled || count <= MIN}
        onClick={() => onChange(Math.max(MIN, count - 1))}
        className="flex h-5 w-5 items-center justify-center rounded-btn text-fg-secondary transition-colors hover:bg-bg-tertiary disabled:opacity-40"
        aria-label="减少数量"
      >
        −
      </button>
      <span className="w-4 text-center tabular-nums text-fg-primary">{count}</span>
      <button
        type="button"
        disabled={disabled || count >= MAX}
        onClick={() => onChange(Math.min(MAX, count + 1))}
        className="flex h-5 w-5 items-center justify-center rounded-btn text-fg-secondary transition-colors hover:bg-bg-tertiary disabled:opacity-40"
        aria-label="增加数量"
      >
        +
      </button>
      <span className="text-fg-muted">张</span>
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
          className="flex h-9 items-center gap-1.5 rounded-btn border border-border bg-bg-tertiary/70 px-3 text-sm font-medium text-fg-secondary transition-all hover:text-fg-primary disabled:opacity-50"
        >
          <Film className="h-4 w-4" />
          {current.label}
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
      }
    >
      {FRAME_MODES.map((m) => {
        const Icon = m.icon
        return (
          <DropdownItem key={m.mode} active={frameMode === m.mode} onClick={() => onChange(m.mode)}>
            <Icon className="h-3.5 w-3.5 shrink-0" />
            <div className="flex flex-col">
              <span>{m.label}</span>
              <span className="text-xs leading-relaxed text-fg-muted">{m.hint}</span>
            </div>
          </DropdownItem>
        )
      })}
    </Dropdown>
  )
}

