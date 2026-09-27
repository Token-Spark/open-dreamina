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

import { FolderOpen, Loader2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { cn, formatRelativeTime } from '@/lib/utils'

/** 会话列表条目的统一视图模型，由素材 / 镜头面板各自映射生成。 */
export interface SessionListItem {
  id: string
  title: string
  /** 目录末段展示名 */
  pathLabel: string
  completed: boolean
  /** 主统计，如「12 个文件」 */
  statPrimary: string
  /** 次统计，如「5 已审」 */
  statSecondary?: string
  updatedAt: string
}

/** 左侧会话列表：素材审阅与镜头审片共用同一套卡片样式。 */
export function SessionListPanel({
  items,
  isLoading,
  selectedId,
  onSelect,
  emptyIcon: EmptyIcon,
  emptyTitle,
  emptyHint,
}: {
  items: SessionListItem[] | undefined
  isLoading: boolean
  selectedId: string | null
  onSelect: (id: string) => void
  emptyIcon: LucideIcon
  emptyTitle: string
  emptyHint: string
}) {
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-fg-muted">
        <Loader2 className="h-4 w-4 animate-spin" />
        加载中…
      </div>
    )
  }

  if (!items || items.length === 0) {
    return (
      <div className="rounded-card border border-dashed border-border p-8 text-center">
        <EmptyIcon className="mx-auto mb-2 h-8 w-8 text-fg-muted" />
        <p className="text-sm font-medium text-fg-secondary">{emptyTitle}</p>
        <p className="mt-1 text-xs text-fg-muted">{emptyHint}</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {items.map((s) => (
        <button
          key={s.id}
          type="button"
          onClick={() => onSelect(s.id)}
          className={cn(
            'w-full rounded-card border p-3 text-left transition-all',
            selectedId === s.id
              ? 'border-accent bg-bg-tertiary ring-1 ring-accent/30'
              : 'border-border bg-bg-secondary hover:bg-bg-tertiary',
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-sm font-medium text-fg-primary">{s.title}</span>
            {s.completed && <Badge variant="success">已完成</Badge>}
          </div>
          <div className="mt-1 flex items-center gap-1 text-xs text-fg-muted">
            <FolderOpen className="h-3 w-3 shrink-0" />
            <span className="truncate">{s.pathLabel}</span>
          </div>
          <div className="mt-1.5 flex items-center gap-2 text-xs tabular-nums text-fg-muted">
            <span>{s.statPrimary}</span>
            {s.statSecondary && (
              <>
                <span>·</span>
                <span>{s.statSecondary}</span>
              </>
            )}
            <span>·</span>
            <span>{formatRelativeTime(s.updatedAt)}</span>
          </div>
        </button>
      ))}
    </div>
  )
}
