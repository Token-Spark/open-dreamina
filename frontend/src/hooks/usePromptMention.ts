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
 * @ 引用素材选择器的共享状态逻辑。
 * 内联输入条（GenerationInputBar）与全屏沉浸式编辑器（PromptFullscreenEditor）
 * 都通过 textarea 输入提示词，需要复用：光标扫描 @ 触发态、候选项构建与过滤、
 * 键盘上下选择 / Enter 插入 / Escape 关闭，以及素材库项追加到参考列表的校验逻辑。
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listCreationAssets } from '@/api/creationAssets'
import { CREATION_ASSETS_KEY } from '@/hooks/useCreationAssets'
import { toast } from '@/stores/uiStore'
import type { ContentMode } from '@/lib/generation'
import {
  KIND_CAPS,
  KIND_LABELS,
  detectMention,
  frameModeSpec,
  isSeedanceProvider,
  pendingAssetsOf,
  type FrameMode,
  type MentionItem,
  type ReferenceAsset,
} from '@/lib/promptMention'
import type { ReferenceKind } from '@/components/ReferenceSlot'

export interface PromptMentionState {
  open: boolean
  /** @ 字符在提示词中的起始下标，选中后用于替换 @ 及其后已输入的查询文本。 */
  start: number
  /** @ 之后已输入的文本，用于过滤候选项。 */
  query: string
  /** 当前键盘高亮的候选项下标。 */
  activeIndex: number
}

export interface UsePromptMentionOptions {
  prompt: string
  onPromptChange: (value: string) => void
  refAssets: ReferenceAsset[]
  onRefAssetsChange: (assets: ReferenceAsset[]) => void
  mode: ContentMode
  providerSlug: string
  params: Record<string, number | string>
  /** 是否启用 @ 引用（纯文本场景如画布备注节点可关闭）。默认启用。 */
  enabled?: boolean
}

export function usePromptMention({
  prompt,
  onPromptChange,
  refAssets,
  onRefAssetsChange,
  mode,
  providerSlug,
  params,
  enabled = true,
}: UsePromptMentionOptions) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const mentionRef = useRef<HTMLDivElement>(null)
  const [mention, setMention] = useState<PromptMentionState>({
    open: false,
    start: -1,
    query: '',
    activeIndex: 0,
  })

  // 镜像 refAssets，供异步审核轮询与插入校验读取最新列表，避免闭包捕获过期状态。
  const refAssetsRef = useRef(refAssets)
  useEffect(() => {
    refAssetsRef.current = refAssets
  }, [refAssets])

  const isSeedance = isSeedanceProvider(providerSlug)
  const frameMode = (params.frame_mode === 'first' || params.frame_mode === 'first_last'
    ? params.frame_mode
    : 'auto') as FrameMode

  /**
   * 素材库查询：仅在 @ 选择器打开时请求。
   * staleTime 1 分钟避免重复请求；useQuery 自带缓存，与素材库页面共享 CREATION_ASSETS_KEY。
   */
  const { data: libData } = useQuery({
    queryKey: [...CREATION_ASSETS_KEY, { mention: true }],
    queryFn: () => listCreationAssets({ page: 1, page_size: 50 }),
    enabled: enabled && mention.open,
    staleTime: 60_000,
  })

  /**
   * 候选项：已上传参考素材（slot）+ 素材库中尚未加入参考列表的素材（library）。
   * slot 项 token 按类型编号（@图1/@视频1…）；library 项选中后追加到 refAssets，
   * token 同样按"加入后的序号"编号，保证与 slot 引用风格一致。
   * 人物素材可能同时含图片与音频，会展开为多个 token。
   */
  const mentionItems = useMemo<MentionItem[]>(() => {
    if (!enabled || !mention.open) return []
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
          source: 'slot' as const,
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
    // 人物素材的图片与音频拆分为独立候选项，用户可按需引用形象或音色。
    // 音频候选项展示角色形象缩略图+Music角标，标签追加「· 音色」后缀。
    const libItems: MentionItem[] = (libData?.items ?? [])
      .flatMap((ca) => {
        const pending = pendingAssetsOf(ca, mode, allowAudio).filter(
          (pa) => !refIds.has(pa.assetId),
        )
        return pending.map((pa) => {
          const kind = (pa.kind ?? 'image') as ReferenceKind
          libStart[kind] += 1
          const short = kind === 'image' ? '图' : kind === 'video' ? '视频' : '音频'
          return {
            source: 'library' as const,
            asset: pa,
            assets: [pa],
            kind,
            tokens: [`@${short}${libStart[kind]}`],
            label: kind === 'audio' && ca.category === 'character' ? `${ca.name} · 音色` : ca.name,
            thumbUrl: ca.image_thumbnail_url ?? '',
          }
        })
      })

    const all = [...slotItems, ...libItems]
    if (!mention.query) return all
    const q = mention.query.toLowerCase()
    return all.filter(
      (it) =>
        it.tokens.some((t) => t.toLowerCase().includes(q)) ||
        it.label.toLowerCase().includes(q),
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

  /** 输入回调：同步提示词并扫描 @ 触发态。 */
  function handlePromptInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const value = e.target.value
    const pos = e.target.selectionStart ?? value.length
    onPromptChange(value)
    if (!enabled) return
    const detected = detectMention(value, pos)
    if (detected) {
      setMention({ open: true, start: detected.start, query: detected.query, activeIndex: 0 })
    } else if (mention.open) {
      setMention({ open: false, start: -1, query: '', activeIndex: 0 })
    }
  }

  /** 键盘处理：⌘/Ctrl+Enter 提交；选择器打开时支持方向键/Enter/Escape。 */
  function handlePromptKeyDown(
    e: React.KeyboardEvent<HTMLTextAreaElement>,
    onGenerate?: () => void,
    submitting?: boolean,
    atConcurrencyLimit?: boolean,
  ) {
    // ⌘/Ctrl + Enter：提交生成（与底部生成按钮逻辑保持一致）
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      if (onGenerate && !submitting && !atConcurrencyLimit) {
        onGenerate()
      }
      return
    }

    if (!enabled || !mention.open || mentionItems.length === 0) return
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

  return {
    textareaRef,
    mentionRef,
    mention,
    mentionItems,
    /** 素材库中是否有可引用的素材（用于空状态提示）。 */
    hasLibraryAssets: (libData?.items ?? []).length > 0,
    handlePromptInputChange,
    handlePromptKeyDown,
    insertMention,
  }
}
