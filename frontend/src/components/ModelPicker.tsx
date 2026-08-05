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

  return (
    <Dropdown
      placement={placement}
      trigger={
        <button
          type="button"
          disabled={disabled || isLoading || models.length === 0}
          className="flex h-8 max-w-[10rem] items-center gap-1.5 rounded-btn border border-border bg-bg-tertiary/70 px-2.5 text-xs text-fg-secondary transition-colors hover:text-fg-primary disabled:opacity-50"
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span className="truncate">{currentModel?.label ?? '选择模型'}</span>
          <ChevronDown className="h-3 w-3 shrink-0" />
        </button>
      }
    >
      <div className="space-y-1">
        {activeProviders.map((p) => (
          <div key={p.id}>
            <div className="px-2.5 py-1 text-[10px] font-medium text-fg-muted">{p.name}</div>
            {modelsForCategory(p, mode).map((m) => (
              <DropdownItem
                key={m.id}
                active={p.slug === providerSlug && m.id === modelId}
                onClick={() => {
                  onProviderChange(p.slug)
                  onModelChange(m.id)
                }}
              >
                {m.label}
              </DropdownItem>
            ))}
          </div>
        ))}
      </div>
    </Dropdown>
  )
}
