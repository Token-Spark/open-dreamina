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

import { useEffect, useMemo, useState } from 'react'
import {
  BadgeCheck,
  CheckCircle2,
  Clapperboard,
  Clock,
  Gauge,
  Layers,
  LayoutGrid,
  List,
  Loader2,
  Trash2,
  TriangleAlert,
  Wand2,
  XCircle,
} from 'lucide-react'
import {
  shotGroupKey,
  useBulkDeleteShotReviewItems,
  useDeleteShotReviewItem,
  useDeleteShotReviewSession,
  useRescanShotReviewSession,
  useShotReviewItems,
  useShotReviewSessions,
  useUpdateShotReviewItem,
  useUpdateShotReviewSession,
} from '@/hooks/useShotReviews'
import type { ShotReviewItem, ShotReviewSession, ShotVerdict } from '@/api/shotReviews'
import { shotReviewItemFileUrl } from '@/api/shotReviews'
import { ShotCompareDialog } from '@/components/shotReview/ShotCompareDialog'
import { ShotGroupCard } from '@/components/shotReview/ShotGroupCard'
import { ShotReviewCard, VERDICT_META, isPortraitItem } from '@/components/shotReview/ShotReviewCard'
import { FilterPill } from '@/components/reviewCenter/FilterPill'
import { SessionListPanel } from '@/components/reviewCenter/SessionListPanel'
import type { SessionListItem } from '@/components/reviewCenter/SessionListPanel'
import { SessionToolbar } from '@/components/reviewCenter/SessionToolbar'
import { SummaryDot } from '@/components/reviewCenter/SummaryDot'
import { ImageLightbox } from '@/components/ImageLightbox'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Select } from '@/components/ui/Select'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { cn, formatFileSize } from '@/lib/utils'

type VerdictFilter = ShotVerdict | 'all'
type ViewMode = 'grouped' | 'flat'

/** 分组视图单页渲染的栏目数：整批可达数百个镜头，分批渲染避免 DOM 与并发请求过重。 */
const PAGE_SIZE_GROUPS = 10
/** 平铺视图单页渲染的镜头卡片数。 */
const PAGE_SIZE_FLAT = 48

const VERDICT_FILTERS: { key: VerdictFilter; label: string; icon: typeof Clock }[] = [
  { key: 'all', label: '全部', icon: Clapperboard },
  { key: 'pending', label: '待审', icon: Clock },
  { key: 'pass', label: '通过', icon: CheckCircle2 },
  { key: 'revise', label: '需重生成', icon: TriangleAlert },
  { key: 'redesign', label: '需重新设计', icon: XCircle },
]

/** 从镜号中提取数字用于自然排序（如 EP05-S12 → 12），无数字的排最后。 */
function shotNoOf(shotId: string): number {
  const m = /S(\d+)/i.exec(shotId)
  return m ? Number.parseInt(m[1], 10) : Number.MAX_SAFE_INTEGER
}

