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
import { createPortal } from 'react-dom'
import { Download, X, ZoomIn, ZoomOut } from 'lucide-react'
import { Button, buttonVariants } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

export interface LightboxItem {
  url: string
  type: 'image' | 'video'
  title?: string
  meta?: Record<string, unknown>
}

export interface ImageLightboxProps {
  item: LightboxItem | null
  open: boolean
  onClose: () => void
}

export function ImageLightbox({ item, open, onClose }: ImageLightboxProps) {
  const [zoom, setZoom] = useState(1)

  useEffect(() => {
    if (!open) return
    setZoom(1)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === '+' || e.key === '=') setZoom((z) => Math.min(4, z + 0.25))
      if (e.key === '-') setZoom((z) => Math.max(0.5, z - 0.25))
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open || !item) return null

  // Lightbox forces a near-black backdrop in both themes; text must stay light
  // even when the app is in light mode, otherwise it would be invisible.
  return createPortal(
    <div className="fixed inset-0 z-[60] flex flex-col bg-black/95 animate-fade-in text-white">
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-white">
            {item.title ?? '预览'}
          </p>
          {item.meta && (
            <p className="truncate text-xs text-white/60">
              {formatMeta(item.meta)}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 [&_button]:text-white/70 [&_button:hover]:bg-white/10 [&_button:hover]:text-white [&_a]:text-white/70 [&_a:hover]:bg-white/10 [&_a:hover]:text-white">
          {item.type === 'image' && (
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
            href={item.url}
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
        {item.type === 'image' ? (
          <img
            src={item.url}
            alt={item.title ?? ''}
            className={cn('max-h-full max-w-full object-contain transition-transform duration-200')}
            style={{ transform: `scale(${zoom})` }}
          />
        ) : (
          <video
            src={item.url}
            controls
            autoPlay
            className="max-h-full max-w-full"
          />
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
