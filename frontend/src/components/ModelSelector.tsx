import { useMemo } from 'react'
import { useProviders } from '@/hooks/useProviders'
import { modelsForCategory } from '@/lib/generation'
import type { ContentMode } from '@/lib/generation'
import { Select } from '@/components/ui/Select'
import { Label } from '@/components/ui/Label'
import { cn } from '@/lib/utils'

export interface ModelSelectorProps {
  /** 当前内容模式（图片/视频），决定模型列表筛选范围。 */
  mode: ContentMode
  providerSlug: string
  modelId: string
  onProviderChange: (slug: string) => void
  onModelChange: (modelId: string) => void
  className?: string
}

export function ModelSelector({
  mode,
  providerSlug,
  modelId,
  onProviderChange,
  onModelChange,
  className,
}: ModelSelectorProps) {
  const { data: providers, isLoading } = useProviders()
  const activeProviders = useMemo(
    () => (providers ?? []).filter((p) => p.is_active),
    [providers],
  )

  const currentProvider = useMemo(
    () => activeProviders.find((p) => p.slug === providerSlug),
    [activeProviders, providerSlug],
  )

  // 需求2：按内容模式(图片/视频)筛选可用模型，而非具体任务类型
  const models = useMemo(
    () => modelsForCategory(currentProvider, mode),
    [currentProvider, mode],
  )

  return (
    <div className={cn('grid grid-cols-2 gap-3', className)}>
      <div className="space-y-1.5">
        <Label>服务提供商</Label>
        <Select
          value={providerSlug}
          onChange={(e) => onProviderChange(e.target.value)}
          disabled={isLoading || activeProviders.length === 0}
        >
          {activeProviders.length === 0 && <option value="">暂无可用服务</option>}
          {activeProviders.map((p) => (
            <option key={p.id} value={p.slug}>
              {p.name}
            </option>
          ))}
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label>模型</Label>
        <Select
          value={modelId}
          onChange={(e) => onModelChange(e.target.value)}
          disabled={models.length === 0}
        >
          {models.length === 0 && <option value="">该模式无可用模型</option>}
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </Select>
      </div>
    </div>
  )
}
