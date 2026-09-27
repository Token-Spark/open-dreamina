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
import { BadgeCheck, Check, Copy, Maximize2, Wand2 } from 'lucide-react'
import type { ShotReviewItem, ShotVerdict } from '@/api/shotReviews'
import {
  shotReviewItemFileUrl,
  shotReviewItemThumbnailUrl,
} from '@/api/shotReviews'
import { Badge } from '@/components/ui/Badge'
import { PromptEditDialog, copyText } from '@/components/shotReview/PromptEditDialog'
import { FeedbackEditor, ScoreEditor, useInView } from '@/components/shotReview/ShotReviewEditors'
import { cn, formatFileSize } from '@/lib/utils'

export const VERDICT_META: Record<
  ShotVerdict,
  { label: string; variant: 'default' | 'success' | 'error' | 'warning' }
> = {
  pending: { label: '待审', variant: 'default' },
  pass: { label: '通过', variant: 'success' },
  revise: { label: '需重生成', variant: 'warning' },
  redesign: { label: '需重新设计', variant: 'error' },
}

/** 竖屏判定：有分辨率元信息且高大于宽（短剧 9:16 视频按竖屏布局展示）。 */
export function isPortraitItem(item: Pick<ShotReviewItem, 'width' | 'height'>): boolean {
  return !!item.width && !!item.height && item.height > item.width
}

/** 竖屏视频的预览高度：固定更高，保证 9:16 画面有足够纵向空间。 */
export const PORTRAIT_VIDEO_HEIGHT = 'h-[420px]'

export interface ShotReviewCardProps {
  item: ShotReviewItem
  onScoreChange: (score: number) => void
  onClearScore: () => void
  onFeedbackChange: (feedback: string) => void
  /** 保存精修提示词（作为该镜的修改备注）；空串表示清除。 */
  onPromptSave: (revisedPrompt: string) => void
  onOpen: () => void
}

