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
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Dropdown, DropdownItem } from '@/components/ui/Dropdown'
import { ReferenceSlot, type ReferenceKind } from '@/components/ReferenceSlot'
import { ModelPicker } from '@/components/ModelPicker'
import { SizePicker } from '@/components/SizePicker'
import { DirectorDeskDialog } from '@/components/DirectorDeskDialog'
import {
  uploadAsset,
  assetFileUrl,
  submitAssetAudit,
  getAssetAudit,
} from '@/api/assets'
import { listCreationAssets, type CreationAsset } from '@/api/creationAssets'
import { useQuery } from '@tanstack/react-query'
import { CREATION_ASSETS_KEY } from '@/hooks/useCreationAssets'
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
import { toast, useUIStore } from '@/stores/uiStore'
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
 * @ 引用候选项：可引用已上传的参考素材（slot）或素材库中的可复用素材（library）。
 * - slot：已在上传槽位中的素材，token 按类型编号（图1/视频1/音频1…）。
 * - library：素材库（人物/场景/道具）中尚未加入参考列表的素材，选中后自动追加到 refAssets。
 */
interface MentionItem {
  /** 候选项来源：已上传参考槽位 / 素材库。 */
  source: 'slot' | 'library'
  /** 主资产：slot 为现有参考项；library 为素材库待加入项中的图片资产（无图时取音频）。 */
  asset: ReferenceAsset
  /** 待加入参考列表的资产（slot 恒为单元素；人物素材可能同时含图片与音频）。 */
  assets: ReferenceAsset[]
  kind: ReferenceKind
  /** 实际插入提示词的引用 token 列表，如 @图1，或 @图2、@音频1。 */
  tokens: string[]
  /** 展示名称。slot 为类型编号（参考图 1），library 为素材名称。 */
  label: string
  /** 缩略图地址；slot 用 file 原图，library 用素材缩略图。 */
  thumbUrl: string
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
  icon: React.ComponentType<{ className?: string }>
}[] = [
  {
    mode: 'auto',
    label: '文生视频/参考图',
    hint: '无需图片可直接生成，上传图片自动转为参考图',
    maxImages: MAX_REF_IMAGES,
    required: 0,
    allowMultimodal: true,
    icon: Wand2,
  },
  { mode: 'first', label: '首帧', hint: '上传 1 张图片作为视频首帧', maxImages: 1, required: 1, allowMultimodal: false, slots: ['首帧'], icon: ImageIcon },
  {
    mode: 'first_last',
    label: '首尾帧',
    hint: '上传 2 张图片，分别作为首帧与尾帧',
    maxImages: 2,
    required: 2,
    allowMultimodal: false,
    slots: ['首帧', '尾帧'],
    icon: Images,
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

/**
 * 素材库素材 → 待加入参考列表的资产：
 * 图片模式仅取图片；视频模式取图片 + 音频（人物音色）；单帧/首尾帧模式不允许音频。
 * 顺序固定为图片在前、音频在后，便于后续按加入顺序编号。
 */
function pendingAssetsOf(
  ca: CreationAsset,
  mode: ContentMode,
  allowAudio: boolean,
): ReferenceAsset[] {
  const list: ReferenceAsset[] = []
  if (ca.image_asset_id) {
    list.push({
      assetId: ca.image_asset_id,
      previewUrl: assetFileUrl(ca.image_asset_id),
      kind: 'image',
    })
  }
  if (mode === 'video' && allowAudio && ca.audio_asset_id) {
    list.push({
      assetId: ca.audio_asset_id,
      previewUrl: assetFileUrl(ca.audio_asset_id),
      kind: 'audio',
    })
  }
  return list
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
  /** 3D 导演台 iframe 地址（空则不显示导演台入口）。 */
  directorDeskUrl?: string
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
}: GenerationInputBarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  // 导演台弹窗开关 & 当前主题（传给 iframe）
  const [directorOpen, setDirectorOpen] = useState(false)
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
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const mentionRef = useRef<HTMLDivElement>(null)
  const [mention, setMention] = useState<{
    open: boolean
    /** @ 字符在提示词中的起始下标，选中后用于替换 @ 及其后已输入的查询文本。 */
    start: number
    /** @ 之后已输入的文本，用于过滤候选项。 */
    query: string
    /** 当前键盘高亮的候选项下标。 */
    activeIndex: number
  }>({ open: false, start: -1, query: '', activeIndex: 0 })

  /**
   * 素材库查询：仅在 @ 选择器打开时请求。
   * staleTime 1 分钟避免重复请求；useQuery 自带缓存，与素材库页面共享 CREATION_ASSETS_KEY。
   */
  const { data: libData } = useQuery({
    queryKey: [...CREATION_ASSETS_KEY, { mention: true }],
    queryFn: () => listCreationAssets({ page: 1, page_size: 50 }),
    enabled: mention.open,
    staleTime: 60_000,
  })

  /**
   * 候选项：已上传参考素材（slot）+ 素材库中尚未加入参考列表的素材（library）。
   * slot 项 token 按类型编号（@图1/@视频1…）；library 项选中后追加到 refAssets，
   * token 同样按"加入后的序号"编号，保证与 slot 引用风格一致。
   * 人物素材可能同时含图片与音频，会展开为多个 token。
   */
  const mentionItems = useMemo<MentionItem[]>(() => {
    if (!mention.open) return []
    const refIds = new Set(refAssets.map((a) => a.assetId))

    // —— slot：已上传参考素材 ——
    const counts: Record<ReferenceKind, number> = { image: 0, video: 0, audio: 0 }
    const slotItems: MentionItem[] = refAssets
      .filter((a) => (mode === 'image' ? (a.kind ?? 'image') === 'image' : true))
      .map((a) => {
        const kind = a.kind ?? 'image'
        counts[kind] += 1
        const short = kind === 'image' ? '图' : kind === 'video' ? '视频' : '音频'
        return {
          source: 'slot',
          asset: a,
          assets: [a],
          kind,
          tokens: [`@${short}${counts[kind]}`],
          label: `${KIND_LABELS[kind]} ${counts[kind]}`,
          thumbUrl: a.previewUrl,
        }
      })

    // —— library：素材库中尚未加入的素材（人物/场景/道具） ——
    // 首帧/首尾帧模式仅图片，不允许音频；auto 合并模式与图片模式允许图片与音频。
    const spec = frameModeSpec(mode, isSeedance, frameMode)
    const allowAudio = mode === 'video' && (!spec || spec.allowMultimodal)
    // 预计算 library 项加入后每种类型的起始编号
    const libStart: Record<ReferenceKind, number> = { ...counts }
    const libItems: MentionItem[] = (libData?.items ?? [])
      .filter((ca) => !refIds.has(ca.image_asset_id ?? ca.audio_asset_id ?? ''))
      .map((ca) => {
        const pending = pendingAssetsOf(ca, mode, allowAudio).filter(
          (pa) => !refIds.has(pa.assetId),
        )
        const tokens = pending.map((pa) => {
          libStart[pa.kind ?? 'image'] += 1
          const short = pa.kind === 'image' ? '图' : pa.kind === 'video' ? '视频' : '音频'
          return `@${short}${libStart[pa.kind ?? 'image']}`
        })
        const primary = pending[0]
        return {
          source: 'library' as const,
          asset: primary,
          assets: pending,
          kind: (primary?.kind ?? 'image') as ReferenceKind,
          tokens,
          label: ca.name,
          thumbUrl: ca.image_thumbnail_url ?? '',
        }
      })
      .filter((it) => it.assets.length > 0)

    const all = [...slotItems, ...libItems]
    if (!mention.query) return all
    const q = mention.query.toLowerCase()
    return all.filter(
      (it) => it.tokens.some((t) => t.toLowerCase().includes(q)) || it.label.toLowerCase().includes(q),
    )
  }, [mention.open, mention.query, refAssets, mode, libData, isSeedance, frameMode])

  // 点击浮层外部关闭引用选择器
  useEffect(() => {
    if (!mention.open) return
    function onClick(e: MouseEvent) {
      if (mentionRef.current && !mentionRef.current.contains(e.target as Node)) {
        setMention({ open: false, start: -1, query: '', activeIndex: 0 })
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [mention.open])

  // 候选项变化时重置高亮，避免越界
  useEffect(() => {
    setMention((m) => (m.activeIndex === 0 ? m : { ...m, activeIndex: 0 }))
  }, [mentionItems])

  /**
   * 扫描光标前的文本，判断是否处于 @ 触发态：
   * 找到位于行首或空白之后的 @，且从 @ 到光标之间不含空白。
   */
  function detectMention(value: string, pos: number): { start: number; query: string } | null {
    const before = value.slice(0, pos)
    for (let i = before.length - 1; i >= 0; i--) {
      const ch = before[i]
      if (ch === '@') {
        const prev = before[i - 1]
        if (i === 0 || /\s/.test(prev ?? '')) {
          return { start: i, query: before.slice(i + 1) }
        }
        return null
      }
      if (/\s/.test(ch)) return null
    }
    return null
  }

  function handlePromptInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const value = e.target.value
    const pos = e.target.selectionStart ?? value.length
    onPromptChange(value)
    const detected = detectMention(value, pos)
    if (detected) {
      setMention({ open: true, start: detected.start, query: detected.query, activeIndex: 0 })
    } else if (mention.open) {
      setMention({ open: false, start: -1, query: '', activeIndex: 0 })
    }
  }

  function handlePromptKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // ⌘/Ctrl + Enter：提交生成（与底部生成按钮逻辑保持一致）
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      if (!submitting && !atConcurrencyLimit) {
        onGenerate()
      }
      return
    }

    if (!mention.open || mentionItems.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setMention((m) => ({ ...m, activeIndex: (m.activeIndex + 1) % mentionItems.length }))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setMention((m) => ({
        ...m,
        activeIndex: (m.activeIndex - 1 + mentionItems.length) % mentionItems.length,
      }))
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      insertMention(mentionItems[mention.activeIndex])
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setMention({ open: false, start: -1, query: '', activeIndex: 0 })
    }
  }

  /**
   * 将引用 token 插入到 @ 起始处，替换 @ 及其后已输入的查询文本，并追加一个空格。
   * 若选择的是素材库项（library），先将其追加到 refAssets（含上限校验），再按加入后的序号生成 token。
   * 人物素材可能同时含图片与音频，会插入多个 token（如 @图2 @音频1）。
   */
  function insertMention(item: MentionItem) {
    let tokens = item.tokens

    // 素材库项：追加到参考列表，并按加入后的实际序号重新编号 token
    if (item.source === 'library') {
      const spec = frameModeSpec(mode, isSeedance, frameMode)
      const allowAudio = mode === 'video' && (!spec || spec.allowMultimodal)
      // 校验并收集可加入的资产（已过滤掉已存在的）
      const toAdd: ReferenceAsset[] = []
      for (const pa of item.assets) {
        const kind = pa.kind ?? 'image'
        // 首帧/首尾帧模式仅接受图片
        if (spec && !spec.allowMultimodal && kind !== 'image') {
          toast(`${spec.label}模式仅支持图片参考`, 'error')
          setMention({ open: false, start: -1, query: '', activeIndex: 0 })
          return
        }
        // 上限校验：与上传流程保持一致
        const cap = KIND_CAPS[kind]
        const currentCount = refAssetsRef.current.filter(
          (a) => (a.kind ?? 'image') === kind,
        ).length
        if (currentCount + toAdd.filter((a) => (a.kind ?? 'image') === kind).length >= cap) {
          toast(`${KIND_LABELS[kind]}最多 ${cap} 个`, 'error')
          setMention({ open: false, start: -1, query: '', activeIndex: 0 })
          return
        }
        if (spec && !spec.allowMultimodal && kind === 'image') {
          const imageCount =
            refAssetsRef.current.filter((a) => (a.kind ?? 'image') === 'image').length +
            toAdd.filter((a) => (a.kind ?? 'image') === 'image').length
          if (imageCount >= spec.maxImages) {
            toast(`${spec.label}模式最多 ${spec.maxImages} 张参考图`, 'error')
            setMention({ open: false, start: -1, query: '', activeIndex: 0 })
            return
          }
        }
        toAdd.push(pa)
      }
      // 按加入后的列表重新编号
      const next = [...refAssetsRef.current, ...toAdd]
      refAssetsRef.current = next
      onRefAssetsChange(next)
      tokens = toAdd.map((pa) => {
        const kind = pa.kind ?? 'image'
        const sameKind = next.filter((a) => (a.kind ?? 'image') === kind)
        const idx = sameKind.findIndex((a) => a.assetId === pa.assetId) + 1
        const short = kind === 'image' ? '图' : kind === 'video' ? '视频' : '音频'
        return `@${short}${idx}`
      })
      void allowAudio
    }

    const textarea = textareaRef.current
    const pos = textarea?.selectionStart ?? prompt.length
    const insertion = tokens.join(' ') + ' '
    const newValue = prompt.slice(0, mention.start) + insertion + prompt.slice(pos)
    onPromptChange(newValue)
    const newPos = mention.start + insertion.length
    setMention({ open: false, start: -1, query: '', activeIndex: 0 })
    requestAnimationFrame(() => {
      textarea?.focus()
      textarea?.setSelectionRange(newPos, newPos)
    })
  }

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
    <div className="bg-transparent p-4">
      <div className="mx-auto max-w-5xl">
        <div
          className="relative rounded-2xl border border-border/60 bg-bg-secondary/70 p-5 shadow-xl backdrop-blur-md transition-colors duration-200 focus-within:border-border"
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
                  />
                ),
              )}
            </div>
          )}

          {/* 输入区：参考素材槽（含导演台）+ 提示词 */}
          <div className="flex gap-4">
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
                  className="absolute bottom-full left-0 z-50 mb-2 w-80 animate-slide-up rounded-card border border-border bg-bg-secondary p-1.5 shadow-xl"
                >
                  {refAssets.length === 0 && (libData?.items ?? []).length === 0 ? (
                    <div className="px-3 py-2 text-sm text-fg-muted">
                      暂无可引用的素材，请先上传或在素材库中新建资产
                    </div>
                  ) : mentionItems.length === 0 ? (
                    <div className="px-3 py-2 text-sm text-fg-muted">无匹配的素材</div>
                  ) : (
                    <>
                      <div className="px-2 pb-1 pt-1 text-[11px] text-fg-muted">
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
                            <span className="h-6 w-6 shrink-0 overflow-hidden rounded border border-border">
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
                onKeyDown={handlePromptKeyDown}
                disabled={submitting}
                placeholder={
                  mode === 'video'
                    ? isSeedance
                      ? `${refHint()}。支持上传图片、视频、音频作为参考素材（参考视频/音频单个时长 2-15 秒，各最多 3 个）。输入文字或 @ 引用素材，描述你想生成的视频。`
                      : '上传参考图/视频/音频、输入文字或 @ 引用素材，描述你想生成的视频。支持最多 9 张参考图、3 个参考视频、3 段参考音频。'
                    : '上传参考图、输入文字或 @ 引用素材，描述你想生成的图片。支持上传多张参考图融合生成。'
                }
                rows={4}
                className={cn(
                  'min-h-[120px] w-full resize-none bg-transparent text-base leading-relaxed text-fg-primary placeholder:text-fg-muted',
                  'transition-[height] duration-200 focus-visible:outline-none',
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
          <div className="mt-4 flex flex-wrap items-center gap-2 pr-36">
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
              modelId={modelId}
              providerSlug={providerSlug}
              aspectRatio={aspectRatio}
              resolution={resolution}
              onChange={updateRatioResolution}
              disabled={submitting}
              placement="top"
            />
            {mode === 'image' && (
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
              className="absolute bottom-5 right-5 transition-transform duration-200 hover:scale-[1.02] active:scale-[0.98]"
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
    <div className="flex h-9 items-center gap-1.5 rounded-btn border border-border bg-bg-tertiary/70 px-3 text-sm text-fg-secondary">
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
    <div className="flex h-9 items-center gap-1.5 rounded-btn border border-border bg-bg-tertiary/70 px-3 text-sm text-fg-secondary">
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
          className="flex h-9 items-center gap-1.5 rounded-btn border border-border bg-bg-tertiary/70 px-3 text-sm text-fg-secondary transition-colors hover:text-fg-primary disabled:opacity-50"
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
              <span className="text-xs text-fg-muted">{m.hint}</span>
            </div>
          </DropdownItem>
        )
      })}
    </Dropdown>
  )
}

