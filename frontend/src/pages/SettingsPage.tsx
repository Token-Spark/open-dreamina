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
import { useProviders } from '@/hooks/useProviders'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select } from '@/components/ui/Select'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { cn } from '@/lib/utils'
import { ProvidersTab } from './settings/ProvidersTab'

export function SettingsPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const tab = location.pathname.includes('general') ? 'general' : 'providers'

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <h1 className="mb-4 text-lg font-medium tracking-tight">设置</h1>
      <div className="mb-4 flex gap-1 rounded-btn border border-border bg-bg-secondary p-1">
        <TabBtn active={tab === 'providers'} onClick={() => navigate('/settings/providers')}>
          服务提供商
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
        'rounded-btn px-4 py-1.5 text-sm transition-colors',
        active ? 'bg-bg-tertiary text-fg-primary' : 'text-fg-secondary hover:text-fg-primary',
      )}
    >
      {children}
    </button>
  )
}

/* ------------------------------ General tab ------------------------------ */

function GeneralTab() {
  const { data: providers } = useProviders()
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

  if (!form) return <p className="py-12 text-center text-sm text-fg-muted">加载中…</p>

  return (
    <div className="space-y-4">
      <Card className="space-y-4 p-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-fg-primary">
          <ShieldCheck className="h-4 w-4" />
          系统状态
        </h2>
        <div className="grid grid-cols-3 gap-3">
          <HealthItem label="数据库" ok={health?.database === 'ok'} />
          <HealthItem label="Redis" ok={health?.redis === 'ok'} />
          <HealthItem label="Worker" ok={health?.worker === 'ok'} />
        </div>
      </Card>

      <Card className="space-y-4 p-4">
        <h2 className="text-sm font-medium text-fg-primary">默认配置</h2>
        <div className="grid grid-cols-2 gap-3">
          <Field label="默认服务提供商">
            <Select
              value={form.default_provider ?? ''}
              onChange={(e) => setForm({ ...form, default_provider: e.target.value })}
            >
              <option value="">未设置</option>
              {(providers ?? []).filter((p) => p.is_active).map((p) => (
                <option key={p.id} value={p.slug}>
                  {p.name}
                </option>
              ))}
            </Select>
          </Field>
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

      <Card className="space-y-3 p-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-fg-primary">
          <Database className="h-4 w-4" />
          数据备份
        </h2>
        <p className="text-xs text-fg-secondary">
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
    <div className="rounded-btn border border-border bg-bg-tertiary p-3">
      <p className="text-xs text-fg-muted">{label}</p>
      <p className={cn('mt-1 text-sm font-medium', ok ? 'text-success' : 'text-error')}>
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
