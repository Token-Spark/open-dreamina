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
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Plus, Search, Trash2 } from 'lucide-react'
import {
  createCanvas,
  deleteCanvas,
  duplicateCanvas,
  listCanvases,
  type CanvasSummary,
} from '@/api/canvas'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Dialog } from '@/components/ui/Dialog'
import { Badge } from '@/components/ui/Badge'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { formatRelativeTime } from '@/lib/utils'

const TEMPLATES = [
  { id: 'blank', name: '空白画布' },
  { id: 'single_image', name: '单图生成' },
  { id: 'img2video', name: '图生视频' },
  { id: 'storyboard', name: '分镜批量' },
]

export function CanvasListPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [templateId, setTemplateId] = useState('blank')

  const { data, isLoading } = useQuery({
    queryKey: ['canvases', search],
    queryFn: () => listCanvases({ search: search || undefined, page_size: 100 }),
  })

  const createMut = useMutation({
    mutationFn: () =>
      createCanvas({ name: newName || undefined, template_id: templateId }),
    onSuccess: (canvas) => {
      qc.invalidateQueries({ queryKey: ['canvases'] })
      toast('画布已创建')
      setOpen(false)
      setNewName('')
      navigate(`/canvas/${canvas.id}`)
    },
    onError: (err) => toast(toApiError(err).message, 'error'),
  })

  const deleteMut = useMutation({
    mutationFn: deleteCanvas,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['canvases'] })
      toast('画布已删除')
    },
    onError: (err) => toast(toApiError(err).message, 'error'),
  })

  const dupMut = useMutation({
    mutationFn: (id: string) => duplicateCanvas(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['canvases'] })
      toast('画布已复制')
    },
    onError: (err) => toast(toApiError(err).message, 'error'),
  })

  const handleDelete = (canvas: CanvasSummary) => {
    if (confirm(`确认删除「${canvas.name}」？`)) {
      deleteMut.mutate(canvas.id)
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 px-6 py-5">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-fg-primary">画布工作流</h1>
          <p className="mt-1 text-sm text-fg-secondary">
            节点式创作画布，自由编排生成流程
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" />
          新建画布
        </Button>
      </div>

      {/* Search bar */}
      <div className="px-6 py-3">
        <div className="relative max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-muted" />
          <Input
            placeholder="搜索画布名称..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Canvas grid */}
      <div className="flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="py-20 text-center text-sm text-fg-secondary">
            <span className="animate-pulse">加载中...</span>
          </div>
        ) : !data?.items?.length ? (
          <div className="flex flex-col items-center justify-center gap-3 py-20">
            <p className="text-sm text-fg-secondary">
              {search ? '没有匹配的画布' : '还没有画布，点击「新建画布」开始'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-5">
            {data.items.map((canvas) => (
              <Card
                key={canvas.id}
                className="group flex cursor-pointer flex-col gap-3 p-5 transition-all hover:border-fg-muted hover:shadow-soft"
                onClick={() => navigate(`/canvas/${canvas.id}`)}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <h3 className="truncate text-sm font-semibold text-fg-primary">
                      {canvas.name}
                    </h3>
                    <p className="mt-0.5 truncate text-xs leading-relaxed text-fg-secondary">
                      {canvas.description || '无描述'}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    <Button
                      variant="ghost"
                      size="icon"
                      title="复制"
                      onClick={(e) => {
                        e.stopPropagation()
                        dupMut.mutate(canvas.id)
                      }}
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      title="删除"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDelete(canvas)
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>

                {canvas.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {canvas.tags.slice(0, 3).map((tag) => (
                      <Badge key={tag} variant="outline">
                      {tag}
                    </Badge>
                    ))}
                  </div>
                )}

                <div className="mt-auto flex items-center justify-between border-t border-border pt-3 text-xs text-fg-muted tabular-nums">
                  <span>{canvas.node_count} 节点</span>
                  <span>v{canvas.version}</span>
                  <span>{formatRelativeTime(canvas.updated_at)}</span>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* New canvas dialog */}
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="新建画布"
        description="选择一个模板开始"
      >
        <div className="flex flex-col gap-4 py-2">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-fg-secondary">画布名称</label>
            <Input
              placeholder="未命名画布"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-fg-secondary">模板</label>
            <div className="grid grid-cols-2 gap-2">
              {TEMPLATES.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTemplateId(t.id)}
                  className={`rounded-btn border px-3 py-2 text-sm font-medium transition-all ${
                    templateId === t.id
                      ? 'border-accent bg-accent/10 text-accent'
                      : 'border-border text-fg-secondary hover:bg-bg-tertiary'
                  }`}
                >
                  {t.name}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 pt-4">
          <Button variant="outline" onClick={() => setOpen(false)}>
            取消
          </Button>
          <Button
            onClick={() => createMut.mutate()}
            disabled={createMut.isPending}
          >
            {createMut.isPending ? '创建中...' : '创建'}
          </Button>
        </div>
      </Dialog>
    </div>
  )
}
