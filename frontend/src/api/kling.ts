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

/** 可灵 4.0 主体 / 音色管理 API（对应后端 /api/v1/kling）。 */

import { apiClient } from './client'

export interface KlingElement {
  id: string
  name: string
  description?: string
  reference_type?: string
  status?: string
  owned_by?: string
  [key: string]: unknown
}

export interface KlingVoice {
  voice_id: string
  voice_name: string
  trial_url?: string
  owned_by?: string
  [key: string]: unknown
}

export interface ElementCreatePayload {
  name: string
  description: string
  reference_type: 'image_refer' | 'video_refer'
  frontal_image_url?: string | null
  refer_image_urls?: string[]
  refer_video_url?: string | null
  element_voice_id?: string | null
  tag_ids?: string[]
}

export interface VoiceCreatePayload {
  name: string
  voice_url?: string | null
  video_id?: string | null
}

export async function listKlingElements(page = 1, pageSize = 30): Promise<KlingElement[]> {
  const { data } = await apiClient.get<{ items: KlingElement[] }>('/kling/elements', {
    params: { page_num: page, page_size: pageSize },
  })
  return data.items
}

/** 从主体查询任务结果中抽取 element_id（任务可能仍在处理中，返回空数组）。 */
export function extractElementIds(task: Record<string, unknown>): KlingElement[] {
  const result = task?.task_result as { elements?: KlingElement[] } | undefined
  return result?.elements ?? []
}

export async function createKlingElement(payload: ElementCreatePayload): Promise<string> {
  const { data } = await apiClient.post<{ task_id: string }>('/kling/elements', payload)
  return data.task_id
}

export async function getKlingElementTask(taskId: string): Promise<Record<string, unknown>> {
  const { data } = await apiClient.get<Record<string, unknown>>(
    `/kling/elements/${encodeURIComponent(taskId)}`,
  )
  return data
}

export async function deleteKlingElement(id: string): Promise<void> {
  await apiClient.post('/kling/elements/delete', { id })
}

export async function listKlingVoices(page = 1, pageSize = 30): Promise<KlingVoice[]> {
  const { data } = await apiClient.get<{ items: KlingVoice[] }>('/kling/voices', {
    params: { page_num: page, page_size: pageSize },
  })
  return data.items
}

/** 从音色查询任务结果中抽取 voice 列表。 */
export function extractVoices(task: Record<string, unknown>): KlingVoice[] {
  const result = task?.task_result as { voices?: KlingVoice[] } | undefined
  return result?.voices ?? []
}

export async function createKlingVoice(payload: VoiceCreatePayload): Promise<string> {
  const { data } = await apiClient.post<{ task_id: string }>('/kling/voices', payload)
  return data.task_id
}

export async function getKlingVoiceTask(taskId: string): Promise<Record<string, unknown>> {
  const { data } = await apiClient.get<Record<string, unknown>>(
    `/kling/voices/${encodeURIComponent(taskId)}`,
  )
  return data
}

export async function deleteKlingVoice(id: string): Promise<void> {
  await apiClient.post('/kling/voices/delete', { id })
}
