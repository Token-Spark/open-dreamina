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
import {
  BadgeCheck,
  BookOpen,
  Check,
  Clock,
  Columns2,
  Copy,
  Film,
  Focus,
  Image as ImageIcon,
  Layers,
  Loader2,
  Maximize2,
  Pencil,
  RefreshCw,
  Trash2,
  TriangleAlert,
  Wand2,
  X,
} from 'lucide-react'
import type {
  ShotRegenerationPayload,
  ShotReviewItem,
  ShotReviewRegeneration,
} from '@/api/shotReviews'
import { shotReviewItemFileUrl, shotReviewItemThumbnailUrl } from '@/api/shotReviews'
import { RegenerateComposer } from '@/components/reviewCenter/RegenerateComposer'
import { VERDICT_META, isPortraitItem } from '@/components/shotReview/ShotReviewCard'
import { FeedbackEditor, ScoreEditor } from '@/components/shotReview/ShotReviewEditors'
import { copyText } from '@/components/shotReview/PromptEditDialog'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { isActiveRegeneration } from '@/hooks/useShotReviews'
import { useTaskSSE } from '@/hooks/useTaskSSE'
import { cn, formatFileSize } from '@/lib/utils'

/**
 * 审阅中心的任务卡片。
 *
 * 以「一次生成任务的结果」为单位组织待审内容：卡片顶部是内容类型 / 剧目 / 剧集 /
 * 镜头等标签，左侧即时预览成片，右侧是可直接改写并复用的提示词，底部是打分与意见。
 * 对不满意的镜头，无需回创作页重建上下文——在卡片内展开返工面板（复用创作页生成模块）
 * 改完提示词即可重新生成，结果回到同一张卡片上，采用后成为该镜的新版本。
 */
export interface ReviewTaskCardProps {
  item: ShotReviewItem
  /** 同镜号版本序号（1 起）与总数，用于标注「版本 2 / 共 3 版」。 */
  versionIndex: number
  versionCount: number
  /** 该条目最近一次返工记录（进行中 / 已完成待采用 / 已采用）。 */
  regeneration: ShotReviewRegeneration | null
  regenerationSubmitting: boolean
  atConcurrencyLimit: boolean
  /** 提交返工生成；抛错表示提交失败（面板保留，便于调整后重试）。 */
  onRegenerate: (payload: ShotRegenerationPayload) => Promise<void>
  onAdopt: (regen: ShotReviewRegeneration) => void
  onDiscard: (regen: ShotReviewRegeneration) => void
  /** 返工任务进入终态后刷新返工记录（后端会同步任务状态与结果资产）。 */
  onRegenerationSettled: () => void
  onScoreChange: (score: number) => void
  onClearScore: () => void
  onFeedbackChange: (feedback: string) => void
  onPromptSave: (revisedPrompt: string) => void
  onSelect: () => void
  onDeselect: () => void
  onDelete: () => void
  onCompare: () => void
  onOpen: () => void
}

