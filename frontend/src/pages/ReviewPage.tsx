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
import {
  ClipboardCheck,
  Plus,
  Trash2,
  RefreshCw,
  FolderOpen,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
} from 'lucide-react'
import {
  useReviewSessions,
  useReviewItems,
  useCreateReviewSession,
  useDeleteReviewSession,
  useRescanReviewSession,
  useUpdateReviewSession,
  useUpdateReviewItem,
  useBatchUpdateReviewItems,
} from '@/hooks/useReviews'
import type { ReviewItem, ReviewStatus, ReviewSession } from '@/api/reviews'
import { reviewItemFileUrl } from '@/api/reviews'
import { CreateReviewSessionDialog } from '@/components/review/CreateReviewSessionDialog'
import { ReviewItemCard, STATUS_META } from '@/components/review/ReviewItemCard'
import { ImageLightbox } from '@/components/ImageLightbox'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Badge } from '@/components/ui/Badge'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { cn, formatRelativeTime } from '@/lib/utils'

type StatusFilter = ReviewStatus | 'all'

const STATUS_FILTERS: { key: StatusFilter; label: string; icon: typeof Clock }[] = [
  { key: 'all', label: '全部', icon: ClipboardCheck },
  { key: 'pending', label: '待审', icon: Clock },
  { key: 'approved', label: '通过', icon: CheckCircle2 },
  { key: 'needs_revision', label: '需修改', icon: AlertTriangle },
  { key: 'rejected', label: '驳回', icon: XCircle },
]

