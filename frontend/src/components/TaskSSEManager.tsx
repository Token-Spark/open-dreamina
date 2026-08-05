import { useTaskStore } from '@/stores/taskStore'
import { useTaskSSE } from '@/hooks/useTaskSSE'

/**
 * Globally subscribes to SSE for every active task, regardless of the current
 * page. This keeps the store (and thus the TaskBar / TasksPage) in sync, and
 * ensures progress resumes after a page refresh. Renders nothing.
 */
export function TaskSSEManager() {
  const activeIds = useTaskStore((s) => Object.keys(s.active))
  return (
    <>
      {activeIds.map((id) => (
        <TaskSubscriber key={id} taskId={id} />
      ))}
    </>
  )
}

function TaskSubscriber({ taskId }: { taskId: string }) {
  useTaskSSE(taskId)
  return null
}
