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
import { Folder, Loader2 } from 'lucide-react'
import { useReviewFolders } from '@/hooks/useReviews'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select } from '@/components/ui/Select'

export interface CreateReviewSessionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreate: (title: string, folderPath: string) => Promise<void>
}

export function CreateReviewSessionDialog({
  open,
  onOpenChange,
  onCreate,
}: CreateReviewSessionDialogProps) {
  const { data: roots, isLoading } = useReviewFolders()
  const [title, setTitle] = useState('')
  const [folderPath, setFolderPath] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // 展平根目录、子目录、孙目录为可选列表
  const folderOptions = useMemo(() => {
    if (!roots) return []
    const opts: { path: string; label: string; depth: number }[] = []
    for (const root of roots) {
      if (root.exists) {
        opts.push({ path: root.path, label: root.name, depth: 0 })
      }
      for (const sub of root.subdirs) {
        opts.push({ path: sub.path, label: sub.name, depth: 1 })
        for (const sub2 of sub.subdirs ?? []) {
          opts.push({ path: sub2.path, label: sub2.name, depth: 2 })
        }
      }
    }
    return opts
  }, [roots])

  async function handleSubmit() {
    if (!title.trim() || !folderPath) return
    setSubmitting(true)
    try {
      await onCreate(title.trim(), folderPath)
      setTitle('')
      setFolderPath('')
      onOpenChange(false)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="新建审阅会话"
      description="选择外部素材文件夹，系统将自动扫描其中的图片/视频文件"
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!title.trim() || !folderPath || submitting}
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            创建并扫描
          </Button>
        </>
      }
    >
      <div className="space-y-4 py-3">
        <div className="space-y-1.5">
          <Label>会话标题</Label>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="如：EP01 分镜审阅"
            autoFocus
          />
        </div>
        <div className="space-y-1.5">
          <Label>素材文件夹</Label>
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-fg-muted">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              加载可用目录…
            </div>
          ) : folderOptions.length === 0 ? (
            <div className="rounded-btn border border-dashed border-border px-3 py-4 text-center">
              <Folder className="mx-auto mb-1.5 h-5 w-5 text-fg-muted" />
              <p className="text-sm text-fg-secondary">未找到可用目录</p>
              <p className="mt-1 text-xs text-fg-muted">
                请在 .env 中配置 REVIEW_SOURCE_ROOTS 指向素材所在目录
              </p>
            </div>
          ) : (
            <Select
              value={folderPath}
              onChange={(e) => setFolderPath(e.target.value)}
            >
              <option value="">选择文件夹…</option>
              {folderOptions.map((opt) => (
                <option key={opt.path} value={opt.path}>
                  {opt.depth === 0
                    ? opt.label
                    : opt.depth === 1
                      ? `  └ ${opt.label}`
                      : `    └ ${opt.label}`}
                </option>
              ))}
            </Select>
          )}
          {folderPath && (
            <p className="truncate text-xs text-fg-muted">{folderPath}</p>
          )}
        </div>
      </div>
    </Dialog>
  )
}
