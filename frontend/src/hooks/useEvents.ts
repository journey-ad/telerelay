import { useEffect, useState } from 'react'
import { connectEvents } from '../api/events'
import type { RelayEvent } from '../types'

export function useEvents(onEvent?: (event: RelayEvent) => void) {
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
      setRecent((current) => [event, ...current].slice(0, 80))
      onEvent?.(event)
    }
    connectEvents(handle, controller.signal).catch(() => {
      if (!controller.signal.aborted) setConnected(false)
    })
    return () => controller.abort()
  }, [onEvent])

  return { connected, recent }
}
