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

import { useState, useEffect } from 'react'
import {
  Check,
  Download,
  MessageSquare,
  Play,
  X,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react'
import type { ReviewItem, ReviewStatus } from '@/api/reviews'
import { reviewItemFileUrl, reviewItemThumbnailUrl } from '@/api/reviews'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/Textarea'
import { cn, formatFileSize, formatRelativeTime } from '@/lib/utils'

export const STATUS_META: Record<
  ReviewStatus,
  { label: string; variant: 'default' | 'success' | 'error' | 'warning' }
> = {
  pending: { label: '待审', variant: 'default' },
  approved: { label: '通过', variant: 'success' },
  rejected: { label: '驳回', variant: 'error' },
  needs_revision: { label: '需修改', variant: 'warning' },
}

export interface ReviewItemCardProps {
  item: ReviewItem
  index: number
  onStatusChange: (status: ReviewStatus) => void
  onFeedbackChange: (feedback: string) => void
  onOpen: () => void
}

export function ReviewItemCard({
  item,
  index,
  onStatusChange,
  onFeedbackChange,
  onOpen,
}: ReviewItemCardProps) {
  const [editingFeedback, setEditingFeedback] = useState(false)
  const [draftFeedback, setDraftFeedback] = useState(item.feedback)
  const isVideo = item.mime_type?.startsWith('video/') ?? false

  // 同步外部数据更新到本地草稿（非编辑状态下）
  useEffect(() => {
    if (!editingFeedback) {
      setDraftFeedback(item.feedback)
    }
  }, [item.feedback, editingFeedback])

  function startEdit() {
    setDraftFeedback(item.feedback)
    setEditingFeedback(true)
  }

  function saveFeedback() {
    setEditingFeedback(false)
    if (draftFeedback !== item.feedback) {
      onFeedbackChange(draftFeedback)
    }
  }

  function cancelEdit() {
    setEditingFeedback(false)
    setDraftFeedback(item.feedback)
  }

  const meta = STATUS_META[item.status]

  return (
    <div
      className={cn(
        'group flex gap-3 rounded-card border border-border bg-bg-secondary p-3 transition-all',
        item.status !== 'pending' && 'ring-1',
        item.status === 'approved' && 'ring-success/20',
        item.status === 'rejected' && 'ring-error/20',
        item.status === 'needs_revision' && 'ring-warning/20',
      )}
    >
      {/* 序号 */}
      <div className="flex w-7 shrink-0 justify-center pt-1">
        <span className="text-xs font-medium tabular-nums text-fg-muted">
          {index + 1}
        </span>
      </div>

      {/* 缩略图 */}
      <button
        type="button"
        onClick={onOpen}
        className="relative h-20 w-20 shrink-0 overflow-hidden rounded-btn border border-border bg-bg-tertiary transition-transform hover:scale-[1.03]"
      >
        {item.thumbnail_url ? (
          <img
            src={reviewItemThumbnailUrl(item.id)}
            alt={item.file_name}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-fg-muted">
            {isVideo ? <Play className="h-5 w-5" /> : <AlertTriangle className="h-5 w-5" />}
          </div>
        )}
        {isVideo && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white/90 shadow">
              <Play className="h-3 w-3 translate-x-[0.5px] fill-black/80 text-black/80" />
            </span>
          </div>
        )}
      </button>

      {/* 主体内容 */}
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-fg-primary" title={item.file_path}>
              {item.file_name}
            </p>
            {item.file_path !== item.file_name && (
              <p className="truncate text-[11px] text-fg-muted" title={item.file_path}>
                {item.file_path}
              </p>
            )}
            <p className="mt-0.5 text-xs tabular-nums text-fg-muted">
              {formatFileSize(item.file_size)}
              {item.width && item.height ? ` · ${item.width}×${item.height}` : ''}
              {item.duration ? ` · ${item.duration.toFixed(1)}s` : ''}
              {' · '}
              {formatRelativeTime(item.created_at)}
            </p>
          </div>
          <Badge variant={meta.variant}>{meta.label}</Badge>
        </div>

        {/* 修改意见 */}
        {editingFeedback ? (
          <div className="space-y-1.5">
            <Textarea
              value={draftFeedback}
              onChange={(e) => setDraftFeedback(e.target.value)}
              placeholder="输入修改意见…"
              rows={2}
              className="text-xs"
            />
            <div className="flex items-center gap-1.5">
              <Button size="sm" variant="primary" onClick={saveFeedback} className="h-6 px-2 text-xs">
                <Check className="h-3 w-3" />
                保存
              </Button>
              <Button size="sm" variant="ghost" onClick={cancelEdit} className="h-6 px-2 text-xs">
                取消
              </Button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={startEdit}
            className="flex items-start gap-1.5 rounded-btn px-1.5 py-1 text-left text-xs text-fg-secondary transition-colors hover:bg-bg-tertiary min-h-[24px]"
          >
            <MessageSquare className="mt-0.5 h-3 w-3 shrink-0 text-fg-muted" />
            {item.feedback ? (
              <span className="line-clamp-2">{item.feedback}</span>
            ) : (
              <span className="text-fg-muted">点击添加修改意见…</span>
            )}
          </button>
        )}

        {/* 操作栏 */}
        <div className="mt-auto flex items-center gap-1 pt-0.5">
          <ActionButton
            active={item.status === 'approved'}
            icon={<Check className="h-3.5 w-3.5" />}
            label="通过"
            onClick={() => onStatusChange('approved')}
            activeClass="border-success/30 bg-success/10 text-success"
          />
          <ActionButton
            active={item.status === 'needs_revision'}
            icon={<RefreshCw className="h-3.5 w-3.5" />}
            label="需修改"
            onClick={() => onStatusChange('needs_revision')}
            activeClass="border-warning/30 bg-warning/10 text-warning"
          />
          <ActionButton
            active={item.status === 'rejected'}
            icon={<X className="h-3.5 w-3.5" />}
            label="驳回"
            onClick={() => onStatusChange('rejected')}
            activeClass="border-error/30 bg-error/10 text-error"
          />
          <ActionButton
            active={item.status === 'pending'}
            icon={<AlertTriangle className="h-3.5 w-3.5" />}
            label="待审"
            onClick={() => onStatusChange('pending')}
            activeClass="border-border bg-bg-tertiary text-fg-secondary"
          />
          <a
            href={reviewItemFileUrl(item.id)}
            download
            target="_blank"
            rel="noreferrer"
            className="ml-auto flex h-6 w-6 items-center justify-center rounded-btn text-fg-muted transition-colors hover:bg-bg-tertiary hover:text-fg-primary"
            aria-label="下载原文件"
          >
            <Download className="h-3.5 w-3.5" />
          </a>
        </div>
      </div>
    </div>
  )
}

function ActionButton({
  active,
  icon,
  label,
  onClick,
  activeClass,
}: {
  active: boolean
  icon: React.ReactNode
  label: string
  onClick: () => void
  activeClass: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center gap-1 rounded-btn border px-2 py-0.5 text-xs font-medium transition-all',
        active
          ? activeClass
          : 'border-transparent text-fg-muted hover:bg-bg-tertiary hover:text-fg-secondary',
      )}
    >
      {icon}
      {label}
    </button>
  )
}
