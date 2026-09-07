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
 * 全屏沉浸式提示词编辑器。
 * 点击输入框的展开按钮后全屏展示，提供大字号、无干扰的录入空间，
 * 并复用 usePromptMention 保持 @ 引用素材、⌘/Ctrl+Enter 提交等交互与内联输入条一致。
 */

import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Maximize2, Music, Video, Wand2, X } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { usePromptMention } from '@/hooks/usePromptMention'
import { cn } from '@/lib/utils'
import type { ContentMode } from '@/lib/generation'
import type { ReferenceAsset } from '@/lib/promptMention'

export interface PromptFullscreenEditorProps {
  /** 是否打开（打开时挂载到 document.body）。 */
  open: boolean
  onClose: () => void
  /** 提示词（受控，与内联输入条共享同一状态，实时同步）。 */
  prompt: string
  onPromptChange: (value: string) => void
  /** 参考素材列表，与内联输入条共享；@ 引用素材库项时会追加。 */
  refAssets?: ReferenceAsset[]
  onRefAssetsChange?: (assets: ReferenceAsset[]) => void
  mode?: ContentMode
  providerSlug?: string
  params?: Record<string, number | string>
  /** 是否启用 @ 引用素材（纯文本场景如画布备注节点传 false）。默认启用。 */
  enableMention?: boolean
  /** 提交生成（底部按钮 / ⌘+Enter 触发）。 */
  onGenerate?: () => void
  submitting?: boolean
  atConcurrencyLimit?: boolean
  /** 顶部标题；缺省为「沉浸式提示词编辑」。 */
  title?: string
}

export function PromptFullscreenEditor({
  open,
  onClose,
  prompt,
  onPromptChange,
  refAssets = [],
  onRefAssetsChange,
  mode = 'image',
  providerSlug = '',
  params = {},
  enableMention = true,
  onGenerate,
  submitting = false,
  atConcurrencyLimit = false,
  title = '沉浸式提示词编辑',
}: PromptFullscreenEditorProps) {
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
    onRefAssetsChange: (assets) => onRefAssetsChange?.(assets),
    mode,
    providerSlug,
    params,
    enabled: enableMention,
  })

  // Esc 关闭 + body 滚动锁定；打开时自动聚焦编辑器（供键盘直接输入）
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    const t = window.setTimeout(() => textareaRef.current?.focus(), 50)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      window.clearTimeout(t)
    }
  }, [open, onClose, textareaRef])

  if (!open) return null

  const placeholder = enableMention
    ? mode === 'video'
      ? '描述你想生成的视频… 输入 @ 可引用已上传的参考素材或素材库素材'
      : '描述你想生成的图片… 输入 @ 可引用已上传的参考素材或素材库素材'
    : '在此输入内容…'

  return createPortal(
    <div className="fixed inset-0 z-[70] flex animate-fade-in flex-col bg-bg-primary text-fg-primary">
      {/* 顶部工具栏 */}
      <div className="flex items-center justify-between border-b border-border/60 px-5 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <Maximize2 className="h-4 w-4 shrink-0 text-fg-secondary" />
          <p className="truncate text-sm font-medium">{title}</p>
          <span className="shrink-0 text-xs text-fg-muted">
            {prompt.length} 字
          </span>
          {onGenerate && (
            <span className="hidden shrink-0 text-xs text-fg-muted sm:inline">
              ⌘/Ctrl + Enter 提交生成
            </span>
          )}
        </div>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="退出全屏编辑">
          <X className="h-4 w-4" />
          <span>退出</span>
        </Button>
      </div>

      {/* 主体编辑区 */}
      <div
        className="relative flex flex-1 flex-col px-5 py-6"
        onClick={(e) => {
          if (e.target === e.currentTarget) textareaRef.current?.focus()
        }}
      >
        {/* @ 引用悬浮选择器 */}
        {enableMention && mention.open && (
          <div
            ref={mentionRef}
            className="absolute left-5 top-2 z-50 w-80 animate-slide-up rounded-card border border-border bg-bg-secondary p-1.5 shadow-elevated"
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

        <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col">
          <textarea
            ref={textareaRef}
            value={prompt}
            onChange={handlePromptInputChange}
            onKeyDown={(e) =>
              handlePromptKeyDown(e, onGenerate, submitting, atConcurrencyLimit)
            }
            placeholder={placeholder}
            autoFocus
            className="flex-1 resize-none bg-transparent text-lg leading-relaxed text-fg-primary placeholder:text-fg-muted focus-visible:outline-none scrollbar-thin"
          />
          <div className="flex items-center justify-between gap-2 pt-4">
            <span className="text-xs text-fg-muted">
              {enableMention
                ? '支持 @ 引用素材 · 拖拽/粘贴上传参考素材在输入条内操作'
                : 'Esc 退出全屏编辑'}
            </span>
            {onGenerate && (
              <Button
                size="md"
                onClick={() => {
                  onClose()
                  onGenerate()
                }}
                disabled={submitting || atConcurrencyLimit}
                className="transition-transform duration-200 hover:scale-[1.02] active:scale-[0.98]"
              >
                <Wand2 className="h-4 w-4" />
                {submitting ? '提交中…' : atConcurrencyLimit ? '并发已满' : '生成'}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}
