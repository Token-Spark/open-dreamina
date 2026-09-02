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

import { useNavigate } from 'react-router-dom'
import { ChevronUp } from 'lucide-react'
import { useActiveTaskList } from '@/stores/taskStore'
import { Progress } from '@/components/ui/Progress'
import { TASK_TYPE_LABEL } from '@/lib/taskStatus'

/**
 * Bottom bar that persistently shows in-flight task thumbnails.
 * Hidden when no active tasks exist to keep the workspace quiet (spec P2.13).
 */
export function TaskBar() {
  const active = useActiveTaskList()
  const navigate = useNavigate()

  if (active.length === 0) return null

  return (
    <div className="shrink-0 border-t border-border bg-bg-secondary/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-6 py-2.5">
        <button
          type="button"
          onClick={() => navigate('/tasks')}
          className="flex items-center gap-1 rounded-btn px-2 py-1 text-xs font-medium text-fg-secondary transition-all hover:bg-bg-tertiary hover:text-fg-primary"
        >
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-accent text-[10px] font-bold text-bg-primary">
            {active.length}
          </span>
          进行中
          <ChevronUp className="h-3 w-3" />
        </button>

        <div className="flex flex-1 items-center gap-3 overflow-x-auto scrollbar-thin">
          {active.map((t) => (
            <div
              key={t.task.id}
              className="group flex w-56 shrink-0 items-center gap-2 rounded-btn border border-border bg-bg-tertiary px-2.5 py-1.5 text-left"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between">
                  <span className="truncate text-[11px] font-medium text-fg-secondary">
                    {TASK_TYPE_LABEL[t.task.type]}
                  </span>
                  <span className="text-[11px] tabular-nums text-fg-muted">
                    {t.progress}%
                  </span>
                </div>
                <Progress
                  value={t.progress}
                  glow={t.status === 'running'}
                  className="mt-1 h-1"
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