export function ReviewPage() {
  const { data: sessions, isLoading: sessionsLoading } = useReviewSessions()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [openCreate, setOpenCreate] = useState(false)
  const [openItem, setOpenItem] = useState<ReviewItem | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<ReviewSession | null>(null)

  const currentSession = sessions?.find((s) => s.id === selectedId) ?? null

  const { data: items, isLoading: itemsLoading } = useReviewItems(
    selectedId,
    statusFilter === 'all' ? undefined : statusFilter,
  )

  const createMutation = useCreateReviewSession()
  const deleteMutation = useDeleteReviewSession()
  const rescanMutation = useRescanReviewSession()
  const updateSessionMutation = useUpdateReviewSession()
  const updateItemMutation = useUpdateReviewItem(selectedId ?? '')
  const batchUpdateMutation = useBatchUpdateReviewItems(selectedId ?? '')

  async function handleCreate(title: string, folderPath: string) {
    try {
      const session = await createMutation.mutateAsync({ title, folderPath })
      setSelectedId(session.id)
      toast(`已创建审阅会话「${title}」，扫描到 ${session.item_count} 个文件`, 'success')
    } catch (e) {
      toast(toApiError(e).message, 'error')
    }
  }

  async function handleDelete() {
    if (!confirmDelete) return
    try {
      await deleteMutation.mutateAsync(confirmDelete.id)
      if (selectedId === confirmDelete.id) setSelectedId(null)
      toast('已删除审阅会话', 'success')
    } catch (e) {
      toast(toApiError(e).message, 'error')
    } finally {
      setConfirmDelete(null)
    }
  }

  async function handleRescan() {
    if (!currentSession) return
    try {
      const result = await rescanMutation.mutateAsync(currentSession.id)
      toast(
        result.added || result.removed
          ? `扫描完成：新增 ${result.added}，移除 ${result.removed}，共 ${result.total} 个`
          : `扫描完成，共 ${result.total} 个文件，无变化`,
        'success',
      )
    } catch (e) {
      toast(toApiError(e).message, 'error')
    }
  }

  function handleStatusChange(itemId: string, status: ReviewStatus) {
    updateItemMutation.mutate({ itemId, payload: { status } })
  }

  function handleFeedbackChange(itemId: string, feedback: string) {
    updateItemMutation.mutate({ itemId, payload: { feedback } })
  }

  function handleBatchApproveAll() {
    if (!items || items.length === 0) return
    const pending = items.filter((i) => i.status === 'pending')
    if (pending.length === 0) {
      toast('没有待审条目', 'default')
      return
    }
    batchUpdateMutation.mutate(
      pending.map((i) => ({ id: i.id, status: 'approved' as ReviewStatus })),
      {
        onSuccess: (res) =>
          toast(`已批量通过 ${res.updated} 个条目`, 'success'),
        onError: (e) => toast(toApiError(e).message, 'error'),
      },
    )
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      {/* 标题 */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-fg-primary">制片人审阅</h1>
          <p className="mt-1 text-sm text-fg-secondary">
            审核外部文件夹中的 AI 批量生成素材，标记通过/驳回并记录修改意见
          </p>
        </div>
        <Button onClick={() => setOpenCreate(true)}>
          <Plus className="h-4 w-4" />
          新建审阅
        </Button>
      </div>

      <div className="flex gap-6">
        {/* 左侧：会话列表 */}
        <div className="w-72 shrink-0 space-y-2">
          {sessionsLoading ? (
            <div className="flex items-center gap-2 py-8 text-sm text-fg-muted">
              <Loader2 className="h-4 w-4 animate-spin" />
              加载中…
            </div>
          ) : sessions && sessions.length > 0 ? (
            sessions.map((s) => (
              <button
                key={s.id}
                onClick={() => {
                  setSelectedId(s.id)
                  setStatusFilter('all')
                }}
                className={cn(
                  'w-full rounded-card border p-3 text-left transition-all',
                  selectedId === s.id
                    ? 'border-accent bg-bg-tertiary ring-1 ring-accent/30'
                    : 'border-border bg-bg-secondary hover:bg-bg-tertiary',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-fg-primary">
                    {s.title}
                  </span>
                  {s.status === 'completed' && (
                    <Badge variant="success">已完成</Badge>
                  )}
                </div>
                <div className="mt-1 flex items-center gap-1 text-xs text-fg-muted">
                  <FolderOpen className="h-3 w-3 shrink-0" />
                  <span className="truncate">
                    {s.folder_path.split(/[\\/]/).pop() || s.folder_path}
                  </span>
                </div>
                <div className="mt-1.5 flex items-center gap-2 text-xs tabular-nums text-fg-muted">
                  <span>{s.item_count} 个文件</span>
                  {s.summary?.reviewed != null && (
                    <>
                      <span>·</span>
                      <span>{s.summary.reviewed} 已审</span>
                    </>
                  )}
                  <span>·</span>
                  <span>{formatRelativeTime(s.updated_at)}</span>
                </div>
              </button>
            ))
          ) : (
            <div className="rounded-card border border-dashed border-border p-8 text-center">
              <ClipboardCheck className="mx-auto mb-2 h-8 w-8 text-fg-muted" />
              <p className="text-sm font-medium text-fg-secondary">暂无审阅会话</p>
              <p className="mt-1 text-xs text-fg-muted">点击「新建审阅」开始</p>
            </div>
          )}
        </div>

        {/* 右侧：条目列表 */}
        <div className="min-w-0 flex-1">
          {!currentSession ? (
            <div className="flex h-72 items-center justify-center rounded-card border border-dashed border-border text-center">
              <div>
                <ClipboardCheck className="mx-auto mb-2 h-8 w-8 text-fg-muted" />
                <p className="text-sm font-medium text-fg-secondary">
                  选择左侧会话或新建审阅
                </p>
              </div>
            </div>
          ) : (
            <div>
              {/* 会话工具栏 */}
              <div className="mb-4 rounded-card border border-border bg-bg-secondary p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <h2 className="truncate text-base font-semibold text-fg-primary">
                      {currentSession.title}
                    </h2>
                    <div className="mt-1 flex items-center gap-1.5 text-xs text-fg-muted">
                      <FolderOpen className="h-3 w-3 shrink-0" />
                      <span className="truncate">{currentSession.folder_path}</span>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleRescan}
                      disabled={rescanMutation.isPending}
                    >
                      <RefreshCw className={cn('h-3.5 w-3.5', rescanMutation.isPending && 'animate-spin')} />
                      重新扫描
                    </Button>
                    {currentSession.status !== 'completed' ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          updateSessionMutation.mutate({
                            sessionId: currentSession.id,
                            payload: { status: 'completed' },
                          })
                        }
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        标记完成
                      </Button>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          updateSessionMutation.mutate({
                            sessionId: currentSession.id,
                            payload: { status: 'in_review' },
                          })
                        }
                      >
                        重新开启
                      </Button>
                    )}
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => setConfirmDelete(currentSession)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      删除
                    </Button>
                  </div>
                </div>

                {/* 统计 */}
                {currentSession.summary && (
                  <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs tabular-nums">
                    <SummaryDot icon={Clock} label="待审" count={currentSession.summary.pending ?? 0} className="text-fg-secondary" />
                    <SummaryDot icon={CheckCircle2} label="通过" count={currentSession.summary.approved ?? 0} className="text-success" />
                    <SummaryDot icon={AlertTriangle} label="需修改" count={currentSession.summary.needs_revision ?? 0} className="text-warning" />
                    <SummaryDot icon={XCircle} label="驳回" count={currentSession.summary.rejected ?? 0} className="text-error" />
                    <span className="text-fg-muted">
                      共 {currentSession.summary.total ?? currentSession.item_count} 个
                    </span>
                  </div>
                )}
              </div>

              {/* 状态筛选 + 批量操作 */}
              <div className="mb-4 flex flex-wrap items-center gap-2">
                {STATUS_FILTERS.map((f) => {
                  const Icon = f.icon
                  const count =
                    f.key === 'all'
                      ? currentSession.summary?.total ?? 0
                      : currentSession.summary?.[f.key] ?? 0
                  return (
                    <button
                      key={f.key}
                      onClick={() => setStatusFilter(f.key)}
                      className={cn(
                        'flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-all',
                        statusFilter === f.key
                          ? 'border-accent bg-accent/10 text-fg-primary'
                          : 'border-border text-fg-muted hover:bg-bg-tertiary hover:text-fg-secondary',
                      )}
                    >
                      <Icon className="h-3 w-3" />
                      {f.label}
                      <span className="tabular-nums text-fg-muted">{count}</span>
                    </button>
                  )
                })}
                <Button
                  variant="outline"
                  size="sm"
                  className="ml-auto"
                  onClick={handleBatchApproveAll}
                  disabled={batchUpdateMutation.isPending}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  全部通过待审
                </Button>
              </div>

              {/* 条目列表 */}
              {itemsLoading ? (
                <div className="flex items-center gap-2 py-12 text-sm text-fg-muted">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  加载中…
                </div>
              ) : items && items.length > 0 ? (
                <div className="space-y-2.5">
                  {items.map((item, idx) => (
                    <ReviewItemCard
                      key={item.id}
                      item={item}
                      index={idx}
                      onStatusChange={(status) => handleStatusChange(item.id, status)}
                      onFeedbackChange={(feedback) => handleFeedbackChange(item.id, feedback)}
                      onOpen={() => setOpenItem(item)}
                    />
                  ))}
                </div>
              ) : (
                <div className="flex h-40 items-center justify-center rounded-card border border-dashed border-border text-center">
                  <p className="text-sm text-fg-muted">
                    {statusFilter === 'all' ? '该文件夹中暂无可审阅文件' : `没有「${STATUS_META[statusFilter as ReviewStatus]?.label}」状态的条目`}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 新建会话弹窗 */}
      <CreateReviewSessionDialog
        open={openCreate}
        onOpenChange={setOpenCreate}
        onCreate={handleCreate}
      />

      {/* 预览 */}
      <ImageLightbox
        open={openItem != null}
        onClose={() => setOpenItem(null)}
        item={
          openItem
            ? {
                url: reviewItemFileUrl(openItem.id),
                type: openItem.mime_type?.startsWith('video/') ? 'video' : 'image',
                title: openItem.file_name,
                meta: {
                  状态: STATUS_META[openItem.status].label,
                  大小: openItem.file_size ? `${(openItem.file_size / 1024 / 1024).toFixed(1)} MB` : undefined,
                  尺寸: openItem.width && openItem.height ? `${openItem.width}×${openItem.height}` : undefined,
                  时长: openItem.duration ? `${openItem.duration.toFixed(1)}s` : undefined,
                  修改意见: openItem.feedback || undefined,
                },
              }
            : null
        }
      />

      {/* 删除确认 */}
      <Dialog
        open={confirmDelete != null}
        onOpenChange={(o) => !o && setConfirmDelete(null)}
        title="确认删除"
        description={`将删除审阅会话「${confirmDelete?.title ?? ''}」及其所有审阅记录，此操作不可恢复。`}
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
        <p className="py-2 text-sm text-fg-secondary">外部文件夹中的原始文件不会被删除。</p>
      </Dialog>
    </div>
  )
}

function SummaryDot({
  icon: Icon,
  label,
  count,
  className,
}: {
  icon: typeof Clock
  label: string
  count: number
  className?: string
}) {
  return (
    <span className={cn('flex items-center gap-1', className)}>
      <Icon className="h-3 w-3" />
      {label}
      <span className="font-medium">{count}</span>
    </span>
  )
}
