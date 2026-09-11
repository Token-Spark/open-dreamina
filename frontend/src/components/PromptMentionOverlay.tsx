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
 * 提示词 @ 引用高亮覆盖层。
 *
 * 在 textarea 下方叠加一层同样式 div，将提示词中已被引用的 @ token（如 @{素材名}）
 * 渲染为带高亮背景的独立标签，让用户直观区分「普通文本」与「已绑定的引用素材」。
 *
 * 原理：
 *   - 视觉层（z-0）与 textarea 共享相同的字体度量、padding 和换行规则
 *   - textarea 文字设为透明（text-transparent），仅显示光标（caret-fg-primary）
 *   - 交互层（z-15）位于 textarea 上方，透明文字，仅 mention span 可交互
 *   - 鼠标悬浮 mention span 时弹出预览弹层（图片大图 / 视频缩略图 / 音频占位）
 *   - 覆盖层随 textarea 滚动同步偏移
 *   - 覆盖层文本与 textarea 文本完全一致（token 原样渲染），通过 title 属性显示素材名
 */

import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import { Music } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ReferenceAsset } from '@/lib/promptMention'

/** 匹配提示词中的 @ 引用 token，如 @{素材名} */
const MENTION_RE = /@\{([^}]+)\}/g

const KIND_LABEL: Record<NonNullable<ReferenceAsset['kind']>, string> = {
  image: '参考图',
  video: '参考视频',
  audio: '参考音频',
}

export interface PromptMentionOverlayProps {
  /** 提示词全文（与 textarea value 完全一致）。 */
  prompt: string
  /** 是否启用高亮（纯文本场景可关闭）。默认启用。 */
  enabled?: boolean
  /** 与 textarea 共享的 className（字体度量、padding、宽高）。 */
  className?: string
  /** textarea 滚动偏移，保持覆盖层内容与 textarea 对齐。 */
  scrollOffset?: { top: number; left: number }
  /** 参考素材列表，用于将 @{素材名} token 解析为素材（title 展示 & 悬浮预览）。 */
  refAssets?: ReferenceAsset[]
  style?: CSSProperties
}

/**
 * 将 @{素材名} token 解析为对应的素材名称。
 * token 格式：@{ + 素材名称 + }
 * 通过名称匹配 refAssets 中的素材。
 */
function resolveTokenName(token: string, refAssets: ReferenceAsset[]): string | null {
  const m = token.match(/^@\{([^}]+)\}$/)
  if (!m) return null
  const name = m[1]
  const asset = refAssets.find((a) => a.name === name)
  return asset?.name ?? null
}

/** 解析 @{素材名} token 对应的参考素材（用于悬浮预览）。 */
function resolveTokenAsset(token: string, refAssets: ReferenceAsset[]): ReferenceAsset | null {
  const m = token.match(/^@\{([^}]+)\}$/)
  if (!m) return null
  const name = m[1]
  return refAssets.find((a) => a.name === name) ?? null
}

/** mention token 悬浮预览弹层：展示素材大图/视频缩略图/音频信息。 */
function MentionHoverPreview({
  asset,
  anchorRect,
}: {
  asset: ReferenceAsset
  anchorRect: DOMRect
}) {
  const kind = (asset.kind ?? 'image') as NonNullable<ReferenceAsset['kind']>
  const name = asset.name ?? KIND_LABEL[kind]

  // 根据锚点位置计算弹层放置方向（上方/下方），避免溢出视口
  const placeBelow = anchorRect.top < 220
  const top = placeBelow ? anchorRect.bottom + 8 : anchorRect.top - 8
  const left = anchorRect.left + anchorRect.width / 2

  return createPortal(
    <div
      className="fixed z-[80] flex -translate-x-1/2 flex-col gap-1 rounded-card border border-border bg-bg-secondary p-2 shadow-elevated animate-fade-in"
      style={{
        top,
        left,
        transform: `translate(-50%, ${placeBelow ? '0' : '-100%'})`,
      }}
    >
      <div className="h-32 w-32 overflow-hidden rounded-btn border border-border">
        {kind === 'video' ? (
          <video src={asset.previewUrl} muted playsInline className="h-full w-full object-cover" />
        ) : kind === 'audio' ? (
          <div className="flex h-full w-full flex-col items-center justify-center gap-1.5 bg-bg-tertiary">
            <Music className="h-8 w-8 text-fg-muted" />
            <span className="text-[10px] text-fg-muted">音频素材</span>
          </div>
        ) : (
          <img src={asset.previewUrl} alt={name} className="h-full w-full object-cover" />
        )}
      </div>
      <span className="block max-w-32 truncate text-center text-xs text-fg-muted">{name}</span>
    </div>,
    document.body,
  )
}

