import { ArrowRight, KeyRound, LockKeyhole, ShieldCheck, UserRound } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { request } from '../api/client'
import { clearCredentials, setCredentials } from '../api/credentials'
import type { SessionInfo } from '../types'
import { cn } from '../utils/cn'
import { Brand } from './Brand'
import { LanguageToggle } from './LanguageToggle'
import { Button, fieldClass } from './ui'

export function Login({ onAuthenticated }: { onAuthenticated: (session: SessionInfo) => void }) {
  const { t } = useTranslation()
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
      setError(reason instanceof Error ? reason.message : t('login.failed'))
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
          <p className="mb-2 text-[11px] font-bold text-blue-200 uppercase">
            {t('login.heroEyebrow')}
          </p>
          <h1 className="mb-5 text-[38px] leading-[1.27] font-bold">{t('login.heroTitle')}</h1>
          <p className="max-w-95 text-[15px] leading-6 text-white/70">
            {t('login.heroDescription')}
          </p>
        </div>
        <div className="relative flex items-center gap-2.5 text-[11px] text-white/70">
          <ShieldCheck size={17} />
          <span className="flex flex-col">
            <strong className="mb-0.5 text-[12px] text-white">{t('login.localFirst')}</strong>
            {t('login.credentialsHint')}
          </span>
        </div>
      </section>

      <section
        className={cn(
          'grid place-items-center p-10',
          'max-md:min-h-dvh max-md:bg-linear-to-b max-md:from-blue-50 max-md:to-white max-md:p-6',
        )}
      >
        <LanguageToggle className="absolute top-5 right-5 z-10" />
        <form className="w-full max-w-90" onSubmit={submit}>
          <div className="mb-7.5">
            <p className="mb-2 text-[11px] font-bold text-blue-600 uppercase">
              {t('login.formEyebrow')}
            </p>
            <h2 className="mb-2 text-2xl font-bold text-slate-900">{t('login.title')}</h2>
            <p className="text-[13px] text-slate-500">{t('login.description')}</p>
          </div>
          <label className={cn(fieldClass, 'mb-4')}>
            <span>{t('login.username')}</span>
            <div
              className={cn(
                'flex h-9.5 items-center gap-2 rounded-[5px] border border-slate-200',
                'px-2.5 text-slate-400 focus-within:border-blue-300',
                'focus-within:ring-3 focus-within:ring-blue-500/10',
              )}
            >
              <UserRound size={17} />
              <input
                className="w-full border-0 bg-transparent text-[13px] text-slate-700 outline-none"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                required
                autoFocus
              />
            </div>
          </label>
          <label className={cn(fieldClass, 'mb-4')}>
            <span>{t('login.password')}</span>
            <div
              className={cn(
                'flex h-9.5 items-center gap-2 rounded-[5px] border border-slate-200',
                'px-2.5 text-slate-400 focus-within:border-blue-300',
                'focus-within:ring-3 focus-within:ring-blue-500/10',
              )}
            >
              <LockKeyhole size={17} />
              <input
                className="w-full border-0 bg-transparent text-[13px] text-slate-700 outline-none"
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
                'text-[11px] text-rose-700',
              )}
            >
              {error}
            </p>
          ) : null}
          <Button className="mt-2 h-10.5 w-full" disabled={submitting} icon={ArrowRight}>
            {t(submitting ? 'login.verifying' : 'login.submit')}
          </Button>
          <p className="mt-4 flex items-center justify-center gap-2 text-[10px] text-slate-400">
            <span className="size-2 rounded-full bg-emerald-500 ring-3 ring-emerald-500/10" />
            {t('login.apiStatus')}
          </p>
        </form>
      </section>
    </main>
  )
}
