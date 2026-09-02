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

import { useMemo, useState } from 'react'
import { Loader2, X } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'

export interface CreationAssetBatchTagDialogProps {
  open: boolean
  /** 选中的素材数量（仅用于展示文案）。 */
  count: number
  /** 素材库中已有的全部标签，用于添加时的快捷选择。 */
  existingTags: string[]
  /** 选中素材中出现过的全部标签（去重），用于批量移除。 */
  selectedTags: string[]
  onSubmit: (addTags: string[], removeTags: string[]) => Promise<void>
  onClose: () => void
}

/** 批量修改标签弹窗：为选中素材统一「添加标签」与「移除标签」。
 * 仅在标签集合变化时才更新对应素材。 */
export function CreationAssetBatchTagDialog({
  open,
  count,
  existingTags,
  selectedTags,
  onSubmit,
  onClose,
}: CreationAssetBatchTagDialogProps) {
  const [addTags, setAddTags] = useState<string[]>([])
  const [removeTags, setRemoveTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [showSuggest, setShowSuggest] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  function addTag(raw: string) {
    const t = raw.trim()
    if (t && !addTags.includes(t)) {
      setAddTags((prev) => [...prev, t])
    }
    setTagInput('')
  }

  function toggleRemove(tag: string) {
    setRemoveTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    )
  }

  /** 根据当前输入从已有标签中过滤匹配项作为备选。 */
  const suggestions = useMemo(() => {
    const q = tagInput.trim().toLowerCase()
    return existingTags
      .filter((t) => !addTags.includes(t))
      .filter((t) => (q ? t.toLowerCase().includes(q) : true))
      .slice(0, 8)
  }, [existingTags, addTags, tagInput])

  const hasChanges = addTags.length > 0 || removeTags.length > 0

  async function handleSubmit() {
    if (!hasChanges) return
    setSubmitting(true)
    try {
      await onSubmit(addTags, removeTags)
      onClose()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="批量修改标签"
      description={`为选中的 ${count} 个素材统一添加或移除标签，仅在标签变化时更新。`}
      className="max-w-xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={submitting || !hasChanges}>
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            应用修改
          </Button>
        </>
      }
    >
      <div className="space-y-4 py-2">
        <div className="space-y-1.5">
          <Label>添加标签</Label>
          <div className="flex flex-wrap items-center gap-1.5">
            {addTags.map((t) => (
              <span
                key={t}
                className="inline-flex items-center gap-1 rounded-full border border-accent bg-accent/10 px-2 py-0.5 text-xs text-fg-primary"
              >
                {t}
                <button
                  type="button"
                  onClick={() => setAddTags((prev) => prev.filter((x) => x !== t))}
                  aria-label={`移除添加标签 ${t}`}
                  className="text-fg-muted hover:text-error"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            <div className="relative">
              <Input
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ',') {
                    e.preventDefault()
                    addTag(tagInput)
                  }
                }}
                onFocus={() => setShowSuggest(true)}
                onBlur={() => {
                  if (tagInput) addTag(tagInput)
                  // 延迟关闭以便点击下拉项时 onClick 先触发
                  setTimeout(() => setShowSuggest(false), 150)
                }}
                placeholder="输入后回车添加"
                className="h-7 w-40"
              />
              {showSuggest && suggestions.length > 0 && (
                <div className="absolute left-0 top-full z-10 mt-1 max-h-48 w-48 overflow-auto rounded-btn border border-border bg-bg-secondary shadow-lg">
                  {suggestions.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onMouseDown={(e) => {
                        e.preventDefault()
                        addTag(t)
                      }}
                      className="block w-full px-3 py-1.5 text-left text-xs text-fg-secondary hover:bg-bg-tertiary"
                    >
                      {t}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>移除标签</Label>
          {selectedTags.length === 0 ? (
            <p className="text-xs text-fg-muted">选中的素材暂无标签</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {selectedTags.map((t) => {
                const removing = removeTags.includes(t)
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => toggleRemove(t)}
                    aria-label={removing ? `取消移除 ${t}` : `移除 ${t}`}
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition-colors ${
                      removing
                        ? 'border-error/50 bg-error/10 text-error line-through'
                        : 'border-border bg-bg-tertiary text-fg-secondary hover:border-error/50 hover:text-error'
                    }`}
                  >
                    {t}
                    <X className="h-3 w-3" />
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </Dialog>
  )
}
