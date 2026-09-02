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

import { useState, useRef, useEffect } from 'react'
import { Plus, MoreHorizontal, Trash2, Pencil, Check, X, MessageSquare } from 'lucide-react'
import { useConversationStore } from '@/stores/conversationStore'
import type { Conversation } from '@/api/conversations'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { cn } from '@/lib/utils'

interface TopicPanelProps {
  className?: string
}

export function TopicPanel({ className }: TopicPanelProps) {
  const topics = useConversationStore((s) => s.topics)
  const currentTopicId = useConversationStore((s) => s.currentTopicId)
  const addTopic = useConversationStore((s) => s.addTopic)
  const removeTopic = useConversationStore((s) => s.removeTopic)
  const renameTopic = useConversationStore((s) => s.renameTopic)
  const setCurrentTopic = useConversationStore((s) => s.setCurrentTopic)

  async function handleNew() {
    try {
      await addTopic()
    } catch (e) {
      toast(toApiError(e).message, 'error')
    }
  }

  return (
    <aside className={cn('flex w-64 shrink-0 flex-col bg-bg-secondary', className)}>
      <div className="flex h-16 items-center justify-between border-b border-border px-3">
        <h2 className="text-sm font-semibold text-fg-primary">对话列表</h2>
        <button
          type="button"
          onClick={handleNew}
          className="flex h-7 items-center gap-1 rounded-btn bg-accent px-2.5 text-xs font-medium text-bg-primary transition-all hover:bg-fg-primary/90 active:scale-95"
        >
          <Plus className="h-3.5 w-3.5" />
          新对话
        </button>
      </div>

      <div className="flex-1 overflow-auto p-2 scrollbar-thin">
        <div className="space-y-1">
          {topics.map((topic) => (
            <TopicItem
              key={topic.id}
              topic={topic}
              isActive={topic.id === currentTopicId}
              onSelect={() => setCurrentTopic(topic.id)}
              onRename={(title) => renameTopic(topic.id, title)}
              onDelete={() => removeTopic(topic.id)}
            />
          ))}
          {topics.length === 0 && (
            <p className="px-2 py-4 text-center text-xs text-fg-muted">暂无对话</p>
          )}
        </div>
      </div>
    </aside>
  )
}

function TopicItem({
  topic,
  isActive,
  onSelect,
  onRename,
  onDelete,
}: {
  topic: Conversation
  isActive: boolean
  onSelect: () => void
  onRename: (title: string) => void
  onDelete: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menuOpen) return
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [menuOpen])

  const thumbnail = topic.last_thumbnail_url
  const lastPrompt = topic.last_prompt

  function startEdit() {
    setEditing(true)
    setMenuOpen(false)
    requestAnimationFrame(() => inputRef.current?.focus())
  }

  function confirmEdit(e: React.FormEvent) {
    e.preventDefault()
    const value = inputRef.current?.value ?? ''
    onRename(value)
    setEditing(false)
  }

  return (
    <div
      className={cn(
        'group relative flex items-center gap-2 rounded-btn border border-transparent p-2 transition-all',
        isActive
          ? 'bg-bg-tertiary text-fg-primary'
          : 'text-fg-secondary hover:bg-bg-tertiary/60 hover:text-fg-primary',
      )}
    >
      <button type="button" onClick={onSelect} className="flex flex-1 items-center gap-2 overflow-hidden text-left">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-btn bg-bg-tertiary">
          {thumbnail ? (
            <img src={thumbnail} alt="" className="h-full w-full object-cover" />
          ) : (
            <MessageSquare className="h-4 w-4 text-fg-muted" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          {editing ? (
            <form onSubmit={confirmEdit} className="flex items-center gap-1">
              <input
                ref={inputRef}
                type="text"
                defaultValue={topic.title}
                className="h-7 w-full rounded-btn border border-border bg-bg-primary px-2 text-xs text-fg-primary focus-visible:outline-none focus-visible:border-fg-muted"
              />
              <button type="submit" className="text-success hover:text-success/80">
                <Check className="h-3.5 w-3.5" />
              </button>
              <button type="button" onClick={() => setEditing(false)} className="text-fg-muted hover:text-fg-primary">
                <X className="h-3.5 w-3.5" />
              </button>
            </form>
          ) : (
            <>
              <p className="truncate text-xs font-medium leading-tight">{topic.title}</p>
              <p className="truncate text-[11px] leading-tight text-fg-muted">
                {lastPrompt ? lastPrompt : topic.message_count > 0 ? `${topic.message_count} 条记录` : '暂无生成内容'}
              </p>
            </>
          )}
        </div>
      </button>

      {!editing && (
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className={cn(
              'flex h-6 w-6 items-center justify-center rounded-btn text-fg-muted transition-colors hover:bg-bg-secondary hover:text-fg-primary',
              menuOpen ? 'opacity-100' : 'opacity-0 group-hover:opacity-100',
            )}
            aria-label="更多"
          >
            <MoreHorizontal className="h-3.5 w-3.5" />
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-full z-10 mt-1 w-28 rounded-card border border-border bg-bg-tertiary py-1 shadow-elevated animate-scale-in">
              <button
                type="button"
                onClick={startEdit}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-xs font-medium text-fg-secondary transition-colors hover:bg-bg-secondary hover:text-fg-primary"
              >
                <Pencil className="h-3.5 w-3.5" />
                重命名
              </button>
              <button
                type="button"
                onClick={onDelete}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-xs font-medium text-error transition-colors hover:bg-error/10"
              >
                <Trash2 className="h-3.5 w-3.5" />
                删除
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
