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

import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronLeft, ChevronRight, Download, X, ZoomIn, ZoomOut } from 'lucide-react'
import { Button, buttonVariants } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

export interface LightboxItem {
  url: string
  type: 'image' | 'video' | 'audio'
  title?: string
  meta?: Record<string, unknown>
}

/** 同批多图（如一次生成 4 张）浏览：可在本批结果间左右切换。 */
export interface LightboxGallery {
  items: LightboxItem[]
  /** 打开时定位的序号，即用户点击的那张。 */
  index?: number
}

export interface ImageLightboxProps {
  /** 单条预览（图片/视频/音频）；用 gallery 批量浏览时可不传。 */
  item?: LightboxItem | null
  gallery?: LightboxGallery | null
  open: boolean
  onClose: () => void
}

export function ImageLightbox({ item, gallery, open, onClose }: ImageLightboxProps) {
  const galleryItems = gallery && gallery.items.length > 0 ? gallery.items : null
  const [cursor, setCursor] = useState(gallery?.index ?? 0)
  const [zoom, setZoom] = useState(1)

  // 每次打开都定位到点击的那张，避免上一次浏览的序号残留
  useEffect(() => {
    if (open) setCursor(gallery?.index ?? 0)
  }, [open, gallery?.index])

  const current = galleryItems ? galleryItems[Math.min(cursor, galleryItems.length - 1)] : item

  // 仅同批多于一张时才提供左右切换
  const steppable = (galleryItems?.length ?? 0) > 1
  const step = useCallback(
    (delta: number) => {
      if (!galleryItems || galleryItems.length < 2) return
      setCursor((c) => (c + delta + galleryItems.length) % galleryItems.length)
      setZoom(1)
    },
    [galleryItems],
  )

  useEffect(() => {
    if (!open) return
    setZoom(1)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === '+' || e.key === '=') setZoom((z) => Math.min(4, z + 0.25))
      if (e.key === '-') setZoom((z) => Math.max(0.5, z - 0.25))
      if (e.key === 'ArrowLeft') step(-1)
      if (e.key === 'ArrowRight') step(1)
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose, step])

  if (!open || !current) return null

  // Lightbox forces a near-black backdrop in both themes; text must stay light
  // even when the app is in light mode, otherwise it would be invisible.
  return createPortal(
    <div className="fixed inset-0 z-[60] flex flex-col bg-black/95 animate-fade-in text-white">
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-white">
            {current.title ?? '预览'}
            {steppable && (
              <span className="ml-2 tabular-nums text-white/60">
                {cursor + 1} / {galleryItems?.length}
              </span>
            )}
          </p>
          {current.meta && (
            <p className="truncate text-xs text-white/60">
              {formatMeta(current.meta)}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 [&_button]:text-white/70 [&_button:hover]:bg-white/10 [&_button:hover]:text-white [&_a]:text-white/70 [&_a:hover]:bg-white/10 [&_a:hover]:text-white">
          {current.type === 'image' && (
            <>
              <Button variant="ghost" size="icon" onClick={() => setZoom((z) => Math.min(4, z + 0.25))} aria-label="放大">
                <ZoomIn className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))} aria-label="缩小">
                <ZoomOut className="h-4 w-4" />
              </Button>
            </>
          )}
          <a
            href={current.url}
            download
            target="_blank"
            rel="noreferrer"
            className={cn(buttonVariants({ variant: 'ghost', size: 'icon' }))}
            aria-label="下载"
          >
            <Download className="h-4 w-4" />
          </a>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="关闭">
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div
        className="relative flex flex-1 items-center justify-center overflow-auto scrollbar-thin"
        onClick={(e) => {
          if (e.target === e.currentTarget) onClose()
        }}
      >
        {steppable && (
          <>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => step(-1)}
              aria-label="上一张"
              className="absolute left-3 top-1/2 z-10 -translate-y-1/2 bg-white/10 text-white/80 hover:bg-white/20 hover:text-white"
            >
              <ChevronLeft className="h-6 w-6" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => step(1)}
              aria-label="下一张"
              className="absolute right-3 top-1/2 z-10 -translate-y-1/2 bg-white/10 text-white/80 hover:bg-white/20 hover:text-white"
            >
              <ChevronRight className="h-6 w-6" />
            </Button>
          </>
        )}
        {current.type === 'image' ? (
          <img
            key={current.url}
            src={current.url}
            alt={current.title ?? ''}
            className={cn('max-h-full max-w-full object-contain transition-transform duration-200')}
            style={{ transform: `scale(${zoom})` }}
          />
        ) : current.type === 'video' ? (
          <video
            key={current.url}
            src={current.url}
            controls
            autoPlay
            className="max-h-full max-w-full"
          />
        ) : (
          <audio key={current.url} src={current.url} controls autoPlay className="w-full max-w-md" />
        )}
      </div>
    </div>,
    document.body,
  )
}

function formatMeta(meta: Record<string, unknown>): string {
  return Object.entries(meta)
    .filter(([, v]) => v != null && v !== '')
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join('  ·  ')
}
