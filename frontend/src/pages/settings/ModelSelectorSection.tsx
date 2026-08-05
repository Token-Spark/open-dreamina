import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import {
  MODE_TASK_TYPES,
  type ContentMode,
  type ModelService,
} from '@/lib/generation'
import type { TaskType } from '@/api/tasks'

/** 服务支持的内容模式 → 任务类型列表（数据驱动，避免硬编码 if-else）。 */
export function modesToTypes(modes: ContentMode[]): TaskType[] {
  return modes.flatMap((m) => MODE_TASK_TYPES[m])
}

export interface ModelSelectorSectionProps {
  service: ModelService | null
  modelId: string
  onModelIdChange: (v: string) => void
}

/** 模型 ID 录入：可自定义或留空使用目录默认。 */
export function ModelSelectorSection({
  service,
  modelId,
  onModelIdChange,
}: ModelSelectorSectionProps) {
  const defaults = service?.models ?? []
  const placeholder = defaults.length > 0
    ? `留空使用默认（${defaults[0].id}）`
    : '输入模型 ID'

  return (
    <div className="space-y-1.5">
      <Label>模型 ID</Label>
      <Input
        value={modelId}
        onChange={(e) => onModelIdChange(e.target.value)}
        placeholder={placeholder}
      />
      {defaults.length > 0 && (
        <p className="text-xs text-fg-muted">
          可选默认：{defaults.map((m) => m.id).join('、')}
        </p>
      )}
    </div>
  )
}
