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
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2">
        <button
          type="button"
          onClick={() => navigate('/tasks')}
          className="flex items-center gap-1 rounded-btn px-2 py-1 text-xs text-fg-secondary transition-colors hover:bg-bg-tertiary hover:text-fg-primary"
        >
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-accent text-[10px] font-bold text-bg-primary">
            {active.length}
          </span>
          进行中
          <ChevronUp className="h-3 w-3" />
        </button>

        <div className="flex flex-1 items-center gap-3 overflow-x-auto scrollbar-thin">
          {active.map((t) => (
            <button
              key={t.task.id}
              type="button"
              onClick={() => navigate('/tasks')}
              className="group flex w-56 shrink-0 items-center gap-2 rounded-btn border border-border bg-bg-tertiary px-2.5 py-1.5 text-left transition-colors hover:border-fg-muted"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between">
                  <span className="truncate text-[11px] text-fg-secondary">
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
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
