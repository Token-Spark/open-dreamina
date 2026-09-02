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

import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, Loader2, RefreshCw, Pencil, ImagePlus } from 'lucide-react'
import { useTaskSSE } from '@/hooks/useTaskSSE'
import { useConversationStore, type GenMessage } from '@/stores/conversationStore'
import { Button } from '@/components/ui/Button'
import { Progress } from '@/components/ui/Progress'
import { TASK_TYPE_LABEL } from '@/lib/taskStatus'
import { errorTitle, errorDetail } from '@/lib/errorMessages'

interface GenMessageCardProps {
  topicId: string
  message: GenMessage
  onRetry: (message: GenMessage) => void
  onOpenLightbox: (message: GenMessage, url?: string) => void
  onEdit: (message: GenMessage) => void
}

export function GenMessageCard({ topicId, message, onRetry, onOpenLightbox, onEdit }: GenMessageCardProps) {
  const updateMessage = useConversationStore((s) => s.updateMessage)
  const running = message.status === 'running'
  const pending = message.status === 'pending'

  const { status, progress, error, data } = useTaskSSE(pending || running ? message.id : null)

  useEffect(() => {
    if (!status && progress === 0 && !error && !data.message) return
    updateMessage(topicId, message.id, {
      status: status ?? message.status,
      progress,
      error,
      message: data.message,
      resultUrl: data.resultUrl,
      thumbnailUrl: data.thumbnailUrl,
      resultUrls: data.resultUrls.length ? data.resultUrls : message.resultUrls,
    })
  }, [status, progress, error, data.resultUrl, data.thumbnailUrl, data.resultUrls, data.message, topicId, message.id, message.status, updateMessage])

  return (
    <div id={`msg-${message.id}`} className="animate-slide-up scroll-mt-4">
      <div className="mb-3 flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-bg-tertiary text-xs font-semibold text-fg-secondary">
          U
        </div>
        <div className="min-w-0 flex-1 space-y-3">
          <div className="space-y-1">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-fg-primary">{message.prompt}</p>
          </div>

          <ResultCard
            message={message}
            onRetry={() => onRetry(message)}
            onOpenLightbox={(url) => onOpenLightbox(message, url)}
            onEdit={() => onEdit(message)}
          />
        </div>
      </div>
    </div>
  )
}

function ResultCard({
  message,
  onRetry,
  onOpenLightbox,
  onEdit,
}: {
  message: GenMessage
  onRetry: () => void
  onOpenLightbox: (url?: string) => void
  onEdit: () => void
}) {
  const running = message.status === 'running'
  const resultType = message.type === 'text2img' || message.type === 'img2img' ? 'image' : 'video'

  // 本地实时计时：基于 createdAt 每秒刷新已等待时长，避免后端状态回调冻结时间戳
  const [elapsedSec, setElapsedSec] = useState(0)
  useEffect(() => {
    if (!running) return
    const tick = () => setElapsedSec(Math.max(0, Math.floor((Date.now() - message.createdAt) / 1000)))
    tick()
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [running, message.createdAt])

  return (
    <div className="rounded-card bg-transparent p-4 space-y-3">
      <div className="flex items-center gap-2">
        {running && <Loader2 className="h-4 w-4 animate-spin text-fg-secondary" />}
        {message.status === 'completed' && <CheckCircle2 className="h-4 w-4 text-success" />}
        {message.status === 'failed' && <AlertCircle className="h-4 w-4 text-error" />}
        <span className="text-sm font-semibold text-fg-primary">{TASK_TYPE_LABEL[message.type]}</span>
      </div>

      {running && (
        <div className="space-y-1.5">
          <Progress value={message.progress} glow />
          <div className="flex items-center justify-between text-xs text-fg-muted">
            <span>生成中…{elapsedSec > 0 ? `（已等待 ${elapsedSec}s）` : ''}</span>
            <span>{message.progress}%</span>
          </div>
        </div>
      )}

      {message.status === 'pending' && (
        <p className="text-xs text-fg-muted animate-pulse">任务已提交，等待分配执行资源…</p>
      )}
      {message.status === 'queued' && (
        <p className="text-xs text-fg-muted animate-pulse">任务已入队，排队等待执行…</p>
      )}

      {message.status === 'failed' && (
        <div className="space-y-1.5 rounded-btn border border-border bg-bg-secondary/50 p-3.5">
          <div className="flex items-start gap-2">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-fg-muted" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-fg-primary">{errorTitle(message.error)}</p>
              <p className="text-xs leading-relaxed text-fg-muted">{errorDetail(message.error)}</p>
            </div>
          </div>
          <div className="flex items-center gap-3 pl-6">
            <button
              onClick={onRetry}
              className="inline-flex items-center gap-1 text-xs font-medium text-fg-secondary transition-colors hover:text-fg-primary"
            >
              <RefreshCw className="h-3 w-3" />
              重新生成
            </button>
            <span className="text-border" />
            <button
              onClick={onEdit}
              className="inline-flex items-center gap-1 text-xs font-medium text-fg-secondary transition-colors hover:text-fg-primary"
            >
              <Pencil className="h-3 w-3" />
              重新编辑
            </button>
          </div>
        </div>
      )}

      {message.status === 'completed' && message.resultUrl && (
        <div className="space-y-2">
          {resultType === 'image' && message.resultUrls.length > 1 ? (
            <div className="grid grid-cols-2 gap-2">
              {message.resultUrls.map((url, i) => (
                <div
                  key={url}
                  className="cursor-pointer overflow-hidden rounded-btn bg-transparent"
                  onClick={() => onOpenLightbox(url)}
                >
                  <img
                    src={url}
                    alt={`生成结果 ${i + 1}`}
                    className="w-full object-contain"
                  />
                </div>
              ))}
            </div>
          ) : (
            <div
              className="cursor-pointer overflow-hidden rounded-btn bg-transparent"
              onClick={() => onOpenLightbox()}
            >
              {resultType === 'image' ? (
                <img src={message.resultUrl} alt="生成结果" className="max-h-[50vh] w-full object-contain" />
              ) : (
                <video src={message.resultUrl} controls className="max-h-[50vh] w-full" />
              )}
            </div>
          )}
          <div className="flex items-center justify-between">
            <span className="text-xs text-fg-muted">
              {resultType === 'image' && message.resultUrls.length > 1
                ? `共 ${message.resultUrls.length} 张，点击可放大查看`
                : '点击可放大查看'}
            </span>
            <Button variant="secondary" size="sm" onClick={onEdit}>
              <Pencil className="h-3.5 w-3.5" />
              重新编辑
            </Button>
          </div>
        </div>
      )}

      {message.status === 'completed' && !message.resultUrl && (
        <div className="flex flex-col items-center justify-center gap-2 rounded-btn border border-dashed border-border py-8 text-fg-muted">
          <ImagePlus className="h-6 w-6" />
          <p className="text-xs">生成已完成，但未返回结果</p>
        </div>
      )}
    </div>
  )
}
