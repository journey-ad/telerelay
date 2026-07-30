import { ArrowRight, KeyRound, LockKeyhole, ShieldCheck, UserRound } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { request } from '../api/client'
import { clearCredentials, setCredentials } from '../api/credentials'
import type { SessionInfo } from '../types'
import { cn } from '../utils/cn'
import { Brand } from './Brand'
import { Button, fieldClass } from './ui'

export function Login({ onAuthenticated }: { onAuthenticated: (session: SessionInfo) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    setCredentials(username, password)
    try {
      onAuthenticated(await request<SessionInfo>('/api/v1/session'))
    } catch (reason) {
      clearCredentials()
      setError(reason instanceof Error ? reason.message : '认证失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main
      className={cn(
        'grid min-h-dvh bg-white max-md:grid-cols-1',
        'grid-cols-[minmax(360px,0.78fr)_minmax(460px,1.22fr)]',
      )}
    >
      <section
        className={cn(
          'relative flex min-h-dvh flex-col justify-between overflow-hidden',
          'bg-blue-700 px-10.5 py-9.5 text-white max-md:hidden',
        )}
      >
        <div
          className={cn(
            'relative [&_.font-display]:text-white [&_small]:text-blue-200',
            '[&_span:first-child]:bg-white [&_span:first-child]:text-blue-600',
            '[&_span:first-child]:shadow-none',
          )}
        >
          <Brand />
        </div>
        <div className="relative my-auto max-w-108">
          <span
            className={cn(
              'mb-9 grid size-13 place-items-center rounded-md border',
              'border-white/20 bg-white/10',
            )}
          >
            <KeyRound size={28} />
          </span>
          <p className="mb-2 text-[9px] font-bold text-blue-200 uppercase">Local control plane</p>
          <h1 className="mb-5 text-[38px] leading-[1.27] font-bold">
            中继消息，
            <br />
            保持掌控。
          </h1>
          <p className="max-w-95 text-[13px] leading-6 text-white/70">
            一个安静、可靠的 Telegram 转发控制台。 规则、队列与运行状态都在本机管理。
          </p>
        </div>
        <div className="relative flex items-center gap-2.5 text-[9px] text-white/70">
          <ShieldCheck size={17} />
          <span className="flex flex-col">
            <strong className="mb-0.5 text-[10px] text-white">本地优先</strong>
            凭据仅存储在当前浏览器会话中
          </span>
        </div>
      </section>

      <section
        className={cn(
          'grid place-items-center p-10',
          'max-md:min-h-dvh max-md:bg-linear-to-b max-md:from-blue-50 max-md:to-white max-md:p-6',
        )}
      >
        <form className="w-full max-w-90" onSubmit={submit}>
          <div className="mb-7.5">
            <p className="mb-2 text-[9px] font-bold text-blue-600 uppercase">Console access</p>
            <h2 className="mb-2 text-2xl font-bold text-slate-900">登录 TeleRelay</h2>
            <p className="text-[11px] text-slate-500">使用管理凭据继续进入控制台。</p>
          </div>
          <label className={cn(fieldClass, 'mb-4')}>
            <span>用户名</span>
            <div
              className={cn(
                'flex h-9.5 items-center gap-2 rounded-[5px] border border-slate-200',
                'px-2.5 text-slate-400 focus-within:border-blue-300',
                'focus-within:ring-3 focus-within:ring-blue-500/10',
              )}
            >
              <UserRound size={17} />
              <input
                className="w-full border-0 bg-transparent text-[11px] text-slate-700 outline-none"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                required
                autoFocus
              />
            </div>
          </label>
          <label className={cn(fieldClass, 'mb-4')}>
            <span>密码</span>
            <div
              className={cn(
                'flex h-9.5 items-center gap-2 rounded-[5px] border border-slate-200',
                'px-2.5 text-slate-400 focus-within:border-blue-300',
                'focus-within:ring-3 focus-within:ring-blue-500/10',
              )}
            >
              <LockKeyhole size={17} />
              <input
                className="w-full border-0 bg-transparent text-[11px] text-slate-700 outline-none"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                autoComplete="current-password"
                required
              />
            </div>
          </label>
          {error ? (
            <p
              className={cn(
                'mb-3 rounded-[5px] border border-rose-100 bg-rose-50 p-2.5',
                'text-[9px] text-rose-700',
              )}
            >
              {error}
            </p>
          ) : null}
          <Button className="mt-2 h-10.5 w-full" disabled={submitting} icon={ArrowRight}>
            {submitting ? '正在验证...' : '进入控制台'}
          </Button>
          <p className="mt-4 flex items-center justify-center gap-2 text-[8px] text-slate-400">
            <span className="size-2 rounded-full bg-emerald-500 ring-3 ring-emerald-500/10" />
            API 状态由本地节点提供
          </p>
        </form>
      </section>
    </main>
  )
}
