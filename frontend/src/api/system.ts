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

// ============================ 即梦 CLI 引导 ============================

/** worker 节点上即梦 CLI 的安装 / 登录状态。 */
export interface DreaminaCliStatus {
  installed: boolean
  installing: boolean
  cli_path: string | null
  version: string | null
  logged_in: boolean
  credit_info: string | null
  message: string
  /** worker 不在线时的降级标记 */
  worker_offline?: boolean
}

/** headless 登录发起结果：需用户在浏览器完成的授权材料。 */
export interface DreaminaCliLoginStart {
  ok: boolean
  message?: string
  verification_uri?: string
  user_code?: string
  device_code?: string
  raw_output?: string
  worker_offline?: boolean
}

/** 登录授权轮询结果。 */
export interface DreaminaCliLoginStatus {
  state: 'no_session' | 'waiting' | 'success' | 'failed'
  logged_in: boolean
  message: string
  credit_info?: string
  worker_offline?: boolean
}

export async function getDreaminaCliStatus(): Promise<DreaminaCliStatus> {
  const { data } = await apiClient.get<DreaminaCliStatus>('/system/dreamina-cli/status')
  return data
}

export async function installDreaminaCli(): Promise<{ message: string }> {
  const { data } = await apiClient.post<{ message: string }>('/system/dreamina-cli/install')
  return data
}

export async function startDreaminaCliLogin(): Promise<DreaminaCliLoginStart> {
  const { data } = await apiClient.post<DreaminaCliLoginStart>('/system/dreamina-cli/login/start')
  return data
}

export async function getDreaminaCliLoginStatus(): Promise<DreaminaCliLoginStatus> {
  const { data } = await apiClient.get<DreaminaCliLoginStatus>('/system/dreamina-cli/login/status')
  return data
}
