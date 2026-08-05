import type { TelegramVideoTicket } from '../types'

type WorkerReady = { type: 'ready'; size: number | null }
type WorkerChunk = { type: 'chunk'; id: number; offset: number; bytes: Uint8Array }
type WorkerError = { type: 'error'; id: number | null; message: string }
type WorkerStats = { type: 'stats'; id: number; stats: TelegramMediaStats }
type WorkerMessage = WorkerReady | WorkerChunk | WorkerError | WorkerStats | { type: 'closed' }

const CHUNK_SIZE = 512 * 1024
const WORKER_READY_TIMEOUT_MS = 20_000

type TelegramMediaRuntime = {
  sessions: Map<string, TelegramMediaSession>
  serviceWorkerReady: Promise<void> | null
  messageListener: ((event: MessageEvent) => void) | null
}

const runtimeKey = '__teleRelayTelegramMediaRuntime'
const runtimeHost = globalThis as typeof globalThis & {
  [runtimeKey]?: TelegramMediaRuntime
}
const runtime = runtimeHost[runtimeKey] ?? {
  sessions: new Map<string, TelegramMediaSession>(),
  serviceWorkerReady: null,
  messageListener: null,
}
runtimeHost[runtimeKey] = runtime
const sessions = runtime.sessions

function workerError(message: string): Error {
  return new Error(message || 'Telegram video could not be loaded')
}

function waitForWorkerReady(ready: Promise<number | null>): Promise<number | null> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(
      () => reject(new Error('Telegram video connection timed out')),
      WORKER_READY_TIMEOUT_MS,
    )
    void ready.then(
      (size) => {
        window.clearTimeout(timer)
        resolve(size)
      },
      (error) => {
        window.clearTimeout(timer)
        reject(error)
      },
    )
  })
}

function waitForServiceWorkerActivation(registration: ServiceWorkerRegistration): Promise<void> {
  if (registration.active) return Promise.resolve()
  const worker = registration.installing ?? registration.waiting
  if (!worker) return Promise.reject(new Error('Telegram media worker could not be activated'))
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(
      () => reject(new Error('Telegram media worker activation timed out')),
      10_000,
    )
    const onStateChange = () => {
      if (worker.state === 'activated') {
        window.clearTimeout(timer)
        worker.removeEventListener('statechange', onStateChange)
        resolve()
      } else if (worker.state === 'redundant') {
        window.clearTimeout(timer)
        worker.removeEventListener('statechange', onStateChange)
        reject(new Error('Telegram media worker activation failed'))
      }
    }
    worker.addEventListener('statechange', onStateChange)
    onStateChange()
  })
}

function waitForServiceWorkerController(): Promise<void> {
  if (navigator.serviceWorker.controller) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(
      () => reject(new Error('Telegram media worker did not take control')),
      10_000,
    )
    const onControllerChange = () => {
      if (!navigator.serviceWorker.controller) return
      window.clearTimeout(timer)
      navigator.serviceWorker.removeEventListener('controllerchange', onControllerChange)
      resolve()
    }
    navigator.serviceWorker.addEventListener('controllerchange', onControllerChange)
  })
}

export interface TelegramMediaSession {
  token: string
  url: string
  mimeType: string
  size: number | null
  dcId: number
  endpoint: string
  read(offset: number, limit: number, purpose?: 'playback' | 'metadata'): Promise<Uint8Array>
  getStats(): Promise<TelegramMediaStats>
  close(): void
}

export interface TelegramMediaStats {
  connected: boolean
  connectedForMs: number
  networkRequests: number
  rangeRequests: number
  bytesDownloaded: number
  bytesServed: number
  cacheHits: number
  deduplicatedRequests: number
  cacheChunks: number
  cachedBytes: number
  activeRequests: number
  averageLatencyMs: number
  lastLatencyMs: number
  maxLatencyMs: number
  throughputBps: number
  networkActivityBytes: number
  errors: number
  lastError: string
  heatmap: Array<{ accesses: number; downloads: number; cached: boolean }>
}

function ensureServiceWorker(): Promise<void> {
  if (!('serviceWorker' in navigator))
    return Promise.reject(new Error('Service Worker is unavailable'))
  if (!runtime.serviceWorkerReady) {
    runtime.serviceWorkerReady = navigator.serviceWorker
      .register('/telegram-media-sw.js', { scope: '/', updateViaCache: 'none' })
      .then(async (registration) => {
        await waitForServiceWorkerActivation(registration)
        await waitForServiceWorkerController()
      })
      .then(() => undefined)
      .catch((error) => {
        runtime.serviceWorkerReady = null
        throw error
      })
  }
  return runtime.serviceWorkerReady
}

