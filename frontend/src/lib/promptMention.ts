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
import { AUDIO_LOGO_URL } from '@/lib/assetPreview'
import type { CreationAsset, CreationAssetCategory } from '@/api/creationAssets'
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
  /**
   * 素材库分类（人物/场景/道具/关键帧），仅 @ 引用素材库时写入。
   * 本地上传、画布连线与历史草稿缺省，输入区统一归入「上传」分组。
   */
  category?: CreationAssetCategory
  /**
   * 素材库缩略图地址；小图列表优先用它，避免为了 40px 的格子下载整张原图。
   * 缺省时回落到 previewUrl。大图预览仍用 previewUrl 保证清晰度。
   */
  thumbUrl?: string
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
  /** 素材库分类；用于在候选项上标记「角色/场景/道具」等类别。 */
  category?: CreationAssetCategory
}

/**
 * 参考素材能力按模型系列区分（火山方舟 Seedance API），不是全局固定值：
 * - Seedance 2.0 系列：单次最多 15 个（参考图 9 + 参考视频 3 + 参考音频 3），
 *   单个音/视频 [2, 15] 秒，参考音频累计 ≤ 15 秒。
 * - Seedance 2.5：单次最多 50 个（参考图 30 + 参考视频 10 + 参考音频 10），
 *   单个音/视频 [2, 30] 秒，参考音频累计 ≤ 30 秒。
 * 各类型上限之和恰好等于总数上限，逐类型校验即可满足「单次最多 N 个素材」。
 * 参考：.trae/docs/seedance 2-5 API.md「50 个多模态参考素材输入」与输入素材要求，
 *      以及 https://www.volcengine.com/docs/82379/2607689。
 */
export interface ReferenceCaps {
  image: number
  video: number
  audio: number
  /** 单次任务的参考素材总数上限。 */
  total: number
  /** 参考音频累计时长上限（秒）。 */
  audioTotalDuration: number
  /** 单个参考视频/音频允许的时长区间（秒）。 */
  mediaDuration: { min: number; max: number }
}

/** Seedance 2.0 系列、未知视频模型与图片模式的参考素材能力。 */
export const LEGACY_REF_CAPS: ReferenceCaps = {
  image: 9,
  video: 3,
  audio: 3,
  total: 15,
  audioTotalDuration: 15,
  mediaDuration: { min: 2, max: 15 },
}

/** Seedance 2.5 的参考素材能力。 */
export const SEEDANCE_25_REF_CAPS: ReferenceCaps = {
  image: 30,
  video: 10,
  audio: 10,
  total: 50,
  audioTotalDuration: 30,
  mediaDuration: { min: 2, max: 30 },
}

/** 模型 ID 是否为 Seedance 2.5（兼容 2_5 / 2-5 / 2.5 三种写法）。 */
export function isSeedance25Model(modelId: string): boolean {
  const id = modelId.toLowerCase()
  return id.includes('2_5') || id.includes('2-5') || id.includes('2.5')
}

/**
 * 当前场景的参考素材能力：仅视频模式下的 Seedance 2.5 放宽到 50 个，
 * 2.0 系列、其他视频 Provider 与图片模式沿用 2.0 的 15 个上限。
 * providerSlug 先判一次，是因为「Seedance 2.5 专用服务」即使 modelId 未选中也应放宽。
 */
export function refCapsFor(
  mode: ContentMode,
  providerSlug: string,
  modelId: string,
): ReferenceCaps {
  if (mode !== 'video' || !isSeedanceProvider(providerSlug)) return LEGACY_REF_CAPS
  const slug = providerSlug.toLowerCase()
  const providerIs25 = slug.includes('2_5') || slug.includes('2-5') || slug.includes('2.5')
  return providerIs25 || isSeedance25Model(modelId)
    ? SEEDANCE_25_REF_CAPS
    : LEGACY_REF_CAPS
}

/**
 * 提交前校验：参考素材是否超出当前模型能力。返回错误文案，合规时返回 null。
 * 用于拦截「在 2.5 下加了 20 张图、随后切回 2.0」这类模型切换后的超限状态。
 */
export function refCapViolation(
  assets: Pick<ReferenceAsset, 'kind'>[],
  caps: ReferenceCaps,
): string | null {
  const countOf = (kind: ReferenceKind) =>
    assets.filter((a) => (a.kind ?? 'image') === kind).length
  if (countOf('image') > caps.image) return `参考图最多 ${caps.image} 张，请移除多余的参考图`
  if (countOf('video') > caps.video) return `参考视频最多 ${caps.video} 个，请移除多余的参考视频`
  if (countOf('audio') > caps.audio) return `参考音频最多 ${caps.audio} 段，请移除多余的参考音频`
  if (assets.length > caps.total) return `参考素材总数最多 ${caps.total} 个，请精简后再生成`
  return null
}

export const MAX_IMAGE_BYTES = 30 * 1024 * 1024 // 单张图片 < 30 MB
export const MAX_VIDEO_BYTES = 200 * 1024 * 1024 // 单个视频 ≤ 200 MB
export const MAX_AUDIO_BYTES = 15 * 1024 * 1024 // 单个音频 ≤ 15 MB
/** API 仅接受 mp4/mov 参考视频、wav/mp3 参考音频（按扩展名兜底，部分浏览器 MIME 缺失）。 */
export const VIDEO_EXTS = ['.mp4', '.mov']
export const AUDIO_EXTS = ['.wav', '.mp3']
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
 * 输入区参考素材的分组维度：素材库四类 + 无分类的一组。
 * 「上传」承载本地上传、画布连线推导与历史草稿，保证旧数据也能稳定展示。
 * 标签用词与创作语境一致（角色），对应素材库里的「人物」分类。
 */
