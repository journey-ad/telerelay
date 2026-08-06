/// <reference lib="webworker" />

import { TelegramMtprotoClient, decodeBase64Url, randomSessionId } from './telegramMtprotoClient'

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
  file: {
    id: string
    access_hash: string
    file_reference: string
    size?: number | null
  }
  size?: number | null
}

type InitMessage = {
  type: 'init'
  ticket: Ticket
}

type ReadMessage = {
  type: 'read'
  id: number
  offset: number
  limit: number
  purpose?: 'playback' | 'metadata'
}
type StatsMessage = { type: 'stats'; id: number }
type CloseMessage = { type: 'close' }

const scope = self as unknown as {
  onmessage:
    ((event: MessageEvent<InitMessage | ReadMessage | StatsMessage | CloseMessage>) => void) | null
  postMessage(message: unknown, transfer?: Transferable[]): void
}

let client: TelegramMtprotoClient | null = null
let ticket: Ticket | null = null
let active = false
let initialChunk: Uint8Array<ArrayBufferLike> = new Uint8Array()
const TELEGRAM_CHUNK_SIZE = 512 * 1024
const PRELOAD_SIZE = 20 * 1024 * 1024
const PRELOAD_CONCURRENCY = 3
const MAX_CACHED_CHUNKS = PRELOAD_SIZE / TELEGRAM_CHUNK_SIZE + PRELOAD_CONCURRENCY + 2
const chunkCache = new Map<number, Uint8Array<ArrayBufferLike>>()
const pendingChunks = new Map<number, Promise<Uint8Array<ArrayBufferLike>>>()
const HEATMAP_BUCKETS = 32
const heatmapAccesses = new Uint32Array(HEATMAP_BUCKETS)
const heatmapDownloads = new Uint32Array(HEATMAP_BUCKETS)
const recentTransfers: Array<{ at: number; bytes: number }> = []
let preloadGeneration = 0
let preloadStart = -1
let preloadEnd = -1
let connectedAt = 0
let networkRequests = 0
let rangeRequests = 0
let bytesDownloaded = 0
let bytesServed = 0
let cacheHits = 0
let deduplicatedRequests = 0
let latencyTotal = 0
let lastLatency = 0
let maxLatency = 0
let errors = 0
let lastError = ''

function postError(id: number | null, error: unknown) {
  const message = error instanceof Error ? error.message : String(error)
  errors += 1
  lastError = message
  scope.postMessage({ type: 'error', id, message })
}

function totalSize() {
  return ticket?.size ?? ticket?.file.size ?? 0
}

function heatmapIndex(offset: number) {
  const size = totalSize()
  return size > 0 ? Math.min(HEATMAP_BUCKETS - 1, Math.floor((offset / size) * HEATMAP_BUCKETS)) : 0
}

function trimTransfers(now: number) {
  while (recentTransfers[0] && recentTransfers[0].at < now - 10_000) recentTransfers.shift()
}

function clearChunkCache() {
  for (const chunk of chunkCache.values()) chunk.fill(0)
  chunkCache.clear()
  pendingChunks.clear()
  preloadGeneration += 1
  preloadStart = -1
  preloadEnd = -1
}

function rememberChunk(offset: number, chunk: Uint8Array<ArrayBufferLike>) {
  chunkCache.delete(offset)
  chunkCache.set(offset, chunk)
  while (chunkCache.size > MAX_CACHED_CHUNKS) {
    const oldestOffset = chunkCache.keys().next().value
    if (oldestOffset === undefined) break
    chunkCache.get(oldestOffset)?.fill(0)
    chunkCache.delete(oldestOffset)
  }
  return chunk
}

function requestChunk(
  offset: number,
  source: 'playback' | 'preload' | 'metadata',
): Promise<Uint8Array<ArrayBufferLike>> {
  if (source === 'playback') heatmapAccesses[heatmapIndex(offset)] += 1
  const cached = chunkCache.get(offset)
  if (cached) {
    chunkCache.delete(offset)
    chunkCache.set(offset, cached)
    if (source === 'playback') cacheHits += 1
    return Promise.resolve(cached)
  }
  const pending = pendingChunks.get(offset)
  if (pending) {
    if (source === 'playback') deduplicatedRequests += 1
    return pending
  }
  const requestClient = client
  const requestTicket = ticket
  if (!requestClient || !requestTicket || !active) {
    return Promise.reject(new Error('Video worker is not ready'))
  }
  const startedAt = performance.now()
  networkRequests += 1
  const request = requestClient
    .getFile(requestTicket.file, offset, TELEGRAM_CHUNK_SIZE)
    .then((chunk) => {
      if (!active || client !== requestClient || ticket !== requestTicket) {
        chunk.fill(0)
        throw new Error('Video worker was closed')
      }
      const now = performance.now()
      lastLatency = now - startedAt
      latencyTotal += lastLatency
      maxLatency = Math.max(maxLatency, lastLatency)
      bytesDownloaded += chunk.length
      heatmapDownloads[heatmapIndex(offset)] += 1
      recentTransfers.push({ at: now, bytes: chunk.length })
      trimTransfers(now)
      return rememberChunk(offset, chunk)
    })
    .finally(() => pendingChunks.delete(offset))
  pendingChunks.set(offset, request)
  return request
}

