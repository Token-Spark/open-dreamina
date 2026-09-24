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

import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import {
  batchUpdateReviewItems,
  createReviewSession,
  deleteReviewSession,
  getReviewSession,
  listReviewFolders,
  listReviewItems,
  listReviewSessions,
  rescanReviewSession,
  updateReviewItem,
  updateReviewSession,
  type BatchUpdateEntry,
  type ReviewItem,
  type ReviewSession,
  type ReviewSessionStatus,
  type ReviewStatus,
} from '@/api/reviews'

export const REVIEW_SESSIONS_KEY = ['reviews', 'sessions'] as const
export const REVIEW_FOLDERS_KEY = ['reviews', 'folders'] as const
export const REVIEW_ITEMS_KEY = ['reviews', 'items'] as const

// ---------------- 会话列表 ----------------

export function useReviewSessions() {
  return useQuery({
    queryKey: REVIEW_SESSIONS_KEY,
    queryFn: listReviewSessions,
  })
}

// ---------------- 可用文件夹 ----------------

export function useReviewFolders() {
  return useQuery({
    queryKey: REVIEW_FOLDERS_KEY,
    queryFn: listReviewFolders,
    staleTime: 60 * 1000,
  })
}

// ---------------- 会话详情 ----------------

export function useReviewSession(sessionId: string | null) {
  return useQuery({
    queryKey: [...REVIEW_SESSIONS_KEY, sessionId],
    queryFn: () => getReviewSession(sessionId as string),
    enabled: !!sessionId,
  })
}

// ---------------- 审阅条目 ----------------

export function useReviewItems(sessionId: string | null, status?: ReviewStatus) {
  return useQuery({
    queryKey: [...REVIEW_ITEMS_KEY, sessionId, status],
    queryFn: () => {
      if (!sessionId) throw new Error('no session')
      return listReviewItems(sessionId, status)
    },
    enabled: !!sessionId,
  })
}

// ---------------- 创建会话 ----------------

export function useCreateReviewSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ title, folderPath }: { title: string; folderPath: string }) =>
      createReviewSession(title, folderPath),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REVIEW_SESSIONS_KEY })
    },
  })
}

// ---------------- 更新会话 ----------------

export function useUpdateReviewSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      sessionId,
      payload,
    }: {
      sessionId: string
      payload: { title?: string; status?: ReviewSessionStatus }
    }) => updateReviewSession(sessionId, payload),
    onSuccess: (session) => {
      qc.setQueryData([...REVIEW_SESSIONS_KEY], (old: ReviewSession[] | undefined) =>
        old ? old.map((s) => (s.id === session.id ? session : s)) : old,
      )
      qc.invalidateQueries({ queryKey: [...REVIEW_SESSIONS_KEY, session.id] })
      qc.invalidateQueries({ queryKey: REVIEW_SESSIONS_KEY })
    },
  })
}

// ---------------- 删除会话 ----------------

export function useDeleteReviewSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sessionId: string) => deleteReviewSession(sessionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REVIEW_SESSIONS_KEY })
    },
  })
}

// ---------------- 重新扫描 ----------------

export function useRescanReviewSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sessionId: string) => rescanReviewSession(sessionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REVIEW_ITEMS_KEY })
      qc.invalidateQueries({ queryKey: REVIEW_SESSIONS_KEY })
    },
  })
}

// ---------------- 更新单个条目 ----------------

export function useUpdateReviewItem(sessionId: string) {
  const qc = useQueryClient()
  // 条目查询按状态过滤缓存（key 尾部带 status），用前缀匹配覆盖全部筛选视图
  const itemsPrefix = [...REVIEW_ITEMS_KEY, sessionId]
  return useMutation({
    mutationFn: ({
      itemId,
      payload,
    }: {
      itemId: string
      payload: { status?: ReviewStatus; feedback?: string }
    }) => updateReviewItem(itemId, payload),
    onMutate: async ({ itemId, payload }) => {
      await qc.cancelQueries({ queryKey: itemsPrefix })
      const prev = qc.getQueriesData<ReviewItem[]>({ queryKey: itemsPrefix })
      qc.setQueriesData<ReviewItem[]>({ queryKey: itemsPrefix }, (old) =>
        old
          ? old.map((it) =>
              it.id === itemId
                ? { ...it, ...payload, updated_at: new Date().toISOString() }
                : it,
            )
          : old,
      )
      return { prev }
    },
    onError: (_e, _vars, ctx) => {
      // 回滚到各自筛选视图的旧数据
      for (const [key, data] of ctx?.prev ?? []) {
        qc.setQueryData(key, data)
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: itemsPrefix })
      qc.invalidateQueries({ queryKey: [...REVIEW_SESSIONS_KEY, sessionId] })
      qc.invalidateQueries({ queryKey: REVIEW_SESSIONS_KEY })
    },
  })
}

// ---------------- 批量更新条目 ----------------

export function useBatchUpdateReviewItems(sessionId: string) {
  const qc = useQueryClient()
  const itemsPrefix = [...REVIEW_ITEMS_KEY, sessionId]
  return useMutation({
    mutationFn: (items: BatchUpdateEntry[]) =>
      batchUpdateReviewItems(sessionId, items),
    onMutate: async (items) => {
      await qc.cancelQueries({ queryKey: itemsPrefix })
      const prev = qc.getQueriesData<ReviewItem[]>({ queryKey: itemsPrefix })
      const updates = new Map(items.map((u) => [u.id, u]))
      qc.setQueriesData<ReviewItem[]>({ queryKey: itemsPrefix }, (old) =>
        old
          ? old.map((it) => {
              const upd = updates.get(it.id)
              if (!upd) return it
              return {
                ...it,
                ...(upd.status !== undefined ? { status: upd.status } : {}),
                ...(upd.feedback !== undefined ? { feedback: upd.feedback } : {}),
                updated_at: new Date().toISOString(),
              }
            })
          : old,
      )
      return { prev }
    },
    onError: (_e, _vars, ctx) => {
      for (const [key, data] of ctx?.prev ?? []) {
        qc.setQueryData(key, data)
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: itemsPrefix })
      qc.invalidateQueries({ queryKey: [...REVIEW_SESSIONS_KEY, sessionId] })
      qc.invalidateQueries({ queryKey: REVIEW_SESSIONS_KEY })
    },
  })
}