export function ReviewTaskCard({
  item,
  versionIndex,
  versionCount,
  regeneration,
  regenerationSubmitting,
  atConcurrencyLimit,
  onRegenerate,
  onAdopt,
  onDiscard,
  onRegenerationSettled,
  onScoreChange,
  onClearScore,
  onFeedbackChange,
  onPromptSave,
  onSelect,
  onDeselect,
  onDelete,
  onCompare,
  onOpen,
}: ReviewTaskCardProps) {
  const [composerOpen, setComposerOpen] = useState(false)
  const [editingPrompt, setEditingPrompt] = useState(false)
  const [promptDraft, setPromptDraft] = useState('')
  const [showSource, setShowSource] = useState(false)
  const [copied, setCopied] = useState(false)
  const copiedTimer = useRef<number | null>(null)

  const isVideo = item.content_type === 'video'
  const portrait = isPortraitItem(item)
  const verdict = VERDICT_META[item.verdict]
  const currentPrompt = item.revised_prompt || item.source_prompt || ''
  const hasSource = !!item.source_prompt && item.source_prompt !== item.revised_prompt
  const multiVersion = versionCount > 1

  // 在途返工：订阅任务直播进度，终态时让上层刷新返工记录（拉回结果资产）
  const activeTaskId =
    regeneration && isActiveRegeneration(regeneration) ? regeneration.task_id : null
  const sse = useTaskSSE(activeTaskId, {
    onComplete: onRegenerationSettled,
    onFailed: onRegenerationSettled,
  })
  const regenerating = !!activeTaskId
  const progress = regenerating ? (sse.status ? sse.progress : regeneration?.progress ?? 0) : 0

  useEffect(
    () => () => {
      if (copiedTimer.current != null) window.clearTimeout(copiedTimer.current)
    },
    [],
  )

  function startEditPrompt() {
    setPromptDraft(currentPrompt)
    setEditingPrompt(true)
  }

  function savePrompt() {
    setEditingPrompt(false)
    const next = promptDraft.trim()
    if (next !== (item.revised_prompt ?? '')) onPromptSave(next)
  }

  async function handleCopy() {
    if (!currentPrompt) return
    if (await copyText(currentPrompt)) {
      setCopied(true)
      if (copiedTimer.current != null) window.clearTimeout(copiedTimer.current)
      copiedTimer.current = window.setTimeout(() => setCopied(false), 1500)
    }
  }

  /** 提交返工：成功即收起面板（进度转由返工条展示），失败保留面板便于调整重试。 */
  async function submitRegeneration(payload: ShotRegenerationPayload) {
    try {
      await onRegenerate(payload)
      setComposerOpen(false)
    } catch {
      /* 错误提示由上层统一 toast，这里只保留面板 */
    }
  }

  /** 返工结果条：进行中显示进度，完成后提供「采用为新版本」入口。 */
  function renderRegenerationStrip() {
    if (!regeneration) return null
    const { status, adopted_item_id: adopted } = regeneration

    if (adopted) {
      return (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-btn border border-success/30 bg-success/5 px-2.5 py-2 text-xs text-success">
          <BadgeCheck className="h-3.5 w-3.5" />
          该返工结果已采用为新版本，可在版本列表里切换评分与选定
        </div>
      )
    }

    if (status === 'pending' || status === 'queued' || status === 'running') {
      return (
        <div className="mt-3 rounded-btn border border-border bg-bg-tertiary/40 px-2.5 py-2">
          <div className="flex items-center gap-2 text-xs text-fg-secondary">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />
            <span className="font-medium">返工生成中</span>
            <span className="tabular-nums text-fg-muted">{progress}%</span>
            <span className="ml-auto text-fg-muted">
              {regeneration.model_id ?? regeneration.provider ?? ''}
            </span>
          </div>
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-border">
            <div
              className="h-full rounded-full bg-accent transition-all duration-500"
              style={{ width: `${Math.min(100, Math.max(3, progress))}%` }}
            />
          </div>
        </div>
      )
    }

    if (status === 'failed' || status === 'cancelled') {
      return (
        <div className="mt-3 rounded-btn border border-error/30 bg-error/5 px-2.5 py-2 text-xs text-error">
          <div className="flex items-start gap-1.5">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="min-w-0 flex-1 break-words">
              返工生成失败：{regeneration.error_msg || '未知错误'}
            </span>
          </div>
          <div className="mt-2 flex gap-1.5">
            <Button size="sm" variant="outline" className="h-6 px-2 text-[11px]" onClick={() => setComposerOpen(true)}>
              <RefreshCw className="h-3 w-3" />
              调整后重试
            </Button>
            <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={() => onDiscard(regeneration)}>
              忽略
            </Button>
          </div>
        </div>
      )
    }

    if (status === 'completed' && regeneration.result_url) {
      return (
        <div className="mt-3 flex flex-col gap-2 rounded-btn border border-accent/40 bg-accent/5 p-2 sm:flex-row sm:items-center">
          <div className="h-24 w-40 shrink-0 overflow-hidden rounded-btn bg-black/70">
            {isVideo ? (
              <video
                src={regeneration.result_url}
                controls
                preload="metadata"
                className="h-full w-full object-contain"
              />
            ) : (
              <img src={regeneration.result_url} alt="返工结果" className="h-full w-full object-contain" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-fg-primary">返工结果已生成（尚未进入审片列表）</p>
            <p className="mt-0.5 line-clamp-2 text-[11px] text-fg-muted" title={regeneration.prompt}>
              {regeneration.prompt}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Button size="sm" variant="primary" className="h-6 px-2 text-[11px]" onClick={() => onAdopt(regeneration)}>
                <Check className="h-3 w-3" />
                采用为新版本
              </Button>
              <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={() => onDiscard(regeneration)}>
                <X className="h-3 w-3" />
                放弃本次结果
              </Button>
            </div>
          </div>
        </div>
      )
    }

    return null
  }

  return (
    <article
      className={cn(
        'flex flex-col overflow-hidden rounded-card border bg-bg-secondary transition-all',
        item.selected ? 'border-success/50 ring-2 ring-success/30' : 'border-border',
        item.origin === 'regen' && !item.selected && 'border-accent/30',
      )}
    >
      {/* 标签行：内容类型 / 剧目 / 剧集 / 镜头 / 版本 */}
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1.5 border-b border-border bg-bg-primary/30 px-3 py-2">
        <Badge variant="outline" className="gap-1">
          {isVideo ? <Film className="h-3 w-3" /> : <ImageIcon className="h-3 w-3" />}
          {isVideo ? '视频' : '图片'}
        </Badge>
        <span className="flex min-w-0 items-center gap-1 text-xs font-medium text-fg-primary">
          <BookOpen className="h-3 w-3 shrink-0 text-fg-muted" />
          <span className="truncate" title={item.drama_title ?? undefined}>
            {item.drama_title || '未标注剧目'}
          </span>
        </span>
        <Badge variant="outline" className="gap-1">
          <Layers className="h-3 w-3" />
          {item.episode ?? '未分集'}
        </Badge>
        <Badge variant="default" className="gap-1 font-mono">
          <Focus className="h-3 w-3" />
          {item.shot_id}
        </Badge>
        {multiVersion && (
          <span className="text-[11px] tabular-nums text-fg-muted">
            版本 {versionIndex} / 共 {versionCount} 版
          </span>
        )}
        {item.origin === 'regen' && (
          <Badge variant="success" className="gap-1">
            <Wand2 className="h-3 w-3" />
            返工版
          </Badge>
        )}
        <div className="ml-auto flex items-center gap-1.5">
          {multiVersion && (
            <button
              type="button"
              onClick={onCompare}
              className="flex items-center gap-1 rounded-btn px-1.5 py-0.5 text-[11px] text-fg-muted transition-colors hover:bg-bg-tertiary hover:text-fg-primary"
              title="并排对比同镜号的多个版本"
            >
              <Columns2 className="h-3 w-3" />
              对比
            </button>
          )}
          {item.selected && (
            <Badge variant="success" className="gap-1">
              <BadgeCheck className="h-3 w-3" />
              已选定
            </Badge>
          )}
          <Badge variant={verdict.variant}>{verdict.label}</Badge>
        </div>
      </header>

      <div className="flex flex-col gap-3 p-3 xl:flex-row">
        {/* 生成结果预览：进入视口附近才挂载媒体，避免整页几十条同时加载 */}
        <div
          className={cn(
            'group relative flex shrink-0 items-center justify-center overflow-hidden rounded-btn bg-black/75 xl:w-[260px]',
            portrait ? 'h-[320px]' : 'h-[200px]',
          )}
        >
          {isVideo ? (
            <video
              src={shotReviewItemFileUrl(item.id)}
              poster={item.thumbnail_url ? shotReviewItemThumbnailUrl(item.id) : undefined}
              controls
              preload="none"
              className="max-h-full max-w-full"
            />
          ) : (
            <img
              src={shotReviewItemFileUrl(item.id)}
              alt={`${item.shot_id} 生成结果`}
              loading="lazy"
              className="max-h-full max-w-full object-contain"
            />
          )}
          <button
            type="button"
            onClick={onOpen}
            className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-btn bg-black/50 text-white opacity-0 transition-opacity hover:bg-black/70 group-hover:opacity-100"
            aria-label="全屏预览"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* 任务信息 + 提示词 */}
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-fg-muted">
            {item.duration != null && (
              <span className="flex items-center gap-1 tabular-nums">
                <Clock className="h-3 w-3" />
                {item.duration.toFixed(1)}s
                {item.script_duration != null && ` / 脚本 ${item.script_duration}s`}
              </span>
            )}
            {item.width && item.height && (
              <span className="tabular-nums">
                {item.width}×{item.height}
              </span>
            )}
            {item.model && <span className="truncate">模型 {item.model}</span>}
            {item.file_size != null && <span className="tabular-nums">{formatFileSize(item.file_size)}</span>}
            {item.render_status && <span>生成状态 {item.render_status}</span>}
          </div>

          {item.shot_function && (
            <p className="line-clamp-2 text-xs text-fg-secondary" title={item.shot_function}>
              <span className="text-fg-muted">镜头功能 </span>
              {item.shot_function}
            </p>
          )}

          {/* 提示词：即时可见、可直接改写；改写后可一键回到生成 */}
          <div className="rounded-btn border border-border/70 bg-bg-primary/40">
            <div className="flex items-center gap-1.5 border-b border-border/60 px-2 py-1">
              <Wand2 className="h-3 w-3 text-fg-muted" />
              <span className="text-[11px] font-medium text-fg-secondary">
                {item.revised_prompt ? '精修提示词' : '提示词底稿'}
              </span>
              {!currentPrompt && <span className="text-[11px] text-fg-muted">（该镜无提示词）</span>}
              <div className="ml-auto flex items-center gap-0.5">
                {hasSource && (
                  <button
                    type="button"
                    onClick={() => setShowSource((v) => !v)}
                    className={cn(
                      'rounded-btn px-1.5 py-0.5 text-[11px] transition-colors hover:bg-bg-tertiary',
                      showSource ? 'text-fg-primary' : 'text-fg-muted',
                    )}
                    title="查看分镜底稿原文"
                  >
                    底稿
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleCopy}
                  disabled={!currentPrompt}
                  className="flex h-6 w-6 items-center justify-center rounded-btn text-fg-muted transition-colors hover:bg-bg-tertiary hover:text-fg-primary disabled:opacity-40"
                  aria-label="复制提示词"
                >
                  {copied ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
                </button>
                {!editingPrompt && (
                  <button
                    type="button"
                    onClick={startEditPrompt}
                    className="flex h-6 w-6 items-center justify-center rounded-btn text-fg-muted transition-colors hover:bg-bg-tertiary hover:text-fg-primary"
                    aria-label="编辑提示词"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>

            {editingPrompt ? (
              <div className="space-y-1.5 p-2">
                <textarea
                  value={promptDraft}
                  onChange={(e) => setPromptDraft(e.target.value)}
                  rows={4}
                  autoFocus
                  placeholder="改写提示词：补人物外观、场景锚点、动作与光感，或修正崩坏点…"
                  className="w-full resize-y rounded-btn border border-border bg-bg-secondary p-2 text-xs leading-relaxed text-fg-primary placeholder:text-fg-muted focus-visible:border-accent/60 focus-visible:outline-none scrollbar-thin"
                />
                <div className="flex items-center gap-1.5">
                  <Button size="sm" variant="primary" className="h-6 px-2 text-[11px]" onClick={savePrompt}>
                    <Check className="h-3 w-3" />
                    保存提示词
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 px-2 text-[11px]"
                    onClick={() => {
                      setEditingPrompt(false)
                      setPromptDraft('')
                    }}
                  >
                    取消
                  </Button>
                  <span className="ml-auto text-[11px] text-fg-muted">仅保存为修改备注，不触发生成</span>
                </div>
              </div>
            ) : (
              <div className="px-2 py-1.5">
                <p
                  className={cn(
                    'max-h-24 overflow-y-auto whitespace-pre-wrap break-words text-xs leading-relaxed scrollbar-thin',
                    currentPrompt ? 'text-fg-secondary' : 'text-fg-muted',
                  )}
                >
                  {currentPrompt || '尚未关联提示词，可直接编辑补写后用于返工生成'}
                </p>
                {showSource && hasSource && (
                  <p className="mt-1.5 max-h-28 overflow-y-auto whitespace-pre-wrap break-words border-t border-dashed border-border pt-1.5 text-[11px] leading-relaxed text-fg-muted scrollbar-thin">
                    {item.source_prompt}
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <Button
              size="sm"
              variant={composerOpen ? 'outline' : 'primary'}
              onClick={() => setComposerOpen((v) => !v)}
              disabled={regenerating}
              className="h-7 gap-1 px-2.5 text-xs"
              title="在卡片内改提示词并重新生成，结果作为该镜新版本"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              {composerOpen ? '收起返工面板' : '改提示词并重新生成'}
            </Button>
            {item.dialogue && (
              <span className="truncate text-[11px] text-fg-muted" title={item.dialogue}>
                台词：{item.dialogue}
              </span>
            )}
            <div className="ml-auto flex items-center gap-1">
              {item.selected ? (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={onDeselect}
                  className="h-7 gap-1 px-2 text-[11px] text-success hover:text-success"
                  title="取消选定（该镜回到未选定状态）"
                >
                  <BadgeCheck className="h-3.5 w-3.5" />
                  取消选定
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onSelect}
                  className="h-7 gap-1 px-2 text-[11px]"
                  title="选定为该镜保留版本（同镜其余版本自动取消选定）"
                >
                  <Check className="h-3 w-3" />
                  选定此版本
                </Button>
              )}
              <button
                type="button"
                onClick={onDelete}
                className="flex h-7 w-7 items-center justify-center rounded-btn text-fg-muted transition-colors hover:bg-error/10 hover:text-error"
                aria-label="删除该版本"
                title="删除该版本（可连同文件）"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 返工结果 / 进度 */}
      <div className="px-3">{renderRegenerationStrip()}</div>

      {/* 卡片内返工生成面板：复用创作页生成模块 */}
      {composerOpen && (
        <div className="px-3">
          <RegenerateComposer
            key={`${item.id}-${item.revised_prompt ?? ''}`}
            item={item}
            submitting={regenerationSubmitting}
            atConcurrencyLimit={atConcurrencyLimit}
            onSubmit={(payload) => void submitRegeneration(payload)}
            onClose={() => setComposerOpen(false)}
          />
        </div>
      )}

      {/* 审阅结论 */}
      <footer className="mt-3 flex flex-col gap-1.5 border-t border-border px-3 py-2">
        <ScoreEditor score={item.score} onScoreChange={onScoreChange} onClearScore={onClearScore} />
        <FeedbackEditor feedback={item.feedback} onFeedbackChange={onFeedbackChange} />
      </footer>
    </article>
  )
}
