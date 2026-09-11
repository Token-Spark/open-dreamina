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

/**
 * 提示词编辑领域的共享模型：参考素材、@ 引用、帧模式判定。
 * 从 GenerationInputBar 抽出，供内联输入条与全屏沉浸式编辑器共用，
 * 避免组件与 hook 之间产生循环依赖。
 */

import type * as React from 'react'
import { Image as ImageIcon, Images, Wand2 } from 'lucide-react'
import { assetFileUrl } from '@/api/assets'
import type { CreationAsset } from '@/api/creationAssets'
import type { ContentMode } from '@/lib/generation'
import type { ReferenceKind } from '@/components/ReferenceSlot'

/** 一个参考素材（图片/视频/音频）：assetId 用于提交任务，previewUrl 用于本地预览。 */
export interface ReferenceAsset {
  assetId: string
  previewUrl: string
  /** 素材类型；旧数据缺省按图片处理。 */
  kind?: ReferenceKind
  /** 素材名称（素材库项为素材名，上传项为文件名）；用于 @ 引用标签展示。 */
  name?: string
  /** Seedance 参考素材审核状态（仅 Spark Hub Seedance 需要）；undefined 表示未提交审核。 */
  auditStatus?: 'pending' | 'active' | 'failed'
  /** 审核失败原因。 */
  auditError?: string | null
  /** 素材时长（秒），仅视频/音频有值；用于提交前校验音频总时长限制。 */
  duration?: number
}

/**
 * @ 引用候选项：可引用已上传的参考素材（slot）或素材库中的可复用素材（library）。
 * - slot：已在上传槽位中的素材，token 使用素材名称（@{素材名}）。
 * - library：素材库（人物/场景/道具）中尚未加入参考列表的素材，选中后自动追加到 refAssets。
 */
export interface MentionItem {
  /** 候选项来源：已上传参考槽位 / 素材库。 */
  source: 'slot' | 'library'
  /** 主资产：slot 为现有参考项；library 为素材库待加入项中的图片资产（无图时取音频）。 */
  asset: ReferenceAsset
  /** 待加入参考列表的资产（slot 恒为单元素；人物素材可能同时含图片与音频）。 */
  assets: ReferenceAsset[]
  kind: ReferenceKind
  /** 实际插入提示词的引用 token 列表，如 @{素材名}。 */
  tokens: string[]
  /** 展示名称。slot 为素材名称，library 为素材名称。 */
  label: string
  /** 缩略图地址；slot 用 file 原图，library 用素材缩略图。 */
  thumbUrl: string
}

/**
 * 视频模式多模态参考限制（火山方舟 Seedance 2.0 系列：参考图 0-9 + 参考视频 0-3 + 参考音频 0-3）。
 * 参考: 创建视频生成任务 API（.trae/docs/火山方舟 - 视频生成 API）。
 */
export const MAX_REF_IMAGES = 9
export const MAX_REF_VIDEOS = 3
export const MAX_REF_AUDIOS = 3
export const MAX_IMAGE_BYTES = 30 * 1024 * 1024 // 单张图片 < 30 MB
export const MAX_VIDEO_BYTES = 200 * 1024 * 1024 // 单个视频 ≤ 200 MB
export const MAX_AUDIO_BYTES = 15 * 1024 * 1024 // 单个音频 ≤ 15 MB
/** API 仅接受 mp4/mov 参考视频、wav/mp3 参考音频（按扩展名兑底，部分浏览器 MIME 缺失）。 */
export const VIDEO_EXTS = ['.mp4', '.mov']
export const AUDIO_EXTS = ['.wav', '.mp3']
export const KIND_CAPS: Record<ReferenceKind, number> = {
  image: MAX_REF_IMAGES,
  video: MAX_REF_VIDEOS,
  audio: MAX_REF_AUDIOS,
}
export const KIND_SIZE_CAPS: Record<ReferenceKind, number> = {
  image: MAX_IMAGE_BYTES,
  video: MAX_VIDEO_BYTES,
  audio: MAX_AUDIO_BYTES,
}
export const KIND_LABELS: Record<ReferenceKind, string> = {
  image: '参考图',
  video: '参考视频',
  audio: '参考音频',
}

/**
 * Seedance 2.0 视频生成：引用音频素材总时长上限（秒）。
 * 多段参考音频时长累加不得超过此值，否则提交时拦截并提示用户。
 */
export const MAX_AUDIO_TOTAL_DURATION = 15
/** 视频模式下文件选择器接受：图片 + mp4/mov 视频 + wav/mp3 音频。 */
export const ACCEPT_VIDEO_MODE =
  'image/*,video/mp4,video/quicktime,audio/wav,audio/mpeg,audio/mp3,audio/x-wav,.mp4,.mov,.wav,.mp3'

/**
 * Seedance 视频生成帧模式（需求1：文生视频与参考图合二为一）。
 * auto 为合并模式：无参考图时按文生视频生成，上传图片后自动按参考图模式生成；
 * 提交时由 effectiveFrameMode 解析为后端接受的 text / reference。
 */
