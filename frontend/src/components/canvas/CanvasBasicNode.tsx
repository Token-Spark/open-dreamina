// Copyright 2026 Open Dreamina Contributors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0

import { useMemo, useRef, useState, type Dispatch, type MouseEvent, type SetStateAction } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Clapperboard, Eye, Film, Image as ImageIcon, Loader2, Maximize2, Music, Pause, Play, StickyNote, Type as TypeIcon, Upload, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useCanvasStore } from '@/stores/canvasStore'
import { useAssets, useAssetTags } from '@/hooks/useAssets'
import { useCreationAssets, useCreationAssetTags } from '@/hooks/useCreationAssets'
import { useUIStore } from '@/stores/uiStore'
import { assetFileUrl, assetThumbnailUrl, uploadAsset, type Asset, type AssetType } from '@/api/assets'
import { CATEGORY_OPTIONS, type CreationAsset, type CreationAssetCategory } from '@/api/creationAssets'
import { getSystemSettings } from '@/api/system'
import { Dialog } from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { DirectorDeskDialog } from '@/components/DirectorDeskDialog'
import { PromptFullscreenEditor } from '@/components/PromptFullscreenEditor'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'

const NODE_ICONS: Record<string, typeof ImageIcon> = {
  asset: ImageIcon,
  prompt: TypeIcon,
  image_gen: ImageIcon,
  video_gen: Film,
  preview: Eye,
  note: StickyNote,
}

const NODE_LABELS: Record<string, string> = {
  asset: '素材',
  prompt: '提示词',
  image_gen: '图片生成',
  video_gen: '视频生成',
  preview: '预览',
  note: '备注',
}

const NODE_COLORS: Record<string, string> = {
  asset: 'border-blue-500/40 bg-blue-500/5',
  prompt: 'border-purple-500/40 bg-purple-500/5',
  image_gen: 'border-orange-500/40 bg-orange-500/5',
  video_gen: 'border-pink-500/40 bg-pink-500/5',
  preview: 'border-green-500/40 bg-green-500/5',
  note: 'border-gray-500/40 bg-gray-500/5',
}

const NODE_PORT_SPECS: Record<
  string,
  { inputs: { id: string }[]; outputs: { id: string }[] }
> = {
  asset: { inputs: [], outputs: [{ id: 'out' }] },
  prompt: { inputs: [{ id: 'in' }], outputs: [{ id: 'out' }] },
  preview: { inputs: [{ id: 'in' }], outputs: [] },
  note: { inputs: [], outputs: [] },
}

/** 音频预览：点击播放/暂停，带进度条。 */
function AudioPreview({ src, className }: { src: string; className?: string }) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)

  function togglePlay(e: MouseEvent) {
    e.stopPropagation()
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) {
      void audio.play()
    } else {
      audio.pause()
    }
  }

  return (
    <div className={cn('flex items-center gap-2 bg-bg-tertiary px-2 py-1.5', className)}>
      <audio
        ref={audioRef}
        src={src}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => { setPlaying(false); setProgress(0) }}
        onTimeUpdate={(e) => {
          const audio = e.currentTarget
          if (audio.duration > 0) {
            setProgress((audio.currentTime / audio.duration) * 100)
          }
        }}
      />
      <button
        type="button"
        onClick={togglePlay}
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent text-white transition-colors hover:bg-accent/80"
        aria-label={playing ? '暂停' : '播放'}
      >
        {playing ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
      </button>
      <div className="h-1 flex-1 overflow-hidden rounded-full bg-fg-muted/30">
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-150"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  )
}

