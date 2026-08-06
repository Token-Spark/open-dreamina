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
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Dropdown, DropdownItem } from '@/components/ui/Dropdown'
import { ReferenceSlot } from '@/components/ReferenceSlot'
import { ModelPicker } from '@/components/ModelPicker'
import { SizePicker } from '@/components/SizePicker'
import { uploadAsset, assetFileUrl } from '@/api/assets'
import {
  CONTENT_MODES,
  GENERATION_COUNTS,
  sizeFromRatioResolution,
  type ContentMode,
  type AspectRatio,
  type Resolution,
} from '@/lib/generation'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { cn } from '@/lib/utils'

/** 一张参考图：assetId 用于提交任务，previewUrl 用于本地预览。 */
export interface ReferenceAsset {
  assetId: string
  previewUrl: string
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
  const count = (params.n as number) ?? 1
  const duration = (params.duration as number) ?? 5

  // 串行上传多张图片，逐张追加到参考图列表（避免并发状态竞争）。
  async function handleUploadFiles(files: FileList | File[]) {
    const images = Array.from(files).filter((f) => f.type.startsWith('image/'))
    if (images.length === 0) return
    const added: ReferenceAsset[] = []
    for (const file of images) {
      try {
        const asset = await uploadAsset(file)
        added.push({ assetId: asset.id, previewUrl: assetFileUrl(asset.id) })
      } catch (e) {
        toast(toApiError(e).message, 'error')
      }
    }
    if (added.length) {
      onRefAssetsChange([...refAssets, ...added])
      toast(`已上传 ${added.length} 张参考图`, 'success')
    }
  }

  function removeRef(index: number) {
    onRefAssetsChange(refAssets.filter((_, i) => i !== index))
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    const files = Array.from(e.dataTransfer.files ?? [])
    if (files.some((f) => f.type.startsWith('image/'))) handleUploadFiles(files)
  }

  function onPaste(e: React.ClipboardEvent) {
    const items = e.clipboardData.items
    const files: File[] = []
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
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

  function updateCount(next: number) {
    onParamsChange({ ...params, n: next })
  }

  function updateDuration(next: number) {
    onParamsChange({ ...params, duration: next })
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
          {/* 已上传的参考图列表（多图） */}
          {refAssets.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {refAssets.map((ref, i) => (
                <ReferenceSlot
                  key={ref.assetId}
                  previewUrl={ref.previewUrl}
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
                placeholder="上传参考图、输入文字或 @主体，描述你想生成的图片。支持上传多张参考图融合生成。"
                rows={3}
                className={cn(
                  'w-full resize-none bg-transparent text-base text-fg-primary placeholder:text-fg-muted',
                  'focus-visible:outline-none',
                )}
              />
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
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
            <CountSelector count={count} onChange={updateCount} disabled={submitting} />

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

function CountSelector({
  count,
  onChange,
  disabled,
}: {
  count: number
  onChange: (count: number) => void
  disabled?: boolean
}) {
  return (
    <div className="flex h-9 items-center rounded-btn border border-border bg-bg-tertiary/70 p-0.5">
      {GENERATION_COUNTS.map((n) => (
        <button
          key={n}
          type="button"
          disabled={disabled}
          onClick={() => onChange(n)}
          className={cn(
            'flex h-7 w-7 items-center justify-center rounded-[4px] text-sm transition-colors',
            count === n ? 'bg-accent text-bg-primary' : 'text-fg-secondary hover:text-fg-primary',
          )}
        >
          {n}
        </button>
      ))}
    </div>
  )
}
