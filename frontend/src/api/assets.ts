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

export type AssetType = 'image' | 'video' | 'audio'

export interface Asset {
  id: string
  task_id: string | null
  type: AssetType
  file_path: string
  thumbnail_path: string | null
  file_size: number | null
  mime_type: string | null
  width: number | null
  height: number | null
  duration: number | null
  tags: string[]
  is_favorite: boolean
  created_at: string
}

export interface ListAssetsQuery {
  type?: AssetType
  tags?: string
  is_favorite?: boolean
  page?: number
  page_size?: number
}

export interface UpdateAssetPayload {
  tags?: string[]
  is_favorite?: boolean
}

export async function listAssets(query: ListAssetsQuery = {}): Promise<Paginated<Asset>> {
  const { data } = await apiClient.get<Paginated<Asset>>('/assets', { params: query })
  return data
}

export async function getAsset(assetId: string): Promise<Asset> {
  const { data } = await apiClient.get<Asset>(`/assets/${assetId}`)
  return data
}

export async function updateAsset(assetId: string, payload: UpdateAssetPayload): Promise<Asset> {
  const { data } = await apiClient.patch<Asset>(`/assets/${assetId}`, payload)
  return data
}

export async function deleteAsset(assetId: string): Promise<void> {
  await apiClient.delete(`/assets/${assetId}`)
}

export async function batchDeleteAssets(assetIds: string[]): Promise<void> {
  await apiClient.post('/assets/batch-delete', { asset_ids: assetIds })
}

/**
 * Upload a reference image (for img2img / img2video) and return the created
 * asset. The returned `id` is used as `input_asset_id` when creating a task.
 *
 * 文件上传 + 后端同步生成缩略图可能耗时较长，覆盖默认 30s 超时，避免大图
 * 或慢网络下出现 "timeout of 30000ms exceeded"。
 */
export async function uploadAsset(file: File): Promise<Asset> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await apiClient.post<Asset>('/assets/upload', form, {
    timeout: 120_000,
    // 必须清除 apiClient 实例默认的 `Content-Type: application/json`（见 client.ts）。
    // 否则 axios 的 transformRequest 检测到 application/json 时会把 FormData
    // 序列化成 JSON 字符串发出（`hasJSONContentType ? JSON.stringify(formDataToJSON(data)) : data`），
    // 后端拿不到 multipart 的 file 字段 → 422。这里置为 null：axios 会跳过值为
    // null 的 header，改由浏览器为 FormData 自动生成带 boundary 的
    // `multipart/form-data`。注：手动设为裸 'multipart/form-data'（无 boundary）
    // 会被原样发出去 → 后端报 "Missing boundary in multipart." → 400。
    headers: { 'Content-Type': null },
  })
  return data
}

/** Public URL helpers (served by the backend file router). */
export function assetFileUrl(assetId: string): string {
  return `/api/v1/assets/${assetId}/file`
}

export function assetThumbnailUrl(assetId: string): string {
  return `/api/v1/assets/${assetId}/thumbnail`
}
