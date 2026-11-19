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
 * 由 asset id 批量补查类型，给出可直接用于 <img> 的缩略图地址。
 *
 * 生成任务与消息里只有 input_asset_ids，没有素材类型；音频若直接请求
 * /thumbnail 会拿到音频原始字节从而破图。这里按 id 查一次类型，音频返回
 * 专用 Logo，其余沿用缩略图接口。
 *
 * 查询失败（素材已被删除）时保留原缩略图地址，由各组件的 onError 兜底，
 * 不会把「已删除」误标成音频。与素材库共用 ['assets'] 命名空间，资产
 * 删除/更新后缓存会自动失效。
 */

import { useQueries } from '@tanstack/react-query'
import { assetThumbnailUrl, getAsset } from '@/api/assets'
import { assetPreviewUrl } from '@/lib/assetPreview'

export function useAssetPreviewUrls(ids: string[]): Record<string, string> {
  // 同一素材可能被多次引用；去重后按 id 建立映射，避免重复请求。
  const unique = Array.from(new Set(ids))
  const results = useQueries({
    queries: unique.map((id) => ({
      queryKey: ['assets', 'detail', id] as const,
      queryFn: () => getAsset(id),
      staleTime: 5 * 60_000,
      retry: false,
    })),
  })

  const urls: Record<string, string> = {}
  unique.forEach((id, i) => {
    const asset = results[i]?.data
    urls[id] = asset ? assetPreviewUrl(asset) : assetThumbnailUrl(id)
  })
  return urls
}
