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

import { cn } from '@/lib/utils'

export interface ProgressProps {
  /** 0–100 */
  value: number
  className?: string
  /** Apply the breathing-glow animation to the active bar. */
  glow?: boolean
}

export function Progress({ value, className, glow }: ProgressProps) {
  const clamped = Math.max(0, Math.min(100, value))
  return (
    <div
      className={cn(
        'relative h-1.5 w-full overflow-hidden rounded-full bg-bg-tertiary',
        className,
      )}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={cn(
          'h-full rounded-full bg-accent transition-[width] duration-300 ease-out',
          glow && 'progress-glow',
        )}
        style={{ width: `${clamped}%` }}
      />
    </div>
  )
}