export type FrameMode = 'auto' | 'first' | 'first_last'

/** 解析后的后端帧模式（text / reference 仅作为 auto 的解析结果，不直接存储）。 */
export type EffectiveFrameMode = 'text' | 'first' | 'first_last' | 'reference'

/** 合并模式解析：无参考图 → 文生视频（text）；有参考图 → 多模态参考（reference）。 */
export function effectiveFrameMode(frameMode: FrameMode, hasImage: boolean): EffectiveFrameMode {
  if (frameMode === 'auto') return hasImage ? 'reference' : 'text'
  return frameMode
}

/** 归一化历史/外部传入的 frame_mode：旧数据中的 text / reference 均映射为合并模式 auto。 */
export function normalizeFrameMode(v: unknown): FrameMode {
  return v === 'first' || v === 'first_last' ? v : 'auto'
}

/**
 * 各帧模式对参考图片数量的要求（required 为提交任务所需张数）。
 * slots 为固定图片格子的角色标注（首帧/尾帧），用于在输入区渲染指定数量的上传格子；
 * auto（合并模式，含参考图状态）走多模态参考，不设固定格子，上限沿用 MAX_REF_IMAGES。
 * allowMultimodal 表示是否允许图片之外的视频/音频参考。
 */
export const FRAME_MODES: {
  mode: FrameMode
  label: string
  hint: string
  maxImages: number
  required: number
  allowMultimodal: boolean
  slots?: string[]
  icon: React.ComponentType<{ className?: string }>
}[] = [
  {
    mode: 'auto',
    label: '文生视频/参考图',
    hint: '无需图片可直接生成，上传图片自动转为参考图',
    maxImages: MAX_REF_IMAGES,
    required: 0,
    allowMultimodal: true,
    icon: Wand2,
  },
  { mode: 'first', label: '首帧', hint: '上传 1 张图片作为视频首帧', maxImages: 1, required: 1, allowMultimodal: false, slots: ['首帧'], icon: ImageIcon },
  {
    mode: 'first_last',
    label: '首尾帧',
    hint: '上传 2 张图片，分别作为首帧与尾帧',
    maxImages: 2,
    required: 2,
    allowMultimodal: false,
    slots: ['首帧', '尾帧'],
    icon: Images,
  },
]

/** 当前帧模式配置；非 Seedance 视频/图片模式返回 null（走通用多模态限制）。 */
export function frameModeSpec(
  mode: ContentMode,
  isSeedance: boolean,
  frameMode: FrameMode,
): (typeof FRAME_MODES)[number] | null {
  if (mode !== 'video' || !isSeedance) return null
  return FRAME_MODES.find((m) => m.mode === frameMode) ?? null
}

/** 判断当前 provider 是否为 Seedance 系列（slug 含 seedance，或已知遗留别名 dreamina-cli）。 */
export function isSeedanceProvider(slug: string): boolean {
  const s = slug.toLowerCase()
  // dreamina-cli 是遗留 slug，后端实际使用 DreaminaSeedanceProvider（Seedance 系列），
  // 见 backend/app/providers/factory.py 中 "dreamina-cli" 注册项。
  return s.includes('seedance') || s === 'dreamina-cli'
}

/**
 * 判断是否为 Spark Hub Seedance 中转（唯一需要参考素材审核的 provider）。
 * 参考素材需先通过 seedance_asset_audit 审核，审核通过后才能用于视频生成。
 */
export function isSparkHubSeedance(slug: string): boolean {
  return slug === 'sparkhub-seedance'
}

/**
 * 素材库素材 → 待加入参考列表的资产：
 * 图片模式仅取图片；视频模式取图片 + 音频（人物音色）；单帧/首尾帧模式不允许音频。
 * 顺序固定为图片在前、音频在后，便于后续按加入顺序编号。
 */
export function pendingAssetsOf(
  ca: CreationAsset,
  mode: ContentMode,
  allowAudio: boolean,
): ReferenceAsset[] {
  const list: ReferenceAsset[] = []
  if (ca.image_asset_id) {
    list.push({
      assetId: ca.image_asset_id,
      previewUrl: assetFileUrl(ca.image_asset_id),
      kind: 'image',
    })
  }
  if (mode === 'video' && allowAudio && ca.audio_asset_id) {
    list.push({
      assetId: ca.audio_asset_id,
      previewUrl: assetFileUrl(ca.audio_asset_id),
      kind: 'audio',
    })
  }
  return list
}

/**
 * 扫描光标前的文本，判断是否处于 @ 触发态：
 * 找到任意位置的 @，且从 @ 到光标之间不含空白。
 */
export function detectMention(value: string, pos: number): { start: number; query: string } | null {
  const before = value.slice(0, pos)
  for (let i = before.length - 1; i >= 0; i--) {
    const ch = before[i]
    if (ch === '@') {
      return { start: i, query: before.slice(i + 1) }
    }
    if (/\s/.test(ch)) return null
  }
  return null
}
