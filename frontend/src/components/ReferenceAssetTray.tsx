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

/**
 * 输入区上方的参考素材陈列：按角色 / 场景 / 道具 / 关键帧 / 上传分组，
 * 每组一行横向小图列表。相比原先所有素材平铺成一排大格子，
 * 分类后能一眼看清「这一条提示词引用了哪些角色、哪些场景」。
 *
 * 小图看不清由悬浮放大预览补偿；点击小图走父组件的大图灯箱。
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Music, Video, X } from 'lucide-react'
import {
  KIND_LABELS,
  groupRefAssets,
  refAssetGroupLabel,
  refAssetGroupKey,
  type ReferenceAsset,
} from '@/lib/promptMention'
import type { ReferenceKind } from '@/components/ReferenceSlot'
import { cn } from '@/lib/utils'

export interface ReferenceAssetTrayProps {
  /** 需要展示的参考素材（首帧/首尾帧模式下由调用方排除已在固定格子中的图片）。 */
  assets: ReferenceAsset[]
  /** 移除某个素材；不传则隐藏移除按钮（只读场景）。 */
  onRemove?: (assetId: string) => void
  /** 点击小图预览大图；不传则小图不可点击。 */
  onPreview?: (asset: ReferenceAsset) => void
  /** 画布节点内的紧凑布局。 */
  compact?: boolean
  className?: string
}

interface HoverState {
  asset: ReferenceAsset
  rect: DOMRect
}

/** 审核状态对应的底部细条颜色与提示文案。 */
function auditHint(asset: ReferenceAsset): { color: string; text: string } | null {
  if (asset.auditStatus === 'pending') return { color: 'bg-amber-400', text: '审核中' }
  if (asset.auditStatus === 'failed') {
    return { color: 'bg-red-400', text: `审核未通过${asset.auditError ? `：${asset.auditError}` : ''}` }
  }
  return null
}

/** 悬浮放大层：小图不足以辨认内容时提供 168px 预览与完整名称。 */
function TrayHoverCard({ hover }: { hover: HoverState }) {
  const { asset, rect } = hover
  const kind = (asset.kind ?? 'image') as ReferenceKind
  const placeBelow = rect.top < 210
  const groupLabel = refAssetGroupLabel(refAssetGroupKey(asset))

  return createPortal(
    <div
      className="pointer-events-none fixed z-[80] flex animate-fade-in flex-col gap-1.5 rounded-btn border border-border bg-bg-secondary p-2 shadow-elevated"
      style={{
        top: placeBelow ? rect.bottom + 8 : rect.top - 8,
        left: rect.left + rect.width / 2,
        transform: `translate(-50%, ${placeBelow ? '0' : '-100%'})`,
      }}
    >
      <div className="h-36 w-36 overflow-hidden rounded-sm border border-border bg-bg-tertiary">
        {kind === 'video' ? (
          <video src={asset.previewUrl} muted playsInline className="h-full w-full object-cover" />
        ) : kind === 'audio' ? (
          <span className="flex h-full w-full flex-col items-center justify-center gap-1.5">
            <Music className="h-8 w-8 text-fg-muted" />
            <span className="text-[10px] text-fg-muted">音频素材</span>
          </span>
        ) : (
          <img src={asset.previewUrl} alt="" className="h-full w-full object-cover" />
        )}
      </div>
      <span className="block max-w-36 truncate text-center text-xs text-fg-primary">
        {asset.name ?? KIND_LABELS[kind]}
      </span>
      <span className="text-center text-[10px] text-fg-muted">
        {groupLabel} · {KIND_LABELS[kind]}
        {asset.auditStatus === 'pending' ? ' · 审核中' : ''}
        {asset.auditStatus === 'failed' ? ' · 审核未通过' : ''}
      </span>
    </div>,
    document.body,
  )
}

