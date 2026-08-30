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
import { Cloud, Plus, Search, Zap } from 'lucide-react'
import {
  CATEGORY_OPTIONS,
  type CreationAsset,
  type CreationAssetCategory,
} from '@/api/creationAssets'
import {
  useAutoSyncConfig,
  useCreateCreationAsset,
  useCreateProject,
  useCreationAssetTags,
  useCreationAssets,
  useDeleteCreationAsset,
  useProjects,
  usePullAssetsByTag,
  useRunAutoSyncNow,
  useSyncAssetsByTag,
  useSyncConfig,
  useUpdateAutoSyncConfig,
  useUpdateCreationAsset,
  useUpdateOwnerName,
} from '@/hooks/useCreationAssets'
import { useQueryClient } from '@tanstack/react-query'
import { PROJECTS_KEY } from '@/hooks/useCreationAssets'
import {
  CreationAssetCard,
} from '@/components/creation/CreationAssetCard'
import {
  CreationAssetFormDialog,
  type CreationAssetFormValues,
} from '@/components/creation/CreationAssetFormDialog'
import { CreationAssetSyncDialog } from '@/components/creation/CreationAssetSyncDialog'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'

type CategoryFilter = CreationAssetCategory | 'all'

export function CreationAssetsPage() {
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [tagFilter, setTagFilter] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<CreationAsset | null>(null)
  const [syncOpen, setSyncOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<CreationAsset | null>(null)

  const query = {
    category: category === 'all' ? undefined : category,
    tags: tagFilter ?? undefined,
    search: search || undefined,
    page_size: 200,
  }
  const { data, isLoading } = useCreationAssets(query)
  const { data: tagData } = useCreationAssetTags()
  const { data: syncConfig } = useSyncConfig()
  const { data: autoSyncConfig } = useAutoSyncConfig()
  const { data: projectsData, isLoading: projectsLoading, refetch: refetchProjects } =
    useProjects(syncOpen)

  const createAsset = useCreateCreationAsset()
  const updateAsset = useUpdateCreationAsset()
  const deleteAsset = useDeleteCreationAsset()
  const syncAssets = useSyncAssetsByTag()
  const pullAssets = usePullAssetsByTag()
  const updateOwner = useUpdateOwnerName()
  const createProject = useCreateProject()
  const updateAutoSync = useUpdateAutoSyncConfig()
  const runAutoSync = useRunAutoSyncNow()
  const queryClient = useQueryClient()

  const assets = data?.items ?? []
  const tagSummaries = tagData?.tags ?? []

  /** 根据后端返回的单资产同步结果显示对应的 toast。 */
  function showSyncToast(
    syncResult: CreationAsset['sync_result'],
    defaultMessage: string,
  ) {
    if (!syncResult) {
      toast(defaultMessage, 'success')
      return
    }
    const SYNC_STATUS_TEXT: Record<string, string> = {
      synced: '已推送',
      updated: '已更新',
      up_to_date: '已是最新',
      conflict: '同步冲突',
      failed: '推送失败',
      skipped: '已跳过',
    }
    const status = syncResult.status
    const label = SYNC_STATUS_TEXT[status] ?? status
    if (status === 'synced' || status === 'updated' || status === 'up_to_date') {
      toast(`${defaultMessage}，${label}`, 'success')
    } else if (status === 'conflict' || status === 'failed') {
      toast(
        `${defaultMessage}，但${label}：${syncResult.message ?? '请稍后在团队项目中手动重试'}`,
        'warning',
      )
    } else {
      toast(`${defaultMessage}`, 'success')
    }
  }

  async function handleSubmit(values: CreationAssetFormValues) {
    if (editing) {
      const updated = await updateAsset.mutateAsync({ id: editing.id, payload: values })
      showSyncToast(updated.sync_result, '已保存')
      return
    }

    const created = await createAsset.mutateAsync(values)
    showSyncToast(created.sync_result, '资产已创建')
  }

  async function handleDelete() {
    if (!confirmDelete) return
    try {
      await deleteAsset.mutateAsync(confirmDelete.id)
      toast('已删除', 'success')
    } catch (e) {
      toast(toApiError(e).message, 'error')
    } finally {
      setConfirmDelete(null)
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      {/* 顶部：标题 + 同步/新建入口 */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-medium tracking-tight text-fg-primary">素材库</h1>
            {autoSyncConfig?.enabled && (
              <span className="inline-flex items-center gap-1 rounded-full border border-success/30 bg-success/10 px-2 py-0.5 text-[11px] text-success">
                <Zap className="h-3 w-3" />
                自动同步中
              </span>
            )}
          </div>
          <p className="text-xs text-fg-secondary">
            集中管理人物、场景、道具等可复用创作资产，按项目同步共享给团队成员
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setSyncOpen(true)}>
            <Cloud className="h-4 w-4" />
            团队项目
          </Button>
          <Button
            size="sm"
            onClick={() => {
              setEditing(null)
              setFormOpen(true)
            }}
          >
            <Plus className="h-4 w-4" />
            新建资产
          </Button>
        </div>
      </div>

      {/* 筛选栏：类别 + 标签 + 搜索 */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="flex gap-1 rounded-btn border border-border bg-bg-secondary p-1">
          {(['all', ...CATEGORY_OPTIONS.map((c) => c.value)] as CategoryFilter[]).map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCategory(c)}
              className={`rounded-btn px-3 py-1 text-xs transition-colors ${
                category === c
                  ? 'bg-bg-tertiary text-fg-primary'
                  : 'text-fg-secondary hover:text-fg-primary'
              }`}
            >
              {c === 'all' ? '全部' : CATEGORY_OPTIONS.find((o) => o.value === c)?.label}
            </button>
          ))}
        </div>

        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-fg-muted" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索名称/设定"
            className="h-8 w-44 pl-8"
          />
        </div>

        {tagFilter && (
          <button
            type="button"
            onClick={() => setTagFilter(null)}
            className="rounded-full border border-accent bg-accent/10 px-2.5 py-1 text-xs text-fg-primary"
          >
            {tagFilter} ×
          </button>
        )}

        {tagSummaries.length > 0 && !tagFilter && (
          <div className="flex flex-wrap gap-1">
            {tagSummaries.slice(0, 10).map((t) => (
              <button
                key={t.name}
                type="button"
                onClick={() => setTagFilter(t.name)}
                className="rounded-full border border-border px-2.5 py-1 text-xs text-fg-secondary transition-colors hover:border-fg-muted hover:text-fg-primary"
              >
                {t.name}（{t.count}）
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 资产网格 */}
      {isLoading ? (
        <div className="py-16 text-center text-sm text-fg-muted">加载中…</div>
      ) : assets.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-16 text-center">
          <p className="text-sm text-fg-secondary">
            {tagFilter || search || category !== 'all'
              ? '没有符合筛选条件的资产'
              : '还没有创作资产，新建一个开始积累你的素材库'}
          </p>
          {!tagFilter && !search && category === 'all' && (
            <Button size="sm" onClick={() => setFormOpen(true)}>
              <Plus className="h-4 w-4" />
              新建资产
            </Button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {assets.map((a) => (
            <CreationAssetCard
              key={a.id}
              asset={a}
              onEdit={(asset) => {
                setEditing(asset)
                setFormOpen(true)
              }}
              onDelete={setConfirmDelete}
            />
          ))}
        </div>
      )}

      <CreationAssetFormDialog
        open={formOpen}
        asset={editing}
        existingTags={tagSummaries.map((t) => t.name)}
        onSubmit={handleSubmit}
        onClose={() => setFormOpen(false)}
      />

      <CreationAssetSyncDialog
        open={syncOpen}
        projects={projectsData ?? []}
        projectsLoading={projectsLoading}
        ownerName={syncConfig?.owner_name ?? ''}
        qiniuConfigured={syncConfig?.qiniu_configured ?? false}
        autoSyncConfig={autoSyncConfig}
        onClose={() => setSyncOpen(false)}
        onSync={(tag) => syncAssets.mutateAsync(tag)}
        onPull={(tag) => pullAssets.mutateAsync(tag)}
        onUpdateOwnerName={async (name) => {
          await updateOwner.mutateAsync(name)
        }}
        onCreateProject={async (name, description) => {
          await createProject.mutateAsync({ name, description })
        }}
        onRefreshProjects={() => {
          void refetchProjects()
          void queryClient.invalidateQueries({ queryKey: PROJECTS_KEY })
        }}
        onToggleAutoSync={async (enabled, tag) => {
          await updateAutoSync.mutateAsync({ enabled, tag })
        }}
        onRunAutoSyncNow={async () => {
          await runAutoSync.mutateAsync()
        }}
      />

      <Dialog
        open={confirmDelete != null}
        onOpenChange={(o) => !o && setConfirmDelete(null)}
        title="确认删除"
        description={`将删除资产「${confirmDelete?.name ?? ''}」及其关联文件，且无法恢复。`}
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
        <p className="py-2 text-sm text-fg-secondary">
          仅删除本地副本，云端已同步的版本不受影响，其他成员仍可拉取。
        </p>
      </Dialog>
    </div>
  )
}
