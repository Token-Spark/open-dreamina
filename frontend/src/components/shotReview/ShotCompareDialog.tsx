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

import { useEffect, useMemo, useRef } from 'react'
import { BadgeCheck, Check, Pause, Play, RotateCcw } from 'lucide-react'
import type { ShotReviewItem } from '@/api/shotReviews'
import { shotReviewItemFileUrl } from '@/api/shotReviews'
import { VERDICT_META, isPortraitItem } from '@/components/shotReview/ShotReviewCard'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { cn } from '@/lib/utils'

/**
 * 同镜号多版本并排对比弹窗：各版本视频同屏播放，可直接选定保留版本。
 * 提供「全部播放 / 全部暂停 / 对齐到片头」同步控制，便于逐帧比较。
 */
export interface ShotCompareDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  shotId: string
  /** 该镜号的全部版本。 */
  items: ShotReviewItem[]
  onSelect: (itemId: string) => void
  onDeselect: (itemId: string) => void
}

export function ShotCompareDialog({
  open,
  onOpenChange,
  shotId,
  items,
  onSelect,
  onDeselect,
}: ShotCompareDialogProps) {
  const videoRefs = useRef<(HTMLVideoElement | null)[]>([])
  // 竖屏（如短剧 9:16）时加宽弹窗、提高视频高度并排更多列，保证足够的纵向比较空间
  const portrait = useMemo(() => {
    const withDims = items.filter((i) => i.width && i.height)
    if (withDims.length === 0) return false
    return withDims.filter(isPortraitItem).length >= withDims.length / 2
  }, [items])

  // 关闭弹窗时停掉全部播放，避免后台出声
  useEffect(() => {
    if (open) return
    for (const v of videoRefs.current) v?.pause()
  }, [open])

  function playAll() {
    for (const v of videoRefs.current) void v?.play().catch(() => {})
  }

  function pauseAll() {
    for (const v of videoRefs.current) v?.pause()
  }

  function alignAndPlay() {
    for (const v of videoRefs.current) {
      if (!v) continue
      v.currentTime = 0
      void v.play().catch(() => {})
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      className={portrait ? 'max-w-7xl' : 'max-w-6xl'}
      title={`镜号对比 · ${shotId}`}
      description={`并排播放 ${items.length} 个版本，比较后选定要保留的版本；未选定的版本可在栏目中一键清理。`}
      footer={
        <div className="flex flex-1 flex-wrap items-center gap-1.5">
          <Button variant="outline" size="sm" onClick={playAll}>
            <Play className="h-3.5 w-3.5" />
            全部播放
          </Button>
          <Button variant="outline" size="sm" onClick={pauseAll}>
            <Pause className="h-3.5 w-3.5" />
            全部暂停
          </Button>
          <Button variant="outline" size="sm" onClick={alignAndPlay}>
            <RotateCcw className="h-3.5 w-3.5" />
            对齐到片头播放
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} className="ml-auto">
            关闭
          </Button>
        </div>
      }
    >
      <div
        className={cn(
          'grid max-h-[70vh] gap-3 overflow-y-auto p-1',
          portrait
            ? 'grid-cols-2 md:grid-cols-3'
            : cn('md:grid-cols-2', items.length > 4 && 'xl:grid-cols-3'),
        )}
      >
        {items.map((item, idx) => {
          const meta = VERDICT_META[item.verdict]
          return (
            <div
              key={item.id}
              className={cn(
                'flex flex-col gap-2 rounded-card border bg-bg-primary/60 p-2',
                item.selected ? 'border-success/60 ring-1 ring-success/40' : 'border-border',
              )}
            >
              <video
                ref={(el) => {
                  videoRefs.current[idx] = el
                }}
                src={shotReviewItemFileUrl(item.id)}
                controls
                preload="metadata"
                className={cn(
                  'rounded-btn bg-black/70 object-contain',
                  portrait
                    ? 'mx-auto h-[min(60vh,540px)] w-auto max-w-full'
                    : 'h-56 w-full',
                )}
              />
              <div className="flex items-center gap-1.5">
                <Badge variant="outline" className="shrink-0 whitespace-nowrap font-mono">
                  版本 {idx + 1}
                </Badge>
                <Badge variant={meta.variant} className="shrink-0 whitespace-nowrap">
                  {meta.label}
                </Badge>
                {item.score != null && (
                  <span className="shrink-0 whitespace-nowrap text-xs tabular-nums text-fg-secondary">
                    {item.score} 分
                  </span>
                )}
                <span className="ml-auto min-w-0 truncate text-[11px] text-fg-muted" title={item.file_name}>
                  {item.file_name}
                </span>
              </div>
              {item.selected ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onDeselect(item.id)}
                  className="h-7 gap-1 text-success hover:text-success"
                >
                  <BadgeCheck className="h-3.5 w-3.5" />
                  已选定保留 · 点击取消
                </Button>
              ) : (
                <Button variant="outline" size="sm" onClick={() => onSelect(item.id)} className="h-7 gap-1">
                  <Check className="h-3.5 w-3.5" />
                  选定此版本
                </Button>
              )}
            </div>
          )
        })}
      </div>
    </Dialog>
  )
}
