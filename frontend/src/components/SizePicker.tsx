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

import { ChevronDown } from 'lucide-react'
import { Dropdown } from '@/components/ui/Dropdown'
import { cn } from '@/lib/utils'
import {
  ASPECT_RATIOS_BY_MODE,
  RESOLUTIONS_BY_MODE,
  sizeFromRatioResolution,
  type AspectRatio,
  type ContentMode,
  type Resolution,
} from '@/lib/generation'

export interface SizePickerProps {
  mode: ContentMode
  aspectRatio: AspectRatio
  resolution: Resolution
  onChange: (ratio: AspectRatio, resolution: Resolution) => void
  disabled?: boolean
  placement?: 'top' | 'bottom'
}

export function SizePicker({
  mode,
  aspectRatio,
  resolution,
  onChange,
  disabled,
  placement = 'bottom',
}: SizePickerProps) {
  const ratios = ASPECT_RATIOS_BY_MODE[mode]
  const resolutions = RESOLUTIONS_BY_MODE[mode]
  // 当前状态若不属于该模式（如切换 mode 时残留），回退到模式默认
  const ratioDef = ratios.find((r) => r.value === aspectRatio) ?? ratios[0]
  const resDef = resolutions.find((r) => r.value === resolution) ?? resolutions[Math.min(1, resolutions.length - 1)]
  const effectiveRatio = ratioDef.value
  const effectiveResolution = resDef.value

  return (
    <Dropdown
      placement={placement}
      opaque
      trigger={
        <button
          type="button"
          disabled={disabled}
          className="flex h-9 items-center gap-1.5 rounded-btn border border-border bg-bg-tertiary/70 px-3 text-sm text-fg-secondary transition-colors hover:text-fg-primary disabled:opacity-50"
        >
          <span className="font-medium">{ratioDef.label}</span>
          <span className="text-fg-muted">{resDef.value}</span>
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
      }
      align="start"
    >
      <div className="w-80 space-y-3 p-1">
        <div>
          <div className="mb-1.5 px-1 text-xs font-medium text-fg-muted">选择比例</div>
          <div className="grid grid-cols-4 gap-1.5">
            {ratios.map((r) => (
              <button
                key={r.value}
                type="button"
                onClick={() => onChange(r.value, effectiveResolution)}
                className={cn(
                  'flex flex-col items-center justify-center gap-1.5 rounded-btn border py-2.5 text-xs transition-colors',
                  effectiveRatio === r.value
                    ? 'border-accent bg-accent text-bg-primary'
                    : 'border-border bg-bg-tertiary/50 text-fg-secondary hover:border-fg-muted hover:text-fg-primary',
                )}
              >
                <RatioIcon ratio={r.value} />
                <span>{r.label}</span>
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="mb-1.5 px-1 text-xs font-medium text-fg-muted">选择分辨率</div>
          <div className="grid grid-cols-3 gap-1.5">
            {resolutions.map((r) => (
              <button
                key={r.value}
                type="button"
                onClick={() => onChange(effectiveRatio, r.value)}
                className={cn(
                  'rounded-btn border px-2 py-2 text-sm transition-colors',
                  effectiveResolution === r.value
                    ? 'border-accent bg-accent text-bg-primary'
                    : 'border-border bg-bg-tertiary/50 text-fg-secondary hover:border-fg-muted hover:text-fg-primary',
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div className="text-xs text-fg-muted">
          {mode === 'image' ? '图片' : '视频'}尺寸：
          {(() => {
            const { width, height } = sizeFromRatioResolution(effectiveRatio, effectiveResolution, mode)
            return `${width} × ${height}`
          })()}
        </div>
      </div>
    </Dropdown>
  )
}

function RatioIcon({ ratio }: { ratio: AspectRatio }) {
  // 长边统一 24px，短边按真实比例缩放，让各比例差异一目了然
  const map: Record<AspectRatio, string> = {
    auto: 'w-6 h-6 rounded-[2px] border-dashed',
    '21:9': 'w-6 h-[10px] rounded-[2px]',
    '16:9': 'w-6 h-[13px] rounded-[2px]',
    '3:2': 'w-6 h-4 rounded-[2px]',
    '4:3': 'w-6 h-[18px] rounded-[2px]',
    '1:1': 'w-6 h-6 rounded-[2px]',
    '3:4': 'w-[18px] h-6 rounded-[2px]',
    '2:3': 'w-4 h-6 rounded-[2px]',
    '9:16': 'w-[13px] h-6 rounded-[2px]',
  }
  return <div className={cn('border border-current', map[ratio])} />
}
