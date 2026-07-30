import { useEffect, useState } from 'react'
import { connectEvents } from '../api/events'
import type { RelayEvent } from '../types'

export function useEvents(onEvent?: (event: RelayEvent) => void) {
  const [connected, setConnected] = useState(false)
  const [recent, setRecent] = useState<RelayEvent[]>([])

  useEffect(() => {
    const controller = new AbortController()
    const handle = (type: string, payload: Record<string, unknown>) => {
      const event = { type, payload, at: new Date().toISOString() }
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