export function CanvasBasicNode({ id, data, selected }: NodeProps) {
  const storedData = useCanvasStore(
    (state) => state.nodes.find((node) => node.id === id)?.data,
  )
  const nodeData = { ...data, ...storedData }
  const nodeType = (nodeData.nodeType as string) ?? 'note'
  const Icon = NODE_ICONS[nodeType] ?? StickyNote
  const label = NODE_LABELS[nodeType] ?? nodeType
  const colorClass = NODE_COLORS[nodeType] ?? ''
  const portSpec = NODE_PORT_SPECS[nodeType] ?? { inputs: [], outputs: [] }
  const updateNodeData = useCanvasStore((state) => state.updateNodeData)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [directorOpen, setDirectorOpen] = useState(false)
  const [directorUploading, setDirectorUploading] = useState(false)
  // 全屏沉浸式文本编辑开关（提示词/备注节点）
  const [fullscreenOpen, setFullscreenOpen] = useState(false)
  const theme = useUIStore((s) => s.theme)

  // 导演台 URL 来自后端系统设置；未配置则不显示入口
  const { data: systemSettings } = useQuery({
    queryKey: ['system', 'settings'],
    queryFn: getSystemSettings,
    staleTime: 5 * 60 * 1000,
  })
  const directorDeskUrl = systemSettings?.director_desk_url

  const assetId = nodeData.asset_id as string | undefined

  function handleSelectAsset(asset: Asset) {
    updateNodeData(id, {
      asset_id: asset.id,
      asset_type: asset.type,
      asset_thumb: assetThumbnailUrl(asset.id),
    })
    setPickerOpen(false)
  }

  /** 素材库创作资产 → 节点素材：用底层 image_asset_id 作为节点 asset_id */
  function handleSelectCreationAsset(ca: CreationAsset) {
    if (!ca.image_asset_id) {
      toast('该素材没有关联图片', 'error')
      return
    }
    updateNodeData(id, {
      asset_id: ca.image_asset_id,
      asset_type: 'image' as AssetType,
      asset_thumb: ca.image_thumbnail_url ?? assetThumbnailUrl(ca.image_asset_id),
    })
    setPickerOpen(false)
  }

  function handleClearAsset() {
    updateNodeData(id, {
      asset_id: undefined,
      asset_type: undefined,
      asset_thumb: undefined,
    })
  }

  /** 导演台采集回调：上传截图并设为节点素材。 */
  async function handleDirectorImage(file: File) {
    setDirectorUploading(true)
    try {
      const asset = await uploadAsset(file)
      updateNodeData(id, {
        asset_id: asset.id,
        asset_type: asset.type,
        asset_thumb: assetThumbnailUrl(asset.id),
      })
      toast('导演台截图已设为素材', 'success')
    } catch (err) {
      toast(toApiError(err).message, 'error')
    } finally {
      setDirectorUploading(false)
    }
  }

  return (
    <div
      className={cn(
        'relative w-48 overflow-hidden rounded-card border bg-bg-secondary px-3 py-2.5 shadow-md transition-all',
        colorClass,
        selected && 'ring-2 ring-accent/50',
      )}
    >
      {portSpec.inputs.map((port, index) => (
        <Handle
          key={port.id}
          id={port.id}
          type="target"
          position={Position.Left}
          className="h-3 w-3 rounded-full border-2 border-bg-secondary bg-fg-muted"
          style={{ top: `${15 + index * 30}px` }}
        />
      ))}

      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 shrink-0 text-fg-secondary" />
        <span className="truncate text-xs font-medium text-fg-primary">{label}</span>
      </div>

      {(nodeType === 'prompt' || nodeType === 'note') && (
        <div className="relative nodrag nowheel mt-2">
          <textarea
            className="w-full resize-none rounded-btn border border-border bg-bg-tertiary px-2 py-1 pr-7 text-xs text-fg-primary placeholder:text-fg-muted focus:outline-none"
            rows={3}
            placeholder={nodeType === 'prompt' ? '输入提示词...' : '备注...'}
            value={(nodeData.text as string) ?? ''}
            onChange={(event) => updateNodeData(id, { text: event.target.value })}
          />
          {/* 全屏沉浸式编辑入口：小尺寸节点内输入体验受限，点击进入全屏大字号编辑 */}
          <button
            type="button"
            onClick={() => setFullscreenOpen(true)}
            title="全屏编辑"
            aria-label="全屏编辑"
            className="absolute right-1 top-1.5 flex h-5 w-5 items-center justify-center rounded text-fg-muted transition-colors hover:bg-bg-secondary hover:text-fg-primary"
          >
            <Maximize2 className="h-3 w-3" />
          </button>
        </div>
      )}

      {nodeType === 'asset' && (
        <div className="nodrag nowheel mt-2 space-y-2">
          {assetId ? (
            <div className="relative overflow-hidden rounded-btn">
              {nodeData.asset_type === 'audio' ? (
                <AudioPreview
                  src={assetFileUrl(assetId)}
                  className="h-24 w-full"
                />
              ) : (
                <img
                  src={(nodeData.asset_thumb as string) ?? assetFileUrl(assetId)}
                  alt="素材预览"
                  className="h-24 w-full object-cover"
                />
              )}
              <button
                type="button"
                onClick={handleClearAsset}
                className="absolute right-1 top-1 rounded-btn bg-black/60 p-1 text-white transition-colors hover:bg-black/80"
                aria-label="移除素材"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ) : (
            <p className="text-xs text-fg-muted">未选择素材</p>
          )}
          <div className="flex gap-1.5">
            <Button
              variant="secondary"
              size="sm"
              className="min-w-0 flex-1"
              onClick={() => setPickerOpen(true)}
            >
              <Upload className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{assetId ? '更换' : '选择素材'}</span>
            </Button>
            {directorDeskUrl && (
              <Button
                variant="secondary"
                size="sm"
                className="shrink-0 px-2"
                onClick={() => setDirectorOpen(true)}
                disabled={directorUploading}
                title="打开 3D 导演台，采集参考图"
              >
                {directorUploading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Clapperboard className="h-3.5 w-3.5" />
                )}
              </Button>
            )}
          </div>
          {pickerOpen && (
            <AssetPickerDialog
              open={pickerOpen}
              onOpenChange={setPickerOpen}
              onSelect={handleSelectAsset}
              onSelectCreationAsset={handleSelectCreationAsset}
            />
          )}
          {directorDeskUrl && (
            <DirectorDeskDialog
              open={directorOpen}
              onClose={() => setDirectorOpen(false)}
              url={directorDeskUrl}
              theme={theme}
              onCaptureImage={handleDirectorImage}
            />
          )}
        </div>
      )}

      {nodeType === 'preview' && (
        <p className="mt-1.5 text-xs text-fg-muted">预览产物</p>
      )}

      {/* 全屏沉浸式文本编辑（提示词/备注节点） */}
      {(nodeType === 'prompt' || nodeType === 'note') && (
        <PromptFullscreenEditor
          open={fullscreenOpen}
          onClose={() => setFullscreenOpen(false)}
          prompt={(nodeData.text as string) ?? ''}
          onPromptChange={(value) => updateNodeData(id, { text: value })}
          enableMention={false}
          title={nodeType === 'prompt' ? '编辑提示词' : '编辑备注'}
        />
      )}

      {portSpec.outputs.map((port) => (
        <Handle
          key={port.id}
          id={port.id}
          type="source"
          position={Position.Right}
          className="h-3 w-3 rounded-full border-2 border-bg-secondary bg-accent"
        />
      ))}
    </div>
  )
}

