/// <reference lib="webworker" />

import {
  TelegramMtprotoClient,
  decodeBase64Url,
  randomSessionId,
  type FileLocation,
} from './telegramMtprotoClient'

type Ticket = {
  ticket: string
  api_id: number
  api_layer: number
  dc_id: number
  auth_key: string
  auth_key_id: string
  server_salt: string
  time_offset: number
  mime_type?: string
  file: FileLocation & {
    size?: number | null
  }
  size?: number | null
}

type OpenMessage = {
  type: 'init' | 'open'
  id: string
  ticket: Ticket
}

type ReadMessage = {
  type: 'read'
  id: number
  file: string
  offset: number
  limit: number
  purpose?: 'playback' | 'metadata'
}
type StatsMessage = { type: 'stats'; id: number; file: string }
type CloseFileMessage = { type: 'close-file'; file: string }
type CloseMessage = { type: 'close' }

const scope = self as unknown as {
  onmessage:
    | ((
        event: MessageEvent<
          OpenMessage | ReadMessage | StatsMessage | CloseFileMessage | CloseMessage
        >,
      ) => void)
    | null
  postMessage(message: unknown, transfer?: Transferable[]): void
}

const TELEGRAM_CHUNK_SIZE = 512 * 1024
const PRELOAD_SIZE = 20 * 1024 * 1024
const PRELOAD_CONCURRENCY = 3
const MAX_CACHED_CHUNKS = PRELOAD_SIZE / TELEGRAM_CHUNK_SIZE + PRELOAD_CONCURRENCY + 2
const HEATMAP_BUCKETS = 32

/**
 * One worker holds one MTProto client (one DC WebSocket + auth key) and serves
 * any number of files on it concurrently. Each file keeps its own chunk cache,
 * preload window, and transfer statistics.
 */
type FileState = {
  id: string
  ticket: Ticket
  initialChunk: Uint8Array<ArrayBufferLike>
  chunkCache: Map<number, Uint8Array<ArrayBufferLike>>
  pendingChunks: Map<number, Promise<Uint8Array<ArrayBufferLike>>>
  heatmapAccesses: Uint32Array
  heatmapDownloads: Uint32Array
  recentTransfers: Array<{ at: number; bytes: number }>
  preloadGeneration: number
  preloadStart: number
  preloadEnd: number
  networkRequests: number
  rangeRequests: number
  bytesDownloaded: number
  bytesServed: number
  cacheHits: number
  deduplicatedRequests: number
  latencyTotal: number
  lastLatency: number
  maxLatency: number
  errors: number
  lastError: string
}

let client: TelegramMtprotoClient | null = null
let connectPromise: Promise<void> | null = null
let connectedAt = 0
const files = new Map<string, FileState>()

function postError(id: number | string | null, error: unknown) {
  const message = error instanceof Error ? error.message : String(error)
  // File-level error accounting only for open failures (string id); read
  // errors (number id) are routed by request id on the main thread instead.
  if (typeof id === 'string') {
    const state = files.get(id)
    if (state) {
      state.errors += 1
      state.lastError = message
    }
  }
  scope.postMessage({ type: 'error', id, message })
}

function createFileState(id: string, ticket: Ticket): FileState {
  return {
    id,
    ticket,
    initialChunk: new Uint8Array(),
    chunkCache: new Map(),
    pendingChunks: new Map(),
    heatmapAccesses: new Uint32Array(HEATMAP_BUCKETS),
    heatmapDownloads: new Uint32Array(HEATMAP_BUCKETS),
    recentTransfers: [],
    preloadGeneration: 0,
    preloadStart: -1,
    preloadEnd: -1,
    networkRequests: 0,
    rangeRequests: 0,
    bytesDownloaded: 0,
    bytesServed: 0,
    cacheHits: 0,
    deduplicatedRequests: 0,
    latencyTotal: 0,
    lastLatency: 0,
    maxLatency: 0,
    errors: 0,
    lastError: '',
  }
}

