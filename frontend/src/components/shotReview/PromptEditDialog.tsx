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

import { useEffect, useState } from 'react'
import { Wand2 } from 'lucide-react'
import type { ShotReviewItem } from '@/api/shotReviews'
import { ShotPromptEditor } from '@/components/shotReview/ShotPromptEditor'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'

// 审片任务卡片一直从这里导入 copyText，保留导出避免改动调用方。
export { copyText } from '@/components/shotReview/ShotPromptEditor'

export interface PromptEditDialogProps {
  item: ShotReviewItem | null
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 保存精修提示词；空串表示清除该镜的提示词备注。 */
  onSave: (revisedPrompt: string) => void
  saving?: boolean
}

/**
 * 精修提示词编辑弹窗。
 *
 * 内容区交给 ShotPromptEditor：左侧对照原始提示词与本镜被引用资产，右侧用与创作页
 * 同源的输入体验改写。保存后的提示词作为该镜的修改备注，下游重生成直接复制使用。
 */
export function PromptEditDialog({ item, open, onOpenChange, onSave, saving }: PromptEditDialogProps) {
  const [draft, setDraft] = useState('')

  // 每次打开时以当前已保存的提示词为编辑起点
  useEffect(() => {
    if (open && item) setDraft(item.revised_prompt ?? '')
  }, [open, item])

  if (!item) return null

  const cleared = draft.trim() === '' && item.revised_prompt != null

  function handleSave() {
    onSave(draft.trim())
    onOpenChange(false)
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={
        <span className="flex items-center gap-2">
          <Wand2 className="h-4 w-4 text-accent" />
          {item.shot_id} · 精修提示词
        </span>
      }
      description="左侧对照原始提示词与本镜被引用资产，右侧改写精修提示词；保存后作为该镜的修改备注。"
      className="max-w-4xl"
      footer={
        <>
          <span className="mr-auto text-xs text-fg-muted">
            {cleared ? '当前内容为空，保存后将清除该镜的精修提示词' : '提示词保存为修改备注，不影响评分'}
          </span>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button variant="primary" onClick={handleSave} disabled={saving}>
            保存
          </Button>
        </>
      }
    >
      <div className="py-1">
        <ShotPromptEditor
          item={item}
          value={draft}
          onChange={setDraft}
          onSave={handleSave}
          saving={saving}
          autoFocus={open}
        />
      </div>
    </Dialog>
  )
}
