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

import { useEffect, useState, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import {
  createProvider,
  type CreateProviderPayload,
  type Provider,
  type TestProviderOverrides,
  type UpdateProviderPayload,
} from '@/api/providers'
import {
  useSlugOptions,
  useTestProvider,
  useTestProviderBeforeCreate,
  useUpdateProvider,
} from '@/hooks/useProviders'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select } from '@/components/ui/Select'
import { Badge } from '@/components/ui/Badge'
import { Dialog } from '@/components/ui/Dialog'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import {
  type CatalogField,
  type ContentMode,
  type ModelService,
  type ProviderModelConfig,
} from '@/lib/generation'
import {
  modesToTypes,
  ModelSelectorSection,
} from './ModelSelectorSection'
import { DreaminaCliSetup } from './DreaminaCliSetup'

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
  const testBeforeCreate = useTestProviderBeforeCreate()
  const { data: slugOptions, isLoading: slugLoading } = useSlugOptions()

  // 动态字段值：key → value（api_key / base_url / 其他自定义字段）
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({})
  // 自定义服务基础信息
  const [customName, setCustomName] = useState('')
  const [customSlug, setCustomSlug] = useState('')
  // 自定义服务内容模式（图片/视频），由所选 slug 支持的能力约束
  const [customModes, setCustomModes] = useState<ContentMode[]>(['image'])
  // 模型 ID（留空使用目录默认）
  const [modelId, setModelId] = useState('')
  const [testing, setTesting] = useState(false)

  const isCustom = !service
  const isEditing = !!existingProvider
  // 即梦 CLI：需引导安装 + 登录（目录服务或自定义服务选中即梦 CLI 系列 slug；
  // 拆分后视频/图片两个 slug 共用同一套 CLI，dreamina-cli 为遗留 slug 兼容）
  const activeSlug = service?.slug ?? customSlug
  const isDreaminaCli = ['dreamina-cli', 'dreamina-seedance', 'dreamina-seedream'].includes(activeSlug)

  // 当前选中的 slug 元信息（自定义服务下拉选择后）
  const selectedSlugOption = slugOptions?.find((o) => o.slug === customSlug)
  // 该 slug 支持的内容模式；目录服务沿用 service.modes
  const availableModes: ContentMode[] = isCustom
    ? (selectedSlugOption?.modes as ContentMode[] | undefined) ?? ['image']
    : (service!.modes as ContentMode[])

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
    } else if (existingProvider) {
      // 编辑自定义服务：回填已有数据（slug 不可改）
      setCustomName(existingProvider.name)
      setCustomSlug(existingProvider.slug)
      setFieldValues({ api_key: '', base_url: existingProvider.base_url ?? '' })
      const existingModels = (existingProvider.config?.models as ProviderModelConfig[] | undefined) ?? []
      setModelId(existingModels[0]?.id ?? '')
      const types = existingModels[0]?.types ?? []
      const modes: ContentMode[] = []
      if (types.includes('text2img') || types.includes('img2img')) modes.push('image')
      if (types.includes('text2video') || types.includes('img2video')) modes.push('video')
      setCustomModes(modes.length > 0 ? modes : ['image'])
    } else {
      // 新建自定义服务
      setCustomName('')
      setCustomSlug('')
      setCustomModes(['image'])
      setFieldValues({ api_key: '', base_url: '' })
      setModelId('')
    }
  }, [open, service, existingProvider])

  function updateField(key: string, value: string) {
    setFieldValues((v) => ({ ...v, [key]: value }))
  }

  /** 自定义服务：选择 slug 后自动填充默认 base_url 并重置内容模式。 */
  function handleCustomSlugChange(slug: string) {
    setCustomSlug(slug)
    const opt = slugOptions?.find((o) => o.slug === slug)
    if (opt) {
      updateField('base_url', opt.default_base_url)
      if (opt.modes.length > 0) {
        setCustomModes([opt.modes[0] as ContentMode])
      }
    }
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
        types: modesToTypes(service?.modes ?? customModes),
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
      const fieldsForCheck = service?.fields ?? CUSTOM_DEFAULT_FIELDS
      if (!apiKey && fieldsForCheck.some((f) => f.key === 'api_key' && f.required)) {
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

  /** 构建测试用 config（与 handleSave 一致，但不含 models 之外的非敏感字段）。 */
  function buildTestConfig(): Record<string, unknown> {
    const config: Record<string, unknown> = {}
    const trimmedId = modelId.trim()
    if (trimmedId) {
      config.models = [{
        id: trimmedId,
        label: trimmedId,
        types: modesToTypes(service?.modes ?? customModes),
      }]
    }
    for (const f of service?.fields ?? []) {
      if (f.key !== 'api_key' && f.key !== 'base_url' && fieldValues[f.key]) {
        config[f.key] = fieldValues[f.key]
      }
    }
    return config
  }

  function handleTest() {
    if (isEditing && existingProvider) {
      // 已落库：按 id 测试，但用表单当前值覆盖 base_url / api_key，可测未保存的改动
      setTesting(true)
      const overrides: TestProviderOverrides = {
        base_url: (fieldValues.base_url ?? '').trim() || existingProvider.base_url,
      }
      const apiKey = fieldValues.api_key ?? ''
      if (apiKey) overrides.api_key = apiKey
      testProvider.mutate(
        { id: existingProvider.id, overrides },
        {
          onSuccess: (r) => toast(r.success ? '连通正常' : `失败：${r.message}`, r.success ? 'success' : 'error'),
          onError: (e) => toast(toApiError(e).message, 'error'),
          onSettled: () => setTesting(false),
        },
      )
      return
    }
    // 新建模式：before-create 测试，无需先落库
    const slug = service?.slug ?? customSlug.trim()
    if (!slug) return toast('请先选择标识', 'error')
    const apiKey = fieldValues.api_key ?? ''
    const baseUrl = (fieldValues.base_url ?? '').trim() || service?.fields.find((f) => f.key === 'base_url')?.default || ''
    if (!baseUrl) return toast('请填写 API 地址', 'error')
    const requiresKey = (service?.fields ?? CUSTOM_DEFAULT_FIELDS).some(
      (f) => f.key === 'api_key' && f.required,
    )
    if (requiresKey && !apiKey) return toast('请先填写 API Key', 'error')
    setTesting(true)
    testBeforeCreate.mutate(
      { slug, base_url: baseUrl, api_key: apiKey, config: buildTestConfig() },
      {
        onSuccess: (r) => toast(r.success ? '连通正常' : `失败：${r.message}`, r.success ? 'success' : 'error'),
        onError: (e) => toast(toApiError(e).message, 'error'),
        onSettled: () => setTesting(false),
      },
    )
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
          <Button variant="outline" onClick={handleTest} disabled={testing} className="mr-auto">
            {testing ? '测试中…' : '测试连通'}
          </Button>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleSave} disabled={createMut.isPending || updateProvider.isPending}>
            {isEditing ? '保存' : '激活'}
          </Button>
        </>
      }
    >
      <div className="space-y-3 py-1">
        {/* 自定义服务：名称 + 标识（下拉） + 内容模式 */}
        {isCustom && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <FieldRow label="名称">
                <Input value={customName} onChange={(e) => setCustomName(e.target.value)} placeholder="如 我的图服务" />
              </FieldRow>
              <FieldRow label="标识 (slug)">
                <Select
                  value={customSlug}
                  onChange={(e) => handleCustomSlugChange(e.target.value)}
                  disabled={isEditing || slugLoading}
                >
                  <option value="">
                    {slugLoading ? '加载中…' : '请选择'}
                  </option>
                  {slugOptions?.map((o) => (
                    <option key={o.slug} value={o.slug}>
                      {o.display_name}（{o.slug}）
                    </option>
                  ))}
                </Select>
              </FieldRow>
            </div>
            <FieldRow label="内容模式">
              <Select
                value={customModes.join('+')}
                onChange={(e) => setCustomModes(e.target.value.split('+') as ContentMode[])}
              >
                {availableModes.includes('image') && availableModes.includes('video') && (
                  <option value="image+video">图片 + 视频</option>
                )}
                {availableModes.includes('image') && (
                  <option value="image">图片</option>
                )}
                {availableModes.includes('video') && (
                  <option value="video">视频</option>
                )}
              </Select>
              {selectedSlugOption && (
                <p className="text-xs text-fg-muted">
                  该标识支持：{selectedSlugOption.modes.map((m) => (m === 'image' ? '图片' : '视频')).join('、')}
                </p>
              )}
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

        {/* 即梦 CLI：安装 / 登录引导（worker 节点） */}
        {isDreaminaCli && <DreaminaCliSetup />}

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
