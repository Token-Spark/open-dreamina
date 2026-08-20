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

import { useEffect, useRef, useState } from 'react'
import {
  getTask,
  taskStreamUrl,
  type TaskStatus,
} from '@/api/tasks'
import { useTaskStore } from '@/stores/taskStore'

export interface SSEData {
  resultUrl: string | null
  thumbnailUrl: string | null
  resultUrls: string[]
  thumbnailUrls: string[]
  message: string | null
}

export interface UseTaskSSEReturn {
  status: TaskStatus | null
  progress: number
  error: string | null
  data: SSEData
  /** True once the task reaches any terminal status. */
  isTerminal: boolean
}

interface SSEPayload {
  task_id: string
  status?: TaskStatus
  progress?: number
  message?: string
  error?: string
  result_url?: string
  thumbnail_url?: string
  result_urls?: string[]
  thumbnail_urls?: string[]
}

const TERMINAL: TaskStatus[] = ['completed', 'failed', 'cancelled']

/**
 * Subscribe to a single task's progress via SSE, with a 3s polling fallback.
 * EventSource reconnects natively; the poll ensures progress is current even
 * if an SSE frame is missed. The live snapshot is mirrored into taskStore so
 * the bottom TaskBar stays in sync across components.
 */
export function useTaskSSE(
  taskId: string | null | undefined,
  options: { onComplete?: () => void; onFailed?: (msg: string) => void } = {},
): UseTaskSSEReturn {
  const [status, setStatus] = useState<TaskStatus | null>(null)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<SSEData>({
    resultUrl: null,
    thumbnailUrl: null,
    resultUrls: [],
    thumbnailUrls: [],
    message: null,
  })

  const patchActive = useTaskStore((s) => s.patchActive)
  const removeActive = useTaskStore((s) => s.removeActive)
  const optsRef = useRef(options)
  optsRef.current = options

  useEffect(() => {
    if (!taskId) return
    let cancelled = false
    let es: EventSource | null = null
    let pollTimer: number | null = null
    let cleanupTimer: number | null = null

    const apply = (payload: SSEPayload) => {
      if (cancelled) return
      if (payload.status) setStatus(payload.status)
      if (typeof payload.progress === 'number') setProgress(payload.progress)
      if (payload.message) {
        setData((d) => ({ ...d, message: payload.message ?? null }))
      }
      if (payload.error) setError(payload.error)
      if (payload.result_url) {
        setData((d) => ({ ...d, resultUrl: payload.result_url ?? null }))
      }
      if (payload.thumbnail_url) {
        setData((d) => ({ ...d, thumbnailUrl: payload.thumbnail_url ?? null }))
      }
      if (Array.isArray(payload.result_urls)) {
        setData((d) => ({ ...d, resultUrls: payload.result_urls ?? [] }))
      }
      if (Array.isArray(payload.thumbnail_urls)) {
        setData((d) => ({ ...d, thumbnailUrls: payload.thumbnail_urls ?? [] }))
      }
      // Mirror into the global store for the TaskBar.
      patchActive(taskId, {
        status: payload.status ?? undefined,
        progress: typeof payload.progress === 'number' ? payload.progress : undefined,
        error: payload.error ?? undefined,
        message: payload.message ?? undefined,
        resultUrl: payload.result_url ?? undefined,
        thumbnailUrl: payload.thumbnail_url ?? undefined,
        runningSince:
          payload.status === 'running' ? Date.now() : undefined,
      })
      if (payload.status === 'completed') {
        optsRef.current.onComplete?.()
        scheduleTerminalCleanup('completed')
      } else if (payload.status === 'failed') {
        optsRef.current.onFailed?.(payload.error ?? '生成失败')
        scheduleTerminalCleanup('failed')
      } else if (payload.status === 'cancelled') {
        scheduleTerminalCleanup('cancelled')
      }
    }

    const scheduleTerminalCleanup = (terminal: TaskStatus) => {
      stop()
      // Keep the entry briefly so the UI can show the final state, then drop it.
      cleanupTimer = window.setTimeout(() => {
        if (!cancelled) removeActive(taskId)
      }, terminal === 'completed' ? 4000 : 8000)
    }

    const stop = () => {
      if (es) {
        es.close()
        es = null
      }
      if (pollTimer) {
        window.clearInterval(pollTimer)
        pollTimer = null
      }
    }

    // Initial fetch to seed state before SSE events arrive.
    getTask(taskId)
      .then((task) => {
        if (cancelled) return
        apply({
          task_id: task.id,
          status: task.status,
          progress: task.progress,
          error: task.error_msg ?? undefined,
          result_url: task.result_url ?? undefined,
          thumbnail_url: task.thumbnail_url ?? undefined,
          result_urls: task.result_urls,
          thumbnail_urls: task.thumbnail_urls,
        })
        if (TERMINAL.includes(task.status)) {
          scheduleTerminalCleanup(task.status)
          return
        }
        openSSE()
        startPolling()
      })
      .catch(() => {
        // If the seed fetch fails, still attempt SSE/polling.
        openSSE()
        startPolling()
      })

    const openSSE = () => {
      if (es || cancelled) return
      es = new EventSource(taskStreamUrl(taskId))
      es.addEventListener('progress', (e) => safeParse(e, apply))
      es.addEventListener('completed', (e) => safeParse(e, apply))
      es.addEventListener('failed', (e) => safeParse(e, apply))
      es.addEventListener('heartbeat', () => {
        // keep-alive; no state change
      })
      es.onerror = () => {
        // EventSource auto-reconnects; nothing to do here. Polling covers gaps.
      }
    }

    const startPolling = () => {
      if (pollTimer || cancelled) return
      pollTimer = window.setInterval(() => {
        getTask(taskId)
          .then((task) => {
            if (cancelled) return
            apply({
              task_id: task.id,
              status: task.status,
              progress: task.progress,
              error: task.error_msg ?? undefined,
              result_url: task.result_url ?? undefined,
              thumbnail_url: task.thumbnail_url ?? undefined,
              result_urls: task.result_urls,
              thumbnail_urls: task.thumbnail_urls,
            })
            if (TERMINAL.includes(task.status)) scheduleTerminalCleanup(task.status)
          })
          .catch(() => {
            /* swallow poll errors; next tick retries */
          })
      }, 3000)
    }

    return () => {
      cancelled = true
      stop()
      if (cleanupTimer) window.clearTimeout(cleanupTimer)
    }
  }, [taskId, patchActive, removeActive])

  return {
    status,
    progress,
    error,
    data,
    isTerminal: status != null && TERMINAL.includes(status),
  }
}

function safeParse(e: MessageEvent, apply: (p: SSEPayload) => void) {
  try {
    apply(JSON.parse(e.data) as SSEPayload)
  } catch {
    /* ignore malformed frames */
  }
}
