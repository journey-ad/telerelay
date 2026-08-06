/**
 * IndexedDB-backed cache for Telegram media blobs (avatars, thumbnails,
 * posters, and full images). Bounded by RESOURCE_CACHE_LIMIT_BYTES with an
 * LRU-style eviction driven by lastAccessed. A future cache-management UI can
 * use getMediaCacheStats / clearMediaCache.
 */

const DB_NAME = 'telerelay-media-cache'
const STORE_NAME = 'files'

export const RESOURCE_CACHE_LIMIT_BYTES = 2 * 1024 * 1024 * 1024 // 2 GiB

export interface CachedResource {
  blob: Blob
  mimeType: string
  size: number
  storedAt: number
  lastAccessed: number
}

let database: IDBDatabase | null = null

function openDatabase(): Promise<IDBDatabase> {
  if (database) return Promise.resolve(database)
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        request.result.createObjectStore(STORE_NAME)
      }
    }
    request.onsuccess = () => {
      database = request.result
      database.onversionchange = () => {
        database?.close()
        database = null
      }
      resolve(database)
    }
    request.onerror = () => reject(request.error ?? new Error('Media cache could not be opened'))
  })
}

function withStore<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  return openDatabase().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const transaction = db.transaction(STORE_NAME, mode)
        const request = run(transaction.objectStore(STORE_NAME))
        request.onsuccess = () => resolve(request.result)
        request.onerror = () => reject(request.error ?? new Error('Media cache request failed'))
      }),
  )
}

export async function getCachedResource(key: string): Promise<CachedResource | null> {
  try {
    const entry = await withStore(
      'readonly',
      (store) => store.get(key) as IDBRequest<CachedResource>,
    )
    if (!entry) return null
    entry.lastAccessed = Date.now()
    // Touch asynchronously; a failure must not break the read path.
    void withStore('readwrite', (store) => store.put(entry, key)).catch(() => undefined)
    return entry
  } catch {
    return null
  }
}

export async function putCachedResource(key: string, blob: Blob, mimeType: string): Promise<void> {
  const now = Date.now()
  const entry: CachedResource = {
    blob,
    mimeType,
    size: blob.size,
    storedAt: now,
    lastAccessed: now,
  }
  try {
    await withStore('readwrite', (store) => store.put(entry, key))
  } catch {
    // Quota exceeded: drop the least recently used entries, then retry once.
    await pruneToLimit(Math.floor(RESOURCE_CACHE_LIMIT_BYTES * 0.9))
    await withStore('readwrite', (store) => store.put(entry, key))
  }
  void maybePrune()
}

let lastPruneAt = 0

async function maybePrune(): Promise<void> {
  const now = Date.now()
  if (now - lastPruneAt < 30_000) return
  lastPruneAt = now
  try {
    const total = await totalBytes()
    if (total > RESOURCE_CACHE_LIMIT_BYTES) await pruneToLimit(RESOURCE_CACHE_LIMIT_BYTES)
  } catch {
    // Cache maintenance must never break media display.
  }
}

async function totalBytes(): Promise<number> {
  const db = await openDatabase()
  return new Promise((resolve, reject) => {
    let total = 0
    const transaction = db.transaction(STORE_NAME, 'readonly')
    const request = transaction.objectStore(STORE_NAME).openCursor()
    request.onsuccess = () => {
      const cursor = request.result
      if (cursor) {
        total += (cursor.value as CachedResource).size
        cursor.continue()
      } else {
        resolve(total)
      }
    }
    request.onerror = () => reject(request.error ?? new Error('Media cache scan failed'))
  })
}

async function pruneToLimit(limit: number): Promise<void> {
  const db = await openDatabase()
  const entries: Array<{ key: IDBValidKey; size: number; lastAccessed: number }> = []
  await new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, 'readonly')
    const request = transaction.objectStore(STORE_NAME).openCursor()
    request.onsuccess = () => {
      const cursor = request.result
      if (cursor) {
        const value = cursor.value as CachedResource
        entries.push({ key: cursor.key, size: value.size, lastAccessed: value.lastAccessed })
        cursor.continue()
      } else {
        resolve()
      }
    }
    request.onerror = () => reject(request.error ?? new Error('Media cache scan failed'))
  })
  entries.sort((a, b) => a.lastAccessed - b.lastAccessed)
  let total = entries.reduce((sum, entry) => sum + entry.size, 0)
  await new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, 'readwrite')
    const store = transaction.objectStore(STORE_NAME)
    for (const entry of entries) {
      if (total <= limit) break
      store.delete(entry.key)
      total -= entry.size
    }
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error ?? new Error('Media cache prune failed'))
  })
}

/** Statistics for a future cache-management screen. */
export async function getMediaCacheStats(): Promise<{ count: number; bytes: number }> {
  const db = await openDatabase()
  return new Promise((resolve, reject) => {
    let count = 0
    let bytes = 0
    const transaction = db.transaction(STORE_NAME, 'readonly')
    const request = transaction.objectStore(STORE_NAME).openCursor()
    request.onsuccess = () => {
      const cursor = request.result
      if (cursor) {
        count += 1
        bytes += (cursor.value as CachedResource).size
        cursor.continue()
      } else {
        resolve({ count, bytes })
      }
    }
    request.onerror = () => reject(request.error ?? new Error('Media cache scan failed'))
  })
}

/** Clear every cached media blob (future cache-management UI). */
export async function clearMediaCache(): Promise<void> {
  await withStore('readwrite', (store) => store.clear())
}
