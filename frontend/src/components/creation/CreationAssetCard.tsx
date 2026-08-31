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

import { Cloud, Pencil, Trash2, User } from 'lucide-react'
import type { CreationAsset } from '@/api/creationAssets'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { formatDateTime } from '@/lib/utils'

const CATEGORY_LABEL: Record<string, string> = {
  character: '人物',
  scene: '场景',
  prop: '道具',
}

export interface CreationAssetCardProps {
  asset: CreationAsset
  onEdit: (asset: CreationAsset) => void
  onDelete: (asset: CreationAsset) => void
}

/** 素材卡片：图片预览 + 音色试听 + 设定文本 + 标签 + 同步状态。
 * 可信团队模型：所有资产（含云端拉取）均可编辑，编辑后推送回原版本链。 */
export function CreationAssetCard({ asset, onEdit, onDelete }: CreationAssetCardProps) {
  return (
    <div className="group flex flex-col overflow-hidden rounded-dialog border border-border bg-bg-secondary transition-colors hover:border-fg-muted/40">
      {/* 图片预览 */}
      <div className="relative aspect-[4/3] overflow-hidden bg-bg-tertiary">
        {asset.image_thumbnail_url ? (
          <img
            src={asset.image_thumbnail_url}
            alt={asset.name}
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-fg-muted">
            <span className="text-xs">暂无图片</span>
          </div>
        )}
        <div className="absolute left-2 top-2 flex gap-1">
          <Badge variant="outline" className="bg-bg-secondary/80 backdrop-blur">
            {CATEGORY_LABEL[asset.category] ?? asset.category}
          </Badge>
          {!asset.is_mine && (
            <Badge variant="outline" className="bg-bg-secondary/80 backdrop-blur">
              云端
            </Badge>
          )}
          {asset.has_pending_changes && (
            <Badge variant="warning" className="bg-bg-secondary/80 backdrop-blur">
              未推送
            </Badge>
          )}
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <h3 className="line-clamp-1 text-sm font-medium text-fg-primary" title={asset.name}>
            {asset.name}
          </h3>
          <div className="flex shrink-0 gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => onEdit(asset)}
              aria-label="编辑"
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-error hover:text-error"
              onClick={() => onDelete(asset)}
              aria-label="删除"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {asset.description && (
          <p className="line-clamp-2 text-xs leading-relaxed text-fg-secondary" title={asset.description}>
            {asset.description}
          </p>
        )}

        {asset.audio_url && (
          <audio controls preload="none" src={asset.audio_url} className="h-8 w-full" />
        )}

        {asset.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {asset.tags.map((t) => (
              <Badge key={t}>{t}</Badge>
            ))}
          </div>
        )}

        <div className="mt-auto flex items-center justify-between pt-1 text-[11px] text-fg-muted">
          <span className="inline-flex items-center gap-1">
            <User className="h-3 w-3" />
            {asset.owner_name || '未知'}
          </span>
          <span
            className="inline-flex items-center gap-1"
            title={
              asset.base_version > 0
                ? `v${asset.base_version} · ${asset.synced_at ?? ''}`
                : '尚未同步'
            }
          >
            <Cloud className="h-3 w-3" />
            {asset.base_version > 0
              ? `v${asset.base_version} · ${asset.synced_at ? formatDateTime(asset.synced_at) : ''}`
              : '未同步'}
          </span>
        </div>
      </div>
    </div>
  )
}
