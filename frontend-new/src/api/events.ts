import { ApiError } from './client'
import { authorization } from './credentials'

export async function connectEvents(
  onEvent: (type: string, payload: Record<string, unknown>) => void,
  signal: AbortSignal,
): Promise<void> {
  const headers = new Headers({ Accept: 'text/event-stream' })
  const auth = authorization()
  if (auth) headers.set('Authorization', auth)
  const response = await fetch('/api/v1/events', { headers, signal })
  if (!response.ok || !response.body) {
    throw new ApiError(response.status, 'events_unavailable', 'Event stream unavailable')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (!signal.aborted) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
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
