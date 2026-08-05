import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { createTask, getTask, retryTask } from '@/api/tasks'
import { assetFileUrl } from '@/api/assets'
import type { Template } from '@/api/templates'
import { listTemplates } from '@/api/templates'
import { useProviders } from '@/hooks/useProviders'
import { useTaskStore } from '@/stores/taskStore'
import { useConversationStore, useCurrentTopic, type GenMessage } from '@/stores/conversationStore'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'
import { TopicPanel } from '@/components/TopicPanel'
import { GenMessageCard } from '@/components/GenMessageCard'
import { GenerationInputBar, type ReferenceAsset } from '@/components/GenerationInputBar'
import { ImageLightbox } from '@/components/ImageLightbox'
import {
  defaultParamsForType,
  deriveTaskType,
  modeOfTaskType,
  modelsForCategory,
  modelSupportsType,
  type ContentMode,
} from '@/lib/generation'

export function CreatePage() {
  const [mode, setMode] = useState<ContentMode>('image')
  const [prompt, setPrompt] = useState('')
  const [negativePrompt, setNegativePrompt] = useState('')
  const [providerSlug, setProviderSlug] = useState('')
  const [modelId, setModelId] = useState('')
  const [params, setParams] = useState<Record<string, number | string>>(
    defaultParamsForType('text2img'),
  )
  const [refAssets, setRefAssets] = useState<ReferenceAsset[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [lightboxOpen, setLightboxOpen] = useState(false)
  const [lightboxMessage, setLightboxMessage] = useState<
    { url: string; type: 'image' | 'video'; meta: Record<string, unknown> } | null
  >(null)

  const { data: providers } = useProviders()
  const { data: templates } = useQuery({
    queryKey: ['templates'],
    queryFn: listTemplates,
  })

  const currentTopic = useCurrentTopic()
  const currentTopicId = useConversationStore((s) => s.currentTopicId)
  const messages = useConversationStore((s) => s.messages)
  const initConversations = useConversationStore((s) => s.init)
  const setCurrentTopic = useConversationStore((s) => s.setCurrentTopic)
  const addTopic = useConversationStore((s) => s.addTopic)
  const addMessage = useConversationStore((s) => s.addMessage)
  const updateMessage = useConversationStore((s) => s.updateMessage)
  const activeTasks = useTaskStore((s) => s.active)
  const addActive = useTaskStore((s) => s.addActive)

  const location = useLocation()
  const appliedTemplateRef = useRef<string | null>(null)
  const feedRef = useRef<HTMLDivElement>(null)
  // "重新编辑"时复用原任务参数，跳过 mode 变化触发的默认参数重置
  const editParamsRef = useRef<Record<string, number | string> | null>(null)

  // 需求4：启动时从后端加载持久化对话
  useEffect(() => {
    initConversations()
  }, [initConversations])

  // Apply a template passed via router state from TemplatesPage ("使用" action).
  useEffect(() => {
    const tpl = (location.state as { template?: Template } | null)?.template
    if (tpl && appliedTemplateRef.current !== tpl.id) {
      appliedTemplateRef.current = tpl.id
      setMode(tpl.category === 'image' ? 'image' : 'video')
      setPrompt(tpl.prompt_text)
      setNegativePrompt(tpl.negative_prompt ?? '')
      if (tpl.params && Object.keys(tpl.params).length) {
        setParams(tpl.params as Record<string, number | string>)
      }
    }
  }, [location.state])

  // Seed a default provider once providers are available.
  useEffect(() => {
    if (providerSlug || !providers) return
    const first = providers.find((p) => p.is_active) ?? providers[0]
    if (first) setProviderSlug(first.slug)
  }, [providers, providerSlug])

  // 内容模式变化时重置参数为该模式默认（无参考图）任务类型
  // "重新编辑"时复用原任务参数，跳过默认重置
  useEffect(() => {
    if (editParamsRef.current) {
      setParams(editParamsRef.current)
      editParamsRef.current = null
      return
    }
    setParams(defaultParamsForType(deriveTaskType(mode, false)))
  }, [mode])

  // 需求2：按内容模式筛选模型；参考图变化时校验当前模型是否仍支持派生类型
  useEffect(() => {
    const provider = providers?.find((p) => p.slug === providerSlug && p.is_active)
    const available = modelsForCategory(provider, mode)
    if (available.length === 0) {
      setModelId('')
      return
    }
    const derivedType = deriveTaskType(mode, refAssets.length > 0)
    const current = available.find((m) => m.id === modelId)
    if (!current || !modelSupportsType(current, derivedType)) {
      const fallback =
        available.find((m) => modelSupportsType(m, derivedType)) ?? available[0]
      setModelId(fallback.id)
    }
  }, [mode, providerSlug, providers, refAssets, modelId])

  // Auto-scroll to bottom when new messages or progress updates happen.
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight
    }
  }, [messages.length, activeTasks])

  const busy = useMemo(() => {
    return messages.some(
      (m) => m.status === 'pending' || m.status === 'queued' || m.status === 'running',
    )
  }, [messages])

  function handleModeChange(next: ContentMode) {
    setMode(next)
  }

  async function submitGeneration(
    requestPrompt: string,
    requestNegative: string,
    requestMode: ContentMode,
    requestParams: Record<string, number | string>,
    requestRefAssets: ReferenceAsset[],
    requestModelId: string,
  ) {
    if (!providerSlug) return toast('请先在设置中启用一个服务提供商', 'error')
    if (!requestPrompt.trim()) return toast('请输入提示词', 'error')
    const hasRef = requestRefAssets.length > 0
    const requestType = deriveTaskType(requestMode, hasRef)
    if (!hasRef && (requestType === 'img2img' || requestType === 'img2video')) {
      return toast('请上传参考图', 'error')
    }
    if (!currentTopicId) return toast('对话未就绪，请稍候', 'error')

    const requestRefAssetIds = requestRefAssets.map((a) => a.assetId)

    setSubmitting(true)
    try {
      const { task_id } = await createTask({
        type: requestType,
        provider: providerSlug,
        model_id: requestModelId || undefined,
        prompt: requestPrompt,
        negative_prompt: requestNegative || undefined,
        params: requestParams as Record<string, unknown>,
        input_asset_id: requestRefAssetIds[0] ?? undefined,
        input_asset_ids: hasRef ? requestRefAssetIds : undefined,
        conversation_id: currentTopicId,
      })
      const task = await getTask(task_id)
      addActive(task)

      addMessage(currentTopicId, {
        id: task_id,
        prompt: requestPrompt,
        negativePrompt: requestNegative,
        type: requestType,
        status: task.status,
        progress: task.progress,
        error: task.error_msg,
        message: null,
        resultUrl: task.result_url,
        thumbnailUrl: task.thumbnail_url,
        params: requestParams as Record<string, unknown>,
        provider: providerSlug,
        modelId: requestModelId || null,
        inputAssetIds: requestRefAssetIds,
        inputAssetUrls: requestRefAssets.map((a) => a.previewUrl),
        createdAt: Date.now(),
      })
    } catch (e) {
      toast(toApiError(e).message, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  function handleGenerate() {
    submitGeneration(prompt, negativePrompt, mode, params, refAssets, modelId)
  }

  // 重试：后端复用同一 task_id 与 conversation_id，本地更新消息状态即可
  async function handleRetry(message: GenMessage) {
    if (!currentTopicId) return
    try {
      await retryTask(message.id)
      const task = await getTask(message.id)
      addActive(task)
      updateMessage(currentTopicId, message.id, {
        status: task.status,
        progress: task.progress,
        error: task.error_msg,
        message: null,
        resultUrl: task.result_url,
        thumbnailUrl: task.thumbnail_url,
      })
    } catch (e) {
      toast(toApiError(e).message, 'error')
    }
  }

  // 重新编辑：将该消息的输入回填到生成对话框，复用提示词/负向提示/参数/模型
  function handleEdit(message: GenMessage) {
    const nextMode = modeOfTaskType(message.type)
    const nextParams = message.params as Record<string, number | string>
    // mode 改变会触发默认参数重置，用 ref 暂存待复用的参数
    if (nextMode !== mode) {
      editParamsRef.current = nextParams
      setMode(nextMode)
    } else {
      setParams(nextParams)
    }
    setPrompt(message.prompt)
    setNegativePrompt(message.negativePrompt)
    if (message.provider) setProviderSlug(message.provider)
    if (message.modelId) setModelId(message.modelId)
    // 复用参考图：回填 assetId 与预览地址列表
    setRefAssets(
      message.inputAssetIds.map((assetId, i) => ({
        assetId,
        previewUrl: message.inputAssetUrls[i] ?? assetFileUrl(assetId),
      })),
    )
  }

  function applyTemplate(t: {
    prompt_text: string
    negative_prompt: string | null
    params: Record<string, unknown>
    category: 'image' | 'video'
  }) {
    setMode(t.category === 'image' ? 'image' : 'video')
    setPrompt(t.prompt_text)
    setNegativePrompt(t.negative_prompt ?? '')
    if (t.params && Object.keys(t.params).length) {
      setParams(t.params as Record<string, number | string>)
    }
    toast('已应用模板', 'success')
  }

  function openLightbox(message: GenMessage) {
    if (!message.resultUrl) return
    setLightboxMessage({
      url: message.resultUrl,
      type: message.type === 'text2img' || message.type === 'img2img' ? 'image' : 'video',
      meta: message.params,
    })
    setLightboxOpen(true)
  }

  async function startNewTopic() {
    const id = await addTopic()
    setCurrentTopic(id)
    setPrompt('')
    setNegativePrompt('')
    setRefAssets([])
  }

  if (!currentTopic) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-fg-muted">
        正在加载对话…
      </div>
    )
  }

  return (
    <div className="flex h-full">
      <TopicPanel />

      <div className="flex flex-1 flex-col">
        {/* Header */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
          <div>
            <h1 className="text-sm font-medium text-fg-primary">{currentTopic.title}</h1>
            <p className="text-xs text-fg-muted">
              {currentTopic.message_count} 条生成记录
            </p>
          </div>
          <div className="flex items-center gap-3">
            {templates && templates.length > 0 && (
              <div className="hidden items-center gap-2 md:flex">
                <span className="text-xs text-fg-muted">模板：</span>
                {templates.slice(0, 4).map((t) => (
                  <button
                    key={t.id}
                    onClick={() => applyTemplate(t)}
                    className="rounded-full border border-border bg-bg-secondary px-3 py-1 text-xs text-fg-secondary transition-colors hover:border-fg-muted hover:text-fg-primary"
                  >
                    {t.name}
                  </button>
                ))}
              </div>
            )}
            <button
              type="button"
              onClick={startNewTopic}
              className="rounded-btn border border-border bg-bg-secondary px-3 py-1.5 text-xs text-fg-secondary transition-colors hover:bg-bg-tertiary hover:text-fg-primary"
            >
              新对话
            </button>
          </div>
        </header>

        {/* Conversation feed */}
        <div ref={feedRef} className="flex-1 overflow-auto p-6 scrollbar-thin">
          <div className="mx-auto max-w-3xl space-y-6">
            {messages.length === 0 && <EmptyFeed onStart={startNewTopic} />}
            {messages.map((message) => (
              <GenMessageCard
                key={message.id}
                topicId={currentTopic.id}
                message={message}
                onRetry={handleRetry}
                onOpenLightbox={openLightbox}
                onEdit={handleEdit}
              />
            ))}
          </div>
        </div>

        {/* Bottom generation input */}
        <GenerationInputBar
          mode={mode}
          onModeChange={handleModeChange}
          prompt={prompt}
          negativePrompt={negativePrompt}
          onPromptChange={setPrompt}
          onNegativeChange={setNegativePrompt}
          providerSlug={providerSlug}
          modelId={modelId}
          onProviderChange={setProviderSlug}
          onModelChange={setModelId}
          params={params}
          onParamsChange={setParams}
          refAssets={refAssets}
          onRefAssetsChange={setRefAssets}
          onGenerate={handleGenerate}
          submitting={submitting}
          busy={busy}
        />
      </div>

      <ImageLightbox
        open={lightboxOpen}
        onClose={() => setLightboxOpen(false)}
        item={
          lightboxMessage
            ? {
                url: lightboxMessage.url,
                type: lightboxMessage.type,
                title: '生成结果',
                meta: lightboxMessage.meta,
              }
            : null
        }
      />
    </div>
  )
}

function EmptyFeed({ onStart }: { onStart: () => void }) {
  return (
    <div className="flex h-full min-h-[40vh] flex-col items-center justify-center rounded-card border border-dashed border-border text-center">
      <p className="text-sm text-fg-secondary">从下方输入提示词开始创作</p>
      <p className="mt-1 text-xs text-fg-muted">对话与生成记录会自动持久保存</p>
      <button
        type="button"
        onClick={onStart}
        className="mt-4 rounded-btn bg-bg-tertiary px-4 py-2 text-xs text-fg-secondary transition-colors hover:text-fg-primary"
      >
        开启新对话
      </button>
    </div>
  )
}
