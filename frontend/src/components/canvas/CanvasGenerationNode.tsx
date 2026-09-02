// Copyright 2026 Open Dreamina Contributors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0

import { useEffect, useMemo, useState } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { AlertCircle, CheckCircle2, Film, Image as ImageIcon, Loader2, Maximize2, RefreshCw, X } from 'lucide-react'
import { GenerationInputBar, type ReferenceAsset, effectiveFrameMode, isSeedanceProvider, normalizeFrameMode } from '@/components/GenerationInputBar'
import { Progress } from '@/components/ui/Progress'
import { createTask, getTask, retryTask, type TaskStatus } from '@/api/tasks'
import { useTaskSSE } from '@/hooks/useTaskSSE'
import { useProviders } from '@/hooks/useProviders'
import { useAssetAudit } from '@/hooks/useAssetAudit'
import { defaultParamsForType, deriveTaskType, modelsForCategory, type ContentMode } from '@/lib/generation'
import { useCanvasStore } from '@/stores/canvasStore'
import { useTaskStore } from '@/stores/taskStore'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { cn } from '@/lib/utils'
import { deriveEdgeRefAssets, mergeRefAssets } from '@/lib/canvasRefAssets'
import { ImageLightbox, type LightboxItem } from '@/components/ImageLightbox'

interface GenerationNodeData extends Record<string, unknown> {
  nodeType?: string
  prompt?: string
  negative_prompt?: string
  provider?: string
  model_id?: string
  params?: Record<string, number | string>
  ref_assets?: ReferenceAsset[]
  task_id?: string
  status?: TaskStatus
  progress?: number
  error?: string | null
  result_url?: string | null
  result_urls?: string[]
  selected_result?: number
}

const ACTIVE_STATUSES: TaskStatus[] = ['pending', 'queued', 'running']

