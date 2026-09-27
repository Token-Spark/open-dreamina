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

import { BadgeCheck, Columns2, Layers, Trash2 } from 'lucide-react'
import type { ShotReviewItem } from '@/api/shotReviews'
import { ShotTakeCard } from '@/components/shotReview/ShotTakeCard'
import { isPortraitItem } from '@/components/shotReview/ShotReviewCard'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

/**
 * 同一镜号的多版本栏目：把同镜号的全部视频合并在一个卡片内，
 * 便于并排比较、选定保留版本并删除其余废弃视频。
 */
export interface ShotGroupCardProps {
  /** 该镜号下的全部版本（已按文件名排序）。 */
  items: ShotReviewItem[]
  onScoreChange: (itemId: string, score: number) => void
  onClearScore: (itemId: string) => void
  onFeedbackChange: (itemId: string, feedback: string) => void
  onPromptSave: (itemId: string, revisedPrompt: string) => void
  onSelect: (itemId: string) => void
  onDeselect: (itemId: string) => void
  /** 删除单个版本（弹确认框）。 */
  onDeleteTake: (item: ShotReviewItem) => void
  /** 删除该镜未选定的其余版本（弹确认框）。 */
  onDeleteUnselected: () => void
  /** 打开并排对比弹窗。 */
  onCompare: () => void
  onOpen: (item: ShotReviewItem) => void
}

export function ShotGroupCard({
  items,
  onScoreChange,
  onClearScore,
  onFeedbackChange,
  onPromptSave,
  onSelect,
  onDeselect,
  onDeleteTake,
  onDeleteUnselected,
  onCompare,
  onOpen,
}: ShotGroupCardProps) {
  const first = items[0]
  const selectedIndex = items.findIndex((i) => i.selected)
  const unselected = items.filter((i) => !i.selected)
  const multiTake = items.length > 1
  // 同镜号各版本分辨率一致，按首版本的画幅方向决定版本网格密度：
  // 竖屏视频卡片更高更窄，用更多列并排以便同屏比较
  const portrait = isPortraitItem(first)

  return (
    <section
      className={cn(
        'overflow-hidden rounded-card border bg-bg-primary/40',
        multiTake ? 'border-accent/40' : 'border-border',
      )}
    >
      {/* 栏目头：镜号 + 分镜信息 + 多版本操作 */}
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b border-border bg-bg-secondary px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant={multiTake ? 'default' : 'outline'} className="font-mono">
              {first.shot_id}
            </Badge>
            {first.episode && !first.shot_id.startsWith(first.episode) && (
              <span className="text-xs font-medium text-fg-secondary">{first.episode}</span>
            )}
            <span className="flex items-center gap-1 text-xs text-fg-muted">
              <Layers className="h-3 w-3" />
              {items.length} 个版本
            </span>
            {multiTake &&
              (selectedIndex >= 0 ? (
                <span className="flex items-center gap-1 text-xs font-medium text-success">
                  <BadgeCheck className="h-3.5 w-3.5" />
                  已选定 版本 {selectedIndex + 1}
                </span>
              ) : (
                <span className="text-xs text-warning">未选定保留版本</span>
              ))}
          </div>
          <p
            className="mt-1 line-clamp-1 text-xs text-fg-secondary"
            title={first.shot_function ?? ''}
          >
            {first.shot_function ?? '未关联分镜信息'}
          </p>
        </div>

        {multiTake && (
          <div className="flex shrink-0 items-center gap-1.5">
            <Button variant="outline" size="sm" onClick={onCompare}>
              <Columns2 className="h-3.5 w-3.5" />
              对比
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={onDeleteUnselected}
              disabled={selectedIndex < 0 || unselected.length === 0}
              title={
                selectedIndex < 0
                  ? '请先选定要保留的版本，再删除其余废弃版本'
                  : `删除该镜未选定的 ${unselected.length} 个版本`
              }
            >
              <Trash2 className="h-3.5 w-3.5" />
              删除未选定（{unselected.length}）
            </Button>
          </div>
        )}
      </div>

      {/* 版本网格：同一镜号的各版本并排，便于直接比较 */}
      <div
        className={cn(
          'grid gap-3 p-3',
          portrait
            ? 'grid-cols-2 md:grid-cols-3 2xl:grid-cols-4'
            : 'grid-cols-1 md:grid-cols-2 2xl:grid-cols-3',
        )}
      >
        {items.map((item, idx) => (
          <ShotTakeCard
            key={item.id}
            item={item}
            index={idx + 1}
            onScoreChange={(score) => onScoreChange(item.id, score)}
            onClearScore={() => onClearScore(item.id)}
            onFeedbackChange={(feedback) => onFeedbackChange(item.id, feedback)}
            onPromptSave={(prompt) => onPromptSave(item.id, prompt)}
            onSelect={() => onSelect(item.id)}
            onDeselect={() => onDeselect(item.id)}
            onDelete={() => onDeleteTake(item)}
            onOpen={() => onOpen(item)}
          />
        ))}
      </div>
    </section>
  )
}
