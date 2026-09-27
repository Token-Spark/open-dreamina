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
import { Check, MessageSquare, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { cn } from '@/lib/utils'

const SCORE_PRESETS = [50, 60, 70, 80, 90]

/** 元素接近视口时返回 true（一次性，触发后即断开观察）。 */
export function useInView<T extends HTMLElement>(rootMargin = '300px') {
  const ref = useRef<T | null>(null)
  const [inView, setInView] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el || inView) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return
        setInView(true)
        observer.disconnect()
      },
      { rootMargin },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [inView, rootMargin])

  return [ref, inView] as const
}

/** 评分编辑器：数字输入 + 快捷档位 + 清除；完整卡片与多版本卡片共用。 */
export function ScoreEditor({
  score,
  onScoreChange,
  onClearScore,
}: {
  score: number | null
  onScoreChange: (score: number) => void
  onClearScore: () => void
}) {
  const [draftScore, setDraftScore] = useState(score == null ? '' : String(score))

  useEffect(() => {
    setDraftScore(score == null ? '' : String(score))
  }, [score])

  function commitScore() {
    const raw = draftScore.trim()
    if (raw === '') {
      if (score != null) onClearScore()
      return
    }
    const parsed = Number(raw)
    if (Number.isNaN(parsed)) {
      setDraftScore(score == null ? '' : String(score))
      return
    }
    const clamped = Math.max(0, Math.min(100, Math.round(parsed)))
    setDraftScore(String(clamped))
    if (clamped !== score) onScoreChange(clamped)
  }

  return (
    <div className="flex items-center gap-2">
      <span className="shrink-0 text-xs text-fg-muted">评分</span>
      <Input
        value={draftScore}
        onChange={(e) => setDraftScore(e.target.value)}
        onBlur={commitScore}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
        }}
        inputMode="numeric"
        placeholder="--"
        className="h-7 w-14 px-2 text-center text-sm tabular-nums"
      />
      <div className="flex flex-wrap items-center gap-1">
        {SCORE_PRESETS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onScoreChange(s)}
            className={cn(
              'rounded-btn border px-1.5 py-0.5 text-[11px] tabular-nums transition-all',
              score === s
                ? 'border-accent bg-accent/10 text-fg-primary'
                : 'border-border text-fg-muted hover:bg-bg-tertiary hover:text-fg-secondary',
            )}
          >
            {s}
          </button>
        ))}
      </div>
      {score != null && (
        <button
          type="button"
          onClick={onClearScore}
          className="ml-auto flex h-6 w-6 shrink-0 items-center justify-center rounded-btn text-fg-muted transition-colors hover:bg-bg-tertiary hover:text-fg-primary"
          aria-label="清除评分"
        >
          <RotateCcw className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  )
}

/** 修改意见编辑器：点击展开输入，失焦/保存提交；完整卡片与多版本卡片共用。 */
export function FeedbackEditor({
  feedback,
  onFeedbackChange,
}: {
  feedback: string
  onFeedbackChange: (feedback: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(feedback)

  useEffect(() => {
    if (!editing) setDraft(feedback)
  }, [feedback, editing])

  function save() {
    setEditing(false)
    if (draft !== feedback) onFeedbackChange(draft)
  }

  if (editing) {
    return (
      <div className="space-y-1.5">
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="输入修改意见，如：面部崩坏 / 运镜过快 / 与分镜不符…"
          rows={2}
          className="text-xs"
          autoFocus
        />
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="primary" onClick={save} className="h-6 px-2 text-xs">
            <Check className="h-3 w-3" />
            保存
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setEditing(false)
              setDraft(feedback)
            }}
            className="h-6 px-2 text-xs"
          >
            取消
          </Button>
        </div>
      </div>
    )
  }

  return (
    <button
      type="button"
      onClick={() => {
        setDraft(feedback)
        setEditing(true)
      }}
      className="flex min-h-[28px] items-start gap-1.5 rounded-btn px-1.5 py-1 text-left text-xs text-fg-secondary transition-colors hover:bg-bg-tertiary"
    >
      <MessageSquare className="mt-0.5 h-3 w-3 shrink-0 text-fg-muted" />
      {feedback ? (
        <span className="line-clamp-2 whitespace-pre-wrap">{feedback}</span>
      ) : (
        <span className="text-fg-muted">点击添加修改意见…</span>
      )}
    </button>
  )
}
