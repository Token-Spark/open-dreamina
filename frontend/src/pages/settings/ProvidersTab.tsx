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
import { ExternalLink, Plus, Pencil, Trash2, CheckCircle2, PlusCircle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useDeleteProvider, useProviders } from '@/hooks/useProviders'
import { getDreaminaCliStatus } from '@/api/system'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import {
  MODEL_SERVICES,
  providerModels,
  type ModelService,
} from '@/lib/generation'
import type { Provider } from '@/api/providers'
import { cn } from '@/lib/utils'
import { ServiceActivationDialog } from './ServiceActivationDialog'
import { DreaminaCliSetup } from './DreaminaCliSetup'

/** 卡片 + 已有 Provider 的合并视图。 */
interface ServiceCardData {
  service: ModelService | null
  provider: Provider | null
  isCustom: boolean
}

export function ProvidersTab() {
  const { data: providers, isLoading } = useProviders()
  const deleteProvider = useDeleteProvider()

  // 即梦 CLI 环境状态（worker 节点）：未就绪时在顶部展示安装/登录引导
  const { data: cliStatus } = useQuery({
    queryKey: ['dreamina-cli-status'],
    queryFn: getDreaminaCliStatus,
    retry: false,
  })
  const showCliSetup = !!cliStatus && !cliStatus.worker_offline && (!cliStatus.installed || !cliStatus.logged_in)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [activeService, setActiveService] = useState<ModelService | null>(null)
  const [activeProvider, setActiveProvider] = useState<Provider | null>(null)

  // 合并目录服务与已配置 Provider：目录中的服务按 slug 匹配 Provider，
  // 目录外的已存在 Provider 作为自定义卡片追加。
  const cards = useMemo<ServiceCardData[]>(() => {
    const list: ServiceCardData[] = MODEL_SERVICES.map((service) => ({
      service,
      provider: (providers ?? []).find((p) => p.slug === service.slug) ?? null,
      isCustom: false,
    }))
    const catalogSlugs = new Set(MODEL_SERVICES.map((s) => s.slug))
    for (const p of providers ?? []) {
      if (!catalogSlugs.has(p.slug)) {
        list.push({ service: null, provider: p, isCustom: true })
      }
    }
    return list
  }, [providers])

  function openActivate(service: ModelService) {
    setActiveService(service)
    setActiveProvider(null)
    setDialogOpen(true)
  }
  function openEdit(service: ModelService | null, provider: Provider) {
    setActiveService(service)
    setActiveProvider(provider)
    setDialogOpen(true)
  }
  function openCustom() {
    setActiveService(null)
    setActiveProvider(null)
    setDialogOpen(true)
  }
  function handleDelete(p: Provider) {
    deleteProvider.mutate(p.id, {
      onSuccess: () => toast('已删除', 'success'),
      onError: (e) => toast(toApiError(e).message, 'error'),
    })
  }

  if (isLoading) {
    return <p className="py-12 text-center text-sm text-fg-muted">加载中…</p>
  }

  return (
    <div className="space-y-4">
      {/* 即梦 CLI 环境未就绪时提供安装 / 登录引导 */}
      {showCliSetup && <DreaminaCliSetup />}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((c) => (
          <ServiceCard
            key={c.service?.slug ?? c.provider?.id ?? 'unknown'}
            data={c}
            onActivate={() => c.service && openActivate(c.service)}
            onEdit={() => c.provider && openEdit(c.service, c.provider)}
            onDelete={() => c.provider && handleDelete(c.provider)}
          />
        ))}
        {/* 添加自定义服务卡片 */}
        <AddCustomCard onClick={openCustom} />
      </div>

      <ServiceActivationDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        service={activeService}
        existingProvider={activeProvider}
      />
    </div>
  )
}

function ServiceCard({
  data,
  onActivate,
  onEdit,
  onDelete,
}: {
  data: ServiceCardData
  onActivate: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  const { service, provider, isCustom } = data
  const configured = !!provider
  const name = service?.name ?? provider?.name ?? '未知服务'
  const vendor = service?.vendor ?? '自定义'
  const description = service?.description ?? '用户自定义的服务提供商'
  const modes = service?.modes ?? []
  const models = provider ? providerModels(provider) : (service?.models ?? [])
  const docsUrl = service?.docsUrl

  return (
    <Card className={cn('flex flex-col p-4 transition-colors', configured && 'border-success/30')}>
      {/* 头部：厂商 + 状态 */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline">{vendor}</Badge>
          {modes.map((m) => (
            <Badge key={m}>{m === 'image' ? '图片' : '视频'}</Badge>
          ))}
          {isCustom && <Badge>自定义</Badge>}
        </div>
        <StatusBadge configured={configured} />
      </div>

      {/* 名称 + 描述 */}
      <div className="mt-2.5 flex-1">
        <h3 className="text-sm font-medium text-fg-primary">{name}</h3>
        <p className="mt-1 line-clamp-2 text-xs text-fg-secondary">{description}</p>
        {docsUrl && (
          <a
            href={docsUrl}
            target="_blank"
            rel="noreferrer"
            className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-fg-muted transition-colors hover:text-fg-primary"
          >
            查看文档 <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>

      {/* 模型列表 */}
      {models.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1">
          {models.slice(0, 4).map((m) => (
            <span
              key={m.id}
              className="rounded-full bg-bg-tertiary px-1.5 py-0.5 text-[10px] text-fg-secondary"
              title={m.id}
            >
              {m.label}
            </span>
          ))}
          {models.length > 4 && (
            <span className="rounded-full bg-bg-tertiary px-1.5 py-0.5 text-[10px] text-fg-muted">
              +{models.length - 4}
            </span>
          )}
        </div>
      )}

      {/* 操作区 */}
      <div className="mt-3 flex items-center gap-2 border-t border-border pt-3">
        {!configured ? (
          <Button size="sm" className="flex-1" onClick={onActivate}>
            <PlusCircle className="h-3.5 w-3.5" />
            激活
          </Button>
        ) : (
          <>
            <div className="ml-auto flex items-center gap-1">
              <Button variant="outline" size="sm" onClick={onEdit}>
                <Pencil className="h-3.5 w-3.5" />
                编辑
              </Button>
              <Button variant="ghost" size="icon" onClick={onDelete} aria-label="删除">
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </>
        )}
      </div>
    </Card>
  )
}

function StatusBadge({ configured }: { configured: boolean }) {
  if (!configured) return <Badge variant="outline">未激活</Badge>
  return <Badge variant="success"><CheckCircle2 className="h-3 w-3" />已激活</Badge>
}

function AddCustomCard({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex min-h-[180px] flex-col items-center justify-center gap-2 rounded-card border border-dashed border-border p-4',
        'text-fg-muted transition-colors hover:border-fg-muted hover:text-fg-secondary',
      )}
    >
      <Plus className="h-6 w-6" />
      <span className="text-sm">添加自定义服务</span>
      <span className="text-xs text-fg-muted">不在目录中的模型服务</span>
    </button>
  )
}
