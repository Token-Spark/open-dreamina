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
  latency_ms?: number
}

/** 可用 slug 元信息：驱动「添加自定义服务」下拉选择。 */
export interface SlugOption {
  slug: string
  display_name: string
  /** 内容模式：image / video。 */
  modes: string[]
  default_base_url: string
  builtin: boolean
}

export interface TestBeforeCreatePayload {
  slug: string
  base_url: string
  api_key?: string
  config?: Record<string, unknown>
}

/** 编辑模式按 id 测试时的可选覆盖项：用表单当前值测试未保存的改动。 */
export interface TestProviderOverrides {
  /** 覆盖已落库的 base_url；不传则用旧值。 */
  base_url?: string
  /** 留空则后端使用已加密的旧 Key。 */
  api_key?: string
  config?: Record<string, unknown>
}

export async function listProviders(): Promise<Provider[]> {
  const { data } = await apiClient.get<Provider[]>('/providers')
  return data
}

export async function listSlugOptions(): Promise<SlugOption[]> {
  const { data } = await apiClient.get<SlugOption[]>('/providers/slug-options')
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

export async function testProvider(
  id: string,
  overrides?: TestProviderOverrides,
): Promise<TestResult> {
  const { data } = await apiClient.post<TestResult>(
    `/providers/${id}/test`,
    overrides ?? {},
  )
  return data
}

export async function testProviderBeforeCreate(
  payload: TestBeforeCreatePayload,
): Promise<TestResult> {
  const { data } = await apiClient.post<TestResult>(
    '/providers/test-before-create',
    payload,
  )
  return data
}
