import { useMemo } from 'react'
import { Sparkles, ChevronDown } from 'lucide-react'
import { Dropdown, DropdownItem } from '@/components/ui/Dropdown'
import { useProviders } from '@/hooks/useProviders'
import { modelsForCategory, type ContentMode } from '@/lib/generation'

export interface ModelPickerProps {
  mode: ContentMode
  providerSlug: string
  modelId: string
  onProviderChange: (slug: string) => void
  onModelChange: (modelId: string) => void
  disabled?: boolean
  placement?: 'top' | 'bottom'
}

export function ModelPicker({
  mode,
  providerSlug,
  modelId,
  onProviderChange,
  onModelChange,
  disabled,
  placement = 'bottom',
}: ModelPickerProps) {
  const { data: providers, isLoading } = useProviders()
  const activeProviders = useMemo(() => (providers ?? []).filter((p) => p.is_active), [providers])
  const currentProvider = useMemo(
    () => activeProviders.find((p) => p.slug === providerSlug),
    [activeProviders, providerSlug],
  )
  const models = useMemo(() => modelsForCategory(currentProvider, mode), [currentProvider, mode])
  const currentModel = useMemo(() => models.find((m) => m.id === modelId), [models, modelId])
  // 是否任意 active provider 在当前模式下有可用模型：决定按钮是否可点。
  // 不能只看 currentProvider，否则默认 provider 与 mode 不匹配时按钮会被禁用，
  // 用户无法打开下拉框切换到匹配的 provider。
  const hasAnyModel = useMemo(
    () => activeProviders.some((p) => modelsForCategory(p, mode).length > 0),
    [activeProviders, mode],
  )

  return (
    <Dropdown
      placement={placement}
      opaque
      trigger={
        <button
          type="button"
          disabled={disabled || isLoading || !hasAnyModel}
          className="flex h-9 max-w-[11rem] items-center gap-1.5 rounded-btn border border-border bg-bg-tertiary/70 px-3 text-sm text-fg-secondary transition-colors hover:text-fg-primary disabled:opacity-50"
        >
          <Sparkles className="h-4 w-4" />
          <span className="truncate">{currentModel?.label ?? '选择模型'}</span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0" />
        </button>
      }
    >
      <div className="space-y-1">
        {activeProviders.map((p) => {
          // 当前模式下无模型的 provider 不展示分组头，避免出现“图片 provider + 视频模式”这类误导项
          const groupModels = modelsForCategory(p, mode)
          if (groupModels.length === 0) return null
          return (
            <div key={p.id}>
              <div className="px-3 py-1 text-xs font-medium text-fg-muted">{p.name}</div>
              {groupModels.map((m) => (
                <DropdownItem
                  key={m.id}
                  active={p.slug === providerSlug && m.id === modelId}
                  className="py-2.5"
                  onClick={() => {
                    onProviderChange(p.slug)
                    onModelChange(m.id)
                  }}
                >
                  {m.label}
                </DropdownItem>
              ))}
            </div>
          )
        })}
      </div>
    </Dropdown>
  )
}
