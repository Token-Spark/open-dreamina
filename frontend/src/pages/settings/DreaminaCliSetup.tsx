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

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, ExternalLink, Loader2, RefreshCw, Terminal } from 'lucide-react'
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
  // J-1：轮询收到 failed / 会话丢失时停止转圈，改显错误与重试入口
  const [loginFailed, setLoginFailed] = useState<string | null>(null)
  // J-3：发起登录失败的后端诊断（执行命令与 CLI 原始输出），卡内展示而非只进 console
  const [loginStartError, setLoginStartError] = useState<{
    message: string
    command?: string
    raw_output?: string
  } | null>(null)

  /** 发起一次登录：先清掉上一轮的失败/诊断展示，避免旧内容残留。 */
  function startLogin() {
    setLoginFailed(null)
    setLoginStartError(null)
    setLoginInfo(null)
    loginMut.mutate()
  }

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
      // CLI 已有有效凭据时 auth login 直接复用，不会再返回授权材料
      if (r.ok && r.already_logged_in) {
        toast(r.message ?? 'CLI 已有有效登录态，无需重新授权', 'success')
        qc.invalidateQueries({ queryKey: ['dreamina-cli-status'] })
        return
      }
      if (r.ok) {
        setLoginInfo(r)
        setPolling(true)
      } else {
        toast(r.message ?? '发起登录失败', 'error')
        // J-3：诊断信息在卡内可展开查看（命令 + CLI 原始输出），不再只写 console
        setLoginStartError({
          message: r.message ?? '发起登录失败',
          command: r.command,
          raw_output: r.raw_output,
        })
      }
    },
    onError: (e) => {
      const message = toApiError(e).message
      toast(message, 'error')
      setLoginStartError({ message })
    },
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
      setLoginFailed(null)
      toast('即梦 CLI 登录成功', 'success')
      qc.invalidateQueries({ queryKey: ['dreamina-cli-status'] })
    } else if (r.state === 'failed') {
      // J-1：授权失败/验证码过期时停止轮询，显式报错并给重试入口，不再无限转圈
      setPolling(false)
      setLoginInfo(null)
      setLoginFailed(r.message || '登录授权失败，请重新发起登录')
    } else if (r.state === 'no_session') {
      // 会话不存在或已过期：同样收起等待态，提示重新发起（否则授权面板会一直转圈）
      setPolling(false)
      setLoginInfo(null)
      setLoginFailed(r.message || '登录会话不存在或已过期，请重新发起登录')
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

  // 已登录：就绪态（J-2：就绪后常驻展示账号/VIP/版本，不再隐藏）
  if (status.installed && status.logged_in) {
    // 后端 get_status 附带 auth account 的账号信息（userId / isVip / vipLevel）
    const account = status.account_info ?? null
    const userId =
      account != null && (typeof account.userId === 'string' || typeof account.userId === 'number')
        ? String(account.userId)
        : null
    const isVip = account?.isVip === true
    const vipLevel = account?.vipLevel != null ? String(account.vipLevel) : null
    return (
      <SetupShell>
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
            <span className="text-xs text-fg-primary">
              即梦 CLI 已就绪{status.version ? `（${status.version}）` : ''}，登录态有效
            </span>
            <span className="ml-auto flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-[11px]"
                onClick={() => qc.invalidateQueries({ queryKey: ['dreamina-cli-status'] })}
                disabled={statusQuery.isFetching}
                aria-label="重新检测即梦 CLI 状态"
              >
                <RefreshCw className="h-3 w-3" />
                重新检测
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-[11px]"
                onClick={startLogin}
                disabled={loginMut.isPending}
              >
                <RefreshCw className="h-3 w-3" />
                切换账号
              </Button>
            </span>
          </div>
          {account && (
            <p className="flex flex-wrap items-center gap-1.5 text-xs text-fg-secondary">
              <span>当前账号：{userId ?? '未知'}</span>
              {isVip ? (
                <Badge variant="success">
                  VIP{vipLevel && vipLevel.toLowerCase() !== 'vip' ? ` ${vipLevel}` : ''}
                </Badge>
              ) : (
                <Badge variant="outline">非会员</Badge>
              )}
            </p>
          )}
          {loginMut.isPending && (
            <p className="text-xs text-fg-muted">正在发起登录…</p>
          )}
          {loginFailed && (
            <LoginFailedNotice
              message={loginFailed}
              onRetry={startLogin}
              retryPending={loginMut.isPending}
            />
          )}
          {loginStartError && <LoginStartErrorPanel error={loginStartError} />}
          {loginInfo && <LoginAuthPanel info={loginInfo} waitingHint={loginStatusQuery.data?.message} />}
        </div>
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
              curl -fsSL https://jimeng.jianying.com/canvas-cli/install.sh | bash）。
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
            <Button size="sm" className="ml-auto" onClick={startLogin}>
              开始登录
            </Button>
          )}
        </div>
        {loginMut.isPending && (
          <p className="flex items-center gap-2 text-xs text-fg-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            正在发起 dreamina-canvas auth login…
          </p>
        )}
        {!loginInfo && !loginMut.isPending && (
          <p className="text-xs text-fg-muted">
            {status.message}。点击「开始登录」获取授权链接，在浏览器中完成授权。
          </p>
        )}
        {loginFailed && (
          <LoginFailedNotice
            message={loginFailed}
            onRetry={startLogin}
            retryPending={loginMut.isPending}
          />
        )}
        {loginStartError && <LoginStartErrorPanel error={loginStartError} />}
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

/** J-1：登录授权失败（轮询收到 failed / 会话丢失）——停转圈、给错误与重试入口。 */
function LoginFailedNotice({
  message,
  onRetry,
  retryPending,
}: {
  message: string
  onRetry: () => void
  retryPending: boolean
}) {
  return (
    <div
      role="alert"
      className="space-y-2 rounded-lg border border-error/40 bg-error/5 p-3"
    >
      <p className="flex items-start gap-1.5 text-xs font-medium text-error">
        <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>登录授权失败：{message}</span>
      </p>
      <Button size="sm" onClick={onRetry} disabled={retryPending}>
        <RefreshCw className="h-3 w-3" />
        重新发起登录
      </Button>
    </div>
  )
}

/** J-3：发起登录失败的诊断信息——执行命令与 CLI 原始输出，卡内可展开查看。 */
function LoginStartErrorPanel({
  error,
}: {
  error: { message: string; command?: string; raw_output?: string }
}) {
  return (
    <div
      role="alert"
      className="space-y-2 rounded-lg border border-error/40 bg-error/5 p-3"
    >
      <p className="flex items-start gap-1.5 text-xs font-medium text-error">
        <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>{error.message}</span>
      </p>
      {(error.command || error.raw_output) && (
        <details className="text-[11px] text-fg-secondary">
          <summary className="cursor-pointer text-fg-muted hover:text-fg-primary">
            查看诊断信息（执行命令与 CLI 原始输出）
          </summary>
          {error.command && (
            <p className="mt-1.5">
              命令：
              <code className="break-all rounded bg-bg-tertiary px-1 py-0.5 font-mono text-[10px] text-fg-primary">
                {error.command}
              </code>
            </p>
          )}
          {error.raw_output && (
            <pre className="mt-1.5 max-h-32 overflow-auto rounded bg-bg-tertiary p-2 text-[10px] text-fg-secondary">
              {error.raw_output}
            </pre>
          )}
        </details>
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