export function PromptMentionOverlay({
  prompt,
  enabled = true,
  className,
  scrollOffset,
  refAssets,
  style,
}: PromptMentionOverlayProps) {
  const [hoverAsset, setHoverAsset] = useState<ReferenceAsset | null>(null)
  const [hoverRect, setHoverRect] = useState<DOMRect | null>(null)
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 清理挂起的定时器，防止组件卸载后回调执行
  useEffect(() => {
    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current)
    }
  }, [])

  // 将提示词按 @ token 拆分：token 部分渲染为高亮标签（title 显示素材名），其余为普通文本。
  // 注意：标签内文本必须与 textarea 中的 token 完全一致，否则换行位置不同导致光标错位。
  const segments = useMemo(() => {
    if (!enabled || !prompt) return null
    const parts: Array<{ type: 'text' | 'mention'; value: string; name?: string }> = []
    let last = 0
    for (const m of prompt.matchAll(MENTION_RE)) {
      const idx = m.index ?? 0
      if (idx > last) parts.push({ type: 'text', value: prompt.slice(last, idx) })
      const token = m[0]
      const name = refAssets ? resolveTokenName(token, refAssets) : null
      parts.push({ type: 'mention', value: token, name: name ?? undefined })
      last = idx + token.length
    }
    if (last < prompt.length) parts.push({ type: 'text', value: prompt.slice(last) })
    return parts
  }, [prompt, enabled, refAssets])

  if (!enabled) return null

  /** 鼠标进入 mention span：清除隐藏定时器，显示预览。 */
  function handleMentionEnter(e: React.MouseEvent, token: string) {
    if (!refAssets) return
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current)
      hideTimerRef.current = null
    }
    const asset = resolveTokenAsset(token, refAssets)
    if (asset) {
      setHoverAsset(asset)
      setHoverRect(e.currentTarget.getBoundingClientRect())
    }
  }

  /** 鼠标离开 mention span：延迟 100ms 关闭，避免鼠标移动抖动。 */
  function handleMentionLeave() {
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current)
    hideTimerRef.current = setTimeout(() => {
      setHoverAsset(null)
      setHoverRect(null)
    }, 100)
  }

  const transform = scrollOffset
    ? `translate(${-scrollOffset.left}px, ${-scrollOffset.top}px)`
    : undefined

  return (
    <>
      {/* 视觉高亮层（textarea 下方，z-0）
          overflow-y-auto + scrollbar-gutter-only：预留与 textarea 相同的滚动条宽度，
          确保两层文本排版宽度一致，避免换行点偏移导致光标/选区错位。 */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 overflow-y-auto scrollbar-gutter-only"
        style={{ ...style, zIndex: 0 }}
      >
        <div
          className={cn('whitespace-pre-wrap break-words', className)}
          style={{ transform }}
        >
          {segments?.map((seg, i) =>
            seg.type === 'mention' ? (
              <span
                key={i}
                title={seg.name ?? undefined}
                style={{
                  backgroundColor: 'color-mix(in srgb, var(--accent) 18%, transparent)',
                  color: 'var(--accent)',
                  borderRadius: '3px',
                }}
              >
                {seg.value}
              </span>
            ) : (
              <span key={i}>{seg.value}</span>
            ),
          )}
        </div>
      </div>
      {/* 交互层（textarea 上方，z-15）：透明文字，仅 mention span 可交互 */}
      <div
        aria-hidden
        className="absolute inset-0 overflow-hidden"
        style={{ zIndex: 15, color: 'transparent', pointerEvents: 'none' }}
      >
        <div
          className={cn('whitespace-pre-wrap break-words', className)}
          style={{ transform }}
        >
          {segments?.map((seg, i) =>
            seg.type === 'mention' ? (
              <span
                key={i}
                style={{ pointerEvents: 'auto' }}
                onMouseEnter={(e) => handleMentionEnter(e, seg.value)}
                onMouseLeave={handleMentionLeave}
              >
                {seg.value}
              </span>
            ) : (
              <span key={i}>{seg.value}</span>
            ),
          )}
        </div>
      </div>
      {hoverAsset && hoverRect && (
        <MentionHoverPreview asset={hoverAsset} anchorRect={hoverRect} />
      )}
    </>
  )
}
