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

export type TemplateCategory = 'image' | 'video'

export interface Template {
  id: string
  name: string
  category: TemplateCategory
  prompt_text: string
  negative_prompt: string | null
  params: Record<string, unknown>
  preview_path: string | null
  created_at: string
  updated_at: string
}

export interface TemplatePayload {
  name: string
  category: TemplateCategory
  prompt_text: string
  negative_prompt?: string
  params?: Record<string, unknown>
}

export async function listTemplates(): Promise<Template[]> {
  const { data } = await apiClient.get<Template[]>('/templates')
  return data
}

export async function createTemplate(payload: TemplatePayload): Promise<Template> {
  const { data } = await apiClient.post<Template>('/templates', payload)
  return data
}

export async function updateTemplate(id: string, payload: TemplatePayload): Promise<Template> {
  const { data } = await apiClient.put<Template>(`/templates/${id}`, payload)
  return data
}

export async function deleteTemplate(id: string): Promise<void> {
  await apiClient.delete(`/templates/${id}`)
}