if (typeof navigator !== 'undefined' && 'serviceWorker' in navigator) {
  if (runtime.messageListener)
    navigator.serviceWorker.removeEventListener('message', runtime.messageListener)
  const onServiceWorkerMessage = (event: MessageEvent) => {
    const value = event.data as { type?: string; token?: string; offset?: number; limit?: number }
    if (value.type !== 'telegram-range' || !value.token || !event.ports[0]) return
    const session = sessions.get(value.token)
    // Another live page may own this token. Only its listener should answer.
    if (!session) return
    void session
      .read(value.offset ?? 0, value.limit ?? CHUNK_SIZE)
      .then((bytes) => {
        const transferable = bytes.buffer as ArrayBuffer
        event.ports[0].postMessage(
          {
            type: 'telegram-range-response',
            bytes: transferable,
            total: session.size,
            mimeType: session.mimeType,
          },
          [transferable],
        )
      })
      .catch((error) => {
        console.error('Telegram media range failed', error)
        event.ports[0].postMessage({
          type: 'telegram-range-error',
          message: error instanceof Error ? error.message : String(error),
        })
      })
  }
  runtime.messageListener = onServiceWorkerMessage
  navigator.serviceWorker.addEventListener('message', onServiceWorkerMessage)

  const hot = (import.meta as ImportMeta & { hot?: { dispose(callback: () => void): void } }).hot
  hot?.dispose(() => {
    navigator.serviceWorker.removeEventListener('message', onServiceWorkerMessage)
    if (runtime.messageListener === onServiceWorkerMessage) runtime.messageListener = null
  })
}

export async function openTelegramMediaSession(
  ticket: TelegramVideoTicket,
): Promise<TelegramMediaSession> {
  await ensureServiceWorker()
  const worker = new Worker(new URL('../workers/telegramMediaWorker.ts', import.meta.url), {
    type: 'module',
  })
  let nextRequestId = 1
  const waiters = new Map<
    number,
    { resolve: (bytes: Uint8Array) => void; reject: (error: Error) => void }
  >()
  const statsWaiters = new Map<
    number,
    { resolve: (stats: TelegramMediaStats) => void; reject: (error: Error) => void }
  >()
  let readyResolve: ((size: number | null) => void) | null = null
  let readyReject: ((error: Error) => void) | null = null
  const ready = new Promise<number | null>((resolve, reject) => {
    readyResolve = resolve
    readyReject = reject
  })
  const onMessage = (event: MessageEvent<WorkerMessage>) => {
    const value = event.data
    if (value.type === 'ready') readyResolve?.(value.size)
    else if (value.type === 'error') {
      const error = workerError(value.message)
      if (value.id === null) readyReject?.(error)
      else waiters.get(value.id)?.reject(error)
      if (value.id !== null) waiters.delete(value.id)
    } else if (value.type === 'chunk') {
      waiters.get(value.id)?.resolve(value.bytes)
      waiters.delete(value.id)
    } else if (value.type === 'stats') {
      statsWaiters.get(value.id)?.resolve(value.stats)
      statsWaiters.delete(value.id)
    }
  }
  const onWorkerError = (event: ErrorEvent) => {
    event.preventDefault()
    console.error(
      `Telegram media worker failed to load: ${event.message || '(no message)'} ` +
        `at ${event.filename || '(no file)'}:${event.lineno}:${event.colno}; ${String(event.error ?? '')}`,
    )
    readyReject?.(workerError(event.message))
  }
  worker.addEventListener('message', onMessage)
  worker.addEventListener('error', onWorkerError)
  const token = ticket.ticket
  const declaredSize = ticket.size ?? ticket.file.size ?? null
  const mimeType = ticket.mime_type || 'video/mp4'
  const dcId = ticket.dc_id
  worker.postMessage({ type: 'init', ticket })
  ticket.auth_key = ''
  ticket.auth_key_id = ''
  ticket.server_salt = '0'
  let size: number | null
  try {
    size = (await waitForWorkerReady(ready)) ?? declaredSize
  } catch (error) {
    worker.terminate()
    throw error
  }

  const close = () => {
    sessions.delete(token)
    for (const waiter of waiters.values()) waiter.reject(new Error('Video session was closed'))
    waiters.clear()
    for (const waiter of statsWaiters.values()) waiter.reject(new Error('Video session was closed'))
    statsWaiters.clear()
    worker.postMessage({ type: 'close' })
    worker.terminate()
  }
  const session: TelegramMediaSession = {
    token,
    url: `/telegram-media/${encodeURIComponent(token)}`,
    mimeType,
    size,
    dcId,
    endpoint: `kws${dcId}-1.web.telegram.org`,
    read(offset, limit, purpose = 'playback') {
      const id = nextRequestId++
      return new Promise<Uint8Array>((resolve, reject) => {
        waiters.set(id, { resolve, reject })
        worker.postMessage({ type: 'read', id, offset, limit, purpose })
      })
    },
    getStats() {
      const id = nextRequestId++
      return new Promise<TelegramMediaStats>((resolve, reject) => {
        statsWaiters.set(id, { resolve, reject })
        worker.postMessage({ type: 'stats', id })
      })
    },
    close,
  }
  sessions.set(session.token, session)
  return session
}
