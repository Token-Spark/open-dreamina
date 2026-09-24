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

export interface ReviewScanResult {
  added: number
  removed: number
  total: number
}

export async function listReviewFolders(): Promise<ReviewFolderRoot[]> {
  const { data } = await apiClient.get<{ roots: ReviewFolderRoot[] }>('/reviews/folders')
  return data.roots
}

export async function listReviewSessions(): Promise<ReviewSession[]> {
  const { data } = await apiClient.get<{ items: ReviewSession[] }>('/reviews/sessions')
  return data.items
}

export async function createReviewSession(
  title: string,
  folderPath: string,
): Promise<ReviewSession> {
  const { data } = await apiClient.post<ReviewSession>('/reviews/sessions', {
    title,
    folder_path: folderPath,
  })
  return data
}

export async function getReviewSession(sessionId: string): Promise<ReviewSession> {
  const { data } = await apiClient.get<ReviewSession>(`/reviews/sessions/${sessionId}`)
  return data
}

export async function updateReviewSession(
  sessionId: string,
  payload: { title?: string; status?: ReviewSessionStatus },
): Promise<ReviewSession> {
  const { data } = await apiClient.patch<ReviewSession>(`/reviews/sessions/${sessionId}`, payload)
  return data
}

export async function deleteReviewSession(sessionId: string): Promise<void> {
  await apiClient.delete(`/reviews/sessions/${sessionId}`)
}

export async function rescanReviewSession(sessionId: string): Promise<ReviewScanResult> {
  const { data } = await apiClient.post<ReviewScanResult>(`/reviews/sessions/${sessionId}/scan`)
  return data
}

export async function listReviewItems(
  sessionId: string,
  status?: ReviewStatus,
): Promise<ReviewItem[]> {
  const { data } = await apiClient.get<ReviewItem[]>(
    `/reviews/sessions/${sessionId}/items`,
    { params: status ? { status } : undefined },
  )
  return data
}

export async function updateReviewItem(
  itemId: string,
  payload: { status?: ReviewStatus; feedback?: string },
): Promise<ReviewItem> {
  const { data } = await apiClient.patch<ReviewItem>(`/reviews/items/${itemId}`, payload)
  return data
}

export interface BatchUpdateEntry {
  id: string
  status?: ReviewStatus
  feedback?: string
}

export async function batchUpdateReviewItems(
  sessionId: string,
  items: BatchUpdateEntry[],
): Promise<{ updated: number; failed: number }> {
  const { data } = await apiClient.post(`/reviews/sessions/${sessionId}/items/batch`, { items })
  return data
}

/** Public URL helpers (served by the backend review router). */
export function reviewItemFileUrl(itemId: string): string {
  return `/api/v1/reviews/items/${itemId}/file`
}

export function reviewItemThumbnailUrl(itemId: string): string {
  return `/api/v1/reviews/items/${itemId}/thumbnail`
}
