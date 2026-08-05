import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Merge Tailwind class names with conditional logic, de-duping conflicts. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

/** Format a byte count into a human-readable string. */
export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null || bytes <= 0) return '--'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

/** Format an ISO date string into a localized date-time. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '--'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '--'
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Relative time label, e.g. "3 分钟前". */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return '--'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '--'
  const diff = Date.now() - d.getTime()
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return '刚刚'
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min} 分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小时前`
  const day = Math.floor(hr / 24)
  if (day < 30) return `${day} 天前`
  return formatDateTime(iso)
}

/** Estimate remaining time from progress percent and elapsed seconds. */
export function estimateEta(progress: number, elapsedSec: number): string {
  if (progress <= 0 || progress >= 100) return '--'
  const total = elapsedSec / (progress / 100)
  const remain = Math.max(0, Math.round(total - elapsedSec))
  if (remain < 60) return `${remain} 秒`
  return `${Math.floor(remain / 60)} 分 ${remain % 60} 秒`
}

/** Mask an API key for display: first 4 + **** + last 4. */
export function maskApiKey(key: string): string {
  if (!key) return ''
  if (key.length <= 8) return '****'
  return `${key.slice(0, 4)}****${key.slice(-4)}`
}
