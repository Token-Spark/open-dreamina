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

import type { TaskType } from '@/api/tasks'
import type { Provider } from '@/api/providers'
import catalogData from '@/config/modelServices.json'

/**
 * Data-driven generation config (spec P0.3: drive UI from data, not if-else).
 *
 * 需求1：合并文生图/图生图、文生视频/图生视频为「内容模式」(图片/视频)。
 * 实际任务类型由内容模式 + 是否上传参考图派生（deriveTaskType）。
 * 需求2：模型列表按内容模式(图片/视频)筛选，而非具体任务类型。
 * 需求3：Provider 可配置接入的模型与自定义展示名，存于 provider.config.models。
 * 需求4：可用模型服务目录与需用户填写参数由 JSON 文件配置（config/modelServices.json）。
 */

export type ContentMode = 'image' | 'video'

export interface ContentModeDef {
  mode: ContentMode
  label: string
}

/** 录入框展示的两个内容模式按钮。 */
export const CONTENT_MODES: ContentModeDef[] = [
  { mode: 'image', label: '图片' },
  { mode: 'video', label: '视频' },
]

/** 内容模式 → 该模式下所有可能的任务类型。 */
export const MODE_TASK_TYPES: Record<ContentMode, TaskType[]> = {
  image: ['text2img', 'img2img'],
  video: ['text2video', 'img2video'],
}

/** 根据内容模式与是否有参考图，派生实际任务类型。 */
export function deriveTaskType(mode: ContentMode, hasReferenceImage: boolean): TaskType {
  if (mode === 'image') return hasReferenceImage ? 'img2img' : 'text2img'
  return hasReferenceImage ? 'img2video' : 'text2video'
}

/** 由任务类型反推内容模式（用于从历史任务重建 UI 状态）。 */
export function modeOfTaskType(type: TaskType): ContentMode {
  return type === 'text2img' || type === 'img2img' ? 'image' : 'video'
}

export interface ModelInfo {
  id: string
  label: string
  types: TaskType[]
}

/** 激活表单字段类型：secret=密码框，url/text=普通输入框。 */
export type CatalogFieldKind = 'secret' | 'url' | 'text'

/** JSON 目录中每个服务需用户填写的参数定义。 */
export interface CatalogField {
  key: string
  label: string
  kind: CatalogFieldKind
  required: boolean
  placeholder?: string
  /** 默认值；如 base_url 的官方地址。 */
  default?: string
}

/** JSON 目录中的单个模型服务定义（一张卡片）。 */
export interface ModelService {
  slug: string
  name: string
  vendor: string
  description: string
  docsUrl?: string
  modes: ContentMode[]
  fields: CatalogField[]
  models: ModelInfo[]
}

/** 从 JSON 加载的完整模型服务目录（数据驱动，避免硬编码）。 */
export const MODEL_SERVICES: ModelService[] = (catalogData as {
  services: ModelService[]
}).services

/** 按 slug 查找目录中的服务定义。 */
export function findService(slug: string): ModelService | undefined {
  return MODEL_SERVICES.find((s) => s.slug === slug)
}

/**
 * 已知 Provider 模型默认目录（由 JSON 派生，保留旧 API 向后兼容）。
 * 需求3：用户可在设置页勾选启用的模型并自定义展示名，
 * 选择结果存入后端 provider.config.models，运行时优先读取。
 */
export const PROVIDER_MODELS: Record<string, ModelInfo[]> = Object.fromEntries(
  MODEL_SERVICES.map((s) => [s.slug, s.models]),
)

/** Provider 配置中存储的模型项（用户勾选 + 自定义名称）。 */
export interface ProviderModelConfig {
  id: string
  /** 用户自定义展示名；为空时回退到目录默认 label。 */
  label: string
  types: TaskType[]
}

/** 已知目录中该 slug 的默认模型（用于设置页展示可选项）。 */
export function catalogModels(providerSlug: string): ModelInfo[] {
  return PROVIDER_MODELS[providerSlug] ?? []
}

/** 读取 Provider 实际启用的模型：优先 config.models，回退默认目录。 */
export function providerModels(provider: Provider): ModelInfo[] {
  const configured = (provider.config?.models as ProviderModelConfig[] | undefined) ?? []
  if (configured.length > 0) {
    return configured.map((m) => ({
      id: m.id,
      label: m.label?.trim() || m.id,
      types: m.types,
    }))
  }
  return catalogModels(provider.slug)
}

/** 某 Provider 在指定内容模式下可用的模型（支持该模式下任意任务类型）。 */
export function modelsForCategory(provider: Provider | undefined, mode: ContentMode): ModelInfo[] {
  if (!provider) return []
  const wantTypes = MODE_TASK_TYPES[mode]
  return providerModels(provider).filter((m) => m.types.some((t) => wantTypes.includes(t)))
}