function totalSize(state: FileState) {
  return state.ticket?.size ?? state.ticket?.file.size ?? 0
}

function heatmapIndex(state: FileState, offset: number) {
  const size = totalSize(state)
  return size > 0 ? Math.min(HEATMAP_BUCKETS - 1, Math.floor((offset / size) * HEATMAP_BUCKETS)) : 0
}

function trimTransfers(state: FileState, now: number) {
  while (state.recentTransfers[0] && state.recentTransfers[0].at < now - 10_000)
    state.recentTransfers.shift()
}

function clearChunkCache(state: FileState) {
  for (const chunk of state.chunkCache.values()) chunk.fill(0)
  state.chunkCache.clear()
  state.pendingChunks.clear()
  state.preloadGeneration += 1
  state.preloadStart = -1
  state.preloadEnd = -1
}

function rememberChunk(state: FileState, offset: number, chunk: Uint8Array<ArrayBufferLike>) {
  state.chunkCache.delete(offset)
  state.chunkCache.set(offset, chunk)
  while (state.chunkCache.size > MAX_CACHED_CHUNKS) {
    const oldestOffset = state.chunkCache.keys().next().value
    if (oldestOffset === undefined) break
    state.chunkCache.get(oldestOffset)?.fill(0)
    state.chunkCache.delete(oldestOffset)
  }
  return chunk
}

function requestChunk(
  fileId: string,
  offset: number,
  source: 'playback' | 'preload' | 'metadata',
): Promise<Uint8Array<ArrayBufferLike>> {
  const state = files.get(fileId)
  const requestClient = client
  if (!state || !requestClient) return Promise.reject(new Error('Video worker is not ready'))
  if (source === 'playback') state.heatmapAccesses[heatmapIndex(state, offset)] += 1
  const cached = state.chunkCache.get(offset)
  if (cached) {
    state.chunkCache.delete(offset)
    state.chunkCache.set(offset, cached)
    if (source === 'playback') state.cacheHits += 1
    return Promise.resolve(cached)
  }
  const pending = state.pendingChunks.get(offset)
  if (pending) {
    if (source === 'playback') state.deduplicatedRequests += 1
    return pending
  }
  const startedAt = performance.now()
  state.networkRequests += 1
  const request = requestClient
    .getFile(state.ticket.file, offset, TELEGRAM_CHUNK_SIZE)
    .then((chunk) => {
      if (client !== requestClient || !files.has(fileId)) {
        chunk.fill(0)
        throw new Error('Video worker was closed')
      }
      const now = performance.now()
      state.lastLatency = now - startedAt
      state.latencyTotal += state.lastLatency
      state.maxLatency = Math.max(state.maxLatency, state.lastLatency)
      state.bytesDownloaded += chunk.length
      state.heatmapDownloads[heatmapIndex(state, offset)] += 1
      state.recentTransfers.push({ at: now, bytes: chunk.length })
      trimTransfers(state, now)
      return rememberChunk(state, offset, chunk)
    })
    .finally(() => state.pendingChunks.delete(offset))
  state.pendingChunks.set(offset, request)
  return request
}

function preloadChunks(state: FileState, from: number) {
  const size = totalSize(state)
  if (!client || !size) return
  const start = Math.floor(from / TELEGRAM_CHUNK_SIZE) * TELEGRAM_CHUNK_SIZE
  const end = Math.min(size, start + PRELOAD_SIZE)
  if (start >= state.preloadStart && start < state.preloadEnd - PRELOAD_SIZE / 2) return
  state.preloadStart = start
  state.preloadEnd = end
  const generation = ++state.preloadGeneration
  void (async () => {
    for (let offset = start; offset < end; offset += TELEGRAM_CHUNK_SIZE * PRELOAD_CONCURRENCY) {
      if (!files.has(state.id) || generation !== state.preloadGeneration) return
      const batch: Promise<Uint8Array<ArrayBufferLike>>[] = []
      for (let index = 0; index < PRELOAD_CONCURRENCY; index += 1) {
        const chunkOffset = offset + index * TELEGRAM_CHUNK_SIZE
        if (chunkOffset < end) batch.push(requestChunk(state.id, chunkOffset, 'preload'))
      }
      await Promise.all(batch)
    }
  })().catch(() => {})
}

