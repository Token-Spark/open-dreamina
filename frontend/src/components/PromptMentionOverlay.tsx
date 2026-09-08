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
 * 在 textarea 下方叠加一层同样式 div，将提示词中已被引用的 @ token（如 @图1、@视频1）
 * 渲染为带高亮背景的独立标签，并显示对应的素材名称，让用户直观区分「普通文本」与「已绑定的引用素材」。
 *
 * 原理：
 *   - 覆盖层与 textarea 共享相同的字体度量、padding 和换行规则
 *   - textarea 文字设为透明（text-transparent），仅显示光标（caret-fg-primary）
 *   - 覆盖层位于 textarea 下方（z-0），textarea 位于上方（z-10）
 *   - 覆盖层随 textarea 滚动同步偏移
 */

import { useMemo, type CSSProperties } from 'react'
import { cn } from '@/lib/utils'
import type { ReferenceAsset } from '@/lib/promptMention'

/** 匹配提示词中的 @ 引用 token，如 @图1、@视频2、@音频3 */
const MENTION_RE = /@(图|视频|音频)(\d+)/g

/** token 中的类型前缀 → ReferenceKind 映射 */
const TOKEN_KIND: Record<string, ReferenceAsset['kind']> = {
  '图': 'image',
  '视频': 'video',
  '音频': 'audio',
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
  /** 参考素材列表，用于将 @图1 token 解析为素材名称展示。 */
  refAssets?: ReferenceAsset[]
  style?: CSSProperties
}

/**
 * 将 @图1 token 解析为对应的素材名称。
 * token 格式：@ + 类型（图/视频/音频）+ 序号（按同类型上传顺序从 1 开始）
 */
function resolveTokenName(token: string, refAssets: ReferenceAsset[]): string | null {
  const m = token.match(/^@(图|视频|音频)(\d+)$/)
  if (!m) return null
  const kind = TOKEN_KIND[m[1]]
  const idx = parseInt(m[2], 10)
  const sameKind = refAssets.filter((a) => (a.kind ?? 'image') === kind)
  const asset = sameKind[idx - 1]
  return asset?.name ?? null
}

export function PromptMentionOverlay({
  prompt,
  enabled = true,
  className,
  scrollOffset,
  refAssets,
  style,
}: PromptMentionOverlayProps) {
  // 将提示词按 @ token 拆分：token 部分渲染为高亮标签（含素材名），其余为普通文本。
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

  return (
    <div
      aria-hidden
      className={cn(
        'pointer-events-none absolute inset-0 overflow-hidden whitespace-pre-wrap break-words',
        className,
      )}
      style={{
        ...style,
        zIndex: 0,
        transform: scrollOffset
          ? `translate(${-scrollOffset.left}px, ${-scrollOffset.top}px)`
          : undefined,
      }}
    >
      {segments?.map((seg, i) =>
        seg.type === 'mention' ? (
          <span
            key={i}
            style={{
              backgroundColor: 'color-mix(in srgb, var(--accent) 18%, transparent)',
              color: 'var(--accent)',
              borderRadius: '3px',
              padding: '0 2px',
            }}
          >
            {seg.name ? `${seg.value}（${seg.name}）` : seg.value}
          </span>
        ) : (
          <span key={i}>{seg.value}</span>
        ),
      )}
    </div>
  )
}
