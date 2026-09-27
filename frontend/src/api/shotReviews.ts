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

/** 评分档位：未打分待审 / 通过（≥70）/ 需重生成（60–69）/ 需重新设计（<60）。 */
export type ShotVerdict = 'pending' | 'pass' | 'revise' | 'redesign'

export type ShotReviewSessionStatus = 'draft' | 'in_review' | 'completed' | 'archived'

export interface ShotReviewItem {
  id: string
  session_id: string
  episode: string | null
  shot_id: string
  file_path: string
  file_name: string
  file_size: number | null
  mime_type: string | null
  width: number | null
  height: number | null
  duration: number | null
  thumbnail_path: string | null
  score: number | null
  verdict: ShotVerdict
  feedback: string
  /** 同镜号多版本时的「选定保留版本」标记；同一集+镜号下至多一条为 true。 */
  selected: boolean
  /** 扫描时从同集 shots.md 提取的提示词底稿，改写精修提示词时的参考。 */
  source_prompt: string | null
  /** 审片人改写的 AIGC 精修提示词，作为该镜的修改备注；null 表示未填写。 */
  revised_prompt: string | null
  shot_function: string | null
  script_duration: number | null
  shot_size: string | null
  movement: string | null
  dialogue: string | null
  render_status: string | null
  model: string | null
  sort_order: number
  reviewed_at: string | null
  created_at: string
  updated_at: string
  thumbnail_url: string | null
  file_url: string
}

export interface ShotReviewSummary {
  pending: number
  pass: number
  revise: number
  redesign: number
  total: number
  scored: number
  /** 已填写精修提示词（修改备注）的镜头数。 */
  prompts_revised: number
  average_score: number | null
  /** 同镜号有 ≥2 个版本的镜头数（多版本栏目数）。 */
  multi_take_shots?: number
  /** 已选定保留版本的镜头数。 */
  selected_shots?: number
}

export interface ShotReviewSession {
  id: string
  title: string
  root_path: string
  status: ShotReviewSessionStatus
  summary: Partial<ShotReviewSummary>
  item_count: number
  created_at: string
  updated_at: string
}

export interface ShotReviewFolderSubdir {
  path: string
  name: string
  subdirs?: ShotReviewFolderSubdir[]
}

export interface ShotReviewFolderRoot {
  path: string
  name: string
  subdirs: ShotReviewFolderSubdir[]
  exists: boolean
}

export interface ShotReviewScanResult {
  added: number
  removed: number
  total: number
}

export interface ShotReviewItemPatch {
  score?: number
  clear_score?: boolean
  feedback?: string
  /** 精修提示词；空串表示清除（后端落库为 null）。 */
  revised_prompt?: string
  /** 选定该版本为同镜号栏目的保留版本；false 取消选定。 */
  selected?: boolean
}

export async function listShotReviewFolders(): Promise<ShotReviewFolderRoot[]> {
  const { data } = await apiClient.get<{ roots: ShotReviewFolderRoot[] }>('/shot-reviews/folders')
  return data.roots
}

export async function listShotReviewSessions(): Promise<ShotReviewSession[]> {
  const { data } = await apiClient.get<{ items: ShotReviewSession[] }>('/shot-reviews/sessions')
  return data.items
}

export async function createShotReviewSession(
  title: string,
  rootPath: string,
): Promise<ShotReviewSession> {
  const { data } = await apiClient.post<ShotReviewSession>('/shot-reviews/sessions', {
    title,
    root_path: rootPath,
  })
  return data
}

export async function getShotReviewSession(sessionId: string): Promise<ShotReviewSession> {
  const { data } = await apiClient.get<ShotReviewSession>(`/shot-reviews/sessions/${sessionId}`)
  return data
}

export async function updateShotReviewSession(
  sessionId: string,
  payload: { title?: string; status?: ShotReviewSessionStatus },
): Promise<ShotReviewSession> {
  const { data } = await apiClient.patch<ShotReviewSession>(
    `/shot-reviews/sessions/${sessionId}`,
    payload,
  )
  return data
}

export async function deleteShotReviewSession(sessionId: string): Promise<void> {
  await apiClient.delete(`/shot-reviews/sessions/${sessionId}`)
}

export async function rescanShotReviewSession(sessionId: string): Promise<ShotReviewScanResult> {
  const { data } = await apiClient.post<ShotReviewScanResult>(
    `/shot-reviews/sessions/${sessionId}/scan`,
  )
  return data
}

export async function listShotReviewItems(
  sessionId: string,
  filters?: { episode?: string; verdict?: ShotVerdict },
): Promise<ShotReviewItem[]> {
  const params: Record<string, string> = {}
  if (filters?.episode) params.episode = filters.episode
  if (filters?.verdict) params.verdict = filters.verdict
  const { data } = await apiClient.get<ShotReviewItem[]>(
    `/shot-reviews/sessions/${sessionId}/items`,
    { params: Object.keys(params).length ? params : undefined },
  )
  return data
}

export async function updateShotReviewItem(
  itemId: string,
  payload: ShotReviewItemPatch,
): Promise<ShotReviewItem> {
  const { data } = await apiClient.patch<ShotReviewItem>(`/shot-reviews/items/${itemId}`, payload)
  return data
}

export interface ShotReviewBatchEntry extends ShotReviewItemPatch {
  id: string
}

export async function batchUpdateShotReviewItems(
  sessionId: string,
  items: ShotReviewBatchEntry[],
): Promise<{ updated: number; failed: number }> {
  const { data } = await apiClient.post(`/shot-reviews/sessions/${sessionId}/items/batch`, {
    items,
  })
  return data
}

export interface ShotReviewBulkDeleteResult {
  deleted: number
  failed: number
  /** 物理删除视频文件时释放的字节数；仅移出列表时为 0。 */
  freed_bytes: number
  errors: { id: string; file_name?: string; message: string }[]
}

/**
 * 批量删除审片条目（通常为同镜号下未选定的废弃版本）。
 * deleteFile=true 时同时从磁盘删除视频文件；false 仅移出审片列表。
 */
export async function bulkDeleteShotReviewItems(
  sessionId: string,
  itemIds: string[],
  deleteFile: boolean,
): Promise<ShotReviewBulkDeleteResult> {
  const { data } = await apiClient.post<ShotReviewBulkDeleteResult>(
    `/shot-reviews/sessions/${sessionId}/items/delete`,
    { item_ids: itemIds, delete_file: deleteFile },
  )
  return data
}

/** 删除单个审片条目；deleteFile=true 时同时从磁盘删除对应视频文件。 */
export async function deleteShotReviewItem(
  itemId: string,
  deleteFile: boolean,
): Promise<ShotReviewBulkDeleteResult> {
  const { data } = await apiClient.delete<ShotReviewBulkDeleteResult>(
    `/shot-reviews/items/${itemId}`,
    { params: deleteFile ? { delete_file: true } : undefined },
  )
  return data
}

/** Public URL helpers (served by the backend shot review router). */
export function shotReviewItemFileUrl(itemId: string): string {
  return `/api/v1/shot-reviews/items/${itemId}/file`
}

export function shotReviewItemThumbnailUrl(itemId: string): string {
  return `/api/v1/shot-reviews/items/${itemId}/thumbnail`
}