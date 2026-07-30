import { useEffect, useState } from 'react'
import { authorization } from '../api/credentials'
import type { TelegramAccount } from '../types'
import { cn } from '../utils/cn'

function initials(account?: TelegramAccount): string {
  const value = account?.display_name || account?.label || 'TG'
  const words = value.trim().split(/\s+/).filter(Boolean)
  return words.length > 1
    ? `${words[0][0]}${words[words.length - 1][0]}`.toUpperCase()
    : value.slice(0, 2).toUpperCase()
}

export function AccountAvatar({
  account,
  className,
  fallbackClassName,
}: {
  account?: TelegramAccount
  className?: string
  fallbackClassName?: string
}) {
  const [source, setSource] = useState<string | null>(null)

  useEffect(() => {
    setSource(null)
    if (!account?.avatar_version) {
      return
    }

    const controller = new AbortController()
    let active = true
    let objectUrl: string | null = null
    const headers = new Headers()
    const auth = authorization()
    if (auth) headers.set('Authorization', auth)

    void fetch(`/api/v1/telegram-accounts/${account.id}/avatar?v=${account.avatar_version}`, {
      headers,
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error(`Avatar request failed: ${response.status}`)
        return response.blob()
      })
      .then((blob) => {
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        setSource(objectUrl)
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) setSource(null)
      })

    return () => {
      active = false
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [account?.id, account?.avatar_version])

  return (
    <span
      className={cn(
        'relative grid shrink-0 place-items-center overflow-hidden rounded bg-slate-100',
        className,
      )}
      aria-hidden
    >
      <span className={cn('font-bold text-slate-600', fallbackClassName)}>{initials(account)}</span>
      {source ? (
        <img
          src={source}
          alt=""
          className="absolute inset-0 size-full object-cover"
          onError={() => setSource(null)}
        />
      ) : null}
    </span>
  )
}
