import { apiClient } from './client'

export interface SystemHealth {
  database: 'ok' | 'error'
  redis: 'ok' | 'error'
  worker: 'ok' | 'error'
}

export interface SystemSettings {
  default_provider: string
  max_concurrent_tasks: number
  [key: string]: unknown
}

export interface BackupResult {
  path: string
  created_at: string
}

export async function getSystemHealth(): Promise<SystemHealth> {
  const { data } = await apiClient.get<SystemHealth>('/system/health')
  return data
}

export async function getSystemSettings(): Promise<SystemSettings> {
  const { data } = await apiClient.get<SystemSettings>('/system/settings')
  return data
}

export async function updateSystemSettings(payload: Partial<SystemSettings>): Promise<SystemSettings> {
  const { data } = await apiClient.put<SystemSettings>('/system/settings', payload)
  return data
}

export async function backupSystem(): Promise<BackupResult> {
  const { data } = await apiClient.post<BackupResult>('/system/backup')
  return data
}
