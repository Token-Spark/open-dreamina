import { apiClient } from './client'

export interface Provider {
  id: string
  name: string
  slug: string
  base_url: string
  /** Masked API key (e.g. "abcd****wxyz"); never the full secret. */
  api_key_masked: string
  is_active: boolean
  config: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface CreateProviderPayload {
  name: string
  slug: string
  base_url: string
  api_key: string
  is_active?: boolean
  config?: Record<string, unknown>
}

export interface UpdateProviderPayload {
  name?: string
  base_url?: string
  /** Omit api_key to keep the existing secret unchanged. */
  api_key?: string
  is_active?: boolean
  config?: Record<string, unknown>
}

export interface TestResult {
  success: boolean
  message: string
}

export async function listProviders(): Promise<Provider[]> {
  const { data } = await apiClient.get<Provider[]>('/providers')
  return data
}

export async function createProvider(payload: CreateProviderPayload): Promise<Provider> {
  const { data } = await apiClient.post<Provider>('/providers', payload)
  return data
}

export async function updateProvider(
  id: string,
  payload: UpdateProviderPayload,
): Promise<Provider> {
  const { data } = await apiClient.put<Provider>(`/providers/${id}`, payload)
  return data
}

export async function deleteProvider(id: string): Promise<void> {
  await apiClient.delete(`/providers/${id}`)
}

export async function testProvider(id: string): Promise<TestResult> {
  const { data } = await apiClient.post<TestResult>(`/providers/${id}/test`)
  return data
}
