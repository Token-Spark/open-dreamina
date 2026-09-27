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
  batchUpdateShotReviewItems,
  bulkDeleteShotReviewItems,
  createShotReviewSession,
  deleteShotReviewItem,
  deleteShotReviewSession,
  getShotReviewSession,
  listShotReviewFolders,
  listShotReviewItems,
  listShotReviewSessions,
  rescanShotReviewSession,
  updateShotReviewItem,
  updateShotReviewSession,
  type ShotReviewBatchEntry,
  type ShotReviewItem,
  type ShotReviewItemPatch,
  type ShotReviewSession,
  type ShotReviewSessionStatus,
  type ShotVerdict,
} from '@/api/shotReviews'

export const SHOT_REVIEW_SESSIONS_KEY = ['shot-reviews', 'sessions'] as const
export const SHOT_REVIEW_FOLDERS_KEY = ['shot-reviews', 'folders'] as const
export const SHOT_REVIEW_ITEMS_KEY = ['shot-reviews', 'items'] as const

/** 按分数派生的档位，用于乐观更新时同步前端展示。 */
export function verdictFromScore(score: number | null | undefined): ShotVerdict {
  if (score === null || score === undefined) return 'pending'
  if (score >= 70) return 'pass'
  if (score >= 60) return 'revise'
  return 'redesign'
}

/** 多版本分组键：同一集 + 同一镜号的视频归入同一栏目。 */
export function shotGroupKey(item: Pick<ShotReviewItem, 'episode' | 'shot_id'>): string {
  return `${item.episode ?? ''}|${item.shot_id}`
}

// ---------------- 会话列表 ----------------

export function useShotReviewSessions() {
  return useQuery({
    queryKey: SHOT_REVIEW_SESSIONS_KEY,
    queryFn: listShotReviewSessions,
  })
}

// ---------------- 可用文件夹 ----------------

export function useShotReviewFolders() {
  return useQuery({
    queryKey: SHOT_REVIEW_FOLDERS_KEY,
    queryFn: listShotReviewFolders,
    staleTime: 60 * 1000,
  })
}

// ---------------- 会话详情 ----------------

export function useShotReviewSession(sessionId: string | null) {
  return useQuery({
    queryKey: [...SHOT_REVIEW_SESSIONS_KEY, sessionId],
    queryFn: () => getShotReviewSession(sessionId as string),
    enabled: !!sessionId,
  })
}

// ---------------- 审片条目 ----------------

export function useShotReviewItems(
  sessionId: string | null,
  filters?: { episode?: string; verdict?: ShotVerdict },
) {
  const episode = filters?.episode || undefined
  const verdict = filters?.verdict || undefined
  return useQuery({
    queryKey: [...SHOT_REVIEW_ITEMS_KEY, sessionId, episode ?? null, verdict ?? null],
    queryFn: () => {
      if (!sessionId) throw new Error('no session')
      return listShotReviewItems(sessionId, { episode, verdict })
    },
    enabled: !!sessionId,
  })
}

// ---------------- 创建会话 ----------------

export function useCreateShotReviewSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ title, rootPath }: { title: string; rootPath: string }) =>
      createShotReviewSession(title, rootPath),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SHOT_REVIEW_SESSIONS_KEY })
    },
  })
}

// ---------------- 更新会话 ----------------

export function useUpdateShotReviewSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      sessionId,
      payload,
    }: {
      sessionId: string
      payload: { title?: string; status?: ShotReviewSessionStatus }
    }) => updateShotReviewSession(sessionId, payload),
    onSuccess: (session) => {
      qc.setQueryData([...SHOT_REVIEW_SESSIONS_KEY], (old: ShotReviewSession[] | undefined) =>
        old ? old.map((s) => (s.id === session.id ? session : s)) : old,
      )
      qc.invalidateQueries({ queryKey: [...SHOT_REVIEW_SESSIONS_KEY, session.id] })
      qc.invalidateQueries({ queryKey: SHOT_REVIEW_SESSIONS_KEY })
    },
  })
}

