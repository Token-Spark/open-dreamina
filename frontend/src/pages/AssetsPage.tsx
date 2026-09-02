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
import { Star, Trash2, CheckSquare } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useAssets,
  useBatchDeleteAssets,
  useDeleteAsset,
  useUpdateAsset,
} from '@/hooks/useAssets'
import {
  assetFileUrl,
  type Asset,
  type AssetType,
} from '@/api/assets'
import { AssetGrid } from '@/components/AssetGrid'
import { ImageLightbox } from '@/components/ImageLightbox'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Label } from '@/components/ui/Label'
import { Switch } from '@/components/ui/Switch'
import { Dialog } from '@/components/ui/Dialog'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { formatDateTime, formatFileSize } from '@/lib/utils'

export function AssetsPage() {
  const [type, setType] = useState<AssetType | 'all'>('all')
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [tag, setTag] = useState('')
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [openAsset, setOpenAsset] = useState<Asset | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string[] | null>(null)

  const query = {
    type: type === 'all' ? undefined : type,
    is_favorite: favoritesOnly || undefined,
    tags: tag || undefined,
    page_size: 100,
  }
  const { data, isLoading } = useAssets(query)
  const updateAsset = useUpdateAsset()
  const deleteAsset = useDeleteAsset()
  const batchDelete = useBatchDeleteAssets()
  const qc = useQueryClient()

  const assets = data?.items ?? []

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function handleToggleFavorite(asset: Asset) {
    updateAsset.mutate(
      { id: asset.id, payload: { is_favorite: !asset.is_favorite } },
      { onError: (e) => toast(toApiError(e).message, 'error') },
    )
  }

  function handleDelete(asset: Asset) {
    setConfirmDelete([asset.id])
  }

  async function confirmBatchDelete() {
    if (!confirmDelete) return
    try {
      if (confirmDelete.length === 1) {
        await deleteAsset.mutateAsync(confirmDelete[0])
      } else {
        await batchDelete.mutateAsync(confirmDelete)
      }
      toast('已删除', 'success')
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ['assets'] })
    } catch (e) {
      toast(toApiError(e).message, 'error')
    } finally {
      setConfirmDelete(null)
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight text-fg-primary">资产库</h1>
        <p className="mt-1 text-sm text-fg-secondary">管理所有生成结果与上传素材</p>
      </div>

      <div className="mb-5 flex flex-wrap items-end gap-3 rounded-card border border-border bg-bg-secondary p-4">
        <div className="space-y-1.5">
          <Label>类型</Label>
          <Select
            value={type}
            onChange={(e) => setType(e.target.value as AssetType | 'all')}
            className="w-32"
          >
            <option value="all">全部</option>
            <option value="image">图片</option>
            <option value="video">视频</option>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>标签</Label>
          <Input
            value={tag}
            onChange={(e) => setTag(e.target.value)}
            placeholder="按标签筛选"
            className="w-44"
          />
        </div>
        <div className="flex items-center gap-2 pb-2">
          <Switch checked={favoritesOnly} onCheckedChange={setFavoritesOnly} aria-label="仅看收藏" />
          <Label className="flex items-center gap-1 pb-0">
            <Star className="h-3.5 w-3.5" />
            仅看收藏
          </Label>
        </div>
        <div className="ml-auto flex items-center gap-2 pb-1">
          <Button
            variant={selectMode ? 'secondary' : 'outline'}
            size="sm"
            onClick={() => {
              setSelectMode((v) => !v)
              setSelected(new Set())
            }}
          >
            <CheckSquare className="h-4 w-4" />
            {selectMode ? '退出选择' : '批量选择'}
          </Button>
          {selectMode && selected.size > 0 && (
            <Button
              variant="danger"
              size="sm"
              onClick={() => setConfirmDelete(Array.from(selected))}
            >
              <Trash2 className="h-4 w-4" />
              删除 ({selected.size})
            </Button>
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="py-16 text-center text-sm text-fg-muted">
          <span className="animate-pulse">加载中…</span>
        </div>
      ) : (
        <AssetGrid
          assets={assets}
          selectable={selectMode}
          selectedIds={selected}
          onToggleSelect={toggleSelect}
          onOpen={setOpenAsset}
          onToggleFavorite={handleToggleFavorite}
          onDelete={handleDelete}
        />
      )}

      <ImageLightbox
        open={openAsset != null}
        onClose={() => setOpenAsset(null)}
        item={
          openAsset
            ? {
                url: assetFileUrl(openAsset.id),
                type: openAsset.type === 'video' ? 'video' : 'image',
                title: `${openAsset.type} · ${formatFileSize(openAsset.file_size)}`,
                meta: {
                  创建时间: formatDateTime(openAsset.created_at),
                  尺寸:
                    openAsset.width && openAsset.height
                      ? `${openAsset.width}×${openAsset.height}`
                      : undefined,
                  时长: openAsset.duration ? `${openAsset.duration}s` : undefined,
                  标签: openAsset.tags.join(', '),
                },
              }
            : null
        }
      />

      <Dialog
        open={confirmDelete != null}
        onOpenChange={(o) => !o && setConfirmDelete(null)}
        title="确认删除"
        description={`将删除 ${confirmDelete?.length ?? 0} 个资产，且无法恢复。`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmDelete(null)}>
              取消
            </Button>
            <Button variant="danger" onClick={confirmBatchDelete}>
              删除
            </Button>
          </>
        }
      >
        <p className="py-2 text-sm text-fg-secondary">删除后关联的文件也会被移除。</p>
      </Dialog>
    </div>
  )
}