function preloadChunks(from: number) {
  const size = ticket?.size ?? ticket?.file.size ?? 0
  if (!active || !size) return
  const start = Math.floor(from / TELEGRAM_CHUNK_SIZE) * TELEGRAM_CHUNK_SIZE
  const end = Math.min(size, start + PRELOAD_SIZE)
  if (start >= preloadStart && start < preloadEnd - PRELOAD_SIZE / 2) return
  preloadStart = start
  preloadEnd = end
  const generation = ++preloadGeneration
  void (async () => {
    for (let offset = start; offset < end; offset += TELEGRAM_CHUNK_SIZE * PRELOAD_CONCURRENCY) {
      if (!active || generation !== preloadGeneration) return
      const batch: Promise<Uint8Array<ArrayBufferLike>>[] = []
      for (let index = 0; index < PRELOAD_CONCURRENCY; index += 1) {
        const chunkOffset = offset + index * TELEGRAM_CHUNK_SIZE
        if (chunkOffset < end) batch.push(requestChunk(chunkOffset, 'preload'))
      }
      await Promise.all(batch)
    }
  })().catch(() => {})
}

async function initialize(value: InitMessage) {
  if (active) return
  active = true
  ticket = value.ticket
  const sessionId = randomSessionId()
  let stage = 'connect-dc'
  try {
    const authKey = decodeBase64Url(ticket.auth_key)
    const expectedAuthKeyId = BigInt(ticket.auth_key_id)
    const serverSalt = BigInt(ticket.server_salt)
    ticket.auth_key = ''
    ticket.auth_key_id = ''
    ticket.server_salt = '0'
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
    stage = 'read-initial-chunk'
    initialChunk = await client.getFile(ticket.file, 0, 4096)
    if (!initialChunk.length) throw new Error('Telegram returned an empty video file')
    if (
      (ticket.mime_type ?? '').toLowerCase().startsWith('video/mp4') &&
      (initialChunk.length < 12 || new TextDecoder().decode(initialChunk.subarray(4, 8)) !== 'ftyp')
    ) {
      throw new Error('Telegram returned an invalid video file')
    }
    scope.postMessage({ type: 'ready', size: ticket.size ?? ticket.file.size ?? null })
  } catch (error) {
    active = false
    initialChunk.fill(0)
    initialChunk = new Uint8Array()
    client?.close()
    client = null
    ticket = null
    const message = error instanceof Error ? error.message : String(error)
    postError(null, new Error(`${message} [${stage}, dc ${value.ticket.dc_id}]`))
  }
}

async function read(value: ReadMessage) {
  if (!client || !ticket || !active) throw new Error('Video worker is not ready')
  const purpose = value.purpose ?? 'playback'
  if (purpose === 'playback') rangeRequests += 1
  const startOffset = Math.max(0, value.offset)
  const requestedLimit = Math.min(TELEGRAM_CHUNK_SIZE, Math.max(1, value.limit))
  const output = new Uint8Array(requestedLimit)
  let written = 0
  while (written < requestedLimit) {
    const currentOffset = startOffset + written
    if (currentOffset < initialChunk.length) {
      const available = Math.min(initialChunk.length - currentOffset, requestedLimit - written)
      output.set(initialChunk.subarray(currentOffset, currentOffset + available), written)
      written += available
      continue
    }
    const alignedOffset = Math.floor(currentOffset / TELEGRAM_CHUNK_SIZE) * TELEGRAM_CHUNK_SIZE
    const leading = currentOffset - alignedOffset
    const chunk = await requestChunk(alignedOffset, purpose)
    if (chunk.length <= leading) break
    const available = Math.min(chunk.length - leading, requestedLimit - written)
    output.set(chunk.subarray(leading, leading + available), written)
    written += available
    if (chunk.length < TELEGRAM_CHUNK_SIZE) break
  }
  const bytes = output.slice(0, written)
  bytesServed += bytes.length
  scope.postMessage({ type: 'chunk', id: value.id, offset: startOffset, bytes }, [bytes.buffer])
  if (purpose === 'playback') preloadChunks(startOffset + written)
}

function postStats(id: number) {
  const now = performance.now()
  trimTransfers(now)
  const cachedBuckets = new Set<number>()
  let cachedBytes = 0
  for (const [offset, chunk] of chunkCache) {
    cachedBytes += chunk.length
    cachedBuckets.add(heatmapIndex(offset))
  }
  const oldestTransfer = recentTransfers[0]
  const transferWindow = oldestTransfer ? Math.max(1_000, now - oldestTransfer.at) : 1_000
  const recentBytes = recentTransfers.reduce((sum, transfer) => sum + transfer.bytes, 0)
  scope.postMessage({
    type: 'stats',
    id,
    stats: {
      connected: active && Boolean(client),
      connectedForMs: connectedAt ? now - connectedAt : 0,
      networkRequests,
      rangeRequests,
      bytesDownloaded,
      bytesServed,
      cacheHits,
      deduplicatedRequests,
      cacheChunks: chunkCache.size,
      cachedBytes,
      activeRequests: pendingChunks.size,
      averageLatencyMs: networkRequests ? latencyTotal / networkRequests : 0,
      lastLatencyMs: lastLatency,
      maxLatencyMs: maxLatency,
      throughputBps: (recentBytes * 1_000) / transferWindow,
      networkActivityBytes: recentBytes,
      errors,
      lastError,
      heatmap: Array.from(heatmapAccesses, (accesses, index) => ({
        accesses,
        downloads: heatmapDownloads[index],
        cached: cachedBuckets.has(index),
      })),
    },
  })
}

function close() {
  active = false
  ticket = null
  clearChunkCache()
  initialChunk.fill(0)
  initialChunk = new Uint8Array()
  client?.close()
  client = null
  scope.postMessage({ type: 'closed' })
}

scope.onmessage = (event) => {
  const value = event.data
  if (value.type === 'init') void initialize(value)
  else if (value.type === 'read') {
    void read(value).catch((error: unknown) => postError(value.id, error))
  } else if (value.type === 'stats') postStats(value.id)
  else if (value.type === 'close') close()
}

export {}
