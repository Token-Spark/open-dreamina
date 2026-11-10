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
import type { TaskType } from './tasks'
import { createReviewApi } from './reviewCore'

/** 评分档位：未打分待审 / 通过（≥70）/ 需重生成（60–69）/ 需重新设计（<60）。 */
export type ShotVerdict = 'pending' | 'pass' | 'revise' | 'redesign'

/** 内容类型：镜头成片视频，或以镜号命名的分镜图/关键帧。 */
export type ShotContentType = 'video' | 'image'

/** 条目来源：素材目录扫描所得 / 审阅中心返工生成。 */
export type ShotItemOrigin = 'scan' | 'regen'

export type ShotReviewSessionStatus = 'draft' | 'in_review' | 'completed' | 'archived'

export interface ShotReviewItem {
  id: string
  session_id: string
  episode: string | null
  shot_id: string
  /** 剧目名称（任务卡片标签）；后端解析不到时回落为会话标题。 */
  drama_title: string | null
  /** 内容类型，决定预览形态与返工生成的内容模式。 */
  content_type: ShotContentType
  /** 来源：扫描所得 / 返工生成的新版本。 */
  origin: ShotItemOrigin
  /** 返工生成的产物指向素材库资产；扫描条目为 null。 */
  asset_id: string | null
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

export interface ShotReviewBatchEntry extends ShotReviewItemPatch {
  id: string
}

export interface ShotReviewItemFilters {
  episode?: string
  verdict?: ShotVerdict
}

// 与制片人审阅共用同一份 HTTP 实现，这里只描述差异。
const core = createReviewApi<
  ShotReviewSession,
  ShotReviewItem,
  ShotReviewFolderRoot,
  ShotReviewItemPatch,
  ShotReviewItemFilters,
  ShotReviewSessionStatus
>({
  prefix: '/shot-reviews',
  createPathKey: 'root_path',
  listItemsParams: (filters) => {
    const params: Record<string, string> = {}
    if (filters.episode) params.episode = filters.episode
    if (filters.verdict) params.verdict = filters.verdict
    return Object.keys(params).length ? params : undefined
  },
})

export const listShotReviewFolders = core.listFolders
export const listShotReviewSessions = core.listSessions
export const createShotReviewSession = core.createSession
export const getShotReviewSession = core.getSession
export const updateShotReviewSession = core.updateSession
export const deleteShotReviewSession = core.deleteSession
export const rescanShotReviewSession = core.rescanSession
export const listShotReviewItems = core.listItems
export const updateShotReviewItem = core.updateItem
export const batchUpdateShotReviewItems = core.batchUpdateItems
export const shotReviewItemFileUrl = core.itemFileUrl
export const shotReviewItemThumbnailUrl = core.itemThumbnailUrl

// 以下为镜头审片独有：删除废弃版本，可连带物理删除磁盘视频。
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

// ---------------- 返工生成（任务卡片内改提示词重生成） ----------------

export type ShotRegenerationStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'discarded'

/** 一条返工生成记录：卡片据此展示进度、结果与「采用为新版本」入口。 */
export interface ShotReviewRegeneration {
  id: string
  session_id: string
  item_id: string
  episode: string | null
  shot_id: string
  task_id: string | null
  prompt: string
  provider: string | null
  model_id: string | null
  task_type: TaskType
  params: Record<string, unknown>
  status: ShotRegenerationStatus
  progress: number
  result_asset_id: string | null
  /** 结果预览地址（/assets/{id}/file）；未完成时为 null。 */
  result_url: string | null
  error_msg: string | null
  /** 已采用生成的新版本条目 id；非空表示不可重复采用。 */
  adopted_item_id: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ShotRegenerationPayload {
  prompt: string
  provider: string
  model_id?: string
  /** 缺省时后端按内容类型 + 是否带参考素材派生。 */
  task_type?: TaskType
  params?: Record<string, unknown>
  input_asset_ids?: string[]
}

/** 会话内全部返工记录（接口会顺手把在途任务状态同步回库）。 */
export async function listShotReviewRegenerations(
  sessionId: string,
): Promise<ShotReviewRegeneration[]> {
  const { data } = await apiClient.get<{ items: ShotReviewRegeneration[]; total: number }>(
    `/shot-reviews/sessions/${sessionId}/regenerations`,
  )
  return data.items
}

/** 按卡片上改写的提示词发起返工生成（复用创作页任务管线）。 */
export async function createShotReviewRegeneration(
  itemId: string,
  payload: ShotRegenerationPayload,
): Promise<ShotReviewRegeneration> {
  const { data } = await apiClient.post<ShotReviewRegeneration>(
    `/shot-reviews/items/${itemId}/regenerations`,
    payload,
  )
  return data
}

/** 把返工结果采用为同镜号的新版本，返回新建的审片条目。 */
export async function adoptShotReviewRegeneration(regenId: string): Promise<ShotReviewItem> {
  const { data } = await apiClient.post<ShotReviewItem>(
    `/shot-reviews/regenerations/${regenId}/adopt`,
  )
  return data
}

/** 放弃某次返工结果（后端软删除留痕）。 */
export async function discardShotReviewRegeneration(
  regenId: string,
): Promise<ShotReviewRegeneration> {
  const { data } = await apiClient.delete<ShotReviewRegeneration>(
    `/shot-reviews/regenerations/${regenId}`,
  )
  return data
}
