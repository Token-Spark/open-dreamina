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

/** Normalize any axios/network error into a structured ApiError. */
export function toApiError(err: unknown): ApiError {
  if (axios.isAxiosError(err)) {
    const ax = err as AxiosError<{ detail?: string; message?: string }>
    const detail = ax.response?.data?.detail ?? ax.response?.data?.message
    return {
      message: detail ?? ax.message ?? '请求失败',
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
