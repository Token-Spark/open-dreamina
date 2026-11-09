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

import { createReviewApi } from './reviewCore'

export type { ReviewScanResult } from './reviewCore'

export type ReviewStatus = 'pending' | 'approved' | 'rejected' | 'needs_revision'

export type ReviewSessionStatus = 'draft' | 'in_review' | 'completed' | 'archived'

export interface ReviewItem {
  id: string
  session_id: string
  file_path: string
  file_name: string
  file_size: number | null
  mime_type: string | null
  width: number | null
  height: number | null
  duration: number | null
  thumbnail_path: string | null
  status: ReviewStatus
  feedback: string
  sort_order: number
  reviewed_at: string | null
  created_at: string
  updated_at: string
  thumbnail_url: string | null
  file_url: string
}

export interface ReviewSession {
  id: string
  title: string
  folder_path: string
  status: ReviewSessionStatus
  summary: Record<string, number>
  item_count: number
  created_at: string
  updated_at: string
}

export interface ReviewFolderRoot {
  path: string
  name: string
  subdirs: ReviewFolderSubdir[]
  exists: boolean
}

export interface ReviewFolderSubdir {
  path: string
  name: string
  /** 第二层子目录（后端递归两层返回）。 */
  subdirs?: ReviewFolderSubdir[]
}

export interface BatchUpdateEntry {
  id: string
  status?: ReviewStatus
  feedback?: string
}

export type ReviewItemPatch = { status?: ReviewStatus; feedback?: string }

// 与镜头审片共用同一份 HTTP 实现，这里只描述差异。
const core = createReviewApi<
  ReviewSession,
  ReviewItem,
  ReviewFolderRoot,
  ReviewItemPatch,
  ReviewStatus,
  ReviewSessionStatus
>({
  prefix: '/reviews',
  createPathKey: 'folder_path',
  listItemsParams: (status) => (status ? { status } : undefined),
})

export const listReviewFolders = core.listFolders
export const listReviewSessions = core.listSessions
export const createReviewSession = core.createSession
export const getReviewSession = core.getSession
export const updateReviewSession = core.updateSession
export const deleteReviewSession = core.deleteSession
export const rescanReviewSession = core.rescanSession
export const listReviewItems = core.listItems
export const updateReviewItem = core.updateItem
export const batchUpdateReviewItems = core.batchUpdateItems
export const reviewItemFileUrl = core.itemFileUrl
export const reviewItemThumbnailUrl = core.itemThumbnailUrl