export type RefAssetGroupKey = CreationAssetCategory | 'upload'

export const REF_ASSET_GROUPS: { key: RefAssetGroupKey; label: string }[] = [
  { key: 'character', label: '角色' },
  { key: 'scene', label: '场景' },
  { key: 'prop', label: '道具' },
  { key: 'keyframe', label: '关键帧' },
  { key: 'upload', label: '上传' },
]

/** 分类值 → 展示标签；未知值回落到「上传」。 */
export function refAssetGroupLabel(key: RefAssetGroupKey | string | undefined): string {
  return REF_ASSET_GROUPS.find((g) => g.key === key)?.label ?? '上传'
}

/** 参考素材所属分组；无分类或非法值归入「上传」。 */
export function refAssetGroupKey(asset: ReferenceAsset): RefAssetGroupKey {
  const category = asset.category
  return category && REF_ASSET_GROUPS.some((g) => g.key === category)
    ? (category as RefAssetGroupKey)
    : 'upload'
}

export interface RefAssetGroup {
  key: RefAssetGroupKey
  label: string
  items: ReferenceAsset[]
}

/**
 * 把扁平的参考列表聚合成有内容的分组，组间顺序固定，组内保持引用/上传顺序。
 * 空分组不返回，输入框上方只展示真正用到的类别。
 */
export function groupRefAssets(assets: ReferenceAsset[]): RefAssetGroup[] {
  const buckets = new Map<RefAssetGroupKey, ReferenceAsset[]>()
  for (const asset of assets) {
    const key = refAssetGroupKey(asset)
    const bucket = buckets.get(key)
    if (bucket) bucket.push(asset)
    else buckets.set(key, [asset])
  }
  return REF_ASSET_GROUPS.flatMap((group) => {
    const items = buckets.get(group.key)
    return items?.length ? [{ ...group, items }] : []
  })
}

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

/** 合并模式解析：无参考素材 → 文生视频（text）；有任意参考素材（图/视频/音频）→ 多模态参考（reference）。 */
export function effectiveFrameMode(frameMode: FrameMode, hasReference: boolean): EffectiveFrameMode {
  if (frameMode === 'auto') return hasReference ? 'reference' : 'text'
  return frameMode
}

/** 归一化历史/外部传入的 frame_mode：旧数据中的 text / reference 均映射为合并模式 auto。 */
export function normalizeFrameMode(v: unknown): FrameMode {
  return v === 'first' || v === 'first_last' ? v : 'auto'
}

/**
 * 各帧模式对参考图片数量的要求（required 为提交任务所需张数）。
 * slots 为固定图片格子的角色标注（首帧/尾帧），用于在输入区渲染指定数量的上传格子；
 * auto（全能参考）走多模态参考，不设固定格子；其 maxImages 由 frameModeSpec
 * 按模型能力覆盖（2.5 为 30 张、2.0 为 9 张）。
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
    label: '全能参考',
    hint: '无需图片可直接生成，上传图片自动转为参考图',
    // 占位值；全能参考模式的实际图片上限见 frameModeSpec。
    maxImages: LEGACY_REF_CAPS.image,
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
  caps: ReferenceCaps = LEGACY_REF_CAPS,
): (typeof FRAME_MODES)[number] | null {
  if (mode !== 'video' || !isSeedance) return null
  const spec = FRAME_MODES.find((m) => m.mode === frameMode) ?? null
  if (!spec || !spec.allowMultimodal) return spec
  // 全能参考模式的图片上限随模型变化：2.5 可到 30 张，2.0 仍是 9 张。
  return { ...spec, maxImages: caps.image }
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
      category: ca.category,
      thumbUrl: ca.image_thumbnail_url ?? undefined,
    })
  }
  if (mode === 'video' && allowAudio && ca.audio_asset_id) {
    list.push({
      assetId: ca.audio_asset_id,
      previewUrl: assetFileUrl(ca.audio_asset_id),
      kind: 'audio',
      category: ca.category,
      // 音色条目统一用音频专用封面：音频文件没有缩略图，沿用角色形象图会让
      // 「谁的音色」被误读成一张参考图，也会掩盖它其实是音频资产。
      thumbUrl: AUDIO_LOGO_URL,
    })
  }
  return list
}

/** 提示词中的 @ 引用 token：@{素材名}。 */
export const MENTION_TOKEN_RE = /@\{([^}]+)\}/g

/** 一个 @ 引用 token 在提示词中的字符区间 [start, end)。 */
export interface MentionRange {
  start: number
  end: number
  name: string
}

/** 扫描提示词中所有 @ 引用 token 的字符区间，用于整体删除与光标吸附。 */
export function findMentionRanges(prompt: string): MentionRange[] {
  const ranges: MentionRange[] = []
  for (const match of prompt.matchAll(MENTION_TOKEN_RE)) {
    const start = match.index ?? 0
    ranges.push({ start, end: start + match[0].length, name: match[1] })
  }
  return ranges
}

/**
 * 将选区 [start, end) 扩展到完整的 @ 引用 token 边界。
 * 与选区相交（含部分覆盖）的 token 会被整体纳入，避免删除后残留 "@{" 等碎片。
 */
export function expandToMentionBounds(
  prompt: string,
  start: number,
  end: number,
): { start: number; end: number } {
  let from = start
  let to = end
  for (const range of findMentionRanges(prompt)) {
    if (range.end > from && range.start < to) {
      from = Math.min(from, range.start)
      to = Math.max(to, range.end)
    }
  }
  return { start: from, end: to }
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
