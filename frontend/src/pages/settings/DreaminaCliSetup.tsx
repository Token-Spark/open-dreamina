import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, ExternalLink, Loader2, RefreshCw, Terminal } from 'lucide-react'
import {
  getDreaminaCliLoginStatus,
  getDreaminaCliStatus,
  installDreaminaCli,
  startDreaminaCliLogin,
  type DreaminaCliLoginStart,
} from '@/api/system'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { toast } from '@/stores/uiStore'
import { toApiError } from '@/api/client'

/**
 * 即梦 CLI 安装 / 登录引导。
 *
 * 分三步引导：① 检测/安装 CLI（worker 节点） → ② headless 登录
 * （展示 verification_uri + user_code，用户浏览器手动授权） → ③ 就绪。
 */
export function DreaminaCliSetup() {
  const qc = useQueryClient()

  // 登录授权材料（start 成功后保存，轮询期间展示）
  const [loginInfo, setLoginInfo] = useState<DreaminaCliLoginStart | null>(null)
  const [polling, setPolling] = useState(false)

  const statusQuery = useQuery({
    queryKey: ['dreamina-cli-status'],
    queryFn: getDreaminaCliStatus,
    // 安装中或等待登录授权时高频轮询
    refetchInterval: (query) => {
      const d = query.state.data
      if (d?.worker_offline) return false
      if (d?.installing || (!d?.installed && !d?.worker_offline)) return 3000
      if (polling && d?.installed && !d?.logged_in) return 3000
      return false
    },
  })
  const status = statusQuery.data

  const installMut = useMutation({
    mutationFn: installDreaminaCli,
    onSuccess: (r) => {
      toast(r.message, 'success')
      qc.invalidateQueries({ queryKey: ['dreamina-cli-status'] })
    },
    onError: (e) => toast(toApiError(e).message, 'error'),
  })

  const loginMut = useMutation({
    mutationFn: startDreaminaCliLogin,
    onSuccess: (r) => {
      if (r.ok) {
        setLoginInfo(r)
        setPolling(true)
      } else {
        toast(r.message ?? '发起登录失败', 'error')
        if (r.raw_output) console.warn('dreamina login output:', r.raw_output)
      }
    },
    onError: (e) => toast(toApiError(e).message, 'error'),
  })

  // 登录授权轮询
  const loginStatusQuery = useQuery({
    queryKey: ['dreamina-cli-login-status'],
    queryFn: getDreaminaCliLoginStatus,
    enabled: polling,
    refetchInterval: polling ? 3000 : false,
  })

  useEffect(() => {
    const r = loginStatusQuery.data
    if (!r) return
    if (r.state === 'success') {
      setPolling(false)
      setLoginInfo(null)
      toast('即梦 CLI 登录成功', 'success')
      qc.invalidateQueries({ queryKey: ['dreamina-cli-status'] })
    } else if (r.state === 'no_session') {
      setPolling(false)
    }
  }, [loginStatusQuery.data, qc])

  // worker 不在线
  if (status?.worker_offline) {
    return (
      <SetupShell>
        <p className="text-xs text-error">{status.message}</p>
      </SetupShell>
    )
  }

  // 加载中
  if (statusQuery.isLoading || !status) {
    return (
      <SetupShell>
        <p className="flex items-center gap-2 text-xs text-fg-muted">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          正在检测 worker 节点上的即梦 CLI…
        </p>
      </SetupShell>
    )
  }

  // 已登录：就绪态
  if (status.installed && status.logged_in) {
    return (
      <SetupShell>
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-success" />
          <span className="text-xs text-fg-primary">
            即梦 CLI 已就绪{status.version ? `（${status.version}）` : ''}，登录态有效
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto h-6 px-2 text-[11px]"
            onClick={() => {
              setLoginInfo(null)
              loginMut.mutate()
            }}
            disabled={loginMut.isPending}
          >
            <RefreshCw className="h-3 w-3" />
            切换账号
          </Button>
        </div>
        {loginMut.isPending && (
          <p className="text-xs text-fg-muted">正在发起登录…</p>
        )}
        {loginInfo && <LoginAuthPanel info={loginInfo} waitingHint={loginStatusQuery.data?.message} />}
      </SetupShell>
    )
  }

  // 安装中
  if (status.installing) {
    return (
      <SetupShell>
        <p className="flex items-center gap-2 text-xs text-fg-secondary">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          正在 worker 节点安装即梦 CLI（首次安装需下载二进制，约 1-2 分钟）…
        </p>
      </SetupShell>
    )
  }

  // 未安装
  if (!status.installed) {
    return (
      <SetupShell>
        <div className="flex items-start gap-2">
          <Terminal className="mt-0.5 h-4 w-4 shrink-0 text-fg-muted" />
          <div className="flex-1 space-y-2">
            <p className="text-xs text-fg-secondary">
              {status.message}。点击下方按钮自动在 celery-worker 节点安装（官方脚本
              curl -fsSL https://jimeng.jianying.com/cli | bash）。
            </p>
            <Button size="sm" onClick={() => installMut.mutate()} disabled={installMut.isPending}>
              {installMut.isPending ? '提交中…' : '一键安装即梦 CLI'}
            </Button>
          </div>
        </div>
      </SetupShell>
    )
  }

  // 已安装未登录：登录引导
  return (
    <SetupShell>
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Badge variant="outline">已安装{status.version ? ` · ${status.version}` : ''}</Badge>
          <Badge>未登录</Badge>
          {!loginMut.isPending && !loginInfo && (
            <Button size="sm" className="ml-auto" onClick={() => loginMut.mutate()}>
              开始登录
            </Button>
          )}
        </div>
        {loginMut.isPending && (
          <p className="flex items-center gap-2 text-xs text-fg-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            正在发起 dreamina login…
          </p>
        )}
        {!loginInfo && !loginMut.isPending && (
          <p className="text-xs text-fg-muted">
            {status.message}。点击「开始登录」获取授权链接，在浏览器中完成授权。
          </p>
        )}
        {loginInfo && <LoginAuthPanel info={loginInfo} waitingHint={loginStatusQuery.data?.message} />}
      </div>
    </SetupShell>
  )
}

