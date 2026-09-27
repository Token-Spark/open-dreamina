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

import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

/** 筛选条中的圆角 pill 按钮（状态 / 档位 / 开关筛选共用样式）。 */
export function FilterPill({
  icon: Icon,
  label,
  count,
  active,
  onClick,
}: {
  icon?: LucideIcon
  label: string
  count?: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-all',
        active
          ? 'border-accent bg-accent/10 text-fg-primary'
          : 'border-border text-fg-muted hover:bg-bg-tertiary hover:text-fg-secondary',
      )}
    >
      {Icon && <Icon className="h-3 w-3" />}
      {label}
      {count != null && <span className="tabular-nums text-fg-muted">{count}</span>}
    </button>
  )
}
