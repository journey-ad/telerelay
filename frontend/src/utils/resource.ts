/**
 * Media references resolved browser-direct: a message media (full file or
 * thumbnail) or a peer avatar. Bytes flow through the service worker + web
 * worker straight from the Telegram DC; small files are cached in IndexedDB.
 */

import { accountRequest, ApiError } from '../api/client'
import {
  openTelegramResourceSession,
  readSessionBlob,
  type TelegramResourceSession,
} from '../api/telegramResource'
import type { TelegramResourceInfo } from '../types'
import { getCachedResource, putCachedResource, type CachedResource } from './resourceCache'

export type ResourceRef =
  | { kind: 'message-media'; chatId: number; messageId: number; thumb?: boolean }
  | { kind: 'peer-avatar'; peerId: number }

export function messageResourceRef(chatId: number, messageId: number, thumb = false): ResourceRef {
  return { kind: 'message-media', chatId, messageId, thumb }
}

export function peerAvatarRef(peerId: number): ResourceRef {
  return { kind: 'peer-avatar', peerId }
}

/** Deterministic key for message media (no ticket round-trip needed to look up). */
export function resourceCacheKey(accountId: string, ref: ResourceRef): string {
  if (ref.kind === 'message-media') {
    return `${accountId}:msg:${ref.chatId}:${ref.messageId}:${ref.thumb ? 't' : 'f'}`
  }
  return `${accountId}:avatar:${ref.peerId}`
}

/**
 * Avatars use a deterministic key (peer id) plus a TTL instead of an
 * in-memory photo_id version map: the version map would be lost on reload and
 * force every avatar through a fresh ticket + worker download. A stale avatar
 * (older than a day) is re-resolved through a fresh ticket on the next load.
 */
const AVATAR_CACHE_TTL_MS = 24 * 60 * 60 * 1000

/**
 * Peers known to have no avatar for this session. A 404 is a normal business
 * outcome (the avatar falls back to initials), but repeating the request on
 * every viewport re-entry is wasteful; the set resets on page reload so a
 * newly added avatar is picked up on the next visit.
 */
const noAvatarPeers = new Set<string>()

function noAvatarKey(accountId: string, ref: ResourceRef): string {
  return ref.kind === 'peer-avatar' ? `${accountId}:${ref.peerId}` : ''
}

export async function requestResourceInfo(
  accountId: string,
  ref: ResourceRef,
): Promise<TelegramResourceInfo> {
  if (ref.kind === 'message-media') {
    const query = ref.thumb ? '?thumb=true' : ''
    return accountRequest<TelegramResourceInfo>(
      accountId,
      `/api/v1/telegram-preview/chats/${ref.chatId}/messages/${ref.messageId}/resource-info${query}`,
      { method: 'POST' },
    )
  }
  return accountRequest<TelegramResourceInfo>(
    accountId,
    `/api/v1/telegram-preview/peers/${ref.peerId}/avatar-info`,
    { method: 'POST' },
  )
}

function resolvedCacheKey(accountId: string, ref: ResourceRef): string {
  return resourceCacheKey(accountId, ref)
}

/**
 * Avatar blobs use a deterministic key plus TTL. A stale avatar is never
 * dropped synchronously: the old blob keeps being served while a fresh copy is
 * fetched in the background and replaces it on success (stale-while-revalidate).
 */
function isAvatarStale(ref: ResourceRef, entry: CachedResource): boolean {
  return ref.kind === 'peer-avatar' && Date.now() - entry.storedAt > AVATAR_CACHE_TTL_MS
}

/** Keys with a background refresh already in flight (dedupe concurrent loads). */
const refreshingKeys = new Set<string>()
/** In-flight downloads per key so concurrent consumers share one worker session. */
const pendingDownloads = new Map<string, Promise<Blob | null>>()

/**
 * Load a media blob by connecting directly to the Telegram DC. A fresh cache
 * hit needs no ticket at all; a stale avatar returns the cached blob
 * immediately and revalidates in the background.
 */
export async function loadDirectResourceBlob(
  accountId: string,
  ref: ResourceRef,
): Promise<Blob | null> {
  if (noAvatarKey(accountId, ref) && noAvatarPeers.has(noAvatarKey(accountId, ref))) return null
  const key = resolvedCacheKey(accountId, ref)
  const cached = await getCachedResource(key)
  if (cached) {
    if (isAvatarStale(ref, cached)) void refreshStaleMedia(accountId, ref, key)
    return cached.blob
  }
  const inFlight = pendingDownloads.get(key)
  if (inFlight) return inFlight
  const download = downloadMediaBlob(accountId, ref, key)
  pendingDownloads.set(key, download)
  try {
    return await download
  } finally {
    pendingDownloads.delete(key)
  }
}

async function downloadMediaBlob(
  accountId: string,
  ref: ResourceRef,
  key: string,
): Promise<Blob | null> {
  let info: TelegramResourceInfo | null = null
  try {
    info = await requestResourceInfo(accountId, ref)
  } catch (error) {
    // A 404 for avatar-info simply means the peer has no avatar; the avatar
    // falls back to initials, which is a normal business outcome. Remember it
    // for the session so viewport re-entry does not repeat the request, and do
    // not log it as an error.
    if (error instanceof ApiError && error.code === 'avatar_not_found') {
      const key = noAvatarKey(accountId, ref)
      if (key) noAvatarPeers.add(key)
      return null
    }
    console.error('Telegram media info failed', error)
    return null
  }
  const fresh = await getCachedResource(key)
  if (fresh && !isAvatarStale(ref, fresh)) return fresh.blob

  for (let attempt = 0; attempt < 2; attempt += 1) {
    let session: TelegramResourceSession | null = null
    try {
      session = await openTelegramResourceSession(accountId, info)
      try {
        const blob = await readSessionBlob(session)
        void putCachedResource(key, blob, session.mimeType).catch(() => undefined)
        return blob
      } finally {
        // The worker + DC WebSocket + in-memory auth key are only needed for
        // the transfer; release them as soon as the blob is in hand so
        // sessions do not accumulate for every avatar/thumbnail viewed.
        session.close()
      }
    } catch (error) {
      if (attempt === 0) {
        // Network/DC hiccup (e.g. the kws WebSocket dropping): retry once with
        // freshly issued file info after a short backoff.
        await new Promise((resolve) => setTimeout(resolve, 600))
        try {
          info = await requestResourceInfo(accountId, ref)
        } catch (infoError) {
          console.error('Telegram media info failed on retry', infoError)
          return null
        }
        continue
      }
      console.error('Telegram media download failed', error)
      return null
    }
  }
  return null
}

/**
 * Fetch a fresh avatar in the background and replace the cached copy. Failures
 * are silent: the old (stale) blob stays in the cache for the next load.
 */
async function refreshStaleMedia(accountId: string, ref: ResourceRef, key: string): Promise<void> {
  if (refreshingKeys.has(key)) return
  refreshingKeys.add(key)
  try {
    await downloadMediaBlob(accountId, ref, key)
  } finally {
    refreshingKeys.delete(key)
  }
}

/**
 * Forget all in-memory resource state (no-avatar peers, in-flight download
 * dedupe, background refresh guards). Used on sign-out so a different account
 * does not inherit stale lookups or rejoin half-finished downloads.
 */
export function resetResourceState(): void {
  noAvatarPeers.clear()
  refreshingKeys.clear()
  pendingDownloads.clear()
}
