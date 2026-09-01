// Copyright 2026 Open Dreamina Contributors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0

import { useRef, useState, type MouseEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Clapperboard, Eye, Film, Image as ImageIcon, Loader2, Pause, Play, StickyNote, Type as TypeIcon, Upload, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useCanvasStore } from '@/stores/canvasStore'
import { useAssets } from '@/hooks/useAssets'
import { useUIStore } from '@/stores/uiStore'
import { assetFileUrl, assetThumbnailUrl, uploadAsset, type Asset } from '@/api/assets'
import { getSystemSettings } from '@/api/system'
import { Dialog } from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { DirectorDeskDialog } from '@/components/DirectorDeskDialog'
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
        <textarea
          className="nodrag nowheel mt-2 w-full resize-none rounded-btn border border-border bg-bg-tertiary px-2 py-1 text-xs text-fg-primary placeholder:text-fg-muted focus:outline-none"
          rows={3}
          placeholder={nodeType === 'prompt' ? '输入提示词...' : '备注...'}
          value={(nodeData.text as string) ?? ''}
          onChange={(event) => updateNodeData(id, { text: event.target.value })}
        />
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

interface AssetPickerDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (asset: Asset) => void
}

function AssetPickerDialog({ open, onOpenChange, onSelect }: AssetPickerDialogProps) {
  const { data, isLoading } = useAssets({ page_size: 50 })
  const assets = data?.items ?? []
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

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

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="选择素材"
      description="从素材库选择或上传新文件"
      className="max-w-2xl"
    >
      <div className="space-y-3">
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
            上传新素材
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
        </div>

        {isLoading ? (
          <div className="py-12 text-center text-sm text-fg-muted">加载中…</div>
        ) : assets.length === 0 ? (
          <div className="py-12 text-center text-sm text-fg-muted">
            素材库为空，请先上传素材
          </div>
        ) : (
          <div className="grid max-h-80 grid-cols-4 gap-2 overflow-y-auto sm:grid-cols-5">
            {assets.map((asset) => (
              <button
                key={asset.id}
                type="button"
                className="group relative aspect-square overflow-hidden rounded-btn border border-border bg-bg-tertiary transition-all hover:ring-1 hover:ring-accent"
                onClick={() => onSelect(asset)}
              >
                {asset.type === 'audio' ? (
                  <AudioPreview
                    src={assetFileUrl(asset.id)}
                    className="h-full w-full"
                  />
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
              </button>
            ))}
          </div>
        )}
      </div>
    </Dialog>
  )
}
