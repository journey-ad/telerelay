import { accountRequest } from './client'
import type { TelegramDcCredentials, TelegramResourceInfo } from '../types'

type WorkerReady = { type: 'ready'; id: string; size: number | null }
type WorkerConnected = { type: 'connected' }
type WorkerChunk = { type: 'chunk'; id: number; offset: number; bytes: Uint8Array }
type WorkerError = { type: 'error'; id: number | string | null; message: string }
type WorkerStats = { type: 'stats'; id: number; stats: TelegramResourceStats }
type WorkerMessage =
  WorkerReady | WorkerConnected | WorkerChunk | WorkerError | WorkerStats | { type: 'closed' }

const CHUNK_SIZE = 512 * 1024
export { CHUNK_SIZE as RESOURCE_CHUNK_SIZE }
const WORKER_READY_TIMEOUT_MS = 20_000

type TelegramResourceRuntime = {
  sessions: Map<string, TelegramResourceSession>
  serviceWorkerReady: Promise<void> | null
  messageListener: ((event: MessageEvent) => void) | null
}

const runtimeKey = '__teleRelayTelegramResourceRuntime'
const runtimeHost = globalThis as typeof globalThis & {
  [runtimeKey]?: TelegramResourceRuntime
}
const runtime = runtimeHost[runtimeKey] ?? {
  sessions: new Map<string, TelegramResourceSession>(),
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

export interface TelegramResourceSession {
  token: string
  url: string
  mimeType: string
  size: number | null
  dcId: number
  endpoint: string
  read(offset: number, limit: number, purpose?: 'playback' | 'metadata'): Promise<Uint8Array>
  getStats(): Promise<TelegramResourceStats>
  close(): void
}

export interface TelegramResourceStats {
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
      .register('/telegram-resource-sw.js', { scope: '/', updateViaCache: 'none' })
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
    // Tear down every pooled worker so HMR does not orphan live sessions (and
    // their in-memory auth keys) in the module-global pool.
    for (const pooled of [...pool.values()]) closePooledWorker(pooled)
  })
}

const IDLE_CLOSE_MS = 60_000

/**
 * Account-level DC credentials are stable (the backend signs the same
 * permanent auth key for every ticket on a DC), so they are cached per
 * account + DC and only re-fetched after a TTL. The server salt is re-synced
 * by the MTProto layer after connect, so a slightly stale cached salt is fine.
 */
const DC_CREDENTIALS_TTL_MS = 30 * 60 * 1000
const dcCredentialsCache = new Map<
  string,
  { credentials: TelegramDcCredentials; expiresAt: number }
>()
const dcCredentialsInflight = new Map<string, Promise<TelegramDcCredentials>>()

export function getDcCredentials(accountId: string, dcId: number): Promise<TelegramDcCredentials> {
  const key = `${accountId}:${dcId}`
  const cached = dcCredentialsCache.get(key)
  if (cached && cached.expiresAt > Date.now()) return Promise.resolve(cached.credentials)
  const inflight = dcCredentialsInflight.get(key)
  if (inflight) return inflight
  const request = accountRequest<TelegramDcCredentials>(
    accountId,
    `/api/v1/telegram-preview/resource-ticket/dc/${dcId}`,
    { method: 'POST' },
  )
    .then((credentials) => {
      dcCredentialsCache.set(key, { credentials, expiresAt: Date.now() + DC_CREDENTIALS_TTL_MS })
      return credentials
    })
    .finally(() => dcCredentialsInflight.delete(key))
  dcCredentialsInflight.set(key, request)
  return request
}

/** Forget cached DC credentials (used on sign-out). */
export function clearDcCredentialsCache(): void {
  dcCredentialsCache.clear()
  dcCredentialsInflight.clear()
}

type PooledWorker = {
  poolKey: string
  worker: Worker
  sessions: Map<string, TelegramResourceSession>
  readWaiters: Map<
    number,
    {
      token: string
      resolve: (bytes: Uint8Array) => void
      reject: (error: Error) => void
    }
  >
  statsWaiters: Map<
    number,
    {
      token: string
      resolve: (stats: TelegramResourceStats) => void
      reject: (error: Error) => void
    }
  >
  readyWaiters: Map<
    string,
    { resolve: (size: number | null) => void; reject: (error: Error) => void }
  >
  nextRequestId: number
  /** True once the worker's first init carried credentials to the worker. */
  credentialsSent: boolean
  /** True once the worker reported a live MTProto connection. */
  connected: boolean
  closed: boolean
}

