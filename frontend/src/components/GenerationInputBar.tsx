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
  Type,
  Clock,
  Film,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Dropdown, DropdownItem } from '@/components/ui/Dropdown'
import { ReferenceSlot, type ReferenceKind } from '@/components/ReferenceSlot'
import { ModelPicker } from '@/components/ModelPicker'
import { SizePicker } from '@/components/SizePicker'
import { uploadAsset, assetFileUrl } from '@/api/assets'
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

/** Seedance 图生视频模式：首帧 / 首尾帧 / 多模态参考。 */
type FrameMode = 'first' | 'first_last' | 'reference'

const FRAME_MODES: { mode: FrameMode; label: string; hint: string }[] = [
  { mode: 'first', label: '首帧', hint: '上传 1 张图片作为视频首帧' },
  { mode: 'first_last', label: '首尾帧', hint: '上传 2 张图片，分别作为首帧与尾帧' },
  { mode: 'reference', label: '参考图', hint: '上传 1~9 张图片作为多模态参考' },
]

/** 判断当前 provider 是否为 Seedance 系列（slug 含 seedance）。 */
function isSeedanceProvider(slug: string): boolean {
  return slug.toLowerCase().includes('seedance')
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
  negativePrompt,
  onPromptChange,
  onNegativeChange,
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
  const [negativeOpen, setNegativeOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const aspectRatio = (params.aspect_ratio as AspectRatio) ?? '1:1'
  const resolution = (params.resolution as Resolution) ?? '2K'
  const duration = (params.duration as number) ?? 5
  const frameMode = (params.frame_mode as FrameMode) ?? 'first'
  const isSeedance = isSeedanceProvider(providerSlug)

  // 切回图片模式时移除视频/音频参考（图片模式不支持多模态参考）。
  useEffect(() => {
    if (mode === 'image' && refAssets.some((a) => (a.kind ?? 'image') !== 'image')) {
      onRefAssetsChange(refAssets.filter((a) => (a.kind ?? 'image') === 'image'))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  // Seedance 首尾帧/参考图模式下仅保留图片参考，视频/音频不适用。
  useEffect(() => {
    if (mode === 'video' && isSeedance && frameMode !== 'reference') {
      const cleaned = refAssets.filter((a) => (a.kind ?? 'image') === 'image')
      if (cleaned.length !== refAssets.length) {
        onRefAssetsChange(cleaned)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, frameMode, isSeedance])

  // 首尾帧模式限制最多 2 张图片。
  useEffect(() => {
    if (mode === 'video' && isSeedance && frameMode === 'first_last') {
      const images = refAssets.filter((a) => (a.kind ?? 'image') === 'image')
      if (images.length > 2) {
        onRefAssetsChange(images.slice(0, 2))
        toast('首尾帧模式最多保留 2 张参考图（首帧 + 尾帧）', 'info')
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, frameMode, isSeedance, refAssets])

  /** 识别文件类型；不支持的类型返回 null。 */
  function kindOfFile(file: File): ReferenceKind | null {
    const ext = '.' + (file.name.split('.').pop() ?? '').toLowerCase()
    if (file.type.startsWith('image/')) return 'image'
    if (file.type.startsWith('video/') || VIDEO_EXTS.includes(ext)) return 'video'
    if (file.type.startsWith('audio/') || AUDIO_EXTS.includes(ext)) return 'audio'
    return null
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
      // Seedance 首尾帧/首帧模式仅接受图片参考
      if (mode === 'video' && isSeedance && frameMode !== 'reference' && kind !== 'image') {
        toast(
          frameMode === 'first_last'
            ? '首尾帧模式仅支持上传图片参考（首帧 + 尾帧）'
            : '首帧模式仅支持上传图片参考',
          'error',
        )
        continue
      }
      // 首尾帧模式最多 2 张图片
      if (mode === 'video' && isSeedance && frameMode === 'first_last' && kind === 'image') {
        const imageCount = next.filter((a) => (a.kind ?? 'image') === 'image').length
        if (imageCount >= 2) {
          toast('首尾帧模式最多上传 2 张参考图（首帧 + 尾帧）', 'error')
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
        next.push({ assetId: asset.id, previewUrl: assetFileUrl(asset.id), kind })
        added.push({ assetId: asset.id, previewUrl: assetFileUrl(asset.id), kind })
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

  return (
    <div className="bg-transparent p-4">
      <div className="mx-auto max-w-4xl">
        <div
          className="relative rounded-2xl border border-border/60 bg-bg-secondary/70 p-4 shadow-xl backdrop-blur-md"
          onPaste={onPaste}
          onDrop={onDrop}
          onDragOver={(e) => e.preventDefault()}
        >
          {/* 已上传的参考素材列表（图片/视频/音频） */}
          {refAssets.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {refAssets.map((ref, i) => (
                <ReferenceSlot
                  key={ref.assetId}
                  previewUrl={ref.previewUrl}
                  kind={ref.kind ?? 'image'}
                  onPick={() => {}}
                  onClear={() => removeRef(i)}
                />
              ))}
            </div>
          )}

          {/* 输入区：参考图槽 + 提示词 */}
          <div className="flex gap-3">
            <ReferenceSlot
              previewUrl={null}
              onPick={() => fileInputRef.current?.click()}
              onClear={() => {}}
            />
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
              {negativeOpen && (
                <input
                  type="text"
                  value={negativePrompt}
                  onChange={(e) => onNegativeChange(e.target.value)}
                  disabled={submitting}
                  placeholder="不希望出现的内容，如：模糊、低质量、变形…"
                  className="w-full rounded-btn border border-border bg-bg-tertiary px-3 py-2 text-sm text-fg-primary placeholder:text-fg-muted focus-visible:outline-none focus-visible:border-fg-muted"
                />
              )}
            </div>
          </div>

          {/* 底部工具栏 */}
          <div className="mt-3 flex flex-wrap items-center gap-2">
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

            <button
              type="button"
              onClick={() => setNegativeOpen((v) => !v)}
              className={cn(
                'flex h-9 items-center gap-1 rounded-btn border border-border px-3 text-sm transition-colors',
                negativeOpen
                  ? 'border-fg-muted text-fg-primary'
                  : 'text-fg-secondary hover:text-fg-primary',
              )}
            >
              <Type className="h-4 w-4" />
              负面词
            </button>

            <div className="flex-1" />

            <Button size="md" onClick={onGenerate} disabled={submitting || atConcurrencyLimit}>
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
        className="w-12 bg-transparent text-fg-primary focus-visible:outline-none disabled:opacity-50"
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