/**
 * Establish the single per-worker MTProto client on first use. Later files on
 * the same DC reuse the existing connection: the backend signs the same
 * permanent auth key for every ticket on a DC, so only the first init carries
 * credentials and subsequent opens simply attach another file to the client.
 */
function ensureClient(ticket: Ticket): Promise<TelegramMtprotoClient> {
  if (client) {
    // Defensive: never let credentials linger on a file state even when the
    // client was already established by another file.
    ticket.auth_key = ''
    ticket.auth_key_id = ''
    ticket.server_salt = '0'
    return Promise.resolve(client)
  }
  if (connectPromise) return connectPromise.then(() => client as TelegramMtprotoClient)
  const sessionId = randomSessionId()
  const authKey = decodeBase64Url(ticket.auth_key)
  const expectedAuthKeyId = BigInt(ticket.auth_key_id)
  const serverSalt = BigInt(ticket.server_salt)
  ticket.auth_key = ''
  ticket.auth_key_id = ''
  ticket.server_salt = '0'
  connectPromise = (async () => {
    client = new TelegramMtprotoClient({
      apiId: ticket.api_id,
      apiLayer: ticket.api_layer,
      dcId: ticket.dc_id,
      authKey,
      expectedAuthKeyId,
      serverSalt,
      sessionId,
      timeOffset: ticket.time_offset,
    })
    await client.connect()
    connectedAt = performance.now()
    scope.postMessage({ type: 'connected' })
  })()
  return connectPromise
    .then(() => client as TelegramMtprotoClient)
    .catch((error) => {
      client = null
      connectPromise = null
      throw error
    })
}

async function openFile(id: string, ticket: Ticket) {
  if (files.has(id)) return
  const state = createFileState(id, ticket)
  files.set(id, state)
  let stage = 'connect-dc'
  try {
    const requestClient = await ensureClient(ticket)
    stage = 'read-initial-chunk'
    state.initialChunk = await requestClient.getFile(ticket.file, 0, 4096)
    if (!state.initialChunk.length) throw new Error('Telegram returned an empty media file')
    if (
      (ticket.mime_type ?? '').toLowerCase().startsWith('video/mp4') &&
      (state.initialChunk.length < 12 ||
        new TextDecoder().decode(state.initialChunk.subarray(4, 8)) !== 'ftyp')
    ) {
      throw new Error('Telegram returned an invalid video file')
    }
    const declaredSize = ticket.size ?? (ticket.file.size ? ticket.file.size : null)
    scope.postMessage({ type: 'ready', id, size: declaredSize })
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    // A connect failure is worker-wide (id null → main thread tears the whole
    // worker down); a file failure only rejects this file's opener.
    postError(
      stage === 'connect-dc' ? null : id,
      new Error(`${message} [${stage}, dc ${ticket.dc_id}]`),
    )
    files.delete(id)
  }
}

