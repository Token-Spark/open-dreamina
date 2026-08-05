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