/** 审阅中心的镜头审片面板：按集→镜分组打分、多版本对比与废弃版本清理。 */
export function ShotReviewPanel({
  selectedId,
  onSelectSession,
}: {
  selectedId: string | null
  onSelectSession: (id: string | null) => void
}) {
  const { data: sessions, isLoading: sessionsLoading } = useShotReviewSessions()
  const [episodeFilter, setEpisodeFilter] = useState('all')
  const [verdictFilter, setVerdictFilter] = useState<VerdictFilter>('all')
  // 分组视图（默认）：同镜号的多个版本合并进同一栏目，选定保留版本并清理废弃视频
  const [viewMode, setViewMode] = useState<ViewMode>('grouped')
  const [multiOnly, setMultiOnly] = useState(false)
  const [openItem, setOpenItem] = useState<ShotReviewItem | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<ShotReviewSession | null>(null)
  const [confirmTakeDelete, setConfirmTakeDelete] = useState<ShotReviewItem | null>(null)
  const [confirmBulkDelete, setConfirmBulkDelete] = useState<{ shotId: string; items: ShotReviewItem[] } | null>(
    null,
  )
  const [compareShot, setCompareShot] = useState<{ shotId: string; items: ShotReviewItem[] } | null>(null)

  // 切换会话（含新建后自动选中）时重置筛选
  useEffect(() => {
    setEpisodeFilter('all')
    setVerdictFilter('all')
    setMultiOnly(false)
  }, [selectedId])

  const listItems = useMemo<SessionListItem[]>(
    () =>
      (sessions ?? []).map((s) => ({
        id: s.id,
        title: s.title,
        pathLabel: s.root_path.split(/[\\/]/).pop() || s.root_path,
        completed: s.status === 'completed',
        statPrimary: `${s.item_count} 个镜头`,
        statSecondary: s.summary.scored != null ? `${s.summary.scored} 已评` : undefined,
        updatedAt: s.updated_at,
      })),
    [sessions],
  )

  const currentSession = sessions?.find((s) => s.id === selectedId) ?? null

  // 一次取回全部条目，集号与档位筛选在本地完成，便于同时派生集号下拉、栏目与计数
  const { data: allItems, isLoading: itemsLoading } = useShotReviewItems(selectedId)

  const episodes = useMemo(() => {
    const set = new Set<string>()
    for (const it of allItems ?? []) {
      if (it.episode) set.add(it.episode)
    }
    return Array.from(set).sort()
  }, [allItems])

  const items = useMemo(() => {
    return (allItems ?? []).filter(
      (it) =>
        (episodeFilter === 'all' || it.episode === episodeFilter) &&
        (verdictFilter === 'all' || it.verdict === verdictFilter),
    )
  }, [allItems, episodeFilter, verdictFilter])

  // 同镜号分组：键为 集|镜号，组内按文件名自然排序，组间按 集 → 镜号 排序
  const groups = useMemo(() => {
    const map = new Map<string, ShotReviewItem[]>()
    for (const it of items) {
      const key = shotGroupKey(it)
      const arr = map.get(key)
      if (arr) arr.push(it)
      else map.set(key, [it])
    }
    for (const arr of map.values()) {
      arr.sort((a, b) => a.file_name.localeCompare(b.file_name, 'zh-Hans-CN', { numeric: true }))
    }
    return Array.from(map.entries()).sort(([keyA, a], [keyB, b]) => {
      const ep = (a[0].episode ?? '~').localeCompare(b[0].episode ?? '~', 'zh-Hans-CN', { numeric: true })
      if (ep !== 0) return ep
      const no = shotNoOf(a[0].shot_id) - shotNoOf(b[0].shot_id)
      return no !== 0 ? no : keyA.localeCompare(keyB)
    })
  }, [items])

  const visibleGroups = useMemo(() => (multiOnly ? groups.filter(([, arr]) => arr.length > 1) : groups), [groups, multiOnly])

  const multiTakeCount = useMemo(
    () => groups.reduce((n, [, arr]) => (arr.length > 1 ? n + 1 : n), 0),
    [groups],
  )

  const [visibleGroupCount, setVisibleGroupCount] = useState(PAGE_SIZE_GROUPS)
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE_FLAT)
  const shownGroups = useMemo(() => visibleGroups.slice(0, visibleGroupCount), [visibleGroups, visibleGroupCount])
  const visibleItems = useMemo(() => items.slice(0, visibleCount), [items, visibleCount])

  // 竖屏模式（如短剧 9:16）：多数条目高大于宽时，抬高预览区并加密网格
  const portraitMode = useMemo(() => {
    const withDims = (allItems ?? []).filter((i) => i.width && i.height)
    if (withDims.length === 0) return false
    return withDims.filter(isPortraitItem).length >= withDims.length / 2
  }, [allItems])

  // 切换会话或筛选条件后回到第一页
  useEffect(() => {
    setVisibleGroupCount(PAGE_SIZE_GROUPS)
    setVisibleCount(PAGE_SIZE_FLAT)
  }, [selectedId, episodeFilter, verdictFilter, viewMode, multiOnly])

  const deleteMutation = useDeleteShotReviewSession()
  const rescanMutation = useRescanShotReviewSession()
  const updateSessionMutation = useUpdateShotReviewSession()
  const updateItemMutation = useUpdateShotReviewItem(selectedId ?? '')
  const deleteItemMutation = useDeleteShotReviewItem(selectedId ?? '')
  const bulkDeleteMutation = useBulkDeleteShotReviewItems(selectedId ?? '')

  async function handleDelete() {
    if (!confirmDelete) return
    try {
      await deleteMutation.mutateAsync(confirmDelete.id)
      if (selectedId === confirmDelete.id) onSelectSession(null)
      toast('已删除审片会话', 'success')
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
          : `扫描完成，共 ${result.total} 个镜头视频，无变化`,
        'success',
      )
    } catch (e) {
      toast(toApiError(e).message, 'error')
    }
  }

  function handleScoreChange(itemId: string, score: number) {
    updateItemMutation.mutate({ itemId, payload: { score } })
  }

  function handleClearScore(itemId: string) {
    updateItemMutation.mutate({ itemId, payload: { clear_score: true } })
  }

  function handleFeedbackChange(itemId: string, feedback: string) {
    updateItemMutation.mutate({ itemId, payload: { feedback } })
  }

  function handlePromptSave(itemId: string, revisedPrompt: string) {
    // 精修提示词作为该镜的修改备注落库；空串表示清除
    updateItemMutation.mutate({ itemId, payload: { revised_prompt: revisedPrompt } })
  }

  function handleSelect(itemId: string) {
    // 后端保证同镜号栏目内互斥：选中新版本会自动取消旧选中
    updateItemMutation.mutate({ itemId, payload: { selected: true } })
  }

  function handleDeselect(itemId: string) {
    updateItemMutation.mutate({ itemId, payload: { selected: false } })
  }

  async function handleTakeDelete(deleteFile: boolean) {
    if (!confirmTakeDelete) return
    const item = confirmTakeDelete
    try {
      const result = await deleteItemMutation.mutateAsync({ itemId: item.id, deleteFile })
      setConfirmTakeDelete(null)
      const freed = result.freed_bytes > 0 ? `，释放 ${formatFileSize(result.freed_bytes)}` : ''
      toast(`已删除「${item.file_name}」${freed}`, 'success')
    } catch (e) {
      toast(toApiError(e).message, 'error')
    }
  }

  async function handleBulkDelete(deleteFile: boolean) {
    if (!confirmBulkDelete) return
    const { shotId, items: targets } = confirmBulkDelete
    const ids = targets.map((i) => i.id)
    try {
      const result = await bulkDeleteMutation.mutateAsync({ itemIds: ids, deleteFile })
      setConfirmBulkDelete(null)
      const freed = result.freed_bytes > 0 ? `，释放 ${formatFileSize(result.freed_bytes)}` : ''
      if (result.failed > 0) {
        toast(`镜号 ${shotId}：已删 ${result.deleted} 个，${result.failed} 个失败（${result.errors[0]?.message ?? '未知错误'}）`, 'error')
      } else {
        toast(`镜号 ${shotId}：已删除 ${result.deleted} 个废弃版本${freed}`, 'success')
      }
    } catch (e) {
      toast(toApiError(e).message, 'error')
    }
  }

  const summary = currentSession?.summary

  return (
    <>
      <div className="flex gap-6">
        {/* 左侧：会话列表 */}
        <div className="w-72 shrink-0">
          <SessionListPanel
            items={listItems}
            isLoading={sessionsLoading}
            selectedId={selectedId}
            onSelect={onSelectSession}
            emptyIcon={Clapperboard}
            emptyTitle="暂无审片会话"
            emptyHint="点击「新建审片」开始"
          />
        </div>

        {/* 右侧：镜头栏目 / 卡片 */}
        <div className="min-w-0 flex-1">
          {!currentSession ? (
            <div className="flex h-72 items-center justify-center rounded-card border border-dashed border-border text-center">
              <div>
                <Clapperboard className="mx-auto mb-2 h-8 w-8 text-fg-muted" />
                <p className="text-sm font-medium text-fg-secondary">选择左侧会话或新建审片</p>
              </div>
            </div>
          ) : (
            <div>
              {/* 会话工具栏 */}
              <SessionToolbar
                title={currentSession.title}
                path={currentSession.root_path}
                completed={currentSession.status === 'completed'}
                rescanPending={rescanMutation.isPending}
                onRescan={handleRescan}
                onToggleStatus={() =>
                  updateSessionMutation.mutate({
                    sessionId: currentSession.id,
                    payload: { status: currentSession.status === 'completed' ? 'in_review' : 'completed' },
                  })
                }
                onDelete={() => setConfirmDelete(currentSession)}
              >
                {summary && (
                  <>
                    <SummaryDot icon={Clock} label="待审" count={summary.pending ?? 0} className="text-fg-secondary" />
                    <SummaryDot icon={CheckCircle2} label="通过" count={summary.pass ?? 0} className="text-success" />
                    <SummaryDot icon={TriangleAlert} label="需重生成" count={summary.revise ?? 0} className="text-warning" />
                    <SummaryDot icon={XCircle} label="需重新设计" count={summary.redesign ?? 0} className="text-error" />
                    <span className="flex items-center gap-1 text-fg-muted">
                      <Gauge className="h-3 w-3" />
                      均分
                      <span className="font-medium text-fg-secondary">
                        {summary.average_score != null ? summary.average_score.toFixed(1) : '--'}
                      </span>
                    </span>
                    <SummaryDot
                      icon={Wand2}
                      label="精修提示词"
                      count={summary.prompts_revised ?? 0}
                      className="text-fg-secondary"
                    />
                    <SummaryDot
                      icon={Layers}
                      label="多版本镜头"
                      count={multiTakeCount}
                      className="text-fg-secondary"
                    />
                    <SummaryDot
                      icon={BadgeCheck}
                      label="已选定"
                      count={groups.reduce((n, [, arr]) => (arr.some((i) => i.selected) ? n + 1 : n), 0)}
                      className="text-success"
                    />
                    <span className="text-fg-muted">
                      已评 {summary.scored ?? 0} / 共 {summary.total ?? currentSession.item_count} 个
                    </span>
                  </>
                )}
              </SessionToolbar>

              {/* 筛选 */}
              <div className="mb-4 flex flex-wrap items-center gap-2">
                {/* 视图切换：栏目分组（同镜号合并）/ 平铺列表 */}
                <div className="flex items-center rounded-card border border-border p-0.5">
                  <button
                    type="button"
                    onClick={() => setViewMode('grouped')}
                    className={cn(
                      'flex items-center gap-1 rounded-btn px-2.5 py-1 text-xs font-medium transition-all',
                      viewMode === 'grouped'
                        ? 'bg-accent/10 text-fg-primary'
                        : 'text-fg-muted hover:text-fg-secondary',
                    )}
                  >
                    <LayoutGrid className="h-3.5 w-3.5" />
                    栏目分组
                  </button>
                  <button
                    type="button"
                    onClick={() => setViewMode('flat')}
                    className={cn(
                      'flex items-center gap-1 rounded-btn px-2.5 py-1 text-xs font-medium transition-all',
                      viewMode === 'flat'
                        ? 'bg-accent/10 text-fg-primary'
                        : 'text-fg-muted hover:text-fg-secondary',
                    )}
                  >
                    <List className="h-3.5 w-3.5" />
                    平铺列表
                  </button>
                </div>

                {VERDICT_FILTERS.map((f) => {
                  const count =
                    f.key === 'all' ? (summary?.total ?? 0) : (summary?.[f.key] ?? 0)
                  return (
                    <FilterPill
                      key={f.key}
                      icon={f.icon}
                      label={f.label}
                      count={count}
                      active={verdictFilter === f.key}
                      onClick={() => setVerdictFilter(f.key)}
                    />
                  )
                })}
                {viewMode === 'grouped' && (
                  <FilterPill
                    icon={Layers}
                    label="多版本镜头"
                    count={multiTakeCount}
                    active={multiOnly}
                    onClick={() => setMultiOnly((v) => !v)}
                  />
                )}
                <div className="ml-auto w-40">
                  <Select
                    value={episodeFilter}
                    onChange={(e) => setEpisodeFilter(e.target.value)}
                  >
                    <option value="all">全部剧集</option>
                    {episodes.map((ep) => (
                      <option key={ep} value={ep}>
                        {ep}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>

              {/* 内容区 */}
              {itemsLoading ? (
                <div className="flex items-center gap-2 py-12 text-sm text-fg-muted">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  加载中…
                </div>
              ) : viewMode === 'grouped' ? (
                shownGroups.length > 0 ? (
                  <>
                    <div className="space-y-4">
                      {shownGroups.map(([key, groupItems]) => (
                        <ShotGroupCard
                          key={key}
                          items={groupItems}
                          onScoreChange={handleScoreChange}
                          onClearScore={handleClearScore}
                          onFeedbackChange={handleFeedbackChange}
                          onPromptSave={handlePromptSave}
                          onSelect={handleSelect}
                          onDeselect={handleDeselect}
                          onDeleteTake={(item) => setConfirmTakeDelete(item)}
                          onDeleteUnselected={() =>
                            setConfirmBulkDelete({
                              shotId: groupItems[0].shot_id,
                              items: groupItems.filter((i) => !i.selected),
                            })
                          }
                          onCompare={() =>
                            setCompareShot({ shotId: groupItems[0].shot_id, items: groupItems })
                          }
                          onOpen={(item) => setOpenItem(item)}
                        />
                      ))}
                    </div>
                    {visibleGroups.length > shownGroups.length && (
                      <div className="mt-4 flex flex-col items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setVisibleGroupCount((n) => n + PAGE_SIZE_GROUPS)}
                        >
                          加载更多（已显示 {shownGroups.length} / {visibleGroups.length} 个栏目）
                        </Button>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="flex h-40 items-center justify-center rounded-card border border-dashed border-border text-center">
                    <p className="text-sm text-fg-muted">
                      {verdictFilter === 'all' && episodeFilter === 'all' && !multiOnly
                        ? '该目录下暂未扫描到镜头视频'
                        : '当前筛选条件下没有镜头'}
                    </p>
                  </div>
                )
              ) : items.length > 0 ? (
                <>
                  <div
                    className={cn(
                      'grid gap-3',
                      portraitMode
                        ? 'grid-cols-2 md:grid-cols-3 2xl:grid-cols-4'
                        : 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3',
                    )}
                  >
                    {visibleItems.map((item) => (
                      <ShotReviewCard
                        key={item.id}
                        item={item}
                        onScoreChange={(score) => handleScoreChange(item.id, score)}
                        onClearScore={() => handleClearScore(item.id)}
                        onFeedbackChange={(feedback) => handleFeedbackChange(item.id, feedback)}
                        onPromptSave={(prompt) => handlePromptSave(item.id, prompt)}
                        onOpen={() => setOpenItem(item)}
                      />
                    ))}
                  </div>
                  {items.length > visibleItems.length && (
                    <div className="mt-4 flex flex-col items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setVisibleCount((n) => n + PAGE_SIZE_FLAT)}
                      >
                        加载更多（已显示 {visibleItems.length} / {items.length}）
                      </Button>
                    </div>
                  )}
                </>
              ) : (
                <div className="flex h-40 items-center justify-center rounded-card border border-dashed border-border text-center">
                  <p className="text-sm text-fg-muted">
                    {verdictFilter === 'all' && episodeFilter === 'all'
                      ? '该目录下暂未扫描到镜头视频'
                      : '当前筛选条件下没有镜头'}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 同镜号多版本对比 */}
      {compareShot && (
        <ShotCompareDialog
          open
          onOpenChange={(o) => !o && setCompareShot(null)}
          shotId={compareShot.shotId}
          items={compareShot.items}
          onSelect={handleSelect}
          onDeselect={handleDeselect}
        />
      )}

      {/* 全屏预览 */}
      <ImageLightbox
        open={openItem != null}
        onClose={() => setOpenItem(null)}
        item={
          openItem
            ? {
                url: shotReviewItemFileUrl(openItem.id),
                type: 'video',
                title: `${openItem.shot_id} · ${openItem.file_name}`,
                meta: {
                  档位: VERDICT_META[openItem.verdict].label,
                  评分: openItem.score ?? undefined,
                  镜头功能: openItem.shot_function ?? undefined,
                  景别: openItem.shot_size ?? undefined,
                  运镜: openItem.movement ?? undefined,
                  台词: openItem.dialogue ?? undefined,
                  脚本时长: openItem.script_duration != null ? `${openItem.script_duration}s` : undefined,
                  实测时长: openItem.duration != null ? `${openItem.duration.toFixed(1)}s` : undefined,
                  生成状态: openItem.render_status ?? undefined,
                  模型: openItem.model ?? undefined,
                  修改意见: openItem.feedback || undefined,
                  精修提示词: openItem.revised_prompt ?? undefined,
                },
              }
            : null
        }
      />

      {/* 删除单个版本 */}
      <Dialog
        open={confirmTakeDelete != null}
        onOpenChange={(o) => !o && setConfirmTakeDelete(null)}
        title="删除该版本？"
        description={confirmTakeDelete ? `${confirmTakeDelete.shot_id} · ${confirmTakeDelete.file_name}` : ''}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmTakeDelete(null)}>
              取消
            </Button>
            <Button variant="outline" onClick={() => handleTakeDelete(false)}>
              仅移出列表
            </Button>
            <Button variant="danger" onClick={() => handleTakeDelete(true)}>
              <Trash2 className="h-3.5 w-3.5" />
              删除文件
            </Button>
          </>
        }
      >
        <p className="py-2 text-sm text-fg-secondary">
          「仅移出列表」只把该版本从审片会话中移除；「删除文件」会把磁盘上的视频文件一并永久删除（释放
          {confirmTakeDelete ? formatFileSize(confirmTakeDelete.file_size) : '--'}），不可恢复。
        </p>
      </Dialog>

      {/* 删除栏目内未选定的废弃版本 */}
      <Dialog
        open={confirmBulkDelete != null}
        onOpenChange={(o) => !o && setConfirmBulkDelete(null)}
        title={`删除未选定版本 · ${confirmBulkDelete?.shotId ?? ''}`}
        description={
          confirmBulkDelete
            ? `将清理 ${confirmBulkDelete.items.length} 个未选定版本，共 ${formatFileSize(
                confirmBulkDelete.items.reduce((n, i) => n + (i.file_size ?? 0), 0),
              )}。已选定的保留版本不受影响。`
            : ''
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmBulkDelete(null)}>
              取消
            </Button>
            <Button variant="outline" onClick={() => handleBulkDelete(false)}>
              仅移出列表
            </Button>
            <Button variant="danger" onClick={() => handleBulkDelete(true)}>
              <Trash2 className="h-3.5 w-3.5" />
              删除文件
            </Button>
          </>
        }
      >
        <ul className="max-h-48 space-y-1 overflow-y-auto py-2 text-sm text-fg-secondary">
          {confirmBulkDelete?.items.map((i) => (
            <li key={i.id} className="flex items-center justify-between gap-3">
              <span className="truncate" title={i.file_name}>
                {i.file_name}
              </span>
              <span className="shrink-0 text-xs tabular-nums text-fg-muted">{formatFileSize(i.file_size)}</span>
            </li>
          ))}
        </ul>
        <p className="text-xs text-warning">
          「删除文件」会把上述视频从磁盘永久删除，不可恢复；确定它们已无保留价值。
        </p>
      </Dialog>

      {/* 删除会话 */}
      <Dialog
        open={confirmDelete != null}
        onOpenChange={(o) => !o && setConfirmDelete(null)}
        title="确认删除"
        description={`将删除审片会话「${confirmDelete?.title ?? ''}」及其全部评分与修改意见，此操作不可恢复。`}
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
        <p className="py-2 text-sm text-fg-secondary">外部文件夹中的原始视频不会被删除。</p>
      </Dialog>
    </>
  )
}
