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

import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Upload, X } from 'lucide-react'
import { uploadAsset, assetThumbnailUrl, type Asset } from '@/api/assets'
import {
  CATEGORY_OPTIONS,
  type CreationAsset,
  type CreationAssetCategory,
} from '@/api/creationAssets'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'

export interface CreationAssetFormValues {
  name: string
  category: CreationAssetCategory
  description: string
  tags: string[]
  image_asset_id: string | null
  audio_asset_id: string | null
}

export interface CreationAssetFormDialogProps {
  open: boolean
  /** 传入则为编辑模式，null 为新建模式。 */
  asset: CreationAsset | null
  existingTags: string[]
  onSubmit: (values: CreationAssetFormValues) => Promise<void>
  onClose: () => void
}

/** 新建/编辑创作资产弹窗：图片与音频先上传为 Asset 再关联。 */
export function CreationAssetFormDialog({
  open,
  asset,
  existingTags,
  onSubmit,
  onClose,
}: CreationAssetFormDialogProps) {
  const [name, setName] = useState('')
  const [category, setCategory] = useState<CreationAssetCategory>('character')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [tagSuggestIdx, setTagSuggestIdx] = useState(-1)
  const [showTagSuggest, setShowTagSuggest] = useState(false)
  const [image, setImage] = useState<Asset | null>(null)
  const [audio, setAudio] = useState<Asset | null>(null)
  const [uploading, setUploading] = useState<'image' | 'audio' | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const audioInputRef = useRef<HTMLInputElement>(null)

  const isEdit = asset != null
  const hasAudio = CATEGORY_OPTIONS.find((c) => c.value === category)?.hasAudio ?? false

  useEffect(() => {
    if (!open) return
    setName(asset?.name ?? '')
    setCategory(asset?.category ?? 'character')
    setDescription(asset?.description ?? '')
    setTags(asset?.tags ?? [])
    setTagInput('')
    setTagSuggestIdx(-1)
    setShowTagSuggest(false)
    setImage(null)
    setAudio(null)
  }, [open, asset])

  function addTag(raw: string) {
    const t = raw.trim()
    if (t && !tags.includes(t)) {
      setTags((prev) => [...prev, t])
    }
    setTagInput('')
    setTagSuggestIdx(-1)
    setShowTagSuggest(false)
  }

  /** 根据当前输入从已有标签中过滤匹配项作为备选。 */
  const tagSuggestions = useMemo(() => {
    const q = tagInput.trim().toLowerCase()
    return existingTags
      .filter((t) => !tags.includes(t))
      .filter((t) => (q ? t.toLowerCase().includes(q) : true))
      .slice(0, 8)
  }, [existingTags, tags, tagInput])

  async function handleUpload(kind: 'image' | 'audio', file: File) {
    setUploading(kind)
    try {
      const uploaded = await uploadAsset(file)
      if (kind === 'image') setImage(uploaded)
      else setAudio(uploaded)
    } catch (e) {
      toast(toApiError(e).message, 'error')
    } finally {
      setUploading(null)
    }
  }

  async function handleSubmit() {
    if (!name.trim()) {
      toast('请填写资产名称', 'error')
      return
    }
    setSubmitting(true)
    try {
      await onSubmit({
        name: name.trim(),
        category,
        description,
        tags,
        // 编辑模式下未重新上传则保留原关联
        image_asset_id: image?.id ?? asset?.image_asset_id ?? null,
        audio_asset_id: audio?.id ?? asset?.audio_asset_id ?? null,
      })
      onClose()
    } catch (e) {
      toast(toApiError(e).message, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title={isEdit ? '编辑资产' : '新建资产'}
      description="人物可包含图片、音色音频与细节设定；场景为图片与设定；道具为图片。"
      className="max-w-xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={submitting || uploading != null}>
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {isEdit ? '保存' : '创建'}
          </Button>
        </>
      }
    >
      <div className="space-y-4 py-2">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>名称 *</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如：女主角-林小雨"
              maxLength={100}
            />
          </div>
          <div className="space-y-1.5">
            <Label>类别</Label>
            <Select
              value={category}
              onChange={(e) => setCategory(e.target.value as CreationAssetCategory)}
            >
              {CATEGORY_OPTIONS.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </Select>
          </div>
        </div>

        {/* 图片上传：显示原有关联或新上传预览 */}
        <div className="space-y-1.5">
          <Label>图片</Label>
          <div className="flex items-center gap-3">
            <div className="flex h-16 w-24 shrink-0 items-center justify-center overflow-hidden rounded-btn border border-border bg-bg-tertiary">
              {image ? (
                <img src={assetThumbnailUrl(image.id)} alt="预览" className="h-full w-full object-cover" />
              ) : asset?.image_thumbnail_url ? (
                <img src={asset.image_thumbnail_url} alt="原图" className="h-full w-full object-cover" />
              ) : (
                <span className="text-xs text-fg-muted">未上传</span>
              )}
            </div>
            <input
              ref={imageInputRef}
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) handleUpload('image', f)
                e.target.value = ''
              }}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => imageInputRef.current?.click()}
              disabled={uploading != null}
            >
              {uploading === 'image' ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              {image || asset?.image_asset_id ? '更换图片' : '上传图片'}
            </Button>
          </div>
        </div>

        {/* 音色音频：仅人物类别 */}
        {hasAudio && (
          <div className="space-y-1.5">
            <Label>音色音频</Label>
            <div className="flex items-center gap-3">
              {audio ? (
                <audio controls preload="none" src={`/api/v1/assets/${audio.id}/file`} className="h-8 flex-1" />
              ) : asset?.audio_url ? (
                <audio controls preload="none" src={asset.audio_url} className="h-8 flex-1" />
              ) : (
                <span className="flex-1 text-xs text-fg-muted">未上传</span>
              )}
              <input
                ref={audioInputRef}
                type="file"
                accept="audio/*"
                hidden
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) handleUpload('audio', f)
                  e.target.value = ''
                }}
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => audioInputRef.current?.click()}
                disabled={uploading != null}
              >
                {uploading === 'audio' ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4" />
                )}
                上传音频
              </Button>
            </div>
          </div>
        )}

        <div className="space-y-1.5">
          <Label>细节设定</Label>
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="外形、性格、服装、说话风格等参考设定，生成时可复用"
            rows={3}
          />
        </div>

        {/* 标签：输入即添加，支持从已有标签快速选择 */}
        <div className="space-y-1.5">
          <Label>标签（如短剧名称，用于筛选与云同步）</Label>
          <div className="flex flex-wrap items-center gap-1.5">
            {tags.map((t) => (
              <span
                key={t}
                className="inline-flex items-center gap-1 rounded-full border border-border bg-bg-tertiary px-2 py-0.5 text-xs text-fg-secondary"
              >
                {t}
                <button
                  type="button"
                  onClick={() => setTags((prev) => prev.filter((x) => x !== t))}
                  aria-label={`移除标签 ${t}`}
                  className="text-fg-muted hover:text-error"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            <div className="relative">
              <Input
                value={tagInput}
                onChange={(e) => {
                  setTagInput(e.target.value)
                  setTagSuggestIdx(-1)
                  setShowTagSuggest(true)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ',') {
                    e.preventDefault()
                    if (showTagSuggest && tagSuggestIdx >= 0 && tagSuggestions[tagSuggestIdx]) {
                      addTag(tagSuggestions[tagSuggestIdx])
                    } else {
                      addTag(tagInput)
                    }
                  } else if (e.key === 'ArrowDown' && tagSuggestions.length > 0) {
                    e.preventDefault()
                    setShowTagSuggest(true)
                    setTagSuggestIdx((prev) => (prev + 1) % tagSuggestions.length)
                  } else if (e.key === 'ArrowUp' && tagSuggestions.length > 0) {
                    e.preventDefault()
                    setTagSuggestIdx((prev) => (prev <= 0 ? tagSuggestions.length - 1 : prev - 1))
                  } else if (e.key === 'Escape') {
                    setShowTagSuggest(false)
                  }
                }}
                onFocus={() => setShowTagSuggest(true)}
                onBlur={() => {
                  if (tagInput) addTag(tagInput)
                  // 延迟关闭以便点击下拉项时 onClick 先触发
                  setTimeout(() => setShowTagSuggest(false), 150)
                }}
                placeholder="输入后回车添加"
                className="h-7 w-40"
              />
              {showTagSuggest && tagSuggestions.length > 0 && (
                <div className="absolute left-0 top-full z-10 mt-1 max-h-48 w-48 overflow-auto rounded-btn border border-border bg-bg-secondary shadow-lg">
                  {tagSuggestions.map((t, i) => (
                    <button
                      key={t}
                      type="button"
                      onMouseDown={(e) => {
                        e.preventDefault()
                        addTag(t)
                      }}
                      className={`block w-full px-3 py-1.5 text-left text-xs transition-colors ${
                        i === tagSuggestIdx
                          ? 'bg-bg-tertiary text-fg-primary'
                          : 'text-fg-secondary hover:bg-bg-tertiary'
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
          {!showTagSuggest && existingTags.filter((t) => !tags.includes(t)).length > 0 && (
            <div className="flex flex-wrap gap-1 pt-1">
              {existingTags
                .filter((t) => !tags.includes(t))
                .slice(0, 8)
                .map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => addTag(t)}
                    className="rounded-full border border-dashed border-border px-2 py-0.5 text-xs text-fg-muted hover:border-fg-muted hover:text-fg-secondary"
                  >
                    + {t}
                  </button>
                ))}
            </div>
          )}
        </div>
      </div>
    </Dialog>
  )
}
