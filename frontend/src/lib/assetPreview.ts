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
 * 音频资产预览的单一真源。
 *
 * 后端只为 image 生成缩略图；音频资产的 /thumbnail 会回退返回原始音频字节，
 * 且被标成 image/webp。任何把该 URL 交给 <img> 的地方都会破图，onError 兜底
 * 也只能显示「素材不可用」这种没有信息量的占位。
 *
 * 这里统一把音频资产的预览指向一张专用封面图：既是「预览图」（可在所有 <img>
 * 场景直接复用），也让音频在参考素材列表里一眼区别于图片与视频。
 * 封面采用固定配色，语义等同专辑封面，不随明暗主题切换。
 */

import audioLogoUrl from '@/static/audio-logo.svg'
import { assetThumbnailUrl } from '@/api/assets'

/** 所有音频资产共用的预览封面（Vite 打包后为带 hash 的稳定 URL）。 */
export const AUDIO_LOGO_URL: string = audioLogoUrl

/** 预览图的无障碍文案；封面本身没有可朗读的文字内容。 */
export const AUDIO_LOGO_ALT = '参考音频'

/** 参考素材类型是否为音频；兼容后端 Asset.type 与前端 ReferenceAsset.kind。 */
export function isAudioKind(kind: string | null | undefined): boolean {
  return kind === 'audio'
}

/**
 * 参考素材在托盘、候选浮层、悬浮卡里的缩略图地址。
 *
 * 音频一律返回 Logo：即便数据里带着 thumbUrl（可能是角色形象图，也可能是会
 * 返回音频字节的 /thumbnail），也不再把它当图片渲染，避免破图与误读。
 */
export function refAssetThumbUrl(asset: {
  kind?: string | null
  thumbUrl?: string
  previewUrl: string
}): string {
  return isAudioKind(asset.kind) ? AUDIO_LOGO_URL : asset.thumbUrl || asset.previewUrl
}

/**
 * 后端资产（只有 id 与 type）的缩略图地址。用于消息卡、任务卡等只有
 * input_asset_ids、没有完整 ReferenceAsset 的场景；类型未知时调用方仍需保留
 * 图片加载失败的兜底。
 */
export function assetPreviewUrl(asset: { id: string; type: string }): string {
  return isAudioKind(asset.type) ? AUDIO_LOGO_URL : assetThumbnailUrl(asset.id)
}
