import { ACCOUNT_ID_HEADER, ApiError } from './client'
import { authorization } from './credentials'
import type { TelegramPreviewUpdate } from '../types'

async function connectEventStream(
  path: string,
  onEvent: (type: string, payload: Record<string, unknown>) => void,
  signal: AbortSignal,
  accountId?: string,
): Promise<void> {
  const headers = new Headers({ Accept: 'text/event-stream' })
  const auth = authorization()
  if (auth) headers.set('Authorization', auth)
  if (accountId) headers.set(ACCOUNT_ID_HEADER, accountId)
  const response = await fetch(path, { headers, signal })
  if (!response.ok || !response.body) {
    throw new ApiError(response.status, 'events_unavailable', 'Event stream unavailable')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (!signal.aborted) {
    const { value, done } = await reader.read()
    if (done) break
    buffer = `${buffer}${decoder.decode(value, { stream: true })}`.replace(/\r\n/g, '\n')
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      let type = 'message'
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) type = line.slice(6).trim()
        if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (data) {
        try {
          onEvent(type, JSON.parse(data) as Record<string, unknown>)
        } catch {
          onEvent(type, { message: data })
        }
      }
      boundary = buffer.indexOf('\n\n')
    }
  }
}

export async function connectEvents(
  onEvent: (type: string, payload: Record<string, unknown>) => void,
  signal: AbortSignal,
  accountId?: string,
  allAccounts = false,
): Promise<void> {
  const path = allAccounts ? '/api/v1/events?all_accounts=true' : '/api/v1/events'
  return connectEventStream(path, onEvent, signal, accountId)
}

export function connectTelegramPreviewUpdates(
  onUpdate: (update: TelegramPreviewUpdate) => void,
  signal: AbortSignal,
  accountId: string,
): Promise<void> {
  return connectEventStream(
    '/api/v1/telegram-preview/updates',
    (type, payload) => {
      if (
        type === 'message' &&
        typeof payload.chat_id === 'number' &&
        typeof payload.message_id === 'number'
      ) {
        onUpdate({ chat_id: payload.chat_id, message_id: payload.message_id })
      }
    },
    signal,
    accountId,
  )
}
