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
 * 镜头审片的提示词编辑主体。
 *
 * 复用创作页的零件（PromptMentionOverlay / ReferenceAssetTray / ImageLightbox /
 * PromptFullscreenEditor），让审片人在同一个视图里对照「原始提示词」和「本镜被引用
 * 资产」改写精修提示词，而不是对着一个孤立的 textarea 盲改。
 *
 * 与创作页的差别只有一处：这里不提供 @ 素材库候选插入。审片保存的是
 * revised_prompt 文本，资产清单由原生成任务决定、不随编辑变化，开放插入会造成误解。
 * 已有 @{素材名} token 仍会高亮并可悬浮预览。
 */

import { useEffect, useRef, useState } from 'react'
import {
  ChevronDown,
  ChevronUp,
  ClipboardCopy,
  FileText,
  Images,
  Maximize2,
  Wand2,
} from 'lucide-react'
import type { ShotReviewItem } from '@/api/shotReviews'
import { ImageLightbox } from '@/components/ImageLightbox'
import { PromptFullscreenEditor } from '@/components/PromptFullscreenEditor'
import { PromptMentionOverlay } from '@/components/PromptMentionOverlay'
import { ReferenceAssetTray } from '@/components/ReferenceAssetTray'
import { Button } from '@/components/ui/Button'
import { useShotRefAssets } from '@/components/shotReview/useShotRefAssets'
import { cn } from '@/lib/utils'

