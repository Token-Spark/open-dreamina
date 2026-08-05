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
 */
export async function uploadAsset(file: File): Promise<Asset> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await apiClient.post<Asset>('/assets/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
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
