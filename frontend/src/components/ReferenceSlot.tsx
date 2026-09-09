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

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, Loader2, Music, Plus, Video, X } from 'lucide-react'

/** 参考素材类型：图片 / 视频 / 音频（视频模式支持多模态参考，见火山方舟视频生成 API）。 */
export type ReferenceKind = 'image' | 'video' | 'audio'

/** Seedance 参考素材审核状态（Spark Hub seedance_asset_audit）。 */
export type AuditStatus = 'pending' | 'active' | 'failed' | 'none'

export interface ReferenceSlotProps {
  previewUrl: string | null
  /** 素材类型，决定预览渲染方式；缺省按图片处理。 */
  kind?: ReferenceKind
  onPick: () => void
  onClear: () => void
  /** 点击已有素材时触发预览；未传则不响应点击。 */
  onPreview?: () => void
  /** 角色标注（如“首帧”“尾帧”），展示在格子下方帮助理解用途。 */
  label?: string
  /** Seedance 参考素材审核状态；仅 Spark Hub Seedance 需要展示。 */
  auditStatus?: AuditStatus
  /** 审核失败原因。 */
  auditError?: string | null
}

const KIND_LABEL: Record<ReferenceKind, string> = {
  image: '参考图',
  video: '参考视频',
  audio: '参考音频',
}

/** 审核状态徽标：pending 显示“审核中”，active 显示“已通过”，failed 显示“未通过”。 */
function AuditBadge({ status, error }: { status: AuditStatus; error?: string | null }) {
  if (status === 'pending') {
    return (
      <span className="absolute inset-x-0 bottom-0 flex items-center justify-center gap-1 bg-black/60 py-0.5 text-[10px] text-amber-300">
        <Loader2 className="h-2.5 w-2.5 animate-spin" />
        审核中
      </span>
    )
  }
  if (status === 'active') {
    return (
      <span className="absolute inset-x-0 bottom-0 flex items-center justify-center gap-1 bg-black/60 py-0.5 text-[10px] text-emerald-300">
        <Check className="h-2.5 w-2.5" />
        已通过
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span
        className="absolute inset-x-0 bottom-0 flex items-center justify-center gap-1 bg-black/70 py-0.5 text-[10px] text-red-300"
        title={error ?? '审核未通过'}
      >
        <X className="h-2.5 w-2.5" />
        未通过
      </span>
    )
  }
  return null
}

/** 鼠标悬浮预览弹层：展示素材大图/视频缩略图/音频信息。 */
function HoverPreview({
  previewUrl,
  kind,
  label,
  anchorRect,
}: {
  previewUrl: string
  kind: ReferenceKind
  label?: string
  anchorRect: DOMRect
}) {
  // 根据锚点位置计算弹层放置方向（上方/下方），避免溢出视口
  const spaceAbove = anchorRect.top
  const placeBelow = spaceAbove < 220
  const top = placeBelow ? anchorRect.bottom + 8 : anchorRect.top - 8
  const left = anchorRect.left + anchorRect.width / 2

  return createPortal(
    <div
      className="fixed z-[80] flex -translate-x-1/2 flex-col gap-1 rounded-card border border-border bg-bg-secondary p-2 shadow-elevated animate-fade-in"
      style={{
        top,
        left,
        transform: `translate(-50%, ${placeBelow ? '0' : '-100%'})`,
      }}
    >
      <div className="h-32 w-32 overflow-hidden rounded-btn border border-border">
        {kind === 'video' ? (
          <video src={previewUrl} muted playsInline className="h-full w-full object-cover" />
        ) : kind === 'audio' ? (
          <div className="flex h-full w-full flex-col items-center justify-center gap-1.5 bg-bg-tertiary">
            <Music className="h-8 w-8 text-fg-muted" />
            <span className="text-[10px] text-fg-muted">音频素材</span>
          </div>
        ) : (
          <img src={previewUrl} alt={label ?? KIND_LABEL[kind]} className="h-full w-full object-cover" />
        )}
      </div>
      <span className="text-center text-xs text-fg-muted">{label ?? KIND_LABEL[kind]}</span>
    </div>,
    document.body,
  )
}

export function ReferenceSlot({
  previewUrl,
  kind = 'image',
  onPick,
  onClear,
  onPreview,
  label,
  auditStatus,
  auditError,
}: ReferenceSlotProps) {
  const [hoverPreview, setHoverPreview] = useState(false)
  const [hoverRect, setHoverRect] = useState<DOMRect | null>(null)
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 清理挂起的定时器，防止组件卸载后回调执行
  useEffect(() => {
    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current)
    }
  }, [])

  /** 显示悬浮预览：延迟 200ms 触发，避免鼠标快速掠过时闪烁。 */
  function handleMouseEnter(e: React.MouseEvent) {
    if (!previewUrl) return
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current)
      hideTimerRef.current = null
    }
    setHoverRect(e.currentTarget.getBoundingClientRect())
    setHoverPreview(true)
  }

  /** 隐藏悬浮预览：延迟 100ms 关闭，避免鼠标移动到弹层时的间隙抖动。 */
  function handleMouseLeave() {
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current)
    hideTimerRef.current = setTimeout(() => setHoverPreview(false), 100)
  }

  const slot = previewUrl ? (
    <div
      className="relative h-16 w-16 shrink-0 cursor-zoom-in overflow-hidden rounded-btn border border-border transition-shadow hover:shadow-elevated"
      onClick={onPreview}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      role={onPreview ? 'button' : undefined}
      tabIndex={onPreview ? 0 : undefined}
      onKeyDown={(e) => {
        if (onPreview && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          onPreview()
        }
      }}
    >
      {kind === 'video' ? (
        <>
          <video src={previewUrl} muted playsInline className="h-full w-full object-cover" />
          <span className="pointer-events-none absolute bottom-0.5 left-0.5 flex items-center rounded bg-black/60 px-1 py-0.5 text-white">
            <Video className="h-2.5 w-2.5" />
          </span>
        </>
      ) : kind === 'audio' ? (
        <div className="flex h-full w-full items-center justify-center bg-bg-tertiary">
          <Music className="h-6 w-6 text-fg-muted" />
        </div>
      ) : (
        <img src={previewUrl} alt={KIND_LABEL[kind]} className="h-full w-full object-cover" />
      )}
      <AuditBadge status={auditStatus ?? 'none'} error={auditError} />
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          onClear()
        }}
        className="absolute right-0.5 top-0.5 flex h-5 w-5 items-center justify-center rounded-full bg-black/60 text-white hover:bg-black/80"
        aria-label="移除"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  ) : (
    <button
      type="button"
      onClick={onPick}
      className="flex h-16 w-16 shrink-0 flex-col items-center justify-center gap-1 rounded-btn border border-dashed border-border text-fg-muted transition-colors hover:border-fg-muted hover:text-fg-secondary"
      aria-label={label ? `上传${label}` : '上传参考素材'}
    >
      <Plus className="h-5 w-5" />
    </button>
  )

  if (!label) return (
    <>
      {slot}
      {hoverPreview && hoverRect && (
        <HoverPreview
          previewUrl={previewUrl!}
          kind={kind}
          anchorRect={hoverRect}
        />
      )}
    </>
  )
  return (
    <div className="flex w-16 shrink-0 flex-col items-center gap-1">
      {slot}
      <span className="text-xs text-fg-muted">{label}</span>
      {hoverPreview && hoverRect && (
        <HoverPreview
          previewUrl={previewUrl!}
          kind={kind}
          label={label}
          anchorRect={hoverRect}
        />
      )}
    </div>
  )
}