/** 一键把文本写入剪贴板，失败时静默返回 false。 */
export async function copyText(text: string): Promise<boolean> {
  if (!text) return false
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

export interface ShotPromptEditorProps {
  item: ShotReviewItem
  /** 受控的精修提示词（与外层保存状态共享，全屏编辑实时同步）。 */
  value: string
  onChange: (value: string) => void
  /** ⌘/Ctrl + Enter 与全屏编辑器的提交按钮触发。 */
  onSave?: () => void
  saving?: boolean
  autoFocus?: boolean
}

export function ShotPromptEditor({
  item,
  value,
  onChange,
  onSave,
  saving = false,
  autoFocus = false,
}: ShotPromptEditorProps) {
  const { refAssets, gallery, loading } = useShotRefAssets(item)
  const source = item.source_prompt ?? ''

  const [sourceOpen, setSourceOpen] = useState(true)
  const [fullscreenOpen, setFullscreenOpen] = useState(false)
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const [scrollSync, setScrollSync] = useState({ top: 0, left: 0 })
  const [copiedSource, setCopiedSource] = useState(false)
  const copiedTimer = useRef<number | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(
    () => () => {
      if (copiedTimer.current != null) window.clearTimeout(copiedTimer.current)
    },
    [],
  )

  // 弹窗类容器可能是条件显示而非重新挂载，用 effect 保证打开时拿到焦点
  useEffect(() => {
    if (autoFocus) textareaRef.current?.focus()
  }, [autoFocus])

  // 覆盖层与 textarea 必须使用完全一致的字体度量，否则光标与 @ 标签会错位。
  // 换行规则由 PromptMentionOverlay 内部统一加 whitespace-pre-wrap / break-words，
  // 这里只共享字体、行高与 padding（与创作页 GenerationInputBar 的做法一致）。
  const editorTextClass = 'w-full p-2.5 font-mono text-xs leading-relaxed'

  async function handleCopySource() {
    if (await copyText(source)) {
      setCopiedSource(true)
      if (copiedTimer.current != null) window.clearTimeout(copiedTimer.current)
      copiedTimer.current = window.setTimeout(() => setCopiedSource(false), 1500)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      if (onSave && !saving) onSave()
    }
  }

  function handleSaveFromFullscreen() {
    setFullscreenOpen(false)
    if (onSave && !saving) onSave()
  }

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {/* 左列：原始提示词 + 本镜被引用资产，编辑时始终可见 */}
      <div className="flex min-w-0 flex-col gap-3">
        <section className="rounded-btn border border-border bg-bg-tertiary/50">
          <header className="flex items-center gap-1.5 border-b border-border px-2.5 py-1.5">
            <FileText className="h-3 w-3 shrink-0 text-fg-muted" />
            <span className="text-[11px] font-medium text-fg-secondary">原始提示词</span>
            <span className="truncate text-[10px] text-fg-muted">
              {source ? '分镜底稿 / 原生成任务' : '未登记'}
            </span>
            <div className="ml-auto flex shrink-0 items-center gap-0.5">
              {source && (
                <>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 px-1.5 text-[11px]"
                    onClick={() => onChange(source)}
                    title="用原始提示词覆盖当前编辑内容"
                  >
                    填入编辑器
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 px-1.5 text-[11px]"
                    onClick={() => void handleCopySource()}
                  >
                    <ClipboardCopy className="h-3 w-3" />
                    {copiedSource ? '已复制' : '复制'}
                  </Button>
                </>
              )}
              <button
                type="button"
                onClick={() => setSourceOpen((v) => !v)}
                className="flex h-6 w-6 items-center justify-center rounded-btn text-fg-muted transition-colors hover:bg-bg-secondary hover:text-fg-primary"
                aria-label={sourceOpen ? '收起原始提示词' : '展开原始提示词'}
              >
                {sourceOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              </button>
            </div>
          </header>
          {sourceOpen && (
            <div className="max-h-44 overflow-y-auto whitespace-pre-wrap px-2.5 py-2 text-[11px] leading-relaxed text-fg-secondary scrollbar-thin">
              {source || (
                <span className="text-fg-muted">
                  该镜未登记原始提示词。可通过 drama review-import 从原生成任务带入，或由 shots.md 扫描提取。
                </span>
              )}
            </div>
          )}
        </section>

        <section className="rounded-btn border border-border bg-bg-tertiary/50">
          <header className="flex items-center gap-1.5 border-b border-border px-2.5 py-1.5">
            <Images className="h-3 w-3 shrink-0 text-fg-muted" />
            <span className="text-[11px] font-medium text-fg-secondary">被引用资产</span>
            <span className="text-[10px] tabular-nums text-fg-muted">{refAssets.length}</span>
            {loading && <span className="text-[10px] text-fg-muted">· 读取素材信息…</span>}
            {refAssets.length > 0 && (
              <button
                type="button"
                onClick={() => setLightboxIndex(0)}
                className="ml-auto rounded-btn px-1.5 py-0.5 text-[11px] text-fg-muted transition-colors hover:bg-bg-secondary hover:text-fg-primary"
              >
                在灯箱中浏览
              </button>
            )}
          </header>
          {refAssets.length > 0 ? (
            <div className="px-2 py-1">
              <ReferenceAssetTray
                assets={refAssets}
                compact
                onPreview={(asset) => {
                  const index = refAssets.findIndex((a) => a.assetId === asset.assetId)
                  setLightboxIndex(index < 0 ? 0 : index)
                }}
              />
            </div>
          ) : (
            <p className="px-2.5 py-2 text-[11px] leading-relaxed text-fg-muted">
              该镜未登记参考素材。历史审片卡片需重新执行 drama review-import，才会带入原生成任务引用的资产。
            </p>
          )}
        </section>
      </div>

      {/* 右列：与创作页同源的提示词输入（@ 引用高亮 + 全屏编辑） */}
      <section className="flex min-w-0 flex-col rounded-btn border border-border bg-bg-primary">
        <header className="flex items-center gap-1.5 border-b border-border px-2.5 py-1.5">
          <Wand2 className="h-3 w-3 shrink-0 text-accent" />
          <span className="text-[11px] font-medium text-fg-secondary">精修提示词</span>
          <span className="text-[10px] tabular-nums text-fg-muted">{value.length} 字</span>
          <button
            type="button"
            onClick={() => setFullscreenOpen(true)}
            className="ml-auto flex h-6 items-center gap-1 rounded-btn px-1.5 text-[11px] text-fg-muted transition-colors hover:bg-bg-tertiary hover:text-fg-primary"
            title="全屏沉浸式编辑"
          >
            <Maximize2 className="h-3 w-3" />
            全屏编辑
          </button>
        </header>
        <div className="relative h-56">
          <PromptMentionOverlay
            prompt={value}
            scrollOffset={scrollSync}
            refAssets={refAssets}
            className={editorTextClass}
          />
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onScroll={() => {
              const ta = textareaRef.current
              if (ta) setScrollSync({ top: ta.scrollTop, left: ta.scrollLeft })
            }}
            onKeyDown={handleKeyDown}
            placeholder="在原始提示词基础上改写下一版生成使用的 AIGC 提示词…"
            autoFocus={autoFocus}
            spellCheck={false}
            className={cn(
              editorTextClass,
              'absolute inset-0 h-full w-full resize-none bg-transparent text-transparent caret-fg-primary placeholder:text-fg-muted focus-visible:outline-none scrollbar-thin',
            )}
            style={{ zIndex: 10 }}
          />
        </div>
        <footer className="border-t border-border px-2.5 py-1.5 text-[10px] text-fg-muted">
          ⌘/Ctrl + Enter 保存 · 提示词中的 {'@{素材名}'} 会高亮并可悬浮预览
        </footer>
      </section>

      <PromptFullscreenEditor
        open={fullscreenOpen}
        onClose={() => setFullscreenOpen(false)}
        prompt={value}
        onPromptChange={onChange}
        refAssets={refAssets}
        mode={item.content_type === 'video' ? 'video' : 'image'}
        mentionCandidates={false}
        placeholder="在原始提示词基础上改写下一版生成使用的 AIGC 提示词…"
        onGenerate={onSave ? handleSaveFromFullscreen : undefined}
        submitting={saving}
        submitLabel="保存"
        title={`${item.shot_id} · 精修提示词`}
      />

      <ImageLightbox
        gallery={lightboxIndex != null ? { items: gallery, index: lightboxIndex } : null}
        open={lightboxIndex != null && gallery.length > 0}
        onClose={() => setLightboxIndex(null)}
      />
    </div>
  )
}
