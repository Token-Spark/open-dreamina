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

import { apiClient, type Paginated } from './client'

export type TaskType = 'text2img' | 'img2img' | 'text2video' | 'img2video'
export type TaskStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface Task {
  id: string
  type: TaskType
  status: TaskStatus
  progress: number
  provider: string
  model_id: string | null
  prompt: string | null
  params: Record<string, unknown>
  input_asset_id: string | null
  input_asset_url: string | null
  result_path: string | null
  thumbnail_path: string | null
  result_url: string | null
  thumbnail_url: string | null
  /** 多图生成：全部结果访问地址（单图时仅 1 项）。 */
  result_urls: string[]
  thumbnail_urls: string[]
  error_msg: string | null
  api_cost: number | null
  /** 该任务消耗的 token 数（可能为 null，表示 Provider 未返回） */
  tokens_used: number | null
  retry_count: number
  conversation_id: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface CreateTaskParams {
  type: TaskType
  provider: string
  model_id?: string
  prompt?: string
  negative_prompt?: string
  params?: Record<string, unknown>
  input_asset_id?: string
  /** 多图参考：完整 asset id 列表。后端将首张写入 input_asset_id，完整列表存入 params。 */
  input_asset_ids?: string[]
  conversation_id?: string
}

export interface ListTasksQuery {
  status?: string
  type?: TaskType
  page?: number
  page_size?: number
}

export interface CreateTaskResponse {
  task_id: string
}

export async function createTask(params: CreateTaskParams): Promise<CreateTaskResponse> {
  const { data } = await apiClient.post<CreateTaskResponse>('/tasks', params)
  return data
}

export async function listTasks(query: ListTasksQuery = {}): Promise<Paginated<Task>> {
  const { data } = await apiClient.get<Paginated<Task>>('/tasks', { params: query })
  return data
}

export async function getTask(taskId: string): Promise<Task> {
  const { data } = await apiClient.get<Task>(`/tasks/${taskId}`)
  return data
}

export async function cancelTask(taskId: string): Promise<void> {
  await apiClient.post(`/tasks/${taskId}/cancel`)
}

export async function retryTask(taskId: string): Promise<CreateTaskResponse> {
  const { data } = await apiClient.post<CreateTaskResponse>(`/tasks/${taskId}/retry`)
  return data
}

export async function deleteTask(taskId: string): Promise<void> {
  await apiClient.delete(`/tasks/${taskId}`)
}

/** Build the SSE stream URL for a task (consumed via EventSource). */
export function taskStreamUrl(taskId: string): string {
  return `/api/v1/tasks/${taskId}/stream`
}

/** Statuses considered "in-flight" for page-recovery subscription. */
export const ACTIVE_STATUSES: TaskStatus[] = ['pending', 'queued', 'running']
