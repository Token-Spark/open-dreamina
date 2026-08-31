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

import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Clapperboard, X, Camera } from 'lucide-react'
import { useDirectorDesk, type DirectorFrameData } from '@/hooks/useDirectorDesk'
import { toast } from '@/stores/uiStore'
import { cn } from '@/lib/utils'

/**
 * 3D 导演台弹窗：以 iframe 嵌入独立导演台应用，通过 postMessage 受控协议
 * 采集首帧/尾帧，回传给宿主用于 Seedance 视频生成。
 *
 * 嵌入协议：https://github.com/xiaozangao/3d-director-desk/blob/main/docs/embed-contract.md
 */

export interface DirectorDeskDialogProps {
  open: boolean
  onClose: () => void
  /** 导演台 iframe 地址（来自后端 /system/settings）。 */
  url: string
  /** 主题：跟随宿主当前主题。 */
  theme: 'dark' | 'light'
  /** 采集到图片，作为参考图添加。 */
  onCaptureImage: (file: File) => void
}

/** data:image/png;base64,... → File */
function dataUrlToFile(dataUrl: string, fileName: string): File {
  const commaIdx = dataUrl.indexOf(',')
  const mime = dataUrl.slice(5, commaIdx).match(/:(.*?);/)?.[1] ?? 'image/png'
  const bstr = atob(dataUrl.slice(commaIdx + 1))
  const u8 = new Uint8Array(bstr.length)
  for (let i = 0; i < bstr.length; i++) u8[i] = bstr.charCodeAt(i)
  return new File([u8], fileName, { type: mime })
}

export function DirectorDeskDialog({
  open,
  onClose,
  url,
  theme,
  onCaptureImage,
}: DirectorDeskDialogProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [busy, setBusy] = useState('')

  // 同一个 instanceId 复用同一导演台工程（浏览器 localStorage 隔离）
  const instanceId = useRef('dreamina-director').current

  const origin = useMemo(() => {
    try {
      return new URL(url).origin
    } catch {
      return ''
    }
  }, [url])

  const iframeSrc = useMemo(() => {
    if (!url) return ''
    try {
      const u = new URL(url)
      u.searchParams.set('instanceId', instanceId)
      u.searchParams.set('theme', theme)
      u.searchParams.set('hostOrigin', window.location.origin)
      return u.toString()
    } catch {
      return ''
    }
  }, [url, instanceId, theme])

  const { ready, request } = useDirectorDesk({
    iframeRef,
    origin,
    onClose,
    // 导演台内置发送按钮回传的截图，作为普通图片添加
    onCaptures: (captures) => {
      for (const c of captures) {
        const file = dataUrlToFile(c.dataUrl, c.fileName || '导演台截图.png')
        onCaptureImage(file)
      }
      if (captures.length) toast(`已接收 ${captures.length} 张导演台截图`, 'success')
    },
  })

  // 关闭时重置 busy 状态
  useEffect(() => {
    if (!open) setBusy('')
  }, [open])

  async function captureFrame() {
    if (busy) return
    setBusy('正在采集截图…')
    try {
      const data = await request<DirectorFrameData>('export.frame', {
        quality: '1080p',
      })
      const file = dataUrlToFile(data.dataUrl, data.fileName || '导演台截图.png')
      onCaptureImage(file)
      toast('已采集截图', 'success')
    } catch (e) {
      toast((e as { message?: string })?.message ?? '采集截图失败', 'error')
    } finally {
      setBusy('')
    }
  }

  if (!open || !url) return null

  return createPortal(
    <div className="fixed inset-0 z-[60] flex flex-col bg-black/95 animate-fade-in">
      {/* 顶部操作栏 */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-bg-secondary/80 px-4 backdrop-blur-md">
        <div className="flex items-center gap-2.5">
          <Clapperboard className="h-5 w-5 text-accent" />
          <span className="text-sm font-medium text-fg-primary">3D 导演台</span>
          {!ready && (
            <span className="flex items-center gap-1 text-xs text-fg-muted">
              <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-fg-muted" />
              加载中…
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* 操作按钮组 */}
          <ActionButton
            icon={Camera}
            label="采集截图"
            title="采集当前镜头画面作为参考图"
            disabled={!ready || !!busy}
            busy={busy.includes('截图')}
            onClick={() => captureFrame()}
          />

          <div className="mx-1 h-6 w-px bg-border" />

          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-btn text-fg-secondary transition-colors hover:bg-bg-tertiary hover:text-fg-primary"
            aria-label="关闭导演台"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </header>

      {/* iframe 容器 */}
      <div className="relative flex-1 overflow-hidden">
        {busy && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/50 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-fg-muted border-t-accent" />
              <span className="text-sm text-fg-secondary">{busy}</span>
            </div>
          </div>
        )}
        <iframe
          ref={iframeRef}
          src={iframeSrc}
          title="3D 导演台"
          className="h-full w-full border-0"
          allow="fullscreen; clipboard-write; accelerometer; gyroscope"
        />
      </div>
    </div>,
    document.body,
  )
}

function ActionButton({
  icon: Icon,
  label,
  title,
  disabled,
  busy,
  onClick,
}: {
  icon: typeof Clapperboard
  label: string
  title: string
  disabled?: boolean
  busy?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        'flex h-8 items-center gap-1.5 rounded-btn border border-border bg-bg-primary px-3 text-xs text-fg-primary transition-colors',
        'hover:bg-bg-primary disabled:opacity-40',
      )}
    >
      <Icon className={cn('h-3.5 w-3.5', busy && 'animate-pulse')} />
      {label}
    </button>
  )
}