// ---------------- 删除会话 ----------------

export function useDeleteShotReviewSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sessionId: string) => deleteShotReviewSession(sessionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SHOT_REVIEW_SESSIONS_KEY })
    },
  })
}

// ---------------- 重新扫描 ----------------

export function useRescanShotReviewSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sessionId: string) => rescanShotReviewSession(sessionId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SHOT_REVIEW_ITEMS_KEY })
      qc.invalidateQueries({ queryKey: SHOT_REVIEW_SESSIONS_KEY })
    },
  })
}

// ---------------- 更新单个条目（含评分/清分/意见） ----------------

export function useUpdateShotReviewItem(sessionId: string) {
  const qc = useQueryClient()
  // 条目查询 key 尾部带筛选条件，用前缀匹配覆盖全部筛选视图
  const itemsPrefix = [...SHOT_REVIEW_ITEMS_KEY, sessionId]
  return useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: ShotReviewItemPatch }) =>
      updateShotReviewItem(itemId, payload),
    onMutate: async ({ itemId, payload }) => {
      await qc.cancelQueries({ queryKey: itemsPrefix })
      const prev = qc.getQueriesData<ShotReviewItem[]>({ queryKey: itemsPrefix })
      const now = new Date().toISOString()
      qc.setQueriesData<ShotReviewItem[]>({ queryKey: itemsPrefix }, (old) => {
        if (!old) return old
        const target = old.find((it) => it.id === itemId)
        const groupKey = target ? shotGroupKey(target) : null
        return old.map((it) => {
          // 选定新版本时，同镜号栏目内的其余版本乐观取消选中（与后端互斥逻辑一致）
          if (
            it.id !== itemId &&
            payload.selected === true &&
            groupKey !== null &&
            it.selected &&
            shotGroupKey(it) === groupKey
          ) {
            return { ...it, selected: false, updated_at: now }
          }
          if (it.id !== itemId) return it
          const nextScore =
            payload.clear_score === true
              ? null
              : payload.score !== undefined
                ? payload.score
                : it.score
          return {
            ...it,
            score: nextScore,
            verdict: verdictFromScore(nextScore),
            ...(payload.feedback !== undefined ? { feedback: payload.feedback } : {}),
            ...(payload.revised_prompt !== undefined
              ? { revised_prompt: payload.revised_prompt.trim() || null }
              : {}),
            ...(payload.selected !== undefined ? { selected: payload.selected } : {}),
            reviewed_at: nextScore === null ? null : now,
            updated_at: now,
          }
        })
      })
      return { prev }
    },
    onError: (_e, _vars, ctx) => {
      for (const [key, data] of ctx?.prev ?? []) {
        qc.setQueryData(key, data)
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: itemsPrefix })
      qc.invalidateQueries({ queryKey: [...SHOT_REVIEW_SESSIONS_KEY, sessionId] })
      qc.invalidateQueries({ queryKey: SHOT_REVIEW_SESSIONS_KEY })
    },
  })
}

// ---------------- 批量更新条目 ----------------

