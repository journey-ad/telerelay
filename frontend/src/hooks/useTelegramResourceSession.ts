import { useCallback, useEffect, useRef, useState } from 'react'
import { accountRequest } from '../api/client'
import { openTelegramResourceSession, type TelegramResourceSession } from '../api/telegramResource'
import type { TelegramResourceInfo } from '../types'

export interface TelegramResourceSessionState {
  /** Direct Telegram DC media session (available once the ticket is ready), null before that */
  session: TelegramResourceSession | null
  /** Ticket request or session establishment failed */
  error: boolean
  /** Re-request the ticket and open a fresh session */
  retry: () => void
  /** Close the current session and reset state (without retrying) */
  close: () => void
}

/**
 * Loads a Telegram media file (video/audio) by connecting directly to the
 * Telegram DC using a temporary ticket issued by the backend. Bytes flow
 * through the service worker + web worker straight to the browser and never
 * pass through the backend.
 */
export function useTelegramResourceSession({
  accountId,
  chatId,
  messageId,
  enabled = true,
}: {
  accountId: string
  chatId: number
  messageId: number
  /** When false, no request is issued (used for lazy loading in inline players) */
  enabled?: boolean
}): TelegramResourceSessionState {
  const [session, setSession] = useState<TelegramResourceSession | null>(null)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const sessionRef = useRef<TelegramResourceSession | null>(null)

  useEffect(() => {
    // Cleanup must run before the early return: when `enabled` flips from
    // true to false, the old effect's cleanup only closes the underlying
    // session, so this clears the externally visible session state here.
    sessionRef.current?.close()
    sessionRef.current = null
    setSession(null)
    setError(false)
    if (!enabled) return
    const controller = new AbortController()
    const startTimer = window.setTimeout(() => {
      if (controller.signal.aborted) return
      void (async () => {
        let info: TelegramResourceInfo | null = null
        try {
          info = await accountRequest<TelegramResourceInfo>(
            accountId,
            `/api/v1/telegram-preview/chats/${chatId}/messages/${messageId}/resource-info`,
            { method: 'POST', signal: controller.signal },
          )
          const nextSession = await openTelegramResourceSession(accountId, info)
          sessionRef.current = nextSession
          if (!controller.signal.aborted) setSession(nextSession)
          else nextSession.close()
        } catch (loadError) {
          const detail = loadError instanceof Error ? loadError.message : String(loadError)
          console.error(
            `Telegram media preview failed ` +
              `(chat=${chatId}, message=${messageId}, ` +
              `dc=${info?.file.dc_id ?? 'unknown'}, ` +
              `endpoint=${info ? `kws${info.file.dc_id}-1.web.telegram.org` : 'unknown'}): ${detail}`,
          )
          if (!controller.signal.aborted) setError(true)
        }
      })()
    }, 0)
    return () => {
      window.clearTimeout(startTimer)
      controller.abort()
      sessionRef.current?.close()
      sessionRef.current = null
    }
  }, [accountId, chatId, messageId, enabled, attempt])

  const retry = useCallback(() => setAttempt((value) => value + 1), [])
  const close = useCallback(() => {
    sessionRef.current?.close()
    sessionRef.current = null
    setSession(null)
    setError(false)
  }, [])

  return { session, error, retry, close }
}