async function read(fileId: string, value: ReadMessage) {
  const state = files.get(fileId)
  const requestClient = client
  if (!state || !requestClient) throw new Error('Video worker is not ready')
  const purpose = value.purpose ?? 'playback'
  if (purpose === 'playback') state.rangeRequests += 1
  const startOffset = Math.max(0, value.offset)
  const requestedLimit = Math.min(TELEGRAM_CHUNK_SIZE, Math.max(1, value.limit))
  const output = new Uint8Array(requestedLimit)
  let written = 0
  while (written < requestedLimit) {
    const currentOffset = startOffset + written
    if (currentOffset < state.initialChunk.length) {
      const available = Math.min(
        state.initialChunk.length - currentOffset,
        requestedLimit - written,
      )
      output.set(state.initialChunk.subarray(currentOffset, currentOffset + available), written)
      written += available
      continue
    }
    const alignedOffset = Math.floor(currentOffset / TELEGRAM_CHUNK_SIZE) * TELEGRAM_CHUNK_SIZE
    const leading = currentOffset - alignedOffset
    const chunk = await requestChunk(fileId, alignedOffset, purpose)
    if (chunk.length <= leading) break
    const available = Math.min(chunk.length - leading, requestedLimit - written)
    output.set(chunk.subarray(leading, leading + available), written)
    written += available
    if (chunk.length < TELEGRAM_CHUNK_SIZE) break
  }
  const bytes = output.slice(0, written)
  state.bytesServed += bytes.length
  scope.postMessage({ type: 'chunk', id: value.id, offset: startOffset, bytes }, [bytes.buffer])
  if (purpose === 'playback') preloadChunks(state, startOffset + written)
}

function postStats(fileId: string, id: number) {
  const state = files.get(fileId)
  if (!state) {
    postError(id, new Error('Resource file is not ready'))
    return
  }
  const now = performance.now()
  trimTransfers(state, now)
  const cachedBuckets = new Set<number>()
  let cachedBytes = 0
  for (const [offset, chunk] of state.chunkCache) {
    cachedBytes += chunk.length
    cachedBuckets.add(heatmapIndex(state, offset))
  }
  const oldestTransfer = state.recentTransfers[0]
  const transferWindow = oldestTransfer ? Math.max(1_000, now - oldestTransfer.at) : 1_000
  const recentBytes = state.recentTransfers.reduce((sum, transfer) => sum + transfer.bytes, 0)
  scope.postMessage({
    type: 'stats',
    id,
    stats: {
      connected: Boolean(client),
      connectedForMs: connectedAt ? now - connectedAt : 0,
      networkRequests: state.networkRequests,
      rangeRequests: state.rangeRequests,
      bytesDownloaded: state.bytesDownloaded,
      bytesServed: state.bytesServed,
      cacheHits: state.cacheHits,
      deduplicatedRequests: state.deduplicatedRequests,
      cacheChunks: state.chunkCache.size,
      cachedBytes,
      activeRequests: state.pendingChunks.size,
      averageLatencyMs: state.networkRequests ? state.latencyTotal / state.networkRequests : 0,
      lastLatencyMs: state.lastLatency,
      maxLatencyMs: state.maxLatency,
      throughputBps: (recentBytes * 1_000) / transferWindow,
      networkActivityBytes: recentBytes,
      errors: state.errors,
      lastError: state.lastError,
      heatmap: Array.from(state.heatmapAccesses, (accesses, index) => ({
        accesses,
        downloads: state.heatmapDownloads[index],
        cached: cachedBuckets.has(index),
      })),
    },
  })
}

function closeFile(fileId: string) {
  const state = files.get(fileId)
  if (!state) return
  clearChunkCache(state)
  state.initialChunk.fill(0)
  state.initialChunk = new Uint8Array()
  files.delete(fileId)
}

function close() {
  for (const state of files.values()) {
    clearChunkCache(state)
    state.initialChunk.fill(0)
  }
  files.clear()
  client?.close()
  client = null
  connectPromise = null
  scope.postMessage({ type: 'closed' })
}

scope.onmessage = (event) => {
  const value = event.data
  if (value.type === 'init' || value.type === 'open') void openFile(value.id, value.ticket)
  else if (value.type === 'read') {
    void read(value.file, value).catch((error: unknown) => {
      const state = files.get(value.file)
      if (state) {
        state.errors += 1
        state.lastError = error instanceof Error ? error.message : String(error)
      }
      postError(value.id, error)
    })
  } else if (value.type === 'stats') postStats(value.file, value.id)
  else if (value.type === 'close-file') closeFile(value.file)
  else if (value.type === 'close') close()
}

export {}
