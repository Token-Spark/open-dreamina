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

import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, Loader2 } from 'lucide-react'
import type { TaskStatus, TaskType } from '@/api/tasks'
import { Badge } from '@/components/ui/Badge'
import { Progress } from '@/components/ui/Progress'
import { STATUS_LABEL, TASK_TYPE_LABEL, statusBadgeVariant } from '@/lib/taskStatus'
import { cn, estimateEta } from '@/lib/utils'

export interface TaskProgressCardProps {
  type: TaskType
  status: TaskStatus
  progress: number
  message?: string | null
  error?: string | null
  runningSince?: number | null
  className?: string
}

export function TaskProgressCard({
  type,
  status,
  progress,
  message,
  error,
  runningSince,
  className,
}: TaskProgressCardProps) {
  const running = status === 'running'
  // Tick once per second while running so the ETA stays live.
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!running) return
    const id = window.setInterval(() => setTick((t) => t + 1), 1000)
    return () => window.clearInterval(id)
  }, [running])

  const eta =
    running && runningSince && progress > 0
      ? estimateEta(progress, (Date.now() - runningSince) / 1000)
      : null

  return (
    <div
      className={cn(
        'rounded-card border border-border bg-bg-secondary p-4 space-y-3 animate-slide-up',
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {running && <Loader2 className="h-4 w-4 animate-spin text-fg-secondary" />}
          {status === 'completed' && <CheckCircle2 className="h-4 w-4 text-success" />}
          {status === 'failed' && <AlertCircle className="h-4 w-4 text-error" />}
          <span className="text-sm font-medium text-fg-primary">
            {TASK_TYPE_LABEL[type]}
          </span>
        </div>
        <Badge variant={statusBadgeVariant(status)}>{STATUS_LABEL[status]}</Badge>
      </div>

      {running && (
        <div className="space-y-1.5">
          <Progress value={progress} glow />
          <div className="flex items-center justify-between text-xs text-fg-muted">
            <span>{message ?? '生成中…'}</span>
            <span>
              {progress}%{eta ? ` · 预计剩余 ${eta}` : ''}
            </span>
          </div>
        </div>
      )}

      {status === 'pending' && (
        <p className="text-xs text-fg-muted">任务已提交，等待分配执行资源…</p>
      )}
      {status === 'queued' && (
        <p className="text-xs text-fg-muted">任务已入队，排队等待执行…</p>
      )}
      {status === 'completed' && (
        <p className="text-xs text-success/90">生成完成，可在下方查看结果。</p>
      )}
      {status === 'failed' && (
        <p className="text-xs text-error/90">失败原因：{error ?? '未知错误'}</p>
      )}
      {status === 'cancelled' && <p className="text-xs text-fg-muted">任务已取消。</p>}
    </div>
  )
}