export function CanvasGenerationNode({ id, data, selected }: NodeProps) {
  const nodeType = data.nodeType === 'video_gen' ? 'video_gen' : 'image_gen'
  const mode: ContentMode = nodeType === 'video_gen' ? 'video' : 'image'
  const storedData = useCanvasStore((state) => state.nodes.find((node) => node.id === id)?.data)
  const edges = useCanvasStore((state) => state.edges)
  const allNodes = useCanvasStore((state) => state.nodes)
  const canvasId = useCanvasStore((state) => state.canvasId)
  const nodeData = { ...data, ...storedData } as GenerationNodeData
  const updateNodeData = useCanvasStore((state) => state.updateNodeData)
  const addActive = useTaskStore((state) => state.addActive)
  const { data: providers } = useProviders()
  const [submitting, setSubmitting] = useState(false)
  const [lightboxItem, setLightboxItem] = useState<LightboxItem | null>(null)

  const prompt = nodeData.prompt ?? ''
  const providerSlug = nodeData.provider ?? ''
  const modelId = nodeData.model_id ?? ''
  const params = nodeData.params ?? defaultParamsForType(mode === 'image' ? 'text2img' : 'text2video')
  // 合并：连线推导的参考素材 + 手动添加的参考素材（按 assetId 去重）
  const manualRefAssets = nodeData.ref_assets ?? []
  const edgeRefAssets = useMemo(
    () => deriveEdgeRefAssets(edges, allNodes, id),
    [edges, allNodes, id],
  )
  const mergedRefAssets = useMemo(
    () => mergeRefAssets(edgeRefAssets, manualRefAssets),
    [edgeRefAssets, manualRefAssets],
  )

  // Spark Hub Seedance：连线推导的参考素材未经上传流程，无审核状态。
  // 此 hook 自动为其提审并轮询，同时将审核状态合并到 refAssets 上用于渲染徽标。
  const { ensureAudited, augmentRefAssets, checkAuditGate } = useAssetAudit(providerSlug)
  useEffect(() => {
    ensureAudited(mergedRefAssets)
  }, [mergedRefAssets, ensureAudited])
  const refAssets = augmentRefAssets(mergedRefAssets)

  const taskId = nodeData.task_id ?? null
  const persistedStatus = nodeData.status
  const isActive = persistedStatus ? ACTIVE_STATUSES.includes(persistedStatus) : false
  const live = useTaskSSE(isActive ? taskId : null)
  const status = live.status ?? persistedStatus
  const progress = live.status ? live.progress : (nodeData.progress ?? 0)
  const resultUrls = live.data.resultUrls.length
    ? live.data.resultUrls
    : nodeData.result_urls?.length
      ? nodeData.result_urls
      : nodeData.result_url
        ? [nodeData.result_url]
        : []
  const selectedResult = Math.min(nodeData.selected_result ?? 0, Math.max(0, resultUrls.length - 1))

  const availableProvider = useMemo(() => {
    const active = (providers ?? []).filter((provider) => provider.is_active)
    return active.find((provider) => provider.slug === providerSlug && modelsForCategory(provider, mode).length > 0)
      ?? active.find((provider) => modelsForCategory(provider, mode).length > 0)
  }, [providers, providerSlug, mode])

  useEffect(() => {
    if (!availableProvider) return
    const models = modelsForCategory(availableProvider, mode)
    const nextModel = models.find((model) => model.id === modelId) ?? models[0]
    if (availableProvider.slug !== providerSlug || nextModel?.id !== modelId) {
      updateNodeData(id, { provider: availableProvider.slug, model_id: nextModel?.id ?? '' })
    }
  }, [availableProvider, id, mode, modelId, providerSlug, updateNodeData])

  useEffect(() => {
    if (!live.status) return
    updateNodeData(id, {
      status: live.status,
      progress: live.progress,
      error: live.error,
      result_url: live.data.resultUrl,
      result_urls: live.data.resultUrls,
    })
  }, [id, live.status, live.progress, live.error, live.data.resultUrl, live.data.resultUrls, updateNodeData])

  async function generate() {
    if (!prompt.trim()) return toast('请输入提示词', 'error')
    if (!providerSlug || !modelId) return toast('请选择可用模型', 'error')
    // Spark Hub Seedance：参考素材须全部审核通过才能生成
    if (!checkAuditGate(refAssets)) return

    setSubmitting(true)
    try {
      const assetIds = refAssets.map((asset) => asset.assetId)
      const hasRef = assetIds.length > 0
      const taskType = deriveTaskType(mode, hasRef)
      // Seedance 视频需将合并模式 auto 解析为后端接受的 text / reference，
      // 否则后端默认 frame_mode=first 只取首张参考图，多图参考被丢弃。
      const sendParams = mode === 'video' && isSeedanceProvider(providerSlug)
        ? { ...params, frame_mode: effectiveFrameMode(normalizeFrameMode(params.frame_mode), refAssets.some((a) => (a.kind ?? 'image') === 'image')) }
        : params
      const { task_id } = await createTask({
        type: taskType,
        provider: providerSlug,
        model_id: modelId,
        prompt,
        params: sendParams,
        input_asset_id: assetIds[0] ?? undefined,
        input_asset_ids: hasRef ? assetIds : undefined,
        canvas_id: canvasId ?? undefined,
      })
      const task = await getTask(task_id)
      addActive(task)
      updateNodeData(id, {
        task_id,
        status: task.status,
        progress: task.progress,
        error: null,
        result_url: null,
        result_urls: [],
        selected_result: 0,
      })
    } catch (error) {
      toast(toApiError(error).message, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  async function retry() {
    if (!taskId) return generate()
    try {
      const { task_id } = await retryTask(taskId)
      const task = await getTask(task_id)
      addActive(task)
      updateNodeData(id, { task_id, status: task.status, progress: 0, error: null })
    } catch (error) {
      toast(toApiError(error).message, 'error')
    }
  }

  const Icon = mode === 'image' ? ImageIcon : Film
  const label = mode === 'image' ? '图片生成' : '视频生成'

  return (
    <div
      className={cn(
        'relative w-[430px] rounded-card border bg-bg-secondary shadow-lg transition-shadow',
        mode === 'image' ? 'border-orange-500/40' : 'border-pink-500/40',
        selected && 'ring-2 ring-accent/50',
      )}
    >
      <Handle id="ref" type="target" position={Position.Left} className="h-3 w-3 border-2 border-bg-secondary bg-fg-muted" />
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex items-center gap-2 text-sm font-medium text-fg-primary">
          <Icon className="h-4 w-4 text-fg-secondary" />
          {label}
        </div>
        <NodeStatus status={status} />
      </div>

      {resultUrls.length > 0 && status === 'completed' && (
        <div className="border-b border-border bg-bg-primary/40 p-3">
          {mode === 'image' ? (
            <button
              type="button"
              className="nodrag group relative block h-56 w-full rounded-btn"
              onClick={() => setLightboxItem({ url: resultUrls[selectedResult], type: 'image', title: label })}
            >
              <img src={resultUrls[selectedResult]} alt="生成结果" className="h-56 w-full rounded-btn object-contain" />
              <span className="absolute inset-0 flex items-center justify-center rounded-btn bg-black/0 opacity-0 transition-all group-hover:bg-black/30 group-hover:opacity-100">
                <Maximize2 className="h-6 w-6 text-white" />
              </span>
            </button>
          ) : (
            <div className="relative">
              <video src={resultUrls[selectedResult]} controls preload="metadata" className="h-56 w-full rounded-btn bg-black object-contain" />
              <button
                type="button"
                className="nodrag absolute right-1.5 top-1.5 flex h-7 w-7 items-center justify-center rounded-btn bg-black/60 text-white transition-colors hover:bg-black/80"
                onClick={() => setLightboxItem({ url: resultUrls[selectedResult], type: 'video', title: label })}
                aria-label="放大预览"
              >
                <Maximize2 className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          {resultUrls.length > 1 && (
            <div className="nodrag mt-2 flex gap-2 overflow-x-auto">
              {resultUrls.map((url, index) => (
                <button
                  key={url}
                  type="button"
                  onClick={() => updateNodeData(id, { selected_result: index, result_url: url })}
                  className={cn('h-12 w-16 shrink-0 overflow-hidden rounded-btn border', selectedResult === index ? 'border-accent' : 'border-border')}
                  title={`选择候选 ${index + 1}`}
                >
                  {mode === 'image' ? <img src={url} alt="" className="h-full w-full object-cover" /> : <Film className="m-auto h-4 w-4" />}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {isActive && (
        <div className="space-y-2 border-b border-border px-3 py-3">
          <div className="flex items-center justify-between text-xs text-fg-muted">
            <span>{status === 'running' ? '生成中' : '等待执行'}</span>
            <span>{progress}%</span>
          </div>
          <Progress value={progress} glow />
        </div>
      )}

      {status === 'failed' && (
        <div className="mx-3 mt-3 flex items-start gap-2 rounded-btn border border-error/30 bg-error/5 p-2 text-xs text-fg-secondary">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-error" />
          <span className="min-w-0 flex-1 break-words">{nodeData.error || '生成失败'}</span>
          <button type="button" onClick={retry} title="重新生成"><RefreshCw className="h-3.5 w-3.5" /></button>
        </div>
      )}

      <div className="nodrag nowheel">
        <GenerationInputBar
          variant="compact"
          mode={mode}
          onModeChange={() => {}}
          prompt={prompt}
          onPromptChange={(value) => updateNodeData(id, { prompt: value })}
          providerSlug={providerSlug}
          modelId={modelId}
          onProviderChange={(value) => updateNodeData(id, { provider: value, model_id: '' })}
          onModelChange={(value) => updateNodeData(id, { model_id: value })}
          params={params}
          onParamsChange={(value) => updateNodeData(id, { params: value })}
          refAssets={refAssets}
          onRefAssetsChange={(value) => {
            const edgeIds = new Set(edgeRefAssets.map((a) => a.assetId))
            updateNodeData(id, { ref_assets: value.filter((a) => !edgeIds.has(a.assetId)) })
          }}
          onGenerate={generate}
          submitting={submitting || isActive}
          atConcurrencyLimit={false}
        />
      </div>
      <Handle id="out" type="source" position={Position.Right} className="h-3 w-3 border-2 border-bg-secondary bg-accent" />

      <ImageLightbox
        item={lightboxItem}
        open={!!lightboxItem}
        onClose={() => setLightboxItem(null)}
      />
    </div>
  )
}

function NodeStatus({ status }: { status?: TaskStatus }) {
  if (status === 'running' || status === 'pending' || status === 'queued') return <Loader2 className="h-4 w-4 animate-spin text-accent" />
  if (status === 'completed') return <CheckCircle2 className="h-4 w-4 text-success" />
  if (status === 'failed') return <AlertCircle className="h-4 w-4 text-error" />
  if (status === 'cancelled') return <X className="h-4 w-4 text-fg-muted" />
  return null
}
