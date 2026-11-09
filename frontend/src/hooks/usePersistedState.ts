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

import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'

/**
 * 与 useState 同签名，额外把值同步写入 localStorage，跨页面切换和刷新都能恢复。
 *
 * legacyKeys 用于平滑迁移旧的持久化键：新键不存在时按顺序尝试旧键，
 * 读取一次后后续只写新键，不需要清理用户浏览器里的旧数据。
 * localStorage 不可用（隐私模式、配额耗尽）时静默降级为普通内存状态。
 */
export function usePersistedState<T>(
  key: string,
  initial: T | (() => T),
  legacyKeys: string[] = [],
): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    for (const k of [key, ...legacyKeys]) {
      try {
        const raw = window.localStorage.getItem(k)
        if (raw != null) return JSON.parse(raw) as T
      } catch {
        // 损坏的 JSON 或存储不可用：继续尝试下一个键
      }
    }
    return typeof initial === 'function' ? (initial as () => T)() : initial
  })

  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value))
    } catch {
      // 存储不可用时保持当前会话内的状态即可
    }
  }, [key, value])

  return [value, setValue]
}
