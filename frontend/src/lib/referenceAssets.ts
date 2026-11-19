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
 * 「被引用对象」预览的共享组装逻辑。
 *
 * CLI / MCP 提交视频生成任务时可以带图片、视频、音频三类参考素材，但任务响应里
 * 只有 asset_id 与派生 URL，没有类型。列表与卡片上显示缩略图不需要类型；点开大图
 * 灯箱时才按 id 逐条补查，让 <img> / <video> / <audio> 走对的渲染分支。
 */

import { assetFileUrl, getAsset } from '@/api/assets'
import type { LightboxGallery, LightboxItem } from '@/components/ImageLightbox'

/**
 * 组装可左右切换的参考素材画廊。
 * 仅在用户点击预览时调用；素材已删除或后端不可达时回落为图片，不让整批预览失败。
 */
export async function buildReferenceGallery(
  ids: string[],
  urls?: string[],
  index = 0,
): Promise<LightboxGallery | null> {
  const valid = ids.filter((id) => typeof id === 'string' && !!id)
  if (valid.length === 0) return null

  const kinds = await Promise.all(
    valid.map(async (id) => {
      try {
        return (await getAsset(id)).type
      } catch {
        return 'image' as const
      }
    }),
  )

  const items: LightboxItem[] = valid.map((id, i) => ({
    url: urls?.[i] || assetFileUrl(id),
    type: kinds[i] === 'video' ? 'video' : kinds[i] === 'audio' ? 'audio' : 'image',
    title: `参考素材 ${i + 1}`,
    meta: { '资产 ID': id },
  }))

  return { items, index: Math.min(Math.max(index, 0), items.length - 1) }
}