/** 模型是否支持指定任务类型（用于上传参考图后校验当前模型）。 */
export function modelSupportsType(model: ModelInfo, type: TaskType): boolean {
  return model.types.includes(type)
}

export type ParamKind = 'number' | 'select'

export interface ParamField {
  key: string
  label: string
  kind: ParamKind
  min?: number
  max?: number
  step?: number
  options?: { value: string; label: string }[]
  default: number | string
}

const SIZE_OPTIONS = [
  { value: '512', label: '512 × 512' },
  { value: '768', label: '768 × 768' },
  { value: '1024', label: '1024 × 1024' },
  { value: '1280', label: '1280 × 720' },
  { value: '1536', label: '1536 × 640' },
]

/** 视频生成时长选项（秒）。 */
export const DURATION_OPTIONS = [
  { value: '5', label: '5 秒' },
  { value: '10', label: '10 秒' },
]

/** 参数 schema 按任务类型定义；驱动动态参数面板。 */
export const PARAM_FIELDS: Record<TaskType, ParamField[]> = {
  text2img: [
    { key: 'count', label: '生成数量', kind: 'number', min: 1, max: 4, step: 1, default: 1 },
    { key: 'width', label: '宽度', kind: 'select', options: SIZE_OPTIONS, default: 1024 },
    { key: 'height', label: '高度', kind: 'select', options: SIZE_OPTIONS, default: 1024 },
    { key: 'steps', label: '采样步数', kind: 'number', min: 1, max: 80, step: 1, default: 30 },
    { key: 'guidance', label: '提示词权重', kind: 'number', min: 1, max: 20, step: 0.5, default: 7 },
  ],
  img2img: [
    { key: 'count', label: '生成数量', kind: 'number', min: 1, max: 4, step: 1, default: 1 },
    { key: 'width', label: '宽度', kind: 'select', options: SIZE_OPTIONS, default: 1024 },
    { key: 'height', label: '高度', kind: 'select', options: SIZE_OPTIONS, default: 1024 },
    { key: 'steps', label: '采样步数', kind: 'number', min: 1, max: 80, step: 1, default: 30 },
    { key: 'strength', label: '重绘强度', kind: 'number', min: 0, max: 1, step: 0.05, default: 0.7 },
  ],
  text2video: [
    { key: 'duration', label: '时长', kind: 'select', options: DURATION_OPTIONS, default: 5 },
    { key: 'width', label: '宽度', kind: 'select', options: SIZE_OPTIONS, default: 1280 },
    { key: 'height', label: '高度', kind: 'select', options: SIZE_OPTIONS, default: 720 },
  ],
  img2video: [
    { key: 'duration', label: '时长', kind: 'select', options: DURATION_OPTIONS, default: 5 },
    { key: 'width', label: '宽度', kind: 'select', options: SIZE_OPTIONS, default: 1280 },
    { key: 'height', label: '高度', kind: 'select', options: SIZE_OPTIONS, default: 720 },
  ],
}

/** 由 schema 默认值构建指定任务类型的参数对象。 */
export function defaultParamsForType(type: TaskType): Record<string, number | string> {
  const out: Record<string, number | string> = {}
  for (const f of PARAM_FIELDS[type]) out[f.key] = f.default
  const mode = modeOfTaskType(type)
  const ratio = defaultAspectRatioForMode(mode)
  const resolution = defaultResolutionForMode(mode)
  out.aspect_ratio = ratio
  out.resolution = resolution
  // 用比例+分辨率反算真实宽高，避免与 SizePicker 展示不一致
  const { width, height } = sizeFromRatioResolution(ratio, resolution, mode)
  out.width = width
  out.height = height
  return out
}

export type AspectRatio =
  | 'auto'
  | '21:9'
  | '16:9'
  | '3:2'
  | '4:3'
  | '1:1'
  | '3:4'
  | '2:3'
  | '9:16'

export type ImageResolution = '1K' | '1.5K' | '2K' | '3K' | '4K'
export type VideoResolution = '480p' | '720p' | '1080p' | '2160p'
export type Resolution = ImageResolution | VideoResolution

export interface AspectRatioDef {
  value: AspectRatio
  label: string
  ratio: number
}

export interface ResolutionDef {
  value: Resolution
  label: string
}

/**
 * 按内容模式区分的可用比例。
 * - 图片（Seedream 5.0 pro/lite）：支持 3:2 / 2:3 等所有常见比例。
 * - 视频（Seedance 1.0/1.5/2.0）：不支持 3:2 / 2:3，仅 6 种。
 * 数据来源：
 * - 图片：https://www.volcengine.com/docs/82379/1541523
 * - 视频：https://www.volcengine.com/docs/82379/1520757
 */
