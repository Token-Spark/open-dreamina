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
  // 后端自定义错误：{ code, message }
  if (typeof detail === 'object') {
    const msg = (detail as { message?: unknown }).message
    if (typeof msg === 'string' && msg.length > 0) return msg
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
