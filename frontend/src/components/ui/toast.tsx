/**
 * Application-level transient notifications. `notify()` is imperative so any
 * code path — including non-React helpers — can report the outcome of an
 * action without threading state through the component tree. The host root is
 * mounted into `document.body` on first use and subscribes through
 * `useSyncExternalStore`, so a notification raised before the host is mounted
 * still renders.
 */

import { CircleAlert, CircleCheck, Info, X, type LucideIcon } from 'lucide-react'
import { useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import { I18nextProvider, useTranslation } from 'react-i18next'
import i18n from '../../i18n'
import { cn } from '../../utils/cn'
import { IconButton } from './button'

export type ToastTone = 'success' | 'error' | 'info'

export interface ToastAction {
  label: string
  onClick: () => void
}

export interface ToastOptions {
  title: string
  description?: string
  tone?: ToastTone
  /** Auto-dismiss delay in milliseconds; 0 keeps the toast until dismissed. */
  duration?: number
  action?: ToastAction
}

interface ToastEntry extends ToastOptions {
  id: number
  tone: ToastTone
  duration: number
}

const defaultDuration = 5000
const errorDuration = 8000
const tones: Record<ToastTone, { icon: LucideIcon; badge: string }> = {
  success: { icon: CircleCheck, badge: 'bg-emerald-50 text-emerald-600' },
  error: { icon: CircleAlert, badge: 'bg-rose-50 text-rose-600' },
  info: { icon: Info, badge: 'bg-blue-50 text-blue-600' },
}

let entries: ToastEntry[] = []
const listeners = new Set<() => void>()
const timers = new Map<number, number>()
let nextId = 1
let host: HTMLElement | null = null

function publish(next: ToastEntry[]) {
  entries = next
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function dismissToast(id: number) {
  const timer = timers.get(id)
  if (timer !== undefined) {
    window.clearTimeout(timer)
    timers.delete(id)
  }
  if (!entries.some((entry) => entry.id === id)) return
  publish(entries.filter((entry) => entry.id !== id))
}

/** Show a transient notification and return its id. */
export function notify(options: ToastOptions): number {
  const tone = options.tone ?? 'info'
  const entry: ToastEntry = {
    ...options,
    id: nextId++,
    tone,
    duration: options.duration ?? (tone === 'error' ? errorDuration : defaultDuration),
  }
  publish([...entries, entry])
  if (entry.duration > 0) {
    timers.set(
      entry.id,
      window.setTimeout(() => dismissToast(entry.id), entry.duration),
    )
  }
  mountHost()
  return entry.id
}

function mountHost() {
  if (host) return
  host = document.createElement('div')
  host.dataset.toastHost = ''
  document.body.appendChild(host)
  createRoot(host).render(
    <I18nextProvider i18n={i18n}>
      <ToastHost />
    </I18nextProvider>,
  )
}

function ToastHost() {
  const { t } = useTranslation()
  const items = useSyncExternalStore(
    subscribe,
    () => entries,
    () => entries,
  )
  if (!items.length) return null
  return (
    <div
      className={cn(
        'pointer-events-none fixed right-4 bottom-4 z-130 flex flex-col gap-2.5',
        'w-[min(360px,calc(100vw-2rem))]',
        'max-sm:right-3 max-sm:bottom-3 max-sm:w-[calc(100vw-1.5rem)]',
      )}
    >
      {items.map((entry) => {
        const tone = tones[entry.tone]
        const Icon = tone.icon
        return (
          <div
            key={entry.id}
            role={entry.tone === 'error' ? 'alert' : 'status'}
            className={cn(
              'pointer-events-auto flex items-start gap-3 rounded-md border border-slate-200',
              'bg-white p-3.5 shadow-2xl',
              'animate-[toast-in_180ms_ease-out] motion-reduce:animate-none',
            )}
          >
            <span
              className={cn('grid size-9 shrink-0 place-items-center rounded-[5px]', tone.badge)}
            >
              <Icon size={18} strokeWidth={2} aria-hidden />
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <strong className="block text-[13px] leading-4.5 font-semibold text-slate-700">
                {entry.title}
              </strong>
              {entry.description ? (
                <p className="mt-1 text-xs leading-4 text-slate-500">{entry.description}</p>
              ) : null}
              {entry.action ? (
                <button
                  type="button"
                  className={cn(
                    'mt-2 rounded-[3px] border-0 bg-transparent p-0',
                    'text-xs font-semibold text-blue-600 hover:text-blue-700',
                  )}
                  onClick={() => {
                    entry.action?.onClick()
                    dismissToast(entry.id)
                  }}
                >
                  {entry.action.label}
                </button>
              ) : null}
            </div>
            <IconButton
              label={t('common.close')}
              icon={X}
              className="-mt-1 -mr-1 border-transparent"
              onClick={() => dismissToast(entry.id)}
            />
          </div>
        )
      })}
    </div>
  )
}