export function ReferenceAssetTray({
  assets,
  onRemove,
  onPreview,
  compact = false,
  className,
}: ReferenceAssetTrayProps) {
  const groups = useMemo(() => groupRefAssets(assets), [assets])
  const [hover, setHover] = useState<HoverState | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    },
    [],
  )

  function showHover(asset: ReferenceAsset, rect: DOMRect) {
    if (timerRef.current) clearTimeout(timerRef.current)
    // 延迟触发，避免鼠标快速掠过整排小图时弹层连续闪烁
    timerRef.current = setTimeout(() => setHover({ asset, rect }), 160)
  }

  function hideHover() {
    if (timerRef.current) clearTimeout(timerRef.current)
    setHover(null)
  }

  if (groups.length === 0) return null

  return (
    <div
      className={cn(
        'overflow-y-auto scrollbar-thin',
        compact ? 'max-h-28' : 'max-h-48',
        className,
      )}
    >
      {groups.map((group) => (
        <div
          key={group.key}
          className="flex items-start gap-2 border-t border-border/40 py-1.5 first:border-t-0"
        >
          {/* 类别标签 + 数量：固定宽度让多行小图左边缘对齐 */}
          <div className="flex w-14 shrink-0 items-baseline gap-1 pt-3">
            <span className="text-[11px] font-medium leading-none text-fg-secondary">
              {group.label}
            </span>
            <span className="text-[10px] leading-none tabular-nums text-fg-muted">
              {group.items.length}
            </span>
          </div>

          {/* 每组独立的横向滚动，类别之间互不挤压 */}
          <div className="flex min-w-0 flex-1 gap-1.5 overflow-x-auto pb-1 scrollbar-thin">
            {group.items.map((asset) => {
              const kind = (asset.kind ?? 'image') as ReferenceKind
              const audit = auditHint(asset)
              const name = asset.name ?? KIND_LABELS[kind]
              return (
                <div
                  key={asset.assetId}
                  className={cn('group relative shrink-0', compact ? 'w-11' : 'w-14')}
                  onMouseEnter={(e) => showHover(asset, e.currentTarget.getBoundingClientRect())}
                  onMouseLeave={hideHover}
                >
                  <div className={cn('relative mx-auto', compact ? 'h-8 w-8' : 'h-10 w-10')}>
                    <button
                      type="button"
                      title={`${name} · ${group.label}${audit ? ` · ${audit.text}` : ''}`}
                      onClick={() => onPreview?.(asset)}
                      className={cn(
                        'relative block h-full w-full overflow-hidden rounded-md border border-border bg-bg-tertiary transition-colors',
                        onPreview ? 'cursor-zoom-in hover:border-fg-muted' : 'cursor-default',
                        asset.auditStatus === 'failed' && 'border-red-400/70',
                      )}
                    >
                      {kind === 'audio' && !asset.thumbUrl ? (
                        <span className="flex h-full w-full items-center justify-center">
                          <Music className="h-4 w-4 text-fg-muted" />
                        </span>
                      ) : (
                        <>
                          {kind === 'video' && !asset.thumbUrl ? (
                            <video src={asset.previewUrl} muted playsInline className="h-full w-full object-cover" />
                          ) : (
                            <img
                              src={asset.thumbUrl ?? asset.previewUrl}
                              alt=""
                              loading="lazy"
                              className="h-full w-full object-cover"
                            />
                          )}
                          {kind !== 'image' && (
                            <span className="absolute bottom-0 right-0 flex h-3 w-3 items-center justify-center rounded-tl bg-black/65 text-white">
                              {kind === 'video' ? (
                                <Video className="h-2 w-2" />
                              ) : (
                                <Music className="h-2 w-2" />
                              )}
                            </span>
                          )}
                        </>
                      )}
                      {audit && (
                        <span className={cn('absolute inset-x-0 bottom-0 h-0.5', audit.color)} />
                      )}
                    </button>

                    {onRemove && (
                      <button
                        type="button"
                        aria-label={`移除 ${name}`}
                        onClick={() => {
                          hideHover()
                          onRemove(asset.assetId)
                        }}
                        className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-black/70 text-white opacity-0 transition-opacity hover:bg-black group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100"
                      >
                        <X className="h-2.5 w-2.5" />
                      </button>
                    )}
                  </div>

                  <span
                    className={cn(
                      'mt-1 block truncate text-center text-[10px] leading-none text-fg-muted',
                      compact ? 'w-11' : 'w-14',
                    )}
                  >
                    {name}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      ))}
      {hover && <TrayHoverCard hover={hover} />}
    </div>
  )
}
