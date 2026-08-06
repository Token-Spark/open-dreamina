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