export const ASPECT_RATIOS_BY_MODE: Record<ContentMode, AspectRatioDef[]> = {
  image: [
    { value: 'auto', label: '智能', ratio: 0 },
    { value: '21:9', label: '21:9', ratio: 21 / 9 },
    { value: '16:9', label: '16:9', ratio: 16 / 9 },
    { value: '3:2', label: '3:2', ratio: 3 / 2 },
    { value: '4:3', label: '4:3', ratio: 4 / 3 },
    { value: '1:1', label: '1:1', ratio: 1 },
    { value: '3:4', label: '3:4', ratio: 3 / 4 },
    { value: '2:3', label: '2:3', ratio: 2 / 3 },
    { value: '9:16', label: '9:16', ratio: 9 / 16 },
  ],
  video: [
    { value: 'auto', label: '智能', ratio: 0 },
    { value: '21:9', label: '21:9', ratio: 21 / 9 },
    { value: '16:9', label: '16:9', ratio: 16 / 9 },
    { value: '4:3', label: '4:3', ratio: 4 / 3 },
    { value: '1:1', label: '1:1', ratio: 1 },
    { value: '3:4', label: '3:4', ratio: 3 / 4 },
    { value: '9:16', label: '9:16', ratio: 9 / 16 },
  ],
}

/**
 * 按内容模式区分的可用分辨率。
 * - 图片：1K / 2K / 4K（基于长边的近似档位，由模型方按 size=2K 或 widthxheight 解析）。
 * - 视频：480p / 720p / 1080p（视频 API 原生字段）。
 */
export const RESOLUTIONS_BY_MODE: Record<ContentMode, ResolutionDef[]> = {
  image: [
    { value: '1K', label: '标清 1K' },
    { value: '2K', label: '高清 2K' },
    { value: '4K', label: '超清 4K' },
  ],
  video: [
    { value: '480p', label: '标清 480p' },
    { value: '720p', label: '高清 720p' },
    { value: '1080p', label: '超清 1080p' },
    { value: '2160p', label: '4K 2160p' },
  ],
}

/**
 * 视频模型支持的分辨率因模型而异（数据来源：spark-hub router.md 第 9.3 节）：
 * - Seedance 2.0（标准版）：480p / 720p / 1080p / 2160p
 * - Seedance 2.0 Fast / Mini：仅 480p / 720p
 * - Seedance 2.5：仅 480p / 720p
 */
export function videoResolutionsForModel(modelId: string): ResolutionDef[] {
  const id = modelId.toLowerCase()
  const isFastOrMini = id.includes('fast') || id.includes('mini')
  const is25 = id.includes('2_5') || id.includes('2-5') || id.includes('2.5')
  const isFullSeedance2 =
    !isFastOrMini &&
    !is25 &&
    (id.includes('seedance_2') || id.includes('seedance-2') || id.includes('seedance2.0'))

  if (isFullSeedance2) {
    return [
      { value: '480p', label: '标清 480p' },
      { value: '720p', label: '高清 720p' },
      { value: '1080p', label: '超清 1080p' },
      { value: '2160p', label: '4K 2160p' },
    ]
  }
  // Fast / Mini / 2.5 及未知视频模型仅支持 480p / 720p
  return [
    { value: '480p', label: '标清 480p' },
    { value: '720p', label: '高清 720p' },
  ]
}

/** 是否为即梦 CLI 的 Seedream 图片 Provider（slug 固定为 dreamina-seedream）。 */
export function isDreaminaSeedreamCli(slug: string): boolean {
  return slug === 'dreamina-seedream'
}

/**
 * 即梦 CLI 图片模型支持的分辨率档位（来源：即梦 CLI 体验指南 / CLI 校验）。
 * 仅当使用 dreamina-seedream Provider 时生效：
 * - 即梦 3.x 支持 1K / 2K；
 * - Seedream 5.0 / 即梦 4.x 支持 2K / 4K。
 */
export function imageResolutionsForModel(modelId: string): ResolutionDef[] {
  const id = modelId.toLowerCase()
  if (id.includes('jimeng3') || id.includes('3.0')) {
    return [
      { value: '1K', label: '标清 1K' },
      { value: '2K', label: '高清 2K' },
    ]
  }
  return [
    { value: '2K', label: '高清 2K' },
    { value: '4K', label: '超清 4K' },
  ]
}

/** 默认比例：图片 1:1 正方形；视频 16:9 横屏（与 Seedance API 默认 ratio 一致）。 */
export function defaultAspectRatioForMode(mode: ContentMode): AspectRatio {
  return mode === 'image' ? '1:1' : '16:9'
}

