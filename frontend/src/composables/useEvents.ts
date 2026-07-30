import { onBeforeUnmount, onMounted, ref } from 'vue'
import { connectEvents } from '../api/client'

export interface RelayEvent {
  type: string
  at: string
  payload: Record<string, unknown>
}

export function useEvents(onEvent?: (event: RelayEvent) => void) {
  const connected = ref(false)
  const recent = ref<RelayEvent[]>([])
  let controller: AbortController | undefined

  onMounted(() => {
    controller = new AbortController()
    connectEvents((type, raw) => {
      connected.value = true
      if (!raw || typeof raw !== 'object') return
      const envelope = raw as Partial<RelayEvent>
      const event: RelayEvent = {
        type: envelope.type ?? type,
        at: envelope.at ?? new Date().toISOString(),
        payload: (envelope.payload ?? {}) as Record<string, unknown>,
      }
      recent.value = [event, ...recent.value].slice(0, 80)
      onEvent?.(event)
    }, controller.signal).catch(() => {
      connected.value = false
    })
  })

  onBeforeUnmount(() => controller?.abort())
  return { connected, recent }
}

