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

// ---------------- 全局 SSE 连接预算 ----------------
// HTTP/1.1 下浏览器对同源最多 6 条并发连接。若每个运行中任务都各开一条
// EventSource，同时运行的任务一多（如批量出图 ≥5 个）就会占满连接池，
// 页面上所有正常数据请求被饿死——请求停在浏览器队列里，服务端根本收不到。
// 因此全局最多保留 MAX_TASK_SSE 条直播流，其余任务自动退化为下方已有的
// 3s 轮询兜底；有任务结束释放预算时，等待中的订阅按先到先得接管直播流。
const MAX_TASK_SSE = 4

interface StreamWaiter {
  cancelled: boolean
  grant: () => void
}

let freeStreamSlots = MAX_TASK_SSE
const streamWaiters: StreamWaiter[] = []

/** 申请一条 SSE 连接预算：有空位立即 grant，否则排队等待（返回等待凭据）。 */
function requestStreamSlot(grant: () => void): StreamWaiter | null {
  if (freeStreamSlots > 0) {
    freeStreamSlots -= 1
    grant()
    return null
  }
  const waiter: StreamWaiter = { cancelled: false, grant }
  streamWaiters.push(waiter)
  return waiter
}

/** 归还一条连接预算，并把它移交给队列中第一个仍有效的等待者。 */
function releaseStreamSlot(): void {
  freeStreamSlots += 1
  while (streamWaiters.length) {
    const waiter = streamWaiters.shift()!
    if (waiter.cancelled) continue
    freeStreamSlots -= 1
    waiter.grant()
    return
  }
}

function cancelStreamWaiter(waiter: StreamWaiter): void {
  waiter.cancelled = true
  const i = streamWaiters.indexOf(waiter)
  if (i >= 0) streamWaiters.splice(i, 1)
}

// ---------------- 单一订阅源 ----------------
// TaskSSEManager、GenMessageCard、画布节点可能同时订阅同一个 taskId。
// 早期每个 hook 各建一条 EventSource 并各发一次 getTask，批量生成时既浪费
// 连接预算又制造重复轮询。这里按 taskId 共享一条流：只有第一个订阅者会
// 建立连接，其余订阅者复用同一份快照与后续事件；最后一个卸载时才断开。
type Emit = (payload: SSEPayload) => void

interface SharedStream {
  listeners: Set<Emit>
  /** 最近一次事件快照，供后加入的订阅者立即回放，避免等到下一帧才有状态。 */
  last: SSEPayload | null
  stop: () => void
}

const streams = new Map<string, SharedStream>()

