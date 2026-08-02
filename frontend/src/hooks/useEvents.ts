import { useEffect, useState } from 'react'
import { connectEvents } from '../api/events'
import type { RelayEvent } from '../types'

interface UseEventsOptions {
  accountId?: string
  maxRecent?: number
  initialRecent?: RelayEvent[]
  shouldStore?: (event: RelayEvent) => boolean
}

function mergeRecent(current: RelayEvent[], incoming: RelayEvent[], limit: number): RelayEvent[] {
  const byId = new Map<number, RelayEvent>()
  for (const event of [...current, ...incoming]) byId.set(event.id, event)
  return [...byId.values()].sort((left, right) => right.id - left.id).slice(0, limit)
}

export function useEvents(onEvent?: (event: RelayEvent) => void, options: UseEventsOptions = {}) {
  const { accountId, maxRecent = 0, initialRecent = [], shouldStore } = options
  const [connected, setConnected] = useState(false)
  const [recent, setRecent] = useState<RelayEvent[]>([])

  useEffect(() => {
    if (maxRecent > 0 && initialRecent.length) {
      setRecent((current) => mergeRecent(current, initialRecent, maxRecent))
    }
  }, [initialRecent, maxRecent])

  useEffect(() => {
    const controller = new AbortController()
    const handle = (streamType: string, value: Record<string, unknown>) => {
      const envelope = value as {
        id?: unknown
        type?: unknown
        at?: unknown
        payload?: unknown
      }
      const payload =
        envelope.payload && typeof envelope.payload === 'object'
          ? (envelope.payload as Record<string, unknown>)
          : value
      setConnected(true)
      if (streamType === 'ready' || typeof envelope.id !== 'number') return
      const event = {
        id: envelope.id,
        type: typeof envelope.type === 'string' ? envelope.type : streamType,
        payload,
        at: typeof envelope.at === 'string' ? envelope.at : new Date().toISOString(),
      }
      if (maxRecent > 0 && (!shouldStore || shouldStore(event))) {
        setRecent((current) => mergeRecent(current, [event], maxRecent))
      }
      onEvent?.(event)
    }
    connectEvents(handle, controller.signal, accountId).catch(() => {
      if (!controller.signal.aborted) setConnected(false)
    })
    return () => controller.abort()
  }, [accountId, maxRecent, onEvent, shouldStore])

  return { connected, recent }
}
