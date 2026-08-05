import type * as React from 'react'
import { Download, Play, Star, Trash2 } from 'lucide-react'
import type { Asset } from '@/api/assets'
import { assetFileUrl, assetThumbnailUrl } from '@/api/assets'
import { Card } from '@/components/ui/Card'
import { cn, formatFileSize, formatRelativeTime } from '@/lib/utils'

export interface AssetGridProps {
  assets: Asset[]
  selectable?: boolean
  selectedIds?: Set<string>
  onToggleSelect?: (id: string) => void
  onOpen?: (asset: Asset) => void
  onToggleFavorite?: (asset: Asset) => void
  onDelete?: (asset: Asset) => void
  className?: string
}

export function AssetGrid({
  assets,
  selectable = false,
  selectedIds,
  onToggleSelect,
  onOpen,
  onToggleFavorite,
  onDelete,
  className,
}: AssetGridProps) {
  if (assets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-card border border-dashed border-border py-16 text-center">
        <p className="text-sm text-fg-secondary">暂无资产</p>
        <p className="mt-1 text-xs text-fg-muted">生成的作品将出现在这里</p>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5',
        className,
      )}
    >
      {assets.map((asset) => {
        const selected = selectedIds?.has(asset.id) ?? false
        return (
          <Card
            key={asset.id}
            className={cn(
              'group overflow-hidden transition-colors',
              selected && 'ring-1 ring-accent',
            )}
          >
            <div className="relative aspect-square cursor-pointer bg-bg-tertiary">
              <img
                src={assetThumbnailUrl(asset.id)}
                alt=""
                loading="lazy"
                className={cn(
                  'h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]',
                  selectable && !selected && 'group-hover:opacity-80',
                )}
                onClick={() =>
                  selectable ? onToggleSelect?.(asset.id) : onOpen?.(asset)
                }
              />
              {asset.type === 'video' && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                  <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white/95 shadow-lg">
                    <Play className="h-4 w-4 translate-x-[1px] fill-black/80 text-black/80" />
                  </span>
                </div>
              )}
              {selectable && (
                <span
                  className={cn(
                    'absolute left-2 top-2 h-4 w-4 rounded-full border transition-colors',
                    selected
                      ? 'border-accent bg-accent'
                      : 'border-fg-muted/60 bg-black/40 opacity-0 group-hover:opacity-100',
                  )}
                />
              )}
              <div className="absolute right-2 top-2 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                <IconBtn label="收藏" onClick={(e) => { e.stopPropagation(); onToggleFavorite?.(asset) }}>
                  <Star
                    className={cn('h-3.5 w-3.5', asset.is_favorite ? 'fill-accent text-accent' : 'text-white')}
                  />
                </IconBtn>
                <a
                  href={assetFileUrl(asset.id)}
                  download
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="flex h-6 w-6 items-center justify-center rounded-full bg-black/60 text-white shadow-sm transition-colors hover:bg-black/80"
                  aria-label="下载"
                >
                  <Download className="h-3.5 w-3.5" />
                </a>
                {onDelete && (
                  <IconBtn label="删除" onClick={(e) => { e.stopPropagation(); onDelete(asset) }}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </IconBtn>
                )}
              </div>
            </div>
            <div className="px-2.5 py-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wide text-fg-muted">
                  {asset.type}
                </span>
                <span className="text-[11px] text-fg-muted">
                  {formatFileSize(asset.file_size)}
                </span>
              </div>
              <p className="mt-0.5 truncate text-[11px] text-fg-muted">
                {formatRelativeTime(asset.created_at)}
              </p>
            </div>
          </Card>
        )
      })}
    </div>
  )
}

function IconBtn({
  children,
  label,
  onClick,
}: {
  children: React.ReactNode
  label: string
  onClick: (e: React.MouseEvent) => void
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="flex h-6 w-6 items-center justify-center rounded-full bg-black/60 text-white shadow-sm transition-colors hover:bg-black/80"
    >
      {children}
    </button>
  )
}