// ---------------- 素材选择弹窗 ----------------

const ASSET_TYPE_FILTERS = [
  { type: undefined as AssetType | undefined, label: '全部' },
  { type: 'image' as AssetType, label: '图片' },
  { type: 'video' as AssetType, label: '视频' },
  { type: 'audio' as AssetType, label: '音频' },
]

const CATEGORY_FILTERS: { value: CreationAssetCategory | undefined; label: string }[] = [
  { value: undefined, label: '全部' },
  ...CATEGORY_OPTIONS.map((o) => ({ value: o.value as CreationAssetCategory, label: o.label })),
]

const CATEGORY_BADGES: Record<CreationAssetCategory, string> = {
  character: '人物',
  scene: '场景',
  prop: '道具',
  keyframe: '关键帧',
}

interface AssetPickerDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (asset: Asset) => void
  onSelectCreationAsset: (ca: CreationAsset) => void
}

type PickerTab = 'library' | 'uploads'

function AssetPickerDialog({
  open,
  onOpenChange,
  onSelect,
  onSelectCreationAsset,
}: AssetPickerDialogProps) {
  const [tab, setTab] = useState<PickerTab>('library')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

  // ---- 素材库（creation assets）筛选状态 ----
  const [category, setCategory] = useState<CreationAssetCategory | undefined>(undefined)
  const [libSelectedTags, setLibSelectedTags] = useState<Set<string>>(new Set())
  const [libSearch, setLibSearch] = useState('')

  // ---- 上传文件（raw assets）筛选状态 ----
  const [typeFilter, setTypeFilter] = useState<AssetType | undefined>(undefined)
  const [rawSelectedTags, setRawSelectedTags] = useState<Set<string>>(new Set())
  const [rawSearch, setRawSearch] = useState('')

  // ---- 标签列表 ----
  const { data: libTagData } = useCreationAssetTags()
  const { data: rawTagList } = useAssetTags()

  // ---- 素材库数据 ----
  const libTagsParam = libSelectedTags.size > 0 ? Array.from(libSelectedTags).join(',') : undefined
  const { data: libData, isLoading: libLoading } = useCreationAssets({
    category,
    tags: libTagsParam,
    search: libSearch.trim() || undefined,
    page_size: 200,
  })
  const libAssets = useMemo(() => libData?.items ?? [], [libData?.items])

  // ---- 上传文件数据 ----
  const rawTagsParam = rawSelectedTags.size > 0 ? Array.from(rawSelectedTags).join(',') : undefined
  const { data: rawData, isLoading: rawLoading } = useAssets({
    type: typeFilter,
    tags: rawTagsParam,
    page_size: 200,
  })
  const rawAssets = useMemo(() => {
    const items = rawData?.items ?? []
    if (!rawSearch.trim()) return items
    const q = rawSearch.trim().toLowerCase()
    return items.filter(
      (a) =>
        a.tags.some((t) => t.toLowerCase().includes(q)) ||
        a.file_path.toLowerCase().includes(q),
    )
  }, [rawData?.items, rawSearch])

  function toggleTag(tag: string, setter: Dispatch<SetStateAction<Set<string>>>) {
    setter((prev) => {
      const next = new Set(prev)
      if (next.has(tag)) next.delete(tag)
      else next.add(tag)
      return next
    })
  }

  async function handleUpload(file: File) {
    setUploading(true)
    try {
      const asset = await uploadAsset(file)
      toast('素材上传成功', 'success')
      onSelect(asset)
    } catch (err) {
      toast(toApiError(err).message, 'error')
    } finally {
      setUploading(false)
    }
  }

  const search = tab === 'library' ? libSearch : rawSearch
  const setSearch = tab === 'library' ? setLibSearch : setRawSearch
  const selectedTags = tab === 'library' ? libSelectedTags : rawSelectedTags
  const tagSetter = tab === 'library' ? setLibSelectedTags : setRawSelectedTags
  const tagList = tab === 'library' ? libTagData?.tags : rawTagList

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="选择素材"
      description="从素材库按分类、标签筛选或上传新文件"
      className="max-w-2xl"
    >
      <div className="space-y-3">
        {/* Tab 切换 */}
        <div className="flex items-center gap-1 border-b border-border">
          {(['library', 'uploads'] as PickerTab[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={cn(
                '-mb-px border-b-2 px-3 py-1.5 text-xs font-medium transition-colors',
                tab === t
                  ? 'border-accent text-accent'
                  : 'border-transparent text-fg-muted hover:text-fg-secondary',
              )}
            >
              {t === 'library' ? '素材库' : '上传文件'}
            </button>
          ))}
        </div>

        {/* 工具栏：上传 + 搜索 */}
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Upload className="h-3.5 w-3.5" />
            )}
            上传
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,video/*,audio/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleUpload(file)
              e.target.value = ''
            }}
          />
          <input
            type="text"
            placeholder={tab === 'library' ? '搜索名称、设定或标签…' : '搜索标签或文件名…'}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="min-w-0 flex-1 rounded-btn border border-border bg-bg-tertiary px-2.5 py-1.5 text-xs text-fg-primary placeholder:text-fg-muted focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>

        {/* 分类 / 类型筛选 */}
        {tab === 'library' ? (
          <div className="flex items-center gap-1.5">
            {CATEGORY_FILTERS.map((f) => (
              <button
                key={f.label}
                type="button"
                onClick={() => setCategory(f.value)}
                className={cn(
                  'rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors',
                  category === f.value
                    ? 'bg-accent text-white'
                    : 'bg-bg-tertiary text-fg-secondary hover:bg-bg-secondary',
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        ) : (
          <div className="flex items-center gap-1.5">
            {ASSET_TYPE_FILTERS.map((f) => (
              <button
                key={f.label}
                type="button"
                onClick={() => setTypeFilter(f.type)}
                className={cn(
                  'rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors',
                  typeFilter === f.type
                    ? 'bg-accent text-white'
                    : 'bg-bg-tertiary text-fg-secondary hover:bg-bg-secondary',
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        )}

        {/* 标签筛选 */}
        {tagList && tagList.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {tagList.map((tag) => (
              <button
                key={tag.name}
                type="button"
                onClick={() => toggleTag(tag.name, tagSetter)}
                className={cn(
                  'rounded-full border px-2 py-0.5 text-[11px] transition-colors',
                  selectedTags.has(tag.name)
                    ? 'border-accent bg-accent/10 text-accent'
                    : 'border-border text-fg-muted hover:border-fg-muted hover:text-fg-secondary',
                )}
              >
                {tag.name}
                <span className="ml-1 opacity-60">{tag.count}</span>
              </button>
            ))}
          </div>
        )}

        {/* 素材网格 */}
        {tab === 'library' ? (
          <LibraryGrid
            assets={libAssets}
            loading={libLoading}
            hasFilters={!!category || libSelectedTags.size > 0 || !!libSearch.trim()}
            onSelect={onSelectCreationAsset}
          />
        ) : (
          <UploadsGrid
            assets={rawAssets}
            loading={rawLoading}
            hasFilters={!!typeFilter || rawSelectedTags.size > 0 || !!rawSearch.trim()}
            onSelect={onSelect}
          />
        )}
      </div>
    </Dialog>
  )
}

/** 素材库网格：创作资产（人物/场景/道具/关键帧） */
function LibraryGrid({
  assets,
  loading,
  hasFilters,
  onSelect,
}: {
  assets: CreationAsset[]
  loading: boolean
  hasFilters: boolean
  onSelect: (ca: CreationAsset) => void
}) {
  if (loading) return <div className="py-12 text-center text-sm text-fg-muted">加载中…</div>
  if (assets.length === 0)
    return (
      <div className="py-12 text-center text-sm text-fg-muted">
        {hasFilters ? '没有匹配的素材，试试调整筛选条件' : '素材库为空，请先在素材库页面创建资产'}
      </div>
    )
  return (
    <div className="grid max-h-80 grid-cols-4 gap-2 overflow-y-auto sm:grid-cols-5">
      {assets.map((ca) => (
        <button
          key={ca.id}
          type="button"
          className="group relative aspect-square overflow-hidden rounded-btn border border-border bg-bg-tertiary transition-all hover:ring-1 hover:ring-accent"
          onClick={() => onSelect(ca)}
        >
          {ca.image_thumbnail_url ? (
            <img
              src={ca.image_thumbnail_url}
              alt={ca.name}
              loading="lazy"
              className="h-full w-full object-cover transition-transform group-hover:scale-[1.05]"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <ImageIcon className="h-8 w-8 text-fg-muted" />
            </div>
          )}
          <span className="absolute bottom-1 left-1 rounded-btn bg-black/60 px-1 text-[10px] text-white">
            {CATEGORY_BADGES[ca.category]}
          </span>
          <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/80 to-transparent px-1 pb-0.5 pt-2 text-[10px] text-white">
            {ca.name}
          </span>
          {ca.tags.length > 0 && (
            <span className="absolute left-1 top-1 max-w-[calc(100%-2rem)] truncate rounded-btn bg-black/60 px-1 text-[10px] text-white">
              {ca.tags.join(', ')}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

/** 上传文件网格：原始素材（图片/视频/音频） */
function UploadsGrid({
  assets,
  loading,
  hasFilters,
  onSelect,
}: {
  assets: Asset[]
  loading: boolean
  hasFilters: boolean
  onSelect: (asset: Asset) => void
}) {
  if (loading) return <div className="py-12 text-center text-sm text-fg-muted">加载中…</div>
  if (assets.length === 0)
    return (
      <div className="py-12 text-center text-sm text-fg-muted">
        {hasFilters ? '没有匹配的素材，试试调整筛选条件' : '暂无上传文件'}
      </div>
    )
  return (
    <div className="grid max-h-80 grid-cols-4 gap-2 overflow-y-auto sm:grid-cols-5">
      {assets.map((asset) => (
        <button
          key={asset.id}
          type="button"
          className="group relative aspect-square overflow-hidden rounded-btn border border-border bg-bg-tertiary transition-all hover:ring-1 hover:ring-accent"
          onClick={() => onSelect(asset)}
        >
          {asset.type === 'audio' ? (
            <div className="flex h-full w-full items-center justify-center bg-bg-tertiary">
              <Music className="h-8 w-8 text-fg-muted" />
            </div>
          ) : (
            <img
              src={assetThumbnailUrl(asset.id)}
              alt=""
              loading="lazy"
              className="h-full w-full object-cover transition-transform group-hover:scale-[1.05]"
            />
          )}
          {asset.type === 'video' && (
            <span className="absolute bottom-1 right-1 rounded-btn bg-black/60 px-1 text-[10px] text-white">
              视频
            </span>
          )}
          {asset.type === 'audio' && (
            <span className="absolute bottom-1 right-1 rounded-btn bg-black/60 px-1 text-[10px] text-white">
              音频
            </span>
          )}
          {asset.tags.length > 0 && (
            <span className="absolute left-1 top-1 max-w-[calc(100%-2rem)] truncate rounded-btn bg-black/60 px-1 text-[10px] text-white">
              {asset.tags.join(', ')}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}
