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
import type { Task } from './tasks'

export interface Conversation {
  id: string
  title: string
  created_at: string | null
  updated_at: string | null
  message_count: number
  last_prompt: string | null
  last_thumbnail_url: string | null
}

export interface CreateConversationPayload {
  title?: string
}

export async function listConversations(): Promise<Conversation[]> {
  const { data } = await apiClient.get<{ items: Conversation[]; total: number }>('/conversations')
  return data.items
}

export async function createConversation(payload: CreateConversationPayload = {}): Promise<Conversation> {
  const { data } = await apiClient.post<Conversation>('/conversations', payload)
  return data
}

export async function getConversation(id: string): Promise<Conversation> {
  const { data } = await apiClient.get<Conversation>(`/conversations/${id}`)
  return data
}

export async function updateConversation(id: string, title: string): Promise<Conversation> {
  const { data } = await apiClient.patch<Conversation>(`/conversations/${id}`, { title })
  return data
}

export async function deleteConversation(id: string): Promise<void> {
  await apiClient.delete(`/conversations/${id}`)
}

/** 对话内的任务列表（按创建时间升序），即对话消息。 */
export async function listConversationMessages(id: string): Promise<Task[]> {
  const { data } = await apiClient.get<Paginated<Task>>(`/conversations/${id}/messages`)
  return data.items
}