const pool = new Map<string, PooledWorker>()
const idleTimers = new Map<string, number>()

function dispatch(pooled: PooledWorker, event: MessageEvent<WorkerMessage>) {
  const value = event.data
  if (value.type === 'connected') {
    pooled.connected = true
  } else if (value.type === 'ready') {
    const waiter = pooled.readyWaiters.get(value.id)
    pooled.readyWaiters.delete(value.id)
    waiter?.resolve(value.size)
  } else if (value.type === 'error') {
    if (typeof value.id === 'string') {
      const waiter = pooled.readyWaiters.get(value.id)
      pooled.readyWaiters.delete(value.id)
      waiter?.reject(workerError(value.message))
    } else if (value.id === null) {
      // Connection-level failure: reject everything pending on this worker.
      for (const waiter of pooled.readyWaiters.values()) waiter.reject(workerError(value.message))
      pooled.readyWaiters.clear()
      for (const waiter of pooled.readWaiters.values()) waiter.reject(workerError(value.message))
      pooled.readWaiters.clear()
      for (const waiter of pooled.statsWaiters.values()) waiter.reject(workerError(value.message))
      pooled.statsWaiters.clear()
      closePooledWorker(pooled)
    } else {
      const waiter = pooled.readWaiters.get(value.id) ?? pooled.statsWaiters.get(value.id)
      if (waiter) {
        waiter.reject(workerError(value.message))
        pooled.readWaiters.delete(value.id)
        pooled.statsWaiters.delete(value.id)
      }
    }
  } else if (value.type === 'chunk') {
    const waiter = pooled.readWaiters.get(value.id)
    if (waiter) {
      waiter.resolve(value.bytes)
      pooled.readWaiters.delete(value.id)
    }
  } else if (value.type === 'stats') {
    const waiter = pooled.statsWaiters.get(value.id)
    if (waiter) {
      waiter.resolve(value.stats)
      pooled.statsWaiters.delete(value.id)
    }
  }
}

function createPooledWorker(poolKey: string): PooledWorker {
  const worker = new Worker(new URL('../workers/telegramResourceWorker.ts', import.meta.url), {
    type: 'module',
  })
  const pooled: PooledWorker = {
    poolKey,
    worker,
    sessions: new Map(),
    readWaiters: new Map(),
    statsWaiters: new Map(),
    readyWaiters: new Map(),
    nextRequestId: 1,
    credentialsSent: false,
    connected: false,
    closed: false,
  }
  const onWorkerError = (event: ErrorEvent) => {
    event.preventDefault()
    console.error(
      `Telegram media worker failed to load: ${event.message || '(no message)'} ` +
        `at ${event.filename || '(no file)'}:${event.lineno}:${event.colno}; ${String(event.error ?? '')}`,
    )
    for (const waiter of pooled.readyWaiters.values()) waiter.reject(workerError(event.message))
    pooled.readyWaiters.clear()
    closePooledWorker(pooled)
  }
  worker.addEventListener('message', (event) => dispatch(pooled, event))
  worker.addEventListener('error', onWorkerError)
  return pooled
}

function closePooledWorker(pooled: PooledWorker): void {
  if (pooled.closed) return
  pooled.closed = true
  for (const waiter of pooled.readWaiters.values())
    waiter.reject(new Error('Resource session was closed'))
  pooled.readWaiters.clear()
  for (const waiter of pooled.statsWaiters.values())
    waiter.reject(new Error('Resource session was closed'))
  pooled.statsWaiters.clear()
  for (const waiter of pooled.readyWaiters.values())
    waiter.reject(new Error('Resource session was closed'))
  pooled.readyWaiters.clear()
  for (const token of pooled.sessions.keys()) sessions.delete(token)
  pooled.sessions.clear()
  const timer = idleTimers.get(pooled.poolKey)
  if (timer !== undefined) window.clearTimeout(timer)
  idleTimers.delete(pooled.poolKey)
  pooled.worker.postMessage({ type: 'close' })
  pooled.worker.terminate()
  if (pool.get(pooled.poolKey) === pooled) pool.delete(pooled.poolKey)
}

