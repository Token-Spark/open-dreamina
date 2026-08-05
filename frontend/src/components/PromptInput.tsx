import { useState } from 'react'
import { ChevronDown, Sparkles } from 'lucide-react'
import { Textarea } from '@/components/ui/Textarea'
import { Label } from '@/components/ui/Label'
import { cn } from '@/lib/utils'

export interface PromptInputProps {
  prompt: string
  negativePrompt: string
  onPromptChange: (v: string) => void
  onNegativeChange: (v: string) => void
  disabled?: boolean
  className?: string
}

export function PromptInput({
  prompt,
  negativePrompt,
  onPromptChange,
  onNegativeChange,
  disabled,
  className,
}: PromptInputProps) {
  const [negativeOpen, setNegativeOpen] = useState(false)

  return (
    <div className={cn('space-y-3', className)}>
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <Label className="flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5" />
            提示词
          </Label>
          <span className="text-xs text-fg-muted">{prompt.length} 字</span>
        </div>
        <Textarea
          value={prompt}
          onChange={(e) => onPromptChange(e.target.value)}
          disabled={disabled}
          placeholder="描述你想要生成的内容，越具体效果越好…"
          rows={5}
        />
      </div>

      <div>
        <button
          type="button"
          onClick={() => setNegativeOpen((v) => !v)}
          className="flex items-center gap-1 text-xs text-fg-secondary transition-colors hover:text-fg-primary"
        >
          <ChevronDown
            className={cn('h-3.5 w-3.5 transition-transform', negativeOpen && 'rotate-180')}
          />
          负面提示词（可选）
        </button>
        {negativeOpen && (
          <div className="mt-2 space-y-1.5">
            <Textarea
              value={negativePrompt}
              onChange={(e) => onNegativeChange(e.target.value)}
              disabled={disabled}
              placeholder="不希望出现的内容，如：模糊、低质量、变形…"
              rows={3}
            />
          </div>
        )}
      </div>
    </div>
  )
}