export function useBatchUpdateShotReviewItems(sessionId: string) {
  const qc = useQueryClient()
  const itemsPrefix = [...SHOT_REVIEW_ITEMS_KEY, sessionId]
  return useMutation({
    mutationFn: (items: ShotReviewBatchEntry[]) =>
      batchUpdateShotReviewItems(sessionId, items),
    onMutate: async (items) => {
      await qc.cancelQueries({ queryKey: itemsPrefix })
      const prev = qc.getQueriesData<ShotReviewItem[]>({ queryKey: itemsPrefix })
      const updates = new Map(items.map((u) => [u.id, u]))
      const now = new Date().toISOString()
      qc.setQueriesData<ShotReviewItem[]>({ queryKey: itemsPrefix }, (old) => {
        if (!old) return old
        // 批量选定：收集本次被选中的分组，用于乐观取消同组其余版本的选中
        const selectedGroups = new Set<string>()
        for (const it of old) {
          const upd = updates.get(it.id)
          if (upd?.selected === true) selectedGroups.add(shotGroupKey(it))
        }
        return old.map((it) => {
          const upd = updates.get(it.id)
          if (!upd) {
            if (it.selected && selectedGroups.has(shotGroupKey(it))) {
              return { ...it, selected: false, updated_at: now }
            }
            return it
          }
          const nextScore =
            upd.clear_score === true
              ? null
              : upd.score !== undefined
                ? upd.score
                : it.score
          return {
            ...it,
            score: nextScore,
            verdict: verdictFromScore(nextScore),
            ...(upd.feedback !== undefined ? { feedback: upd.feedback } : {}),
            ...(upd.revised_prompt !== undefined
              ? { revised_prompt: upd.revised_prompt.trim() || null }
              : {}),
            ...(upd.selected !== undefined ? { selected: upd.selected } : {}),
            updated_at: now,
          }
        })
      })
      return { prev }
    },
    onError: (_e, _vars, ctx) => {
      for (const [key, data] of ctx?.prev ?? []) {
        qc.setQueryData(key, data)
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: itemsPrefix })
      qc.invalidateQueries({ queryKey: [...SHOT_REVIEW_SESSIONS_KEY, sessionId] })
      qc.invalidateQueries({ queryKey: SHOT_REVIEW_SESSIONS_KEY })
    },
  })
}
// ---------------- 删除条目（废弃视频清理） ----------------

/** 从会话的全部条目缓存中乐观移除指定条目（各筛选视图前缀匹配）。 */
function removeItemsFromItemCaches(
  qc: ReturnType<typeof useQueryClient>,
  sessionId: string,
  ids: Set<string>,
) {
  qc.setQueriesData<ShotReviewItem[]>(
    { queryKey: [...SHOT_REVIEW_ITEMS_KEY, sessionId] },
    (old) => (old ? old.filter((it) => !ids.has(it.id)) : old),
  )
}

export function useDeleteShotReviewItem(sessionId: string) {
  const qc = useQueryClient()
  const itemsPrefix = [...SHOT_REVIEW_ITEMS_KEY, sessionId]
  return useMutation({
    mutationFn: ({ itemId, deleteFile }: { itemId: string; deleteFile: boolean }) =>
      deleteShotReviewItem(itemId, deleteFile),
    onMutate: async ({ itemId }) => {
      await qc.cancelQueries({ queryKey: itemsPrefix })
      const prev = qc.getQueriesData<ShotReviewItem[]>({ queryKey: itemsPrefix })
      removeItemsFromItemCaches(qc, sessionId, new Set([itemId]))
      return { prev }
    },
    onError: (_e, _vars, ctx) => {
      for (const [key, data] of ctx?.prev ?? []) {
        qc.setQueryData(key, data)
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SHOT_REVIEW_SESSIONS_KEY })
    },
  })
}

export function useBulkDeleteShotReviewItems(sessionId: string) {
  const qc = useQueryClient()
  const itemsPrefix = [...SHOT_REVIEW_ITEMS_KEY, sessionId]
  return useMutation({
    mutationFn: ({ itemIds, deleteFile }: { itemIds: string[]; deleteFile: boolean }) =>
      bulkDeleteShotReviewItems(sessionId, itemIds, deleteFile),
    onMutate: async ({ itemIds }) => {
      await qc.cancelQueries({ queryKey: itemsPrefix })
      const prev = qc.getQueriesData<ShotReviewItem[]>({ queryKey: itemsPrefix })
      removeItemsFromItemCaches(qc, sessionId, new Set(itemIds))
      return { prev }
    },
    onError: (_e, _vars, ctx) => {
      for (const [key, data] of ctx?.prev ?? []) {
        qc.setQueryData(key, data)
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SHOT_REVIEW_SESSIONS_KEY })
    },
  })
}
