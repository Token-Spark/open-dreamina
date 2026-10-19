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
 * 素材审核状态轮询：全局单调度器。
 *
 * 此前每个 pending 素材各自起一条递归 setTimeout(3000) 链，N 个素材就是 N 条互不相关的
 * 高频链（画布 hook 与输入栏各一份），后端每个请求都要重新连一次上游审核接口。
 * 收敛为单一定时器后：同一 (provider, asset) 只查一次，同一时刻最多一个在途请求，
 * 页面隐藏时暂停，回到前台自动续上。
 */
import { getAssetAudit, type Asset } from '@/api/assets'

const POLL_INTERVAL_MS = 10000

type Watcher = (asset: Asset) => void

interface Entry {
  assetId: string
  providerSlug: string
  watchers: Set<Watcher>
}

const entries = new Map<string, Entry>()
let timer: number | null = null
let ticking = false

function entryKey(providerSlug: string, assetId: string): string {
  return `${providerSlug}::${assetId}`
}

function isHidden(): boolean {
  return typeof document !== 'undefined' && document.hidden
}

function schedule(): void {
  if (timer !== null || ticking || entries.size === 0 || isHidden()) return
  timer = window.setTimeout(run, POLL_INTERVAL_MS)
}

async function run(): Promise<void> {
  timer = null
  if (isHidden()) return
  ticking = true
  try {
    for (const entry of [...entries.values()]) {
      let asset: Asset
      try {
        asset = await getAssetAudit(entry.assetId, entry.providerSlug)
      } catch {
        // 与原实现一致：查询失败即停止该素材轮询，下次上传/刷新时重新发起
        entries.delete(entryKey(entry.providerSlug, entry.assetId))
        continue
      }
      for (const watcher of [...entry.watchers]) watcher(asset)
      if (asset.audit_status !== 'pending') {
        entries.delete(entryKey(entry.providerSlug, entry.assetId))
      }
    }
  } finally {
    ticking = false
  }
  schedule()
}

/**
 * 轮询指定素材的审核状态，每次拿到结果回调一次 watcher。
 * 返回取消函数：组件卸载时必须调用，否则会留下无人认领的轮询。
 */
export function watchAssetAudit(
  assetId: string,
  providerSlug: string,
  watcher: Watcher,
): () => void {
  const key = entryKey(providerSlug, assetId)
  let entry = entries.get(key)
  if (!entry) {
    entry = { assetId, providerSlug, watchers: new Set() }
    entries.set(key, entry)
  }
  entry.watchers.add(watcher)
  schedule()

  return () => {
    const current = entries.get(key)
    if (!current) return
    current.watchers.delete(watcher)
    if (current.watchers.size === 0) entries.delete(key)
  }
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) schedule()
  })
}
