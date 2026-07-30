export interface ApiErrorBody {
  detail?: { code?: string; message?: string } | string
  message?: string
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
  }
}

const CREDENTIALS_KEY = 'telerelay.basic'

function authorization(): string | undefined {
  const encoded = sessionStorage.getItem(CREDENTIALS_KEY)
  return encoded ? `Basic ${encoded}` : undefined
}

export function setCredentials(username: string, password: string): void {
  sessionStorage.setItem(CREDENTIALS_KEY, btoa(`${username}:${password}`))
}

export function clearCredentials(): void {
  sessionStorage.removeItem(CREDENTIALS_KEY)
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers)
  const auth = authorization()
  if (auth) headers.set('Authorization', auth)
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(path, { ...options, headers })
  if (!response.ok) {
    let body: ApiErrorBody = {}
    try {
      body = await response.json()
    } catch {
      body = { message: response.statusText }
    }
    const detail = typeof body.detail === 'object' ? body.detail : undefined
    throw new ApiError(
      response.status,
      detail?.code ?? `http_${response.status}`,
      detail?.message ?? body.message ?? String(body.detail ?? response.statusText),
    )
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function json(method: string, body?: unknown): RequestInit {
  return { method, body: body === undefined ? undefined : JSON.stringify(body) }
}

export async function downloadFile(path: string, fallbackName = 'download'): Promise<void> {
  const headers = new Headers()
  const auth = authorization()
  if (auth) headers.set('Authorization', auth)
  const response = await fetch(path, { headers })
  if (!response.ok) {
    throw new ApiError(response.status, `http_${response.status}`, response.statusText)
  }

  const disposition = response.headers.get('Content-Disposition') ?? ''
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const quotedName = disposition.match(/filename="([^"]+)"/i)?.[1]
  const filename = encodedName ? decodeURIComponent(encodedName) : quotedName ?? fallbackName
  const objectUrl = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(objectUrl)
}

export async function connectEvents(
  onEvent: (type: string, payload: unknown) => void,
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
          onEvent(type, JSON.parse(data))
        } catch {
          onEvent(type, data)
        }
      }
      boundary = buffer.indexOf('\n\n')
    }
  }
}
