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
  expandToMentionBounds,
  findMentionRanges,
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
   * token 使用素材名称（@{name}），而非序号编号，这样移除某个引用不会影响其他引用的文本。
   * 人物素材可能同时含图片与音频，会展开为多个候选项。
   */
  const mentionItems = useMemo<MentionItem[]>(() => {
    if (!enabled || !mention.open) return []
    const refIds = new Set(refAssets.map((a) => a.assetId))

    // —— slot：已上传参考素材 ——
    const slotItems: MentionItem[] = refAssets
      .filter((a) => (mode === 'image' ? (a.kind ?? 'image') === 'image' : true))
      .map((a) => {
        const kind = a.kind ?? 'image'
        const name = a.name ?? KIND_LABELS[kind]
        return {
          source: 'slot' as const,
          asset: a,
          assets: [a],
          kind,
          tokens: [`@{${name}}`],
          label: name,
          thumbUrl: a.previewUrl,
        }
      })

    // —— library：素材库中尚未加入的素材（人物/场景/道具） ——
    // 首帧/首尾帧模式仅图片，不允许音频；auto 合并模式与图片模式允许图片与音频。
    const spec = frameModeSpec(mode, isSeedance, frameMode)
    const allowAudio = mode === 'video' && (!spec || spec.allowMultimodal)
    // 人物素材的图片与音频拆分为独立候选项，用户可按需引用形象或音色。
    // 音频候选项展示角色形象缩略图+Music角标，标签追加「· 音色」后缀。
    const libItems: MentionItem[] = (libData?.items ?? [])
      .flatMap((ca) => {
        const pending = pendingAssetsOf(ca, mode, allowAudio).filter(
          (pa) => !refIds.has(pa.assetId),
        )
        return pending.map((pa) => {
          const kind = (pa.kind ?? 'image') as ReferenceKind
          const label = kind === 'audio' && ca.category === 'character' ? `${ca.name} · 音色` : ca.name
          return {
            source: 'library' as const,
            asset: pa,
            assets: [pa],
            kind,
            tokens: [`@{${label}}`],
            label,
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

  /**
   * 光标吸附：引用标签在视觉与语义上是一个整体元素，光标不允许落在 token 内部，
   * 否则会出现 "@{Stel|la}" 这类半截编辑；鼠标点击落到 token 内部时吸附到最近边界。
   */
  function handlePromptSelect(e: React.SyntheticEvent<HTMLTextAreaElement>) {
    if (!enabled) return
    const textarea = e.currentTarget
    const start = textarea.selectionStart ?? 0
    const end = textarea.selectionEnd ?? 0
    if (start !== end) return
    const range = findMentionRanges(prompt).find((r) => start > r.start && start < r.end)
    if (!range) return
    const snapped = start - range.start <= range.end - start ? range.start : range.end
    textarea.setSelectionRange(snapped, snapped)
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

    // 方向键：光标位于引用标签边界时整体跳过 token。
    // 否则光标会先落到 token 内部、再被 handlePromptSelect 吸附回原边界，导致左右键卡住。
    if (enabled && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
      const textarea = e.currentTarget
      const caret = textarea.selectionStart ?? 0
      if (caret === (textarea.selectionEnd ?? 0)) {
        const jump =
          e.key === 'ArrowLeft'
            ? findMentionRanges(prompt).find((r) => r.end === caret)
            : findMentionRanges(prompt).find((r) => r.start === caret)
        if (jump) {
          e.preventDefault()
          const next = e.key === 'ArrowLeft' ? jump.start : jump.end
          textarea.setSelectionRange(next, next)
          return
        }
      }
    }

    // 退格/删除：与引用 token 相交时把待删区间扩展到 token 完整边界整体删除，
    // 避免只删掉半个 token 而残留 "@{" / "}" 等碎片。
    if (enabled && (e.key === 'Backspace' || e.key === 'Delete')) {
      const textarea = e.currentTarget
      const collapsed = (textarea.selectionStart ?? 0) === (textarea.selectionEnd ?? 0)
      let start = textarea.selectionStart ?? 0
      let end = textarea.selectionEnd ?? 0
      if (collapsed) {
        // 折叠光标：先按一个字符确定待删区间，再判断是否落在 token 上
        if (e.key === 'Backspace') start = Math.max(0, start - 1)
        else end = Math.min(prompt.length, end + 1)
      }
      const bounds = expandToMentionBounds(prompt, start, end)
      if (bounds.start !== start || bounds.end !== end) {
        e.preventDefault()
        onPromptChange(prompt.slice(0, bounds.start) + prompt.slice(bounds.end))
        setMention({ open: false, start: -1, query: '', activeIndex: 0 })
        requestAnimationFrame(() => textarea.setSelectionRange(bounds.start, bounds.start))
        return
      }
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
   * 若选择的是素材库项（library），先将其追加到 refAssets（含上限校验），再按素材名称生成 token。
   * 人物素材可能同时含图片与音频，会插入多个 token（如 @{角色名} @{角色名 · 音色}）。
   */
  function insertMention(item: MentionItem) {
    let tokens = item.tokens

    // 素材库项：追加到参考列表，并按素材名称生成 token
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
      // 设置素材名称到 ReferenceAsset，便于 overlay 展示
      toAdd.forEach((pa) => {
        if (!pa.name) pa.name = item.label
      })
      const next = [...refAssetsRef.current, ...toAdd]
      refAssetsRef.current = next
      onRefAssetsChange(next)
      // 按素材名称生成 token，移除某个引用不会影响其他引用
      tokens = toAdd.map((pa) => `@{${pa.name ?? item.label}}`)
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
    handlePromptSelect,
    handlePromptKeyDown,
    insertMention,
  }
}
