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

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Trash2, XCircle } from 'lucide-react'
import {
  cancelTask,
  deleteTask,
  listTasks,
  retryTask,
  type Task,
  type TaskStatus,
} from '@/api/tasks'
import { useTaskStore } from '@/stores/taskStore'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Progress } from '@/components/ui/Progress'
import { Dialog } from '@/components/ui/Dialog'
import { STATUS_LABEL, TASK_TYPE_LABEL, isActiveStatus, statusBadgeVariant } from '@/lib/taskStatus'
import { catalogModels } from '@/lib/generation'
import { cn, formatDateTime } from '@/lib/utils'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'

type Tab = 'all' | 'active' | 'completed' | 'failed'

const TABS: { key: Tab; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'active', label: '进行中' },
  { key: 'completed', label: '已完成' },
  { key: 'failed', label: '失败' },
]

function statusFilter(tab: Tab): string | undefined {
  switch (tab) {
    case 'active':
      return 'pending,queued,running'
    case 'completed':
      return 'completed'
    case 'failed':
      return 'failed'
    default:
      return undefined
  }
}

/** 友好显示模型：根据 provider + model_id 在已知目录中查找展示名，未找到时回退原 id。 */
function modelLabel(provider: string, modelId: string | null): string {
  if (!modelId) return '--'
  const found = catalogModels(provider).find((m) => m.id === modelId)
  return found?.label ?? modelId
}

/** 格式化 token 用量：null 显示 --，否则按千分位展示。 */
function formatTokens(tokens: number | null | undefined): string {
  if (tokens == null) return '--'
  return tokens.toLocaleString('zh-CN')
}

export function TasksPage() {
  const [tab, setTab] = useState<Tab>('all')
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const qc = useQueryClient()
  const activeMap = useTaskStore((s) => s.active)

  const { data, isLoading } = useQuery({
    queryKey: ['tasks', tab],
    queryFn: () => listTasks({ status: statusFilter(tab), page_size: 100 }),
    refetchInterval: tab === 'active' ? 5000 : false,
  })

  const tasks = data?.items ?? []

  async function handleCancel(task: Task) {
    try {
      await cancelTask(task.id)
      toast('已请求取消', 'success')
      qc.invalidateQueries({ queryKey: ['tasks'] })
    } catch (e) {
      toast(toApiError(e).message, 'error')
    }
  }
  async function handleRetry(task: Task) {
    try {
      await retryTask(task.id)
      toast('已重新提交', 'success')
      qc.invalidateQueries({ queryKey: ['tasks'] })
    } catch (e) {
      toast(toApiError(e).message, 'error')
    }
  }
  async function handleDelete() {
    if (!confirmDelete) return
    try {
      await deleteTask(confirmDelete)
      toast('任务已删除', 'success')
      qc.invalidateQueries({ queryKey: ['tasks'] })
    } catch (e) {
      toast(toApiError(e).message, 'error')
    } finally {
      setConfirmDelete(null)
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="mb-4 flex items-center gap-1 rounded-btn border border-border bg-bg-secondary p-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              'rounded-btn px-3 py-1.5 text-sm transition-colors',
              tab === t.key
                ? 'bg-bg-tertiary text-fg-primary'
                : 'text-fg-secondary hover:text-fg-primary',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="overflow-hidden rounded-card border border-border">
        <table className="w-full text-sm">
          <thead className="bg-bg-secondary text-xs text-fg-muted">
            <tr>
              <th className="px-4 py-2.5 text-left font-medium">类型</th>
              <th className="px-4 py-2.5 text-left font-medium">模型</th>
              <th className="px-4 py-2.5 text-left font-medium">状态</th>
              <th className="px-4 py-2.5 text-left font-medium">进度</th>
              <th className="px-4 py-2.5 text-right font-medium">Token</th>
              <th className="px-4 py-2.5 text-left font-medium">创建时间</th>
              <th className="px-4 py-2.5 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-fg-muted">
                  加载中…
                </td>
              </tr>
            ) : tasks.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-fg-muted">
                  暂无任务
                </td>
              </tr>
            ) : (
              tasks.map((task) => {
                const live = activeMap[task.id]
                const status: TaskStatus = live?.status ?? task.status
                const progress = live?.progress ?? task.progress
                return (
                  <tr key={task.id} className="border-t border-border hover:bg-bg-secondary/60">
                    <td className="px-4 py-3 text-fg-primary">
                      {TASK_TYPE_LABEL[task.type]}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-0.5">
                        <span className="text-xs text-fg-primary">
                          {modelLabel(task.provider, task.model_id)}
                        </span>
                        <span className="text-[11px] text-fg-muted">{task.provider}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        variant={statusBadgeVariant(status)}
                        title={
                          status === 'failed' && task.error_msg
                            ? task.error_msg
                            : undefined
                        }
                      >
                        {STATUS_LABEL[status]}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Progress
                          value={progress}
                          glow={status === 'running'}
                          className="w-28"
                        />
                        <span className="text-xs tabular-nums text-fg-muted">
                          {progress}%
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={cn(
                          'tabular-nums',
                          task.tokens_used == null
                            ? 'text-fg-muted'
                            : 'text-fg-secondary',
                        )}
                        title={
                          task.tokens_used == null
                            ? 'Provider 未返回 token 用量'
                            : `${task.tokens_used.toLocaleString('zh-CN')} tokens`
                        }
                      >
                        {formatTokens(task.tokens_used)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-fg-secondary">
                      {formatDateTime(task.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        {isActiveStatus(status) && (
                          <Button variant="ghost" size="sm" onClick={() => handleCancel(task)}>
                            <XCircle className="h-3.5 w-3.5" />
                            取消
                          </Button>
                        )}
                        {status === 'failed' && (
                          <Button variant="ghost" size="sm" onClick={() => handleRetry(task)}>
                            <RefreshCw className="h-3.5 w-3.5" />
                            重试
                          </Button>
                        )}
                        {!isActiveStatus(status) && (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setConfirmDelete(task.id)}
                            aria-label="删除"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      <Dialog
        open={confirmDelete != null}
        onOpenChange={(o) => !o && setConfirmDelete(null)}
        title="删除任务"
        description="将删除该任务记录，关联的生成结果不会被删除。"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmDelete(null)}>
              取消
            </Button>
            <Button variant="danger" onClick={handleDelete}>
              删除
            </Button>
          </>
        }
      >
        <p className="py-2 text-sm text-fg-secondary">此操作无法撤销。</p>
      </Dialog>
    </div>
  )
}
