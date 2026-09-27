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

import { useEffect, useRef, useState } from 'react'
import { ClipboardCopy, FileText, Wand2 } from 'lucide-react'
import type { ShotReviewItem } from '@/api/shotReviews'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Textarea } from '@/components/ui/Textarea'
import { cn } from '@/lib/utils'

export interface PromptEditDialogProps {
  item: ShotReviewItem | null
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 保存精修提示词；空串表示清除该镜的提示词备注。 */
  onSave: (revisedPrompt: string) => void
  saving?: boolean
}

/** 一键把文本写入剪贴板，失败时回落到选中文本。 */
export async function copyText(text: string): Promise<boolean> {
  if (!text) return false
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

/**
 * 精修提示词编辑器：上半部分展示扫描时从分镜脚本提取的提示词底稿（只读），
 * 供审片人在其基础上改写；保存后的提示词作为该镜的修改备注，下游重生成直接复制使用。
 */
export function PromptEditDialog({ item, open, onOpenChange, onSave, saving }: PromptEditDialogProps) {
  const [draft, setDraft] = useState('')
  const [copiedSource, setCopiedSource] = useState(false)
  const copiedTimer = useRef<number | null>(null)

  // 每次打开时以当前已保存的提示词为编辑起点
  useEffect(() => {
    if (open && item) setDraft(item.revised_prompt ?? '')
  }, [open, item])

  useEffect(
    () => () => {
      if (copiedTimer.current != null) window.clearTimeout(copiedTimer.current)
    },
    [],
  )

  if (!item) return null

  const source = item.source_prompt ?? ''
  const cleared = draft.trim() === '' && item.revised_prompt != null

  async function handleCopySource() {
    if (await copyText(source)) {
      setCopiedSource(true)
      if (copiedTimer.current != null) window.clearTimeout(copiedTimer.current)
      copiedTimer.current = window.setTimeout(() => setCopiedSource(false), 1500)
    }
  }

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
      description="改写后的 AIGC 提示词将作为该镜的修改备注，精修重生成时可直接复制使用。"
      className="max-w-2xl"
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
      <div className="space-y-3 py-1">
        {/* 分镜底稿（扫描时从 shots.md 提取，只读参考） */}
        {source && (
          <div className="rounded-btn border border-border bg-bg-tertiary/60">
            <div className="flex items-center justify-between gap-2 border-b border-border px-2.5 py-1.5">
              <span className="flex items-center gap-1.5 text-[11px] font-medium text-fg-secondary">
                <FileText className="h-3 w-3 shrink-0 text-fg-muted" />
                分镜底稿（shots.md 提取）
              </span>
              <div className="flex items-center gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 px-1.5 text-[11px]"
                  onClick={() => setDraft(source)}
                >
                  填入编辑器
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 px-1.5 text-[11px]"
                  onClick={handleCopySource}
                >
                  <ClipboardCopy className="h-3 w-3" />
                  {copiedSource ? '已复制' : '复制'}
                </Button>
              </div>
            </div>
            <div className="max-h-40 overflow-y-auto whitespace-pre-wrap px-2.5 py-2 text-[11px] leading-relaxed text-fg-secondary scrollbar-thin">
              {source}
            </div>
          </div>
        )}

        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={10}
          spellCheck={false}
          placeholder={
            source
              ? '在分镜底稿基础上改写，或直接粘贴下一版生成使用的完整提示词…'
              : '填写下一版生成使用的 AIGC 提示词，作为该镜的精修修改备注…'
          }
          className={cn('font-mono text-xs leading-relaxed', 'resize-y')}
          autoFocus
        />
      </div>
    </Dialog>
  )
}