function scheduleIdleClose(poolKey: string, pooled: PooledWorker): void {
  const previous = idleTimers.get(poolKey)
  if (previous !== undefined) window.clearTimeout(previous)
  idleTimers.set(
    poolKey,
    window.setTimeout(() => {
      idleTimers.delete(poolKey)
      if (pooled.sessions.size === 0 && !pooled.closed) closePooledWorker(pooled)
    }, IDLE_CLOSE_MS),
  )
}

function clearIdleClose(poolKey: string): void {
  const timer = idleTimers.get(poolKey)
  if (timer !== undefined) {
    window.clearTimeout(timer)
    idleTimers.delete(poolKey)
  }
}

export async function openTelegramResourceSession(
  accountId: string,
  info: TelegramResourceInfo,
): Promise<TelegramResourceSession> {
  await ensureServiceWorker()
  // File info and account-level DC credentials come from separate endpoints;
  // merge them into the full ticket the worker understands. Credentials are
  // cached per account + DC, so only the first open per DC pays the round trip.
  const credentials = await getDcCredentials(accountId, info.file.dc_id)
  const ticket = { ...info, ...credentials }
  // Workers are pooled per Telegram DC + auth key: the backend signs the same
  // permanent auth key for every ticket on a DC, so one worker (one WebSocket)
  // serves any number of files there concurrently.
  const poolKey = `${ticket.dc_id}:${ticket.auth_key_id}`
  let pooled = pool.get(poolKey)
  if (!pooled) {
    pooled = createPooledWorker(poolKey)
    pool.set(poolKey, pooled)
  }
  clearIdleClose(poolKey)
  const token = ticket.ticket
  const declaredSize = ticket.size ?? (ticket.file.size > 0 ? ticket.file.size : null)
  const mimeType = ticket.mime_type || 'video/mp4'
  const dcId = ticket.dc_id
  const ready = new Promise<number | null>((resolve, reject) => {
    pooled.readyWaiters.set(token, { resolve, reject })
  })
  // Only the first file on a worker carries credentials; later opens reuse the
  // established client, so strip the credential fields before posting them.
  // The flag is set synchronously so concurrent opens on a fresh worker do not
  // all send credentials.
  const firstWithCredentials = !pooled.credentialsSent
  pooled.credentialsSent = true
  if (!firstWithCredentials) {
    ticket.auth_key = ''
    ticket.auth_key_id = ''
    ticket.server_salt = '0'
  }
  pooled.worker.postMessage({
    type: firstWithCredentials ? 'init' : 'open',
    id: token,
    ticket,
  })
  ticket.auth_key = ''
  ticket.auth_key_id = ''
  ticket.server_salt = '0'
  let size: number | null
  try {
    size = (await waitForWorkerReady(ready)) ?? declaredSize
  } catch (error) {
    pooled.readyWaiters.delete(token)
    // Connection-level failures already tore the worker down in dispatch; a
    // file-level failure must not kill the healthy worker. Only tear down when
    // the connection never came up.
    if (!pooled.connected) closePooledWorker(pooled)
    throw error
  }

  let closed = false
  const close = () => {
    if (closed || pooled.closed) {
      closed = true
      return
    }
    closed = true
    sessions.delete(token)
    pooled.sessions.delete(token)
    for (const [requestId, waiter] of pooled.readWaiters) {
      if (waiter.token === token) {
        waiter.reject(new Error('Resource session was closed'))
        pooled.readWaiters.delete(requestId)
      }
    }
    for (const [requestId, waiter] of pooled.statsWaiters) {
      if (waiter.token === token) {
        waiter.reject(new Error('Resource session was closed'))
        pooled.statsWaiters.delete(requestId)
      }
    }
    pooled.worker.postMessage({ type: 'close-file', file: token })
    if (pooled.sessions.size === 0) scheduleIdleClose(poolKey, pooled)
  }
  const session: TelegramResourceSession = {
    token,
    url: `/telegram-resource/${encodeURIComponent(token)}`,
    mimeType,
    size,
    dcId,
    endpoint: `kws${dcId}-1.web.telegram.org`,
    read(offset, limit, purpose = 'playback') {
      const id = pooled.nextRequestId++
      return new Promise<Uint8Array>((resolve, reject) => {
        pooled.readWaiters.set(id, { token, resolve, reject })
        pooled.worker.postMessage({ type: 'read', id, file: token, offset, limit, purpose })
      })
    },
    getStats() {
      const id = pooled.nextRequestId++
      return new Promise<TelegramResourceStats>((resolve, reject) => {
        pooled.statsWaiters.set(id, { token, resolve, reject })
        pooled.worker.postMessage({ type: 'stats', id, file: token })
      })
    },
    close,
  }
  sessions.set(session.token, session)
  pooled.sessions.set(session.token, session)
  return session
}

