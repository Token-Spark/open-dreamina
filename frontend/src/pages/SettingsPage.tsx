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
import type * as React from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, ShieldCheck } from 'lucide-react'
import {
  backupSystem,
  getSystemHealth,
  getSystemSettings,
  updateSystemSettings,
  type SystemSettings,
} from '@/api/system'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { cn } from '@/lib/utils'
import { ProvidersTab } from './settings/ProvidersTab'

export function SettingsPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const tab = location.pathname.includes('general') ? 'general' : 'providers'

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight text-fg-primary">设置</h1>
        <p className="mt-1 text-sm text-fg-secondary">管理模型接入与系统配置</p>
      </div>
      <div className="mb-5 flex gap-1 rounded-btn border border-border bg-bg-secondary p-1">
        <TabBtn active={tab === 'providers'} onClick={() => navigate('/settings/providers')}>
          模型接入
        </TabBtn>
        <TabBtn active={tab === 'general'} onClick={() => navigate('/settings/general')}>
          系统设置
        </TabBtn>
      </div>
      {tab === 'providers' ? <ProvidersTab /> : <GeneralTab />}
    </div>
  )
}

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'rounded-btn px-4 py-1.5 text-sm font-medium transition-all',
        active ? 'bg-bg-tertiary text-fg-primary shadow-soft' : 'text-fg-secondary hover:text-fg-primary',
      )}
    >
      {children}
    </button>
  )
}

/* ------------------------------ General tab ------------------------------ */

function GeneralTab() {
  const { data: settings } = useQuery({ queryKey: ['system', 'settings'], queryFn: getSystemSettings })
  const { data: health } = useQuery({ queryKey: ['system', 'health'], queryFn: getSystemHealth, refetchInterval: 30000 })
  const qc = useQueryClient()
  const [form, setForm] = useState<SystemSettings | null>(null)

  useEffect(() => {
    if (settings) setForm(settings)
  }, [settings])

  const updateMut = useMutation({
    mutationFn: updateSystemSettings,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['system', 'settings'] })
      toast('设置已保存', 'success')
    },
    onError: (e) => toast(toApiError(e).message, 'error'),
  })
  const backupMut = useMutation({
    mutationFn: backupSystem,
    onSuccess: () => toast('备份已创建', 'success'),
    onError: (e) => toast(toApiError(e).message, 'error'),
  })

  if (!form) return <p className="py-12 text-center text-sm text-fg-muted"><span className="animate-pulse">加载中…</span></p>

  return (
    <div className="space-y-5">
      <Card className="space-y-4 p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-fg-primary">
          <ShieldCheck className="h-4 w-4" />
          系统状态
        </h2>
        <div className="grid grid-cols-3 gap-3">
          <HealthItem label="数据库" ok={health?.database === 'ok'} />
          <HealthItem label="Redis" ok={health?.redis === 'ok'} />
          <HealthItem label="Worker" ok={health?.worker === 'ok'} />
        </div>
      </Card>

      <Card className="space-y-4 p-5">
        <h2 className="text-sm font-semibold text-fg-primary">默认配置</h2>
        <div className="grid grid-cols-2 gap-3">
          <Field label="最大并发任务数">
            <Input
              type="number"
              min={1}
              max={8}
              value={form.max_concurrent_tasks ?? 2}
              onChange={(e) => setForm({ ...form, max_concurrent_tasks: Number(e.target.value) })}
            />
          </Field>
        </div>
        <div className="flex justify-end">
          <Button onClick={() => updateMut.mutate(form)} disabled={updateMut.isPending}>
            保存设置
          </Button>
        </div>
      </Card>

      <Card className="space-y-3 p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-fg-primary">
          <Database className="h-4 w-4" />
          数据备份
        </h2>
        <p className="text-xs leading-relaxed text-fg-secondary">
          手动创建一次数据库快照，保留最近 3 份手动备份。
        </p>
        <div className="flex justify-end">
          <Button variant="secondary" onClick={() => backupMut.mutate()} disabled={backupMut.isPending}>
            立即备份
          </Button>
        </div>
      </Card>
    </div>
  )
}

function HealthItem({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="rounded-btn border border-border bg-bg-tertiary p-3.5">
      <p className="text-xs text-fg-muted">{label}</p>
      <p className={cn('mt-1 text-sm font-semibold', ok ? 'text-success' : 'text-error')}>
        {ok ? '正常' : '异常'}
      </p>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  )
}
