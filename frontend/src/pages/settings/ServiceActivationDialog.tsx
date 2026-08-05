import { useEffect, useState, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import {
  createProvider,
  type CreateProviderPayload,
  type Provider,
  type UpdateProviderPayload,
} from '@/api/providers'
import { useTestProvider, useUpdateProvider } from '@/hooks/useProviders'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Badge } from '@/components/ui/Badge'
import { Dialog } from '@/components/ui/Dialog'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import {
  type CatalogField,
  type ModelService,
  type ProviderModelConfig,
} from '@/lib/generation'
import {
  modesToTypes,
  ModelSelectorSection,
} from './ModelSelectorSection'

export interface ServiceActivationDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 目录中的服务定义；为 null 表示自定义服务。 */
  service: ModelService | null
  /** 编辑模式下传入已有 Provider；新建模式为 null。 */
  existingProvider: Provider | null
}

export function ServiceActivationDialog({
  open,
  onOpenChange,
  service,
  existingProvider,
}: ServiceActivationDialogProps) {
  const qc = useQueryClient()
  const updateProvider = useUpdateProvider()
  const testProvider = useTestProvider()

  // 动态字段值：key → value（api_key / base_url / 其他自定义字段）
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({})
  // 自定义服务基础信息
  const [customName, setCustomName] = useState('')
  const [customSlug, setCustomSlug] = useState('')
  // 模型 ID（留空使用目录默认）
  const [modelId, setModelId] = useState('')
  const [testing, setTesting] = useState(false)

  const isCustom = !service
  const isEditing = !!existingProvider

  const createMut = useMutation({
    mutationFn: createProvider,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['providers'] })
      toast('服务已激活', 'success')
      onOpenChange(false)
    },
    onError: (e) => toast(toApiError(e).message, 'error'),
  })

  // 打开时初始化表单
  useEffect(() => {
    if (!open) return
    if (service) {
      // 目录服务：用默认值初始化字段
      const defaults: Record<string, string> = {}
      for (const f of service.fields) {
        if (f.default) defaults[f.key] = f.default
      }
      setFieldValues(defaults)
      if (existingProvider) {
        // 编辑模式：回填 base_url 等字段
        if (existingProvider.base_url) setFieldValues((v) => ({ ...v, base_url: existingProvider.base_url }))
        const existingModels = (existingProvider.config?.models as ProviderModelConfig[] | undefined) ?? []
        setModelId(existingModels[0]?.id ?? '')
      } else {
        setModelId('')
      }
    } else {
      // 自定义服务
      setCustomName('')
      setCustomSlug('')
      setFieldValues({ api_key: '', base_url: '' })
      setModelId('')
    }
  }, [open, service, existingProvider])

  function updateField(key: string, value: string) {
    setFieldValues((v) => ({ ...v, [key]: value }))
  }

  function handleSave() {
    const trimmedId = modelId.trim()
    // 自定义服务无目录可回退，必须填写模型 ID
    if (!service && !trimmedId) {
      return toast('请输入模型 ID', 'error')
    }

    const apiKey = fieldValues.api_key ?? ''
    const baseUrl = (fieldValues.base_url ?? '').trim() || service?.fields.find((f) => f.key === 'base_url')?.default || ''
    const config: Record<string, unknown> = {}
    if (trimmedId) {
      config.models = [{
        id: trimmedId,
        label: trimmedId,
        types: modesToTypes(service?.modes ?? ['image']),
      }]
    }
    // 其他自定义字段写入 config
    for (const f of service?.fields ?? []) {
      if (f.key !== 'api_key' && f.key !== 'base_url' && fieldValues[f.key]) {
        config[f.key] = fieldValues[f.key]
      }
    }

    if (isEditing && existingProvider) {
      const payload: UpdateProviderPayload = {
        name: service?.name ?? customName.trim(),
        base_url: baseUrl,
        is_active: true,
        config,
      }
      if (apiKey) payload.api_key = apiKey
      updateProvider.mutate(
        { id: existingProvider.id, payload },
        {
          onSuccess: () => { toast('已更新', 'success'); onOpenChange(false) },
          onError: (e) => toast(toApiError(e).message, 'error'),
        },
      )
    } else {
      // 新建
      if (!apiKey && service?.fields.some((f) => f.key === 'api_key' && f.required)) {
        return toast('请输入 API Key', 'error')
      }
      const name = service?.name ?? customName.trim()
      const slug = service?.slug ?? customSlug.trim()
      if (!name || !slug) return toast('名称与标识不能为空', 'error')
      if (!baseUrl) return toast('请填写 API 地址', 'error')
      const payload: CreateProviderPayload = {
        name,
        slug,
        base_url: baseUrl,
        api_key: apiKey,
        is_active: true,
        config,
      }
      createMut.mutate(payload)
    }
  }

  function handleTest() {
    if (!existingProvider) return
    setTesting(true)
    testProvider.mutate(existingProvider.id, {
      onSuccess: (r) => toast(r.success ? '连通正常' : `失败：${r.message}`, r.success ? 'success' : 'error'),
      onError: (e) => toast(toApiError(e).message, 'error'),
      onSettled: () => setTesting(false),
    })
  }

  const title = isEditing
    ? `编辑 · ${service?.name ?? existingProvider?.name ?? '服务'}`
    : service
      ? `激活 · ${service.name}`
      : '添加自定义服务'

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={service?.description}
      className="max-w-xl"
      footer={
        <>
          {isEditing && (
            <Button variant="outline" onClick={handleTest} disabled={testing} className="mr-auto">
              {testing ? '测试中…' : '测试连通'}
            </Button>
          )}
          <Button variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleSave} disabled={createMut.isPending || updateProvider.isPending}>
            {isEditing ? '保存' : '激活'}
          </Button>
        </>
      }
    >
      <div className="space-y-3 py-1">
        {/* 自定义服务：名称 + 标识 */}
        {isCustom && (
          <div className="grid grid-cols-2 gap-3">
            <FieldRow label="名称">
              <Input value={customName} onChange={(e) => setCustomName(e.target.value)} placeholder="如 我的图服务" />
            </FieldRow>
            <FieldRow label="标识 (slug)">
              <Input
                value={customSlug}
                onChange={(e) => setCustomSlug(e.target.value)}
                placeholder="如 my-image-svc"
                disabled={isEditing}
              />
            </FieldRow>
          </div>
        )}

        {/* 目录服务的元信息 */}
        {service && (
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{service.vendor}</Badge>
            {service.modes.map((m) => (
              <Badge key={m}>{m === 'image' ? '图片' : '视频'}</Badge>
            ))}
            {service.docsUrl && (
              <a
                href={service.docsUrl}
                target="_blank"
                rel="noreferrer"
                className="ml-auto inline-flex items-center gap-1 text-xs text-fg-muted transition-colors hover:text-fg-primary"
              >
                文档 <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        )}

        {/* 动态字段（由 JSON 驱动） */}
        <DynamicFields
          fields={service?.fields ?? CUSTOM_DEFAULT_FIELDS}
          values={fieldValues}
          editing={isEditing}
          onChange={updateField}
        />

        {/* 模型 ID 录入 */}
        <ModelSelectorSection
          service={service}
          modelId={modelId}
          onModelIdChange={setModelId}
        />
      </div>
    </Dialog>
  )
}

/** 自定义服务的默认字段。 */
const CUSTOM_DEFAULT_FIELDS: CatalogField[] = [
  { key: 'api_key', label: 'API Key', kind: 'secret', required: true, placeholder: '输入 API Key' },
  { key: 'base_url', label: 'API 地址', kind: 'url', required: true, placeholder: 'https://api.example.com' },
]

function FieldRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  )
}

/** 根据 JSON 字段定义动态渲染输入框。 */
function DynamicFields({
  fields,
  values,
  editing,
  onChange,
}: {
  fields: CatalogField[]
  values: Record<string, string>
  editing: boolean
  onChange: (key: string, value: string) => void
}) {
  return (
    <div className="space-y-2">
      {fields.map((f) => {
        const isSecret = f.kind === 'secret'
        const label = isSecret && editing ? `${f.label}（留空则保持不变）` : f.label
        return (
          <FieldRow key={f.key} label={label}>
            <Input
              type={isSecret ? 'password' : 'text'}
              value={values[f.key] ?? ''}
              onChange={(e) => onChange(f.key, e.target.value)}
              placeholder={f.placeholder}
            />
          </FieldRow>
        )
      })}
    </div>
  )
}
