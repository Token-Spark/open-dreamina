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

/**
 * 制片人审阅与镜头审片的 HTTP 契约是同构的：同样的会话 CRUD、扫描、条目
 * 更新、批量更新与文件 URL，只有前缀、创建会话时的目录字段名、条目筛选
 * 参数不同。这里放唯一一份实现，两个 api 模块各自只保留类型与差异配置。
 */
export interface ReviewScanResult {
  added: number
  removed: number
  total: number
}

export interface ReviewCoreConfig<F> {
  /** 后端路由前缀，不含 /api/v1。 */
  prefix: string
  /** 创建会话时目录字段的后端名称。 */
  createPathKey: 'folder_path' | 'root_path'
  /** 把各自的条目筛选条件翻译成 query 参数。 */
  listItemsParams?: (filters: F) => Record<string, string> | undefined
}

export function createReviewApi<
  Session,
  Item,
  FolderRoot,
  ItemPatch,
  ItemFilters = undefined,
  SessionStatus extends string = string,
>(config: ReviewCoreConfig<ItemFilters>) {
  const base = config.prefix

  return {
    listFolders: async (): Promise<FolderRoot[]> => {
      const { data } = await apiClient.get<{ roots: FolderRoot[] }>(`${base}/folders`)
      return data.roots
    },

    listSessions: async (): Promise<Session[]> => {
      const { data } = await apiClient.get<{ items: Session[] }>(`${base}/sessions`)
      return data.items
    },

    createSession: async (title: string, path: string): Promise<Session> => {
      const { data } = await apiClient.post<Session>(`${base}/sessions`, {
        title,
        [config.createPathKey]: path,
      })
      return data
    },

    getSession: async (sessionId: string): Promise<Session> => {
      const { data } = await apiClient.get<Session>(`${base}/sessions/${sessionId}`)
      return data
    },

    updateSession: async (
      sessionId: string,
      payload: { title?: string; status?: SessionStatus },
    ): Promise<Session> => {
      const { data } = await apiClient.patch<Session>(`${base}/sessions/${sessionId}`, payload)
      return data
    },

    deleteSession: async (sessionId: string): Promise<void> => {
      await apiClient.delete(`${base}/sessions/${sessionId}`)
    },

    rescanSession: async (sessionId: string): Promise<ReviewScanResult> => {
      const { data } = await apiClient.post<ReviewScanResult>(
        `${base}/sessions/${sessionId}/scan`,
      )
      return data
    },

    listItems: async (sessionId: string, filters?: ItemFilters): Promise<Item[]> => {
      const params = filters != null && config.listItemsParams
        ? config.listItemsParams(filters)
        : undefined
      const { data } = await apiClient.get<Item[]>(
        `${base}/sessions/${sessionId}/items`,
        { params },
      )
      return data
    },

    updateItem: async (itemId: string, payload: ItemPatch): Promise<Item> => {
      const { data } = await apiClient.patch<Item>(`${base}/items/${itemId}`, payload)
      return data
    },

    batchUpdateItems: async (
      sessionId: string,
      items: (ItemPatch & { id: string })[],
    ): Promise<{ updated: number; failed: number }> => {
      const { data } = await apiClient.post(`${base}/sessions/${sessionId}/items/batch`, { items })
      return data
    },

    itemFileUrl: (itemId: string): string => `/api/v1${base}/items/${itemId}/file`,
    itemThumbnailUrl: (itemId: string): string => `/api/v1${base}/items/${itemId}/thumbnail`,
  }
}
