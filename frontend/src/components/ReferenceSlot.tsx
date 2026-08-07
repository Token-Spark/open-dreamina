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

import { ImagePlus, Music, Video, X } from 'lucide-react'

/** 参考素材类型：图片 / 视频 / 音频（视频模式支持多模态参考，见火山方舟视频生成 API）。 */
export type ReferenceKind = 'image' | 'video' | 'audio'

export interface ReferenceSlotProps {
  previewUrl: string | null
  /** 素材类型，决定预览渲染方式；缺省按图片处理。 */
  kind?: ReferenceKind
  onPick: () => void
  onClear: () => void
}

const KIND_LABEL: Record<ReferenceKind, string> = {
  image: '参考图',
  video: '参考视频',
  audio: '参考音频',
}

export function ReferenceSlot({ previewUrl, kind = 'image', onPick, onClear }: ReferenceSlotProps) {
  return previewUrl ? (
    <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-btn border border-border">
      {kind === 'video' ? (
        <>
          <video src={previewUrl} muted playsInline className="h-full w-full object-cover" />
          <span className="absolute bottom-0.5 left-0.5 flex items-center rounded bg-black/60 px-1 py-0.5 text-white">
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
      <button
        type="button"
        onClick={onClear}
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
      aria-label="上传参考素材"
    >
      <ImagePlus className="h-5 w-5" />
    </button>
  )
}
