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

import { create } from 'zustand'
import type { Task, TaskStatus } from '@/api/tasks'

/**
 * Live snapshot of an in-flight task, kept in sync via SSE updates.
 * Terminal tasks (completed/failed/cancelled) are removed from the store
 * shortly after their final event so the bottom TaskBar stays focused.
 */
export interface ActiveTask {
  task: Task
  progress: number
  status: TaskStatus
  error: string | null
  resultUrl: string | null
  thumbnailUrl: string | null
  message: string | null
  /** Epoch ms when the task entered running, used for ETA. */
  runningSince: number | null
}

interface TaskState {
  active: Record<string, ActiveTask>
  addActive: (task: Task) => void
  patchActive: (taskId: string, patch: Partial<ActiveTask>) => void
  removeActive: (taskId: string) => void
  setActive: (tasks: Task[]) => void
  clearTerminal: () => void
}

export const useTaskStore = create<TaskState>((set) => ({
  active: {},

  addActive: (task) =>
    set((state) => ({
      active: {
        ...state.active,
        [task.id]: {
          task,
          progress: task.progress,
          status: task.status,
          error: task.error_msg,
          resultUrl: null,
          thumbnailUrl: null,
          message: null,
          runningSince: task.started_at ? new Date(task.started_at).getTime() : null,
        },
      },
    })),

  patchActive: (taskId, patch) =>
    set((state) => {
      const current = state.active[taskId]
      if (!current) return state
      return { active: { ...state.active, [taskId]: { ...current, ...patch } } }
    }),

  removeActive: (taskId) =>
    set((state) => {
      const next = { ...state.active }
      delete next[taskId]
      return { active: next }
    }),

  setActive: (tasks) =>
    set(() => {
      const next: Record<string, ActiveTask> = {}
      for (const task of tasks) {
        next[task.id] = {
          task,
          progress: task.progress,
          status: task.status,
          error: task.error_msg,
          resultUrl: null,
          thumbnailUrl: null,
          message: null,
          runningSince: task.started_at ? new Date(task.started_at).getTime() : null,
        }
      }
      return { active: next }
    }),

  clearTerminal: () =>
    set((state) => {
      const terminal: TaskStatus[] = ['completed', 'failed', 'cancelled']
      const next: Record<string, ActiveTask> = {}
      for (const [id, t] of Object.entries(state.active)) {
        if (!terminal.includes(t.status)) next[id] = t
      }
      return { active: next }
    }),
}))

/** Selector: active tasks as a stable array sorted by creation time (newest first). */
export function useActiveTaskList(): ActiveTask[] {
  return useTaskStore((state) =>
    Object.values(state.active).sort(
      (a, b) =>
        new Date(b.task.created_at).getTime() - new Date(a.task.created_at).getTime(),
    ),
  )
}
