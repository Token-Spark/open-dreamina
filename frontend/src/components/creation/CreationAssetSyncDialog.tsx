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
import { CloudDownload, Loader2, Plus, RefreshCw, Upload, Users } from 'lucide-react'
import type { SyncResult, TeamProject } from '@/api/creationAssets'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Textarea } from '@/components/ui/Textarea'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'

export interface CreationAssetSyncDialogProps {
  open: boolean
  projects: TeamProject[]
  projectsLoading: boolean
  ownerName: string
  qiniuConfigured: boolean
  onClose: () => void
  onSync: (tag: string) => Promise<SyncResult>
  onPull: (tag: string) => Promise<SyncResult>
  onUpdateOwnerName: (name: string) => Promise<void>
  onCreateProject: (name: string, description: string) => Promise<void>
  onRefreshProjects: () => void
}

const STATUS_LABEL: Record<string, string> = {
  synced: '已同步',
  imported: '已导入',
  updated: '已更新',
  up_to_date: '已是最新',
  skipped: '跳过',
  conflict: '冲突',
  failed: '失败',
}

const STATUS_VARIANT: Record<string, 'success' | 'error' | 'warning' | 'default'> = {
  synced: 'success',
  imported: 'success',
  updated: 'success',
  up_to_date: 'default',
  skipped: 'default',
  conflict: 'warning',
  failed: 'error',
}

