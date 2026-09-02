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
import { Pencil, Plus, Trash2, Wand2 } from 'lucide-react'
import {
  createTemplate,
  deleteTemplate,
  listTemplates,
  updateTemplate,
  type Template,
  type TemplateCategory,
  type TemplatePayload,
} from '@/api/templates'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import { Label } from '@/components/ui/Label'
import { Dialog } from '@/components/ui/Dialog'
import { Badge } from '@/components/ui/Badge'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { formatRelativeTime } from '@/lib/utils'

const EMPTY_FORM: TemplatePayload = {
  name: '',
  category: 'image',
  prompt_text: '',
  negative_prompt: '',
}

export function TemplatesPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { data: templates, isLoading } = useQuery({
    queryKey: ['templates'],
    queryFn: listTemplates,
  })
  const [editing, setEditing] = useState<Template | null>(null)
  const [form, setForm] = useState<TemplatePayload>(EMPTY_FORM)
  const [open, setOpen] = useState(false)

  const createMut = useMutation({
    mutationFn: createTemplate,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['templates'] })
      toast('模板已创建', 'success')
      setOpen(false)
    },
    onError: (e) => toast(toApiError(e).message, 'error'),
  })
  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: TemplatePayload }) =>
      updateTemplate(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['templates'] })
      toast('模板已更新', 'success')
      setOpen(false)
    },
    onError: (e) => toast(toApiError(e).message, 'error'),
  })
  const deleteMut = useMutation({
    mutationFn: deleteTemplate,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['templates'] })
      toast('模板已删除', 'success')
    },
    onError: (e) => toast(toApiError(e).message, 'error'),
  })

  function openCreate() {
    setEditing(null)
    setForm(EMPTY_FORM)
    setOpen(true)
  }
  function openEdit(t: Template) {
    setEditing(t)
    setForm({
      name: t.name,
      category: t.category,
      prompt_text: t.prompt_text,
      negative_prompt: t.negative_prompt ?? '',
    })
    setOpen(true)
  }
  function save() {
    if (!form.name.trim() || !form.prompt_text.trim()) {
      return toast('名称和提示词不能为空', 'error')
    }
    if (editing) updateMut.mutate({ id: editing.id, payload: form })
    else createMut.mutate(form)
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-fg-primary">模板库</h1>
          <p className="mt-1 text-sm text-fg-secondary">保存常用提示词以快速复用</p>
        </div>
        <Button size="sm" onClick={openCreate}>
          <Plus className="h-4 w-4" />
          新建模板
        </Button>
      </div>

      {isLoading ? (
        <div className="py-16 text-center text-sm text-fg-muted">
          <span className="animate-pulse">加载中…</span>
        </div>
      ) : !templates || templates.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-card border border-dashed border-border py-16">
          <p className="text-sm font-medium text-fg-secondary">暂无模板</p>
          <p className="mt-1 text-xs text-fg-muted">点击「新建模板」开始保存常用提示词</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {templates.map((t) => (
            <Card key={t.id} className="flex flex-col p-5 transition-all hover:shadow-soft">
              <div className="mb-2 flex items-center justify-between">
                <Badge variant="outline">{t.category === 'image' ? '图片' : '视频'}</Badge>
                <span className="text-[11px] tabular-nums text-fg-muted">
                  {formatRelativeTime(t.updated_at)}
                </span>
              </div>
              <h3 className="text-sm font-semibold text-fg-primary">{t.name}</h3>
              <p className="mt-1.5 line-clamp-3 flex-1 text-xs leading-relaxed text-fg-secondary">
                {t.prompt_text}
              </p>
              <div className="mt-4 flex items-center gap-1">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => navigate('/', { state: { template: t } })}
                >
                  <Wand2 className="h-3.5 w-3.5" />
                  使用
                </Button>
                <Button variant="ghost" size="icon" onClick={() => openEdit(t)} aria-label="编辑">
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => deleteMut.mutate(t.id)}
                  aria-label="删除"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={editing ? '编辑模板' : '新建模板'}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button onClick={save} disabled={createMut.isPending || updateMut.isPending}>
              保存
            </Button>
          </>
        }
      >
        <div className="space-y-3 py-1">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>名称</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label>分类</Label>
              <Select
                value={form.category}
                onChange={(e) =>
                  setForm({ ...form, category: e.target.value as TemplateCategory })
                }
              >
                <option value="image">图片</option>
                <option value="video">视频</option>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>提示词</Label>
            <Textarea
              rows={4}
              value={form.prompt_text}
              onChange={(e) => setForm({ ...form, prompt_text: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label>负面提示词（可选）</Label>
            <Textarea
              rows={2}
              value={form.negative_prompt ?? ''}
              onChange={(e) => setForm({ ...form, negative_prompt: e.target.value })}
            />
          </div>
        </div>
      </Dialog>
    </div>
  )
}
