import { useEffect, useState } from 'react'
import { connectEvents } from '../api/events'
import type { RelayEvent } from '../types'

interface UseEventsOptions {
  maxRecent?: number
  shouldStore?: (event: RelayEvent) => boolean
}

export function useEvents(onEvent?: (event: RelayEvent) => void, options: UseEventsOptions = {}) {
  const { maxRecent = 0, shouldStore } = options
  const [connected, setConnected] = useState(false)
  const [recent, setRecent] = useState<RelayEvent[]>([])

  useEffect(() => {
    const controller = new AbortController()
    const handle = (streamType: string, value: Record<string, unknown>) => {
      const envelope = value as {
        type?: unknown
        at?: unknown
        payload?: unknown
      }
      const payload =
        envelope.payload && typeof envelope.payload === 'object'
          ? (envelope.payload as Record<string, unknown>)
          : value
      const event = {
        type: typeof envelope.type === 'string' ? envelope.type : streamType,
        payload,
        at: typeof envelope.at === 'string' ? envelope.at : new Date().toISOString(),
      }
      setConnected(true)
      if (maxRecent > 0 && (!shouldStore || shouldStore(event))) {
        setRecent((current) => [event, ...current].slice(0, maxRecent))
      }
      onEvent?.(event)
    }
    connectEvents(handle, controller.signal).catch(() => {
      if (!controller.signal.aborted) setConnected(false)
    })
    return () => controller.abort()
  }, [maxRecent, onEvent, shouldStore])

  return { connected, recent }
}