/** 团队同步弹窗：项目列表 + 按项目推送/拉取 + 新建项目 + 逐条结果。 */
export function CreationAssetSyncDialog({
  open,
  projects,
  projectsLoading,
  ownerName,
  qiniuConfigured,
  onClose,
  onSync,
  onPull,
  onUpdateOwnerName,
  onCreateProject,
  onRefreshProjects,
}: CreationAssetSyncDialogProps) {
  const [selectedTag, setSelectedTag] = useState('')
  const [nameDraft, setNameDraft] = useState(ownerName)
  const [busy, setBusy] = useState<'sync' | 'pull' | null>(null)
  const [result, setResult] = useState<SyncResult | null>(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')

  useEffect(() => {
    if (open) {
      setNameDraft(ownerName)
      setResult(null)
      setSelectedTag('')
    }
  }, [open, ownerName])

  const effectiveTag = selectedTag || projects[0]?.tag || ''

  async function run(kind: 'sync' | 'pull') {
    if (!effectiveTag) {
      toast('请先选择项目', 'error')
      return
    }
    setBusy(kind)
    setResult(null)
    try {
      // 展示名有修改时先保存，让本次同步的 manifest 带上最新名称
      if (nameDraft.trim() && nameDraft.trim() !== ownerName) {
        await onUpdateOwnerName(nameDraft.trim())
      }
      const res = kind === 'sync' ? await onSync(effectiveTag) : await onPull(effectiveTag)
      setResult(res)
      const ok = res.items.filter(
        (i) => i.status === 'synced' || i.status === 'imported' || i.status === 'updated',
      ).length
      const conflicts = res.items.filter((i) => i.status === 'conflict').length
      toast(
        `${kind === 'sync' ? '同步' : '拉取'}完成：${ok} 个资产${conflicts > 0 ? `，${conflicts} 个冲突` : ''}`,
        conflicts > 0 ? 'warning' : 'success',
      )
    } catch (e) {
      toast(toApiError(e).message, 'error')
    } finally {
      setBusy(null)
    }
  }

  async function handleCreateProject() {
    if (!newName.trim()) {
      toast('请填写项目名称', 'error')
      return
    }
    setCreating(true)
    try {
      await onCreateProject(newName.trim(), newDesc.trim())
      toast('项目已创建', 'success')
      setNewName('')
      setNewDesc('')
    } catch (e) {
      toast(toApiError(e).message, 'error')
    } finally {
      setCreating(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="团队项目"
      description="项目即云端共享目录。推送本地资产供成员拉取；云端对象按创建者隔离，乐观锁保证绝不盲覆盖。"
      className="max-w-2xl"
    >
      <div className="space-y-4 py-2">
        {!qiniuConfigured && (
          <div className="rounded-btn border border-error/30 bg-error/10 px-3 py-2 text-xs text-error">
            未检测到七牛云配置，请在后端 .env 中设置 QINIU_* 环境变量并重启服务后再使用同步。
          </div>
        )}

        <div className="space-y-1.5">
          <Label>我的名称（团队成员看到的署名）</Label>
          <Input
            value={nameDraft}
            onChange={(e) => setNameDraft(e.target.value)}
            maxLength={50}
            placeholder="如：小李"
          />
        </div>

        {/* 项目列表 */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label>选择项目</Label>
            <Button variant="ghost" size="sm" onClick={onRefreshProjects} disabled={projectsLoading}>
              <RefreshCw className={`h-3.5 w-3.5 ${projectsLoading ? 'animate-spin' : ''}`} />
              刷新
            </Button>
          </div>
          {projects.length === 0 && !projectsLoading && (
            <p className="text-xs text-fg-muted">
              暂无云端项目，可在下方新建；也可直接对资产打的任意标签推送（自动建目录）
            </p>
          )}
          <div className="grid max-h-44 grid-cols-1 gap-1.5 overflow-auto">
            {projects.map((p) => (
              <button
                key={p.tag}
                type="button"
                onClick={() => setSelectedTag(p.tag)}
                className={`flex items-center justify-between gap-2 rounded-btn border px-3 py-2 text-left transition-colors ${
                  effectiveTag === p.tag
                    ? 'border-accent bg-accent/10'
                    : 'border-border hover:border-fg-muted'
                }`}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm text-fg-primary">{p.name}</span>
                    {p.members.length > 0 && (
                      <span className="inline-flex shrink-0 items-center gap-1 text-[11px] text-fg-muted">
                        <Users className="h-3 w-3" />
                        {p.members.length}
                      </span>
                    )}
                  </div>
                  {p.description && (
                    <p className="truncate text-xs text-fg-muted">{p.description}</p>
                  )}
                </div>
                <span className="shrink-0 text-[11px] text-fg-muted">
                  {p.created_by ? `由 ${p.created_by} 创建` : ''}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* 推送 / 拉取 */}
        <div className="flex gap-2">
          <Button
            onClick={() => run('sync')}
            disabled={busy != null || !qiniuConfigured || !effectiveTag}
            className="flex-1"
          >
            {busy === 'sync' ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            推送该项目资产
          </Button>
          <Button
            variant="secondary"
            onClick={() => run('pull')}
            disabled={busy != null || !qiniuConfigured || !effectiveTag}
            className="flex-1"
          >
            {busy === 'pull' ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <CloudDownload className="h-4 w-4" />
            )}
            拉取该项目资产
          </Button>
        </div>

        {result && (
          <div className="max-h-48 space-y-1 overflow-auto rounded-btn border border-border bg-bg-tertiary p-2">
            {result.items.length === 0 && (
              <p className="px-1 py-2 text-xs text-fg-muted">云端该项目下没有可拉取的新资产</p>
            )}
            {result.items.map((item) => (
              <div key={`${item.asset_id}-${item.name}`} className="flex items-center gap-2 px-1 py-1 text-xs">
                <Badge variant={STATUS_VARIANT[item.status] ?? 'default'}>
                  {STATUS_LABEL[item.status] ?? item.status}
                </Badge>
                <span className="flex-1 truncate text-fg-secondary">
                  {item.name}
                  {item.version != null ? `（v${item.version}）` : ''}
                </span>
                {item.message && (
                  <span className="max-w-[50%] truncate text-fg-muted" title={item.message}>
                    {item.message}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* 新建项目 */}
        <div className="space-y-1.5 rounded-btn border border-border bg-bg-tertiary p-3">
          <Label>新建项目</Label>
          <div className="flex gap-2">
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="项目名称（如短剧名）"
              maxLength={50}
              className="flex-1"
            />
            <Button size="sm" onClick={handleCreateProject} disabled={creating || !qiniuConfigured}>
              {creating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              创建
            </Button>
          </div>
          <Textarea
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            placeholder="项目简介（可选）"
            rows={2}
          />
        </div>
      </div>
    </Dialog>
  )
}