function createStream(taskId: string): SharedStream {
  const stream: SharedStream = { listeners: new Set(), last: null, stop: () => {} }
  let stopped = false
  let es: EventSource | null = null
  let pollTimer: number | null = null
  let holdingSlot = false
  let slotWaiter: StreamWaiter | null = null
  let terminalReached = false

  const broadcast: Emit = (payload) => {
    for (const listener of [...stream.listeners]) listener(payload)
  }

  const stop = () => {
    if (stopped) return
    stopped = true
    if (slotWaiter) {
      cancelStreamWaiter(slotWaiter)
      slotWaiter = null
    }
    if (es) {
      es.close()
      es = null
    }
    if (holdingSlot) {
      holdingSlot = false
      releaseStreamSlot()
    }
    if (pollTimer) {
      window.clearInterval(pollTimer)
      pollTimer = null
    }
  }
  stream.stop = stop

  const scheduleTerminalCleanup = (terminal: TaskStatus) => {
    if (terminalReached) return
    terminalReached = true
    stop()
    // 终态任务在 TaskBar 里短暂停留后移除。这个定时器不随订阅者卸载取消：
    // 任务已经结束，从活跃列表里清掉是期望行为，重复调用也是幂等的。
    window.setTimeout(() => {
      useTaskStore.getState().removeActive(taskId)
    }, terminal === 'completed' ? 4000 : 8000)
  }

  const emit = (payload: SSEPayload) => {
    if (stopped) return
    stream.last = payload
    // store 是全局单份，只在共享层镜像一次，不让每个订阅者各写一遍。
    useTaskStore.getState().patchActive(taskId, {
      status: payload.status ?? undefined,
      progress: typeof payload.progress === 'number' ? payload.progress : undefined,
      error: payload.error ?? undefined,
      message: payload.message ?? undefined,
      resultUrl: payload.result_url ?? undefined,
      thumbnailUrl: payload.thumbnail_url ?? undefined,
      runningSince: payload.status === 'running' ? Date.now() : undefined,
    })
    broadcast(payload)
    if (payload.status && TERMINAL.includes(payload.status)) {
      scheduleTerminalCleanup(payload.status)
    }
  }

  const openSSE = () => {
    if (es || stopped || terminalReached) return
    const grant = () => {
      // 排队期间任务可能已结束或所有订阅者已卸载：把预算原样归还
      if (stopped || terminalReached) {
        releaseStreamSlot()
        return
      }
      holdingSlot = true
      // SSE 连上后停掉轮询兜底，避免同一份数据触发两次状态更新。
      if (pollTimer) {
        window.clearInterval(pollTimer)
        pollTimer = null
      }
      es = new EventSource(taskStreamUrl(taskId))
      es.addEventListener('progress', (e) => safeParse(e, emit))
      es.addEventListener('completed', (e) => safeParse(e, emit))
      es.addEventListener('failed', (e) => safeParse(e, emit))
      es.addEventListener('heartbeat', () => {
        // keep-alive; no state change
      })
      es.onerror = () => {
        // EventSource auto-reconnects; nothing to do here. Polling covers gaps.
      }
    }
    slotWaiter = requestStreamSlot(grant)
  }

  const startPolling = () => {
    if (pollTimer || stopped) return
    pollTimer = window.setInterval(() => {
      getTask(taskId)
        .then((task) => {
          if (stopped) return
          emit({
            task_id: task.id,
            status: task.status,
            progress: task.progress,
            error: task.error_msg ?? undefined,
            result_url: task.result_url ?? undefined,
            thumbnail_url: task.thumbnail_url ?? undefined,
            result_urls: task.result_urls,
            thumbnail_urls: task.thumbnail_urls,
          })
        })
        .catch(() => {
          /* swallow poll errors; next tick retries */
        })
    }, 3000)
  }

  // 只有流的创建者发这一次 getTask，用来在 SSE 首帧到达前播种状态。
  getTask(taskId)
    .then((task) => {
      if (stopped) return
      emit({
        task_id: task.id,
        status: task.status,
        progress: task.progress,
        error: task.error_msg ?? undefined,
        result_url: task.result_url ?? undefined,
        thumbnail_url: task.thumbnail_url ?? undefined,
        result_urls: task.result_urls,
        thumbnail_urls: task.thumbnail_urls,
      })
      if (TERMINAL.includes(task.status)) return
      openSSE()
      if (slotWaiter) startPolling()
    })
    .catch(() => {
      if (stopped) return
      openSSE()
      if (slotWaiter) startPolling()
    })

  return stream
}

function attach(taskId: string, listener: Emit): () => void {
  let stream = streams.get(taskId)
  if (!stream) {
    stream = createStream(taskId)
    streams.set(taskId, stream)
  }
  stream.listeners.add(listener)
  if (stream.last) listener(stream.last)

  return () => {
    const current = streams.get(taskId)
    if (!current) return
    current.listeners.delete(listener)
    if (current.listeners.size === 0) {
      current.stop()
      streams.delete(taskId)
    }
  }
}

/**
 * Subscribe to a single task's progress. Multiple components subscribing to the
 * same task share one SSE stream and one seed request; see "单一订阅源" above.
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

  const optsRef = useRef(options)
  optsRef.current = options

  useEffect(() => {
    if (!taskId) return
    return attach(taskId, (payload) => {
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
      if (payload.status === 'completed') {
        optsRef.current.onComplete?.()
      } else if (payload.status === 'failed') {
        optsRef.current.onFailed?.(payload.error ?? '生成失败')
      }
    })
  }, [taskId])

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
