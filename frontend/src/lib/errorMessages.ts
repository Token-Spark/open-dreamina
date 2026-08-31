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
 * 已知 CLI 错误文案 → 友好提示的映射表。
 *
 * 后端/CLI 返回的错误信息通常是英文技术描述（如 "pre-TNS check did not pass"），
 * 直接展示给用户难以理解。这里用声明式配置将已知错误模式映射为简洁的中文说明，
 * 未匹配时回退到原始错误文案。
 */
interface ErrorHint {
  /** 主标题，简短概括失败原因。 */
  title: string
  /** 补充说明，给出可能的原因或修复建议。 */
  hint?: string
}

interface ErrorPattern {
  /** 正则匹配片段（大小写不敏感）。 */
  pattern: RegExp
  /** 映射后的友好提示。 */
  hint: ErrorHint
}

const ERROR_PATTERNS: ErrorPattern[] = [
  {
    // pre-TNS（预审核）未通过：参考图疑似涉及公众人物肖像
    pattern: /pre-tns|pre_tns|pre-?TNS/i,
    hint: {
      title: '参考图未通过内容安全检查',
      hint: '参考图可能涉及公众人物相似肖像，请更换图片后重试。',
    },
  },
  {
    // NSFW 内容检测未通过
    pattern: /nsfw|content.?filter|safety.?check/i,
    hint: {
      title: '内容未通过安全审核',
      hint: '生成的图片或提示词可能包含敏感内容，请调整后重试。',
    },
  },
  {
    // 额度不足 / 积分耗尽
    pattern: /quota|insufficient.?credit|balance|额度|积分/i,
    hint: {
      title: '额度不足',
      hint: '当前账户额度已耗尽，请充值或联系管理员后重试。',
    },
  },
  {
    // 模型不可用 / 下线
    pattern: /model.?not.?found|model.?unavailable|model.?deprecat/i,
    hint: {
      title: '模型不可用',
      hint: '所选模型已下线或暂不可用，请在设置中切换其他模型。',
    },
  },
  {
    // 超时
    pattern: /timeout|timed.?out|超时/i,
    hint: {
      title: '生成超时',
      hint: '服务繁忙导致请求超时，请稍后重试。',
    },
  },
]

/**
 * 将原始错误文案映射为用户友好的提示。
 * 匹配失败时返回 null，调用方可回退到原始文案。
 */
export function matchErrorHint(rawError: string | null | undefined): ErrorHint | null {
  if (!rawError) return null
  for (const { pattern, hint } of ERROR_PATTERNS) {
    if (pattern.test(rawError)) return hint
  }
  return null
}

/**
 * 返回失败时展示的标题文案。
 * 优先使用映射后的友好标题，未匹配时回退到"生成失败"。
 */
export function errorTitle(rawError: string | null | undefined): string {
  return matchErrorHint(rawError)?.title ?? '生成失败'
}

/**
 * 返回失败时展示的详细说明文案。
 * 优先使用映射后的友好说明，未匹配时回退到原始错误（若为空则给默认）。
 */
export function errorDetail(rawError: string | null | undefined): string {
  const matched = matchErrorHint(rawError)
  if (matched) return matched.hint ?? matched.title
  return rawError ?? '未知错误，请稍后重试'
}