/** 展示 headless 登录的授权材料，并提供复制 / 打开链接。 */
function LoginAuthPanel({
  info,
  waitingHint,
}: {
  info: DreaminaCliLoginStart
  waitingHint?: string
}) {
  function copy(text: string, label: string) {
    navigator.clipboard.writeText(text).then(
      () => toast(`${label}已复制`, 'success'),
      () => toast('复制失败，请手动选择复制', 'error'),
    )
  }

  return (
    <div className="space-y-2 rounded-lg border border-border bg-bg-secondary p-3">
      <p className="text-xs font-medium text-fg-primary">请在浏览器完成授权：</p>
      <ol className="list-inside list-decimal space-y-1 text-xs text-fg-secondary">
        <li>
          打开授权链接：
          {info.verification_uri ? (
            <span className="ml-1 inline-flex items-center gap-1">
              <a
                href={info.verification_uri}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-0.5 text-accent underline-offset-2 hover:underline"
              >
                打开授权页 <ExternalLink className="h-3 w-3" />
              </a>
              <button
                className="text-fg-muted hover:text-fg-primary"
                onClick={() => copy(info.verification_uri!, '授权链接')}
              >
                复制
              </button>
            </span>
          ) : (
            <span className="text-error">（未能解析出链接，见下方原始输出）</span>
          )}
        </li>
        {info.user_code && (
          <li>
            在页面输入验证码：
            <code className="mx-1 rounded bg-bg-tertiary px-1.5 py-0.5 font-mono text-[11px] text-fg-primary">
              {info.user_code}
            </code>
            <button
              className="text-fg-muted hover:text-fg-primary"
              onClick={() => copy(info.user_code!, '验证码')}
            >
              复制
            </button>
          </li>
        )}
        <li>点击「授权」，本页面将自动检测登录结果。</li>
      </ol>
      <p className="flex items-center gap-1.5 text-[11px] text-fg-muted">
        <Loader2 className="h-3 w-3 animate-spin" />
        {waitingHint ?? '等待浏览器完成授权…'}
      </p>
      <p className="text-[11px] text-fg-secondary">
        提示：若授权页显示「非法应用」，请先在即梦网页端登录后重试；
        首次使用视频模型前，还需在即梦网页端完成一次视频生成（合规要求）。
      </p>
      {info.raw_output && !info.verification_uri && (
        <pre className="max-h-32 overflow-auto rounded bg-bg-tertiary p-2 text-[10px] text-fg-secondary">
          {info.raw_output}
        </pre>
      )}
    </div>
  )
}

function SetupShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-border bg-bg-secondary/50 p-3">
      <p className="mb-2 text-xs font-medium text-fg-primary">即梦 CLI 环境引导</p>
      {children}
    </div>
  )
}
