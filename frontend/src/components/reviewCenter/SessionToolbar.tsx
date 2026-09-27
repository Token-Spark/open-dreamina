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

import type { ReactNode } from 'react'
import { CheckCircle2, FolderOpen, RefreshCw, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

/** 会话工具栏：标题 + 目录路径 + 操作按钮，children 渲染统计行。 */
export function SessionToolbar({
  title,
  path,
  completed,
  rescanPending,
  onRescan,
  onToggleStatus,
  onDelete,
  children,
}: {
  title: string
  path: string
  completed: boolean
  rescanPending: boolean
  onRescan: () => void
  onToggleStatus: () => void
  onDelete: () => void
  children?: ReactNode
}) {
  return (
    <div className="mb-4 rounded-card border border-border bg-bg-secondary p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-base font-semibold text-fg-primary">{title}</h2>
          <div className="mt-1 flex items-center gap-1.5 text-xs text-fg-muted">
            <FolderOpen className="h-3 w-3 shrink-0" />
            <span className="truncate">{path}</span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button variant="outline" size="sm" onClick={onRescan} disabled={rescanPending}>
            <RefreshCw className={cn('h-3.5 w-3.5', rescanPending && 'animate-spin')} />
            重新扫描
          </Button>
          {completed ? (
            <Button variant="outline" size="sm" onClick={onToggleStatus}>
              重新开启
            </Button>
          ) : (
            <Button variant="outline" size="sm" onClick={onToggleStatus}>
              <CheckCircle2 className="h-3.5 w-3.5" />
              标记完成
            </Button>
          )}
          <Button variant="danger" size="sm" onClick={onDelete}>
            <Trash2 className="h-3.5 w-3.5" />
            删除
          </Button>
        </div>
      </div>
      {children && (
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs tabular-nums">
          {children}
        </div>
      )}
    </div>
  )
}