/** 默认分辨率：图片 2K；视频 720p。 */
export function defaultResolutionForMode(mode: ContentMode): Resolution {
  return mode === 'image' ? '2K' : '720p'
}

/**
 * 图片生成像素表（基于 Seedream 5.0 lite 官方推荐宽高组合，全部按 64 对齐）。
 * 来源：https://www.volcengine.com/docs/82379/1541523
 * 1K / 4K 档位由同规则外推。
 */
const IMAGE_SIZE_TABLE: Partial<Record<ImageResolution, Partial<Record<AspectRatio, { width: number; height: number }>>>> = {
  '1K': {
    '1:1': { width: 1024, height: 1024 },
    '3:4': { width: 768, height: 1024 },
    '4:3': { width: 1024, height: 768 },
    '16:9': { width: 1024, height: 576 },
    '9:16': { width: 576, height: 1024 },
    '3:2': { width: 1024, height: 640 },
    '2:3': { width: 640, height: 1024 },
    '21:9': { width: 1024, height: 448 },
  },
  '2K': {
    '1:1': { width: 2048, height: 2048 },
    '3:4': { width: 1728, height: 2304 },
    '4:3': { width: 2304, height: 1728 },
    '16:9': { width: 2848, height: 1600 },
    '9:16': { width: 1600, height: 2848 },
    '3:2': { width: 2496, height: 1664 },
    '2:3': { width: 1664, height: 2496 },
    '21:9': { width: 3136, height: 1344 },
  },
  '4K': {
    '1:1': { width: 4096, height: 4096 },
    '3:4': { width: 3456, height: 4608 },
    '4:3': { width: 4608, height: 3456 },
    '16:9': { width: 5696, height: 3200 },
    '9:16': { width: 3200, height: 5696 },
    '3:2': { width: 4992, height: 3328 },
    '2:3': { width: 3328, height: 4992 },
    '21:9': { width: 6272, height: 2688 },
  },
}

/**
 * 视频生成像素表（Seedance 1.0/1.5/2.0 官方固定组合，非长边公式）。
 * 来源：https://www.volcengine.com/docs/82379/1520757
 */
const VIDEO_SIZE_TABLE: Record<VideoResolution, Partial<Record<AspectRatio, { width: number; height: number }>>> = {
  '480p': {
    '16:9': { width: 864, height: 480 },
    '4:3': { width: 736, height: 544 },
    '1:1': { width: 640, height: 640 },
    '3:4': { width: 544, height: 736 },
    '9:16': { width: 480, height: 864 },
    '21:9': { width: 960, height: 416 },
  },
  '720p': {
    '16:9': { width: 1248, height: 704 },
    '4:3': { width: 1120, height: 832 },
    '1:1': { width: 960, height: 960 },
    '3:4': { width: 832, height: 1120 },
    '9:16': { width: 704, height: 1248 },
    '21:9': { width: 1504, height: 640 },
  },
  '1080p': {
    '16:9': { width: 1920, height: 1088 },
    '4:3': { width: 1664, height: 1248 },
    '1:1': { width: 1440, height: 1440 },
    '3:4': { width: 1248, height: 1664 },
    '9:16': { width: 1088, height: 1920 },
    '21:9': { width: 2176, height: 928 },
  },
  '2160p': {
    '16:9': { width: 3840, height: 2176 },
    '4:3': { width: 3328, height: 2496 },
    '1:1': { width: 2880, height: 2880 },
    '3:4': { width: 2496, height: 3328 },
    '9:16': { width: 2176, height: 3840 },
    '21:9': { width: 4352, height: 1856 },
  },
}

/** auto 比例的回退尺寸：图片 1:1；视频 16:9。 */
const DEFAULT_SIZE: Record<ContentMode, { width: number; height: number }> = {
  image: { width: 1024, height: 1024 },
  video: { width: 1280, height: 720 },
}

/** 根据比例与分辨率计算实际宽高（图片走像素表，视频走官方固定组合）。 */
export function sizeFromRatioResolution(
  ratio: AspectRatio,
  resolution: Resolution,
  mode: ContentMode,
): { width: number; height: number } {
  if (mode === 'video') {
    const table = VIDEO_SIZE_TABLE[resolution as VideoResolution]
    if (ratio === 'auto' || !table) return DEFAULT_SIZE.video
    return table[ratio] ?? DEFAULT_SIZE.video
  }
  const table = IMAGE_SIZE_TABLE[resolution as ImageResolution]
  if (ratio === 'auto' || !table) return DEFAULT_SIZE.image
  return table[ratio] ?? DEFAULT_SIZE.image
}
