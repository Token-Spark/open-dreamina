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

import { create } from 'zustand'
import type { TaskStatus, TaskType, Task } from '@/api/tasks'
import { assetFileUrl } from '@/api/assets'
import {
  listConversations,
  createConversation,
  updateConversation,
  deleteConversation,
  listConversationMessages,
  type Conversation,
} from '@/api/conversations'

export interface GenMessage {
  id: string
  prompt: string
  negativePrompt: string
  type: TaskType
  status: TaskStatus
  progress: number
  error: string | null
  message: string | null
  resultUrl: string | null
  thumbnailUrl: string | null
  /** 多图生成：全部结果访问地址（单图时仅 1 项）。 */
  resultUrls: string[]
  params: Record<string, unknown>
  provider: string
  modelId: string | null
  /** 参考图 asset id 列表（多图；旧单图任务回退为 [input_asset_id]）。 */
  inputAssetIds: string[]
  /** 参考图预览地址列表，由 inputAssetIds 派生（与后端 input_asset_url 同构）。 */
  inputAssetUrls: string[]
  createdAt: number
}

/** 将后端 Task 记录重建为对话消息（任务即消息，无数据冗余）。 */
export function taskToMessage(task: Task): GenMessage {
  const params = (task.params ?? {}) as Record<string, unknown>
  const negativePrompt = (params.negative_prompt as string) ?? ''
  // 多图参考：优先读 params.input_asset_ids，回退到 input_asset_id 单图（兼容旧任务）
  const rawIds = Array.isArray(params.input_asset_ids)
    ? (params.input_asset_ids as unknown[]).filter((id): id is string => typeof id === 'string')
    : []
  const inputAssetIds = rawIds.length > 0
    ? rawIds
    : task.input_asset_id
      ? [task.input_asset_id]
      : []
  return {
    id: task.id,
    prompt: task.prompt ?? '',
    negativePrompt,
    type: task.type,
    status: task.status,
    progress: task.progress,
    error: task.error_msg,
    message: null,
    resultUrl: task.result_url,
    thumbnailUrl: task.thumbnail_url,
    resultUrls: task.result_urls?.length ? task.result_urls : task.result_url ? [task.result_url] : [],
    params,
    provider: task.provider,
    modelId: task.model_id,
    inputAssetIds,
    inputAssetUrls: inputAssetIds.map(assetFileUrl),
    createdAt: task.created_at ? new Date(task.created_at).getTime() : Date.now(),
  }
}

interface ConversationState {
  topics: Conversation[]
  currentTopicId: string | null
  /** 当前对话的消息列表（按时间升序）。 */
  messages: GenMessage[]
  initialized: boolean
  loadingMessages: boolean

  init: () => Promise<void>
  addTopic: (title?: string) => Promise<string>
  removeTopic: (id: string) => Promise<void>
  renameTopic: (id: string, title: string) => Promise<void>
  setCurrentTopic: (id: string) => Promise<void>
  /** 任务创建后更新本地消息缓存与对话预览（任务已通过后端持久化）。 */
  addMessage: (topicId: string, message: GenMessage) => void
  updateMessage: (topicId: string, messageId: string, patch: Partial<GenMessage>) => void
  deleteMessage: (topicId: string, messageId: string) => void
}

export const useConversationStore = create<ConversationState>((set, get) => ({
  topics: [],
  currentTopicId: null,
  messages: [],
  initialized: false,
  loadingMessages: false,

  init: async () => {
    if (get().initialized) return
    try {
      const topics = await listConversations()
      const first = topics[0]
      let currentId = get().currentTopicId
      if (!currentId || !topics.some((t) => t.id === currentId)) {
        currentId = first?.id ?? null
      }
      let messages: GenMessage[] = []
      if (currentId) {
        messages = (await listConversationMessages(currentId)).map(taskToMessage)
      } else {
        // 无任何对话时自动创建一个
        const created = await createConversation()
        set({ topics: [created], currentTopicId: created.id, messages: [], initialized: true })
        return
      }
      set({ topics, currentTopicId: currentId, messages, initialized: true })
    } catch {
      // 加载失败保持未初始化，CreatePage 可重试
      set({ initialized: true })
    }
  },

  addTopic: async (title) => {
    const created = await createConversation(title ? { title } : {})
    set((state) => ({
      topics: [created, ...state.topics],
      currentTopicId: created.id,
      messages: [],
    }))
    return created.id
  },

  removeTopic: async (id) => {
    await deleteConversation(id)
    set((state) => {
      const next = state.topics.filter((t) => t.id !== id)
      const wasCurrent = state.currentTopicId === id
      const nextCurrentId = wasCurrent ? next[0]?.id ?? null : state.currentTopicId
      return {
        topics: next,
        currentTopicId: nextCurrentId,
        messages: wasCurrent ? [] : state.messages,
      }
    })
    // 删除当前对话后，若仍有其他对话，加载其消息
    const nextId = get().currentTopicId
    if (nextId && get().messages.length === 0) {
      await get().setCurrentTopic(nextId)
    } else if (!nextId) {
      // 全部删空则自动新建一个
      await get().addTopic()
    }
  },

  renameTopic: async (id, title) => {
    const nextTitle = title.trim()
    if (!nextTitle) return
    const updated = await updateConversation(id, nextTitle)
    set((state) => ({
      topics: state.topics.map((t) => (t.id === id ? updated : t)),
    }))
  },

  setCurrentTopic: async (id) => {
    const isCurrent = get().currentTopicId === id
    const msgCount = get().topics.find((t) => t.id === id)?.message_count ?? 0
    // 已是当前对话且消息已加载（非空已加载，或已知为空）则跳过重复请求
    if (isCurrent && (get().messages.length > 0 || msgCount === 0)) {
      set({ currentTopicId: id })
      return
    }
    set({ currentTopicId: id, loadingMessages: true })
    try {
      const tasks = await listConversationMessages(id)
      set({ messages: tasks.map(taskToMessage), loadingMessages: false })
    } catch {
      set({ messages: [], loadingMessages: false })
    }
  },

  addMessage: (topicId, message) => {
    set((state) => {
      const isCurrent = state.currentTopicId === topicId
      return {
        messages: isCurrent ? [...state.messages, message] : state.messages,
        topics: state.topics.map((t) =>
          t.id === topicId
            ? {
                ...t,
                message_count: t.message_count + 1,
                last_prompt: message.prompt,
                last_thumbnail_url: message.thumbnailUrl ?? t.last_thumbnail_url,
                updated_at: new Date().toISOString(),
              }
            : t,
        ),
      }
    })
  },

  updateMessage: (topicId, messageId, patch) => {
    set((state) => {
      if (state.currentTopicId !== topicId) return state
      return {
        messages: state.messages.map((m) =>
          m.id === messageId ? { ...m, ...patch } : m,
        ),
      }
    })
  },

  deleteMessage: (topicId, messageId) => {
    set((state) => {
      if (state.currentTopicId !== topicId) return state
      return {
        messages: state.messages.filter((m) => m.id !== messageId),
        topics: state.topics.map((t) =>
          t.id === topicId
            ? { ...t, message_count: Math.max(0, t.message_count - 1) }
            : t,
        ),
      }
    })
  },
}))

/** 当前对话的元信息。 */
export function useCurrentTopic(): Conversation | undefined {
  return useConversationStore((s) => s.topics.find((t) => t.id === s.currentTopicId))
}
