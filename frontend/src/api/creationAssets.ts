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

/** 创作资产类别：人物（图片+音色+设定）/ 场景（图片+设定）/ 道具（图片） */
export type CreationAssetCategory = 'character' | 'scene' | 'prop'

export const CATEGORY_OPTIONS: {
  value: CreationAssetCategory
  label: string
  hasAudio: boolean
}[] = [
  { value: 'character', label: '人物', hasAudio: true },
  { value: 'scene', label: '场景', hasAudio: false },
  { value: 'prop', label: '道具', hasAudio: false },
]

export interface CreationAsset {
  id: string
  name: string
  category: CreationAssetCategory
  description: string
  image_asset_id: string | null
  audio_asset_id: string | null
  tags: string[]
  owner_id: string
  owner_name: string
  origin: 'local' | 'remote'
  is_mine: boolean
  synced_at: string | null
  created_at: string | null
  updated_at: string | null
  base_version: number
  cloud_tag: string
  has_pending_changes: boolean
  image_url: string | null
  image_thumbnail_url: string | null
  audio_url: string | null
  /** 创建/编辑后即刻推送到云端的单资产同步结果（无推送则为 null） */
  sync_result: {
    asset_id: string
    name: string
    status: string
    version: number | null
    message: string | null
  } | null
}

export interface ListCreationAssetsQuery {
  category?: CreationAssetCategory
  tags?: string
  search?: string
  page?: number
  page_size?: number
}

export interface CreateCreationAssetPayload {
  name: string
  category: CreationAssetCategory
  description?: string
  tags?: string[]
  image_asset_id?: string | null
  audio_asset_id?: string | null
}

export interface UpdateCreationAssetPayload extends Partial<CreateCreationAssetPayload> {}

export interface TagSummary {
  name: string
  count: number
}

export interface SyncConfig {
  owner_id: string
  owner_name: string
  qiniu_configured: boolean
}

export type SyncResultStatus =
  | 'synced'
  | 'conflict'
  | 'failed'
  | 'imported'
  | 'updated'
  | 'up_to_date'
  | 'skipped'

export interface SyncResultItem {
  asset_id: string
  name: string
  status: SyncResultStatus
  version: number | null
  message: string | null
}

export interface SyncResult {
  tag: string
  items: SyncResultItem[]
}

export async function listCreationAssets(
  query: ListCreationAssetsQuery = {},
): Promise<Paginated<CreationAsset>> {
  const { data } = await apiClient.get<Paginated<CreationAsset>>('/creation-assets', {
    params: query,
  })
  return data
}

export async function listCreationAssetTags(): Promise<{ tags: TagSummary[] }> {
  const { data } = await apiClient.get<{ tags: TagSummary[] }>('/creation-assets/tags')
  return data
}

export async function createCreationAsset(
  payload: CreateCreationAssetPayload,
): Promise<CreationAsset> {
  const { data } = await apiClient.post<CreationAsset>('/creation-assets', payload)
  return data
}

export async function updateCreationAsset(
  id: string,
  payload: UpdateCreationAssetPayload,
): Promise<CreationAsset> {
  const { data } = await apiClient.patch<CreationAsset>(`/creation-assets/${id}`, payload)
  return data
}

export async function deleteCreationAsset(id: string): Promise<void> {
  await apiClient.delete(`/creation-assets/${id}`)
}

// ---------------- 团队项目 ----------------

export interface ProjectMember {
  owner_id: string
  owner_name: string
}

export interface TeamProject {
  tag: string
  name: string
  description: string
  created_by: string
  created_by_id: string
  created_at: string
  members: ProjectMember[]
}

export async function listProjects(): Promise<TeamProject[]> {
  const { data } = await apiClient.get<{ items: TeamProject[] }>(
    '/creation-assets/projects',
  )
  return data.items
}

export async function createProject(
  name: string,
  description: string,
): Promise<TeamProject> {
  const { data } = await apiClient.post<TeamProject>('/creation-assets/projects', {
    name,
    description,
  })
  return data
}

export async function getSyncConfig(): Promise<SyncConfig> {
  const { data } = await apiClient.get<SyncConfig>('/creation-assets/sync/status')
  return data
}

export async function updateOwnerName(ownerName: string): Promise<SyncConfig> {
  const { data } = await apiClient.put<SyncConfig>('/creation-assets/sync/status', {
    owner_name: ownerName,
  })
  return data
}

/** 将该标签下「我的」资产上传到七牛云。 */
export async function syncAssetsByTag(tag: string): Promise<SyncResult> {
  const { data } = await apiClient.post<SyncResult>(
    '/creation-assets/sync',
    { tag },
    { timeout: 300_000 },
  )
  return data
}

/** 从七牛云拉取该标签下全部用户共享的资产。 */
export async function pullAssetsByTag(tag: string): Promise<SyncResult> {
  const { data } = await apiClient.post<SyncResult>(
    '/creation-assets/pull',
    { tag },
    { timeout: 300_000 },
  )
  return data
}

// ---------------- 集中化自动同步 ----------------

export interface AutoSyncConfig {
  enabled: boolean
  tag: string
  last_sync_at: string
}

export interface AutoSyncResult {
  tag: string
  pushed: SyncResultItem[]
  pulled: SyncResultItem[]
  errors: string[]
}

export async function getAutoSyncConfig(): Promise<AutoSyncConfig> {
  const { data } = await apiClient.get<AutoSyncConfig>(
    '/creation-assets/auto-sync',
  )
  return data
}

export async function updateAutoSyncConfig(
  enabled: boolean,
  tag: string,
): Promise<AutoSyncConfig> {
  const { data } = await apiClient.put<AutoSyncConfig>(
    '/creation-assets/auto-sync',
    { enabled, tag },
  )
  return data
}

/** 手动触发一次集中化自动同步周期（推送 + 拉取）。 */
export async function runAutoSyncNow(): Promise<AutoSyncResult> {
  const { data } = await apiClient.post<AutoSyncResult>(
    '/creation-assets/auto-sync/run',
    {},
    { timeout: 300_000 },
  )
  return data
}
