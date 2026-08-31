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

import {
  useEffect,
  useRef,
  useState,
  type RefObject,
} from 'react'

/**
 * 3D 导演台 postMessage 嵌入协议客户端。
 *
 * 协议文档：https://github.com/xiaozangao/3d-director-desk/blob/main/docs/embed-contract.md
 *
 * 设计要点：
 * - 所有请求通过 requestId 配对响应，不假设响应顺序与请求顺序相同。
 * - origin 校验：只接受来自 directorOrigin 的消息，只发回该 origin。
 * - 超时清理：每个请求独立超时，超时后 reject 并清理 pending 条目。
 * - 卸载时 reject 所有未决请求，避免 Promise 泄漏。
 */

// ---- 协议类型 ----

export type DirectorDeskAction =
  | 'capabilities.get'
  | 'project.get'
  | 'timeline.get'
  | 'export.frame'

export interface DirectorDeskError {
  code: string
  message: string
}

interface DirectorResponse<T> {
  protocolVersion: number
  requestId: string
  action: string
  ok: boolean
  data?: T
  error?: DirectorDeskError
}

export interface DirectorFrameData {
  dataUrl: string
  fileName: string
  width: number
  height: number
  progress: number
}

export interface DirectorCapture {
  dataUrl: string
  fileName: string
}

// ---- Hook ----

export interface UseDirectorDeskOptions {
  iframeRef: RefObject<HTMLIFrameElement | null>
  /** 导演台 iframe 的 origin，用于 postMessage targetOrigin 与来源校验。 */
  origin: string
  /** 导演台初始化就绪后回调。 */
  onReady?: () => void
  /** 用户在导演台内点击关闭时回调。 */
  onClose?: () => void
  /** 用户通过导演台内置发送按钮回传截图时回调。 */
  onCaptures?: (captures: DirectorCapture[]) => void
}

export function useDirectorDesk({
  iframeRef,
  origin,
  onReady,
  onClose,
  onCaptures,
}: UseDirectorDeskOptions) {
  const [ready, setReady] = useState(false)

  // 回调用 ref 保持引用最新，避免重新绑定 message listener。
  const onReadyRef = useRef(onReady)
  const onCloseRef = useRef(onClose)
  const onCapturesRef = useRef(onCaptures)
  onReadyRef.current = onReady
  onCloseRef.current = onClose
  onCapturesRef.current = onCaptures

  // requestId → { resolve, reject, timer }
  type Pending = { resolve: (v: unknown) => void; reject: (e: unknown) => void; timer: number }
  const pendingRef = useRef(new Map<string, Pending>())

  useEffect(() => {
    if (!origin) return

    function handleMessage(event: MessageEvent) {
      if (event.origin !== origin) return
      const msg = event.data
      if (!msg || typeof msg !== 'object') return

      switch (msg.type) {
        case 'storyai:director-desk-ready':
          setReady(true)
          onReadyRef.current?.()
          break
        case 'storyai:director-desk-close':
          onCloseRef.current?.()
          break
        case 'storyai:director-desk-captures-sent':
          onCapturesRef.current?.(msg.payload?.captures ?? [])
          break
        case 'storyai:director-desk:response': {
          const resp = msg.payload as DirectorResponse<unknown>
          if (!resp?.requestId) return
          const entry = pendingRef.current.get(resp.requestId)
          if (!entry) return
          pendingRef.current.delete(resp.requestId)
          clearTimeout(entry.timer)
          if (resp.ok) entry.resolve(resp.data)
          else entry.reject(resp.error ?? { code: 'unknown', message: '导演台请求失败' })
          break
        }
      }
    }

    window.addEventListener('message', handleMessage)
    return () => {
      window.removeEventListener('message', handleMessage)
      // 卸载时 reject 所有未决请求
      for (const [, entry] of pendingRef.current) {
        clearTimeout(entry.timer)
        entry.reject({ code: 'aborted', message: '导演台已关闭' })
      }
      pendingRef.current.clear()
    }
  }, [origin])

  // origin 变化（新 iframe 加载）时重置就绪状态
  useEffect(() => {
    setReady(false)
  }, [origin])

  /**
   * 向导演台发送受控请求，返回 Promise。
   * 按 requestId 配对响应；超时后自动 reject。
   */
  function request<T = unknown>(
    action: DirectorDeskAction,
    options: Record<string, unknown> = {},
    timeoutMs = 120_000,
  ): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const win = iframeRef.current?.contentWindow
      if (!win) {
        reject({ code: 'no-iframe', message: '导演台未加载' })
        return
      }
      const requestId =
        typeof crypto !== 'undefined' && crypto.randomUUID
          ? crypto.randomUUID()
          : `req-${Date.now()}-${Math.random().toString(36).slice(2)}`

      const timer = window.setTimeout(() => {
        pendingRef.current.delete(requestId)
        reject({ code: 'timeout', message: `导演台响应超时（${timeoutMs / 1000}s）` })
      }, timeoutMs)

      pendingRef.current.set(requestId, {
        resolve: resolve as (v: unknown) => void,
        reject,
        timer,
      })

      win.postMessage(
        { type: 'storyai:director-desk:request', payload: { requestId, action, options } },
        origin,
      )
    })
  }

  return { ready, request }
}
