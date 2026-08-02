import { useEffect, useState } from 'react'
import { ACCOUNT_ID_HEADER } from '../api/client'
import { authorization } from '../api/credentials'
import type { TelegramAccount } from '../types'
import { avatarInitials } from '../utils/avatar'
import { cn } from '../utils/cn'
import { hashColor } from '../utils/color'

function initials(account?: TelegramAccount): string {
  return avatarInitials(account?.display_name || account?.label || '')
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
  const colors = hashColor(String(account?.telegram_user_id ?? account?.id ?? 'TG'))

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
    headers.set(ACCOUNT_ID_HEADER, account.id)

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
      className={cn('relative grid shrink-0 place-items-center overflow-hidden rounded', className)}
      style={{
        backgroundColor: colors.background,
      }}
      aria-hidden
    >
      <span className={cn('font-bold', fallbackClassName)} style={{ color: colors.foreground }}>
        {initials(account)}
      </span>
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
