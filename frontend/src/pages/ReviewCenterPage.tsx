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
import { useSearchParams } from 'react-router-dom'
import { Clapperboard, ClipboardCheck, Plus } from 'lucide-react'
import { MaterialReviewPanel } from '@/components/review/MaterialReviewPanel'
import { ShotReviewPanel } from '@/components/shotReview/ShotReviewPanel'
import { CreateSessionDialog } from '@/components/reviewCenter/CreateSessionDialog'
import type { ReviewMode } from '@/components/reviewCenter/reviewMode'
import { useCreateReviewSession } from '@/hooks/useReviews'
import { useCreateShotReviewSession } from '@/hooks/useShotReviews'
import { Button } from '@/components/ui/Button'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { cn } from '@/lib/utils'

const MODE_TABS: { key: ReviewMode; label: string; icon: typeof ClipboardCheck }[] = [
  { key: 'material', label: '素材审阅', icon: ClipboardCheck },
  { key: 'shot', label: '镜头审片', icon: Clapperboard },
]

function modeFromSearch(param: string | null): ReviewMode {
  return param === 'shot' ? 'shot' : 'material'
}

/** 审阅中心：素材审阅与镜头审片的统一入口，页头 Tab 切换两种模式。 */
export function ReviewCenterPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const mode = modeFromSearch(searchParams.get('mode'))
  const [openCreate, setOpenCreate] = useState(false)
  // 每个模式各自记住选中的会话，切换 Tab 不丢失
  const [selection, setSelection] = useState<Record<ReviewMode, string | null>>({
    material: null,
    shot: null,
  })

  const createMaterialMutation = useCreateReviewSession()
  const createShotMutation = useCreateShotReviewSession()

  function switchMode(next: ReviewMode) {
    if (next === mode) return
    setSearchParams(next === 'material' ? {} : { mode: next }, { replace: true })
  }

  async function handleCreate(title: string, path: string) {
    try {
      if (mode === 'material') {
        const session = await createMaterialMutation.mutateAsync({ title, folderPath: path })
        setSelection((prev) => ({ ...prev, material: session.id }))
        toast(`已创建审阅会话「${title}」，扫描到 ${session.item_count} 个文件`, 'success')
      } else {
        const session = await createShotMutation.mutateAsync({ title, rootPath: path })
        setSelection((prev) => ({ ...prev, shot: session.id }))
        toast(`已创建审片会话「${title}」，扫描到 ${session.item_count} 个镜头视频`, 'success')
      }
    } catch (e) {
      toast(toApiError(e).message, 'error')
    }
  }

  return (
    <div className={cn('mx-auto px-6 py-6', mode === 'shot' ? 'max-w-[1600px]' : 'max-w-7xl')}>
      {/* 标题 + 模式切换 */}
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-fg-primary">审阅中心</h1>
          <p className="mt-1 text-sm text-fg-secondary">
            素材审阅与镜头审片的统一入口：标记审核结论、按镜打分，多版本对比与废弃版本清理
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {/* 模式切换：素材审阅 / 镜头审片 */}
          <div className="flex items-center rounded-card border border-border p-0.5">
            {MODE_TABS.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => switchMode(tab.key)}
                  className={cn(
                    'flex items-center gap-1.5 rounded-btn px-3 py-1.5 text-sm font-medium transition-all',
                    mode === tab.key
                      ? 'bg-accent/10 text-fg-primary'
                      : 'text-fg-muted hover:text-fg-secondary',
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {tab.label}
                </button>
              )
            })}
          </div>
          <Button onClick={() => setOpenCreate(true)}>
            <Plus className="h-4 w-4" />
            {mode === 'material' ? '新建审阅' : '新建审片'}
          </Button>
        </div>
      </div>

      {/* 当前模式面板（含各自的会话列表、筛选与内容区） */}
      {mode === 'material' ? (
        <MaterialReviewPanel
          selectedId={selection.material}
          onSelectSession={(id) => setSelection((prev) => ({ ...prev, material: id }))}
        />
      ) : (
        <ShotReviewPanel
          selectedId={selection.shot}
          onSelectSession={(id) => setSelection((prev) => ({ ...prev, shot: id }))}
        />
      )}

      {/* 新建会话弹窗 */}
      <CreateSessionDialog
        mode={mode}
        open={openCreate}
        onOpenChange={setOpenCreate}
        onCreate={handleCreate}
      />
    </div>
  )
}