/**
 * Close every live resource session and pooled worker (workers + DC WebSocket
 * + in-memory auth key). Used on sign-out so the previous account's media
 * connections do not outlive the session.
 */
export function closeAllTelegramResourceSessions(): void {
  for (const pooled of [...pool.values()]) closePooledWorker(pooled)
}

/**
 * Read the full file behind a Telegram media session into a Blob. Bytes are
 * fetched chunk by chunk straight from the Telegram DC and never pass through
 * the backend.
 */
export async function readSessionBlob(session: TelegramResourceSession): Promise<Blob> {
  const chunks: BlobPart[] = []
  const size = session.size ?? 0
  let offset = 0
  for (;;) {
    const chunk = await session.read(offset, CHUNK_SIZE)
    if (!chunk.length) break
    // BlobPart requires an ArrayBuffer-backed view; worker chunks may arrive on
    // a SharedArrayBuffer, so copy into a fresh ArrayBuffer.
    chunks.push(new Uint8Array(chunk).buffer)
    offset += chunk.length
    if (size > 0 && offset >= size) break
  }
  return new Blob(chunks, { type: session.mimeType || 'application/octet-stream' })
}

/**
 * Download the full file behind a Telegram media session as a browser
 * download. Bytes never pass through the backend.
 */
export async function downloadTelegramResource(
  session: TelegramResourceSession,
  filename: string,
): Promise<void> {
  const blob = await readSessionBlob(session)
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  // Revoke after the browser has started the download: an immediate revoke can
  // race the save in some browsers.
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
}

/**
 * Pausable, progress-reporting download of the full file behind a Telegram
 * media session. Chunks are fetched straight from the Telegram DC by offset,
 * so pausing keeps the downloaded bytes and resuming continues from where it
 * stopped. The owning UI calls `close()` once `run()` settles to release the
 * worker session.
 */
export class ResourceDownload {
  private _paused = false
  private _cancelled = false
  private _transferred = 0
  private resumeWaiter: (() => void) | null = null

  constructor(
    private readonly session: TelegramResourceSession,
    private readonly filename: string,
    private readonly onProgress?: (transferred: number, total: number) => void,
  ) {}

  get transferred(): number {
    return this._transferred
  }

  /** Total size in bytes; 0 when the ticket did not carry a size. */
  get total(): number {
    return this.session.size ?? 0
  }

  get paused(): boolean {
    return this._paused
  }

  pause(): void {
    if (this._paused || this._cancelled) return
    this._paused = true
  }

  resume(): void {
    if (!this._paused) return
    this._paused = false
    this.resumeWaiter?.()
    this.resumeWaiter = null
  }

  cancel(): void {
    this._cancelled = true
    this._paused = false
    this.resumeWaiter?.()
    this.resumeWaiter = null
  }

  close(): void {
    this.session.close()
  }

  private waitWhilePaused(): Promise<void> {
    if (!this._paused) return Promise.resolve()
    return new Promise((resolve) => {
      this.resumeWaiter = resolve
    })
  }

  /** Run to completion and trigger the browser save; returns false when cancelled. */
  async run(): Promise<boolean> {
    const chunks: BlobPart[] = []
    let offset = 0
    for (;;) {
      if (this._cancelled) return false
      await this.waitWhilePaused()
      if (this._cancelled) return false
      const chunk = await this.session.read(offset, CHUNK_SIZE)
      if (!chunk.length) break
      // BlobPart requires an ArrayBuffer-backed view; worker chunks may arrive
      // on a SharedArrayBuffer, so copy into a fresh ArrayBuffer.
      chunks.push(new Uint8Array(chunk).buffer)
      offset += chunk.length
      this._transferred += chunk.length
      this.onProgress?.(this._transferred, this.total)
      if (this.total > 0 && offset >= this.total) break
    }
    const blob = new Blob(chunks, { type: this.session.mimeType || 'application/octet-stream' })
    const objectUrl = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = this.filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    // Revoke after the browser has started the download: an immediate revoke
    // can race the save in some browsers.
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
    return true
  }
}