export function ShotReviewCard({
  item,
  onScoreChange,
  onClearScore,
  onFeedbackChange,
  onPromptSave,
  onOpen,
}: ShotReviewCardProps) {
  const [promptOpen, setPromptOpen] = useState(false)
  const [copiedPrompt, setCopiedPrompt] = useState(false)
  const copiedTimer = useRef<number | null>(null)
  const [containerRef, inView] = useInView<HTMLDivElement>()

  useEffect(
    () => () => {
      if (copiedTimer.current != null) window.clearTimeout(copiedTimer.current)
    },
    [],
  )

  const meta = VERDICT_META[item.verdict]
  const portrait = isPortraitItem(item)

  async function handleCopyPrompt() {
    if (!item.revised_prompt) return
    if (await copyText(item.revised_prompt)) {
      setCopiedPrompt(true)
      if (copiedTimer.current != null) window.clearTimeout(copiedTimer.current)
      copiedTimer.current = window.setTimeout(() => setCopiedPrompt(false), 1500)
    }
  }

  return (
    <div
      className={cn(
        'flex flex-col overflow-hidden rounded-card border border-border bg-bg-secondary transition-all',
        item.verdict === 'pass' && 'ring-1 ring-success/20',
        item.verdict === 'revise' && 'ring-1 ring-warning/20',
        item.verdict === 'redesign' && 'ring-1 ring-error/20',
        item.selected && 'ring-2 ring-success/50',
      )}
    >
      {/* 视频预览：进入视口附近才挂载，避免一次性触发上百个视频与缩略图抽帧请求。
          竖屏视频用更高的预览区并以高度定宽居中，避免 9:16 画面被压得过小 */}
      <div
        ref={containerRef}
        className={cn(
          'group relative flex items-center justify-center overflow-hidden bg-black/70',
          portrait ? PORTRAIT_VIDEO_HEIGHT : 'h-52',
        )}
      >
        {inView ? (
          <video
            src={shotReviewItemFileUrl(item.id)}
            poster={item.thumbnail_url ? shotReviewItemThumbnailUrl(item.id) : undefined}
            controls
            preload="none"
            className={portrait ? 'h-full w-auto max-w-full' : 'max-h-full max-w-full'}
          />
        ) : (
          <span className="text-xs text-fg-muted">滚动到此加载预览</span>
        )}
        <button
          type="button"
          onClick={onOpen}
          className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-btn bg-black/50 text-white opacity-0 transition-opacity hover:bg-black/70 group-hover:opacity-100"
          aria-label="全屏预览"
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </button>
        {item.selected && (
          <span className="absolute left-2 top-2 flex items-center gap-1 rounded-btn bg-success px-1.5 py-0.5 text-[11px] font-medium text-white">
            <BadgeCheck className="h-3 w-3" />
            已选定保留
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-2 p-3">
        {/* 标题行 */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <Badge variant="outline" className="shrink-0 font-mono">
                {item.shot_id}
              </Badge>
              {item.episode && !item.shot_id.startsWith(item.episode) && (
                <span className="text-xs font-medium text-fg-secondary">{item.episode}</span>
              )}
            </div>
            <p className="mt-1 line-clamp-2 text-xs text-fg-secondary" title={item.shot_function ?? ''}>
              {item.shot_function ?? '未关联分镜信息'}
            </p>
          </div>
          <Badge variant={meta.variant} className="shrink-0 whitespace-nowrap">
            {meta.label}
          </Badge>
        </div>

        {/* 应有 vs 实际 */}
        <div className="space-y-1 rounded-btn bg-bg-tertiary/60 px-2.5 py-2 text-[11px]">
          <MetaRow label="时长" expected={fmtSec(item.script_duration)} actual={fmtSec(item.duration)} />
          <MetaRow label="景别" expected={item.shot_size} actual={null} />
          <MetaRow label="运镜" expected={item.movement} actual={null} />
          {item.dialogue && <MetaRow label="台词" expected={item.dialogue} actual={null} />}
          <MetaRow
            label="生成"
            expected={item.render_status}
            actual={item.model}
            raw
          />
        </div>

        {/* 评分 */}
        <ScoreEditor score={item.score} onScoreChange={onScoreChange} onClearScore={onClearScore} />

        {/* 修改意见 */}
        <FeedbackEditor feedback={item.feedback} onFeedbackChange={onFeedbackChange} />

        {/* 精修提示词：直接改写该镜的 AIGC 提示词，作为可执行的修改备注 */}
        <div className="flex items-start gap-1">
          <button
            type="button"
            onClick={() => setPromptOpen(true)}
            className="flex min-h-[28px] min-w-0 flex-1 items-start gap-1.5 rounded-btn px-1.5 py-1 text-left text-xs text-fg-secondary transition-colors hover:bg-bg-tertiary"
          >
            <Wand2 className="mt-0.5 h-3 w-3 shrink-0 text-fg-muted" />
            {item.revised_prompt ? (
              <span className="line-clamp-2 whitespace-pre-wrap">{item.revised_prompt}</span>
            ) : (
              <span className="text-fg-muted">填写精修提示词，作为可直接执行的修改备注…</span>
            )}
          </button>
          {item.revised_prompt && (
            <button
              type="button"
              onClick={handleCopyPrompt}
              className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-btn text-fg-muted transition-colors hover:bg-bg-tertiary hover:text-fg-primary"
              aria-label="复制精修提示词"
              title="复制精修提示词"
            >
              {copiedPrompt ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          )}
        </div>

        {/* 底部信息 */}
        <div className="mt-auto flex items-center justify-between gap-2 pt-1 text-[11px] tabular-nums text-fg-muted">
          <span className="truncate" title={item.file_name}>
            {item.file_name}
          </span>
          <span className="shrink-0">
            {formatFileSize(item.file_size)}
            {item.width && item.height ? ` · ${item.width}×${item.height}` : ''}
          </span>
        </div>
      </div>

      <PromptEditDialog
        item={item}
        open={promptOpen}
        onOpenChange={setPromptOpen}
        onSave={onPromptSave}
      />
    </div>
  )
}

function MetaRow({
  label,
  expected,
  actual,
  raw = false,
}: {
  label: string
  expected: string | null
  actual: string | null
  raw?: boolean
}) {
  if (!expected && !actual) return null
  const mismatch =
    !raw && expected != null && actual != null && expected !== actual
  return (
    <div className="flex items-start gap-2">
      <span className="w-8 shrink-0 text-fg-muted">{label}</span>
      <span className="min-w-0 flex-1 truncate text-fg-secondary" title={expected ?? undefined}>
        {expected ?? '--'}
      </span>
      {actual != null && (
        <>
          <span className="shrink-0 text-fg-muted">→</span>
          <span
            className={cn('shrink-0 tabular-nums', mismatch ? 'text-warning' : 'text-fg-secondary')}
            title={actual}
          >
            {actual}
          </span>
        </>
      )}
      {mismatch && <span className="shrink-0 text-warning">≠</span>}
    </div>
  )
}

function fmtSec(value: number | null): string | null {
  if (value == null) return null
  return `${value.toFixed(1)}s`
}
