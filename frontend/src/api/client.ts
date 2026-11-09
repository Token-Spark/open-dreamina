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

import axios, { AxiosError } from 'axios'

/** Base axios instance; all requests are prefixed with /api/v1 (proxied to backend). */
export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

/** Standard error shape returned by the backend. */
export interface ApiError {
  message: string
  detail?: string
  statusCode?: number
  /** 原始 detail，供需要结构化字段（如 current_version、errors）的调用方读取 */
  rawDetail?: unknown
}

/**
 * Turn a backend/FastAPI error `detail` into a human-readable string.
 *
 * FastAPI 的 422 校验错误 detail 是数组 `[{ type, loc, msg, ... }]`，而后端自定义
 * 错误 detail 是对象 `{ code, message }`。若直接把这类非字符串塞进 toast 的 message
 * 渲染（`<span>{t.message}</span>`），React 会抛 "Objects are not valid as a React
 * child" 导致整棵树崩溃白屏。这里统一收敛为字符串。
 */
function detailToMessage(detail: unknown): string | undefined {
  if (detail == null) return undefined
  if (typeof detail === 'string') return detail
  // FastAPI 422 校验错误：[{ type, loc, msg, ... }, ...]
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (typeof d === 'string' ? d : d?.msg))
      .filter((m): m is string => typeof m === 'string' && m.length > 0)
    if (msgs.length) return msgs.join('；')
  }
  // 后端自定义错误：{ code, message, errors? }
  // 带上头两条具体原因，避免只显示「校验失败: 3 个错误」这类无信息量提示。
  if (typeof detail === 'object' && !Array.isArray(detail)) {
    const obj = detail as { message?: unknown; errors?: unknown }
    const msg = typeof obj.message === 'string' && obj.message.length > 0 ? obj.message : undefined
    if (msg) {
      const parts = Array.isArray(obj.errors)
        ? obj.errors
            .map((item) =>
              typeof item === 'object' && item !== null
                ? (item as { message?: unknown }).message
                : undefined,
            )
            .filter((item): item is string => typeof item === 'string' && item.length > 0)
        : []
      return parts.length ? `${msg}：${parts.slice(0, 2).join('；')}` : msg
    }
  }
  try {
    return JSON.stringify(detail)
  } catch {
    return undefined
  }
}

/** Normalize any axios/network error into a structured ApiError. */
export function toApiError(err: unknown): ApiError {
  if (axios.isAxiosError(err)) {
    const ax = err as AxiosError<{ detail?: unknown; message?: string }>
    return {
      message:
        detailToMessage(ax.response?.data?.detail) ??
        ax.response?.data?.message ??
        ax.message ??
        '请求失败',
      statusCode: ax.response?.status,
      rawDetail: ax.response?.data?.detail,
    }
  }
  if (err instanceof Error) return { message: err.message }
  return { message: '未知错误' }
}

/** Generic paginated response wrapper. */
export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
