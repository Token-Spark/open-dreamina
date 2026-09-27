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
import { BadgeCheck, Check, Maximize2, Trash2, Wand2 } from 'lucide-react'
import type { ShotReviewItem } from '@/api/shotReviews'
import {
  shotReviewItemFileUrl,
  shotReviewItemThumbnailUrl,
} from '@/api/shotReviews'
import { VERDICT_META, isPortraitItem } from '@/components/shotReview/ShotReviewCard'
import { PromptEditDialog } from '@/components/shotReview/PromptEditDialog'
import { FeedbackEditor, ScoreEditor, useInView } from '@/components/shotReview/ShotReviewEditors'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { cn, formatFileSize } from '@/lib/utils'

/**
 * 多版本栏目内的紧凑镜头卡片：与完整卡片（ShotReviewCard）相比省略
 * 「应有 vs 实际」分镜对照——同镜号各版本该信息完全一致，在栏目头部统一展示。
 */
export interface ShotTakeCardProps {
  item: ShotReviewItem
  /** 组内版本序号（1 起），用于「版本 N」标识。 */
  index: number
  onScoreChange: (score: number) => void
  onClearScore: () => void
  onFeedbackChange: (feedback: string) => void
  onPromptSave: (revisedPrompt: string) => void
  onSelect: () => void
  onDeselect: () => void
  onDelete: () => void
  onOpen: () => void
}

export function ShotTakeCard({
  item,
  index,
  onScoreChange,
  onClearScore,
  onFeedbackChange,
  onPromptSave,
  onSelect,
  onDeselect,
  onDelete,
  onOpen,
}: ShotTakeCardProps) {
  const [promptOpen, setPromptOpen] = useState(false)
  const [containerRef, inView] = useInView<HTMLDivElement>('200px')
  const meta = VERDICT_META[item.verdict]
  const portrait = isPortraitItem(item)
  const copiedTimer = useRef<number | null>(null)

  useEffect(
    () => () => {
      if (copiedTimer.current != null) window.clearTimeout(copiedTimer.current)
    },
    [],
  )

  return (
    <div
      className={cn(
        'flex flex-col overflow-hidden rounded-card border bg-bg-secondary transition-all',
        item.selected
          ? 'border-success/60 ring-2 ring-success/40'
          : 'border-border',
      )}
    >
      {/* 视频预览：进入视口附近才挂载；竖屏视频抬高预览区，按高度定宽居中 */}
      <div
        ref={containerRef}
        className={cn(
          'group relative flex items-center justify-center overflow-hidden bg-black/70',
          portrait ? 'h-[380px]' : 'h-44',
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

      <div className="flex flex-1 flex-col gap-2 p-2.5">
        {/* 版本标识 + 档位：徽章不折行，操作按钮空间不足时整体换行 */}
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" className="shrink-0 whitespace-nowrap font-mono">
            版本 {index}
          </Badge>
          <Badge variant={meta.variant} className="shrink-0 whitespace-nowrap">
            {meta.label}
          </Badge>
          <div className="ml-auto flex items-center gap-1">
            {item.selected ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={onDeselect}
                className="h-6 gap-1 px-1.5 text-[11px] text-success hover:text-success"
                title="取消选定（该镜回到未选定状态）"
              >
                <BadgeCheck className="h-3.5 w-3.5" />
                取消选定
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={onSelect}
                className="h-6 gap-1 px-1.5 text-[11px]"
                title="选定为该镜保留版本（同镜其余版本自动取消选定）"
              >
                <Check className="h-3 w-3" />
                选定此版本
              </Button>
            )}
            <button
              type="button"
              onClick={onDelete}
              className="flex h-6 w-6 items-center justify-center rounded-btn text-fg-muted transition-colors hover:bg-error/10 hover:text-error"
              aria-label="删除该版本"
              title="删除该版本（可连同视频文件）"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        <div className="flex items-center justify-between gap-2 text-[11px] tabular-nums text-fg-muted">
          <span className="truncate" title={item.file_name}>
            {item.file_name}
          </span>
          <span className="shrink-0">
            {formatFileSize(item.file_size)}
            {item.duration != null ? ` · ${item.duration.toFixed(1)}s` : ''}
          </span>
        </div>

        <ScoreEditor score={item.score} onScoreChange={onScoreChange} onClearScore={onClearScore} />

        <FeedbackEditor feedback={item.feedback} onFeedbackChange={onFeedbackChange} />

        <button
          type="button"
          onClick={() => setPromptOpen(true)}
          className="flex min-h-[26px] items-start gap-1.5 rounded-btn px-1.5 py-1 text-left text-xs text-fg-secondary transition-colors hover:bg-bg-tertiary"
        >
          <Wand2 className="mt-0.5 h-3 w-3 shrink-0 text-fg-muted" />
          {item.revised_prompt ? (
            <span className="line-clamp-1 whitespace-pre-wrap">{item.revised_prompt}</span>
          ) : (
            <span className="text-fg-muted">填写精修提示词…</span>
          )}
        </button>
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
