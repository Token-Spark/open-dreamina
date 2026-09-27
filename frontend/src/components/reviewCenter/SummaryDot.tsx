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

/** 会话统计行中的单个统计点：图标 + 名称 + 数值。 */
export function SummaryDot({
  icon: Icon,
  label,
  count,
  className,
}: {
  icon: LucideIcon
  label: string
  count: number
  className?: string
}) {
  return (
    <span className={cn('flex items-center gap-1', className)}>
      <Icon className="h-3 w-3" />
      {label}
      <span className="font-medium">{count}</span>
    </span>
  )
}
