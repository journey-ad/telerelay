import { authorization } from './credentials'

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

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
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
