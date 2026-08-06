import { LoaderCircle } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, Dispatch, ReactNode, SetStateAction } from 'react'
import { cn } from '../utils/cn'
import { loadDirectResourceBlob, type ResourceRef } from '../utils/resource'

const MAX_CACHED_IMAGES = 200

type CacheEntry = {
  promise: Promise<string | null>
  url: string | null
  refs: number
}

// LRU cache of blob URLs: Map keeps insertion order, a load hit touches to
// refresh recency; when over the limit, evict the least recently used entry
// with no component references and revoke its blob URL.
const imageCache = new Map<string, CacheEntry>()

function cacheKey(ref: ResourceRef, accountId?: string): string {
  return `${accountId ?? ''}:${JSON.stringify(ref)}`
}

function touch(key: string) {
  const entry = imageCache.get(key)
  if (!entry) return
  imageCache.delete(key)
  imageCache.set(key, entry)
}

function evictIfNeeded() {
  for (const [key, entry] of imageCache) {
    if (imageCache.size <= MAX_CACHED_IMAGES) break
    if (entry.refs > 0 || !entry.url) continue
    imageCache.delete(key)
    URL.revokeObjectURL(entry.url)
  }
}

function load(ref: ResourceRef, accountId?: string): Promise<string | null> {
  const key = cacheKey(ref, accountId)
  const cached = imageCache.get(key)
  if (cached) {
    touch(key)
    return cached.promise
  }
  if (!accountId) return Promise.resolve(null)

  const promise = loadDirectResourceBlob(accountId, ref)
    .then((blob) => (blob ? URL.createObjectURL(blob) : null))
    .catch(() => null)
    .then((url) => {
      const entry = imageCache.get(key)
      if (!entry) return url
      if (url) {
        entry.url = url
        touch(key)
        evictIfNeeded()
      } else {
        imageCache.delete(key)
      }
      return url
    })
  imageCache.set(key, { promise, url: null, refs: 0 })
  return promise
}

export function preloadAuthenticatedImage(media: ResourceRef, accountId?: string) {
  return load(media, accountId)
}

function getResolvedUrl(ref: ResourceRef, accountId?: string): string | null {
  const entry = imageCache.get(cacheKey(ref, accountId))
  return entry?.url ?? null
}

function isImageCached(ref: ResourceRef, accountId?: string): boolean {
  return imageCache.has(cacheKey(ref, accountId))
}

function retain(ref: ResourceRef, accountId?: string) {
  const entry = imageCache.get(cacheKey(ref, accountId))
  if (entry) entry.refs += 1
}

function release(ref: ResourceRef, accountId?: string) {
  const entry = imageCache.get(cacheKey(ref, accountId))
  if (entry) entry.refs = Math.max(0, entry.refs - 1)
}

export function clearAuthenticatedImages() {
  for (const entry of imageCache.values()) {
    if (entry.url) URL.revokeObjectURL(entry.url)
  }
  imageCache.clear()
}

type Layer = { src: string; ready: boolean } | null

function markReady(setter: Dispatch<SetStateAction<Layer>>): () => void {
  return () => setter((prev) => (prev ? { ...prev, ready: true } : prev))
}

function reload(ref: ResourceRef, accountId?: string) {
  return load(ref, accountId).then((url) => (url ? { src: url, ready: false } : null))
}

export function AuthenticatedImage({
  media,
  thumbnailMedia,
  inlineSource,
  alt,
  className,
  style,
  fallback,
  accountId,
  blurred = false,
  spinnerWhileLoading = false,
  isVideo = false,
  fit = 'cover',
  onFullImageLoad,
}: {
  media?: ResourceRef | null
  thumbnailMedia?: ResourceRef | null
  inlineSource?: string | null
  alt: string
  className?: string
  style?: CSSProperties
  fallback?: ReactNode
  accountId?: string
  blurred?: boolean
  spinnerWhileLoading?: boolean
  isVideo?: boolean
  fit?: 'cover' | 'contain'
  onFullImageLoad?: (image: HTMLImageElement) => void
}) {
  const [thumb, setThumb] = useState<Layer>(() =>
    inlineSource
      ? { src: inlineSource, ready: false }
      : thumbnailMedia && accountId
        ? (() => {
            const cached = getResolvedUrl(thumbnailMedia, accountId)
            return cached ? { src: cached, ready: false } : null
          })()
        : null,
  )
  const [full, setFull] = useState<Layer>(() =>
    media && accountId
      ? (() => {
          const cached = getResolvedUrl(media, accountId)
          return cached ? { src: cached, ready: false } : null
        })()
      : null,
  )
  const [loading, setLoading] = useState(false)
  const [inView, setInView] = useState(false)
  const containerRef = useRef<HTMLSpanElement>(null)
  const fullRef = useRef(full)
  fullRef.current = full
  const thumbRef = useRef(thumb)
  thumbRef.current = thumb

  useEffect(() => {
    const node = containerRef.current
    if (!node || (!media && !thumbnailMedia)) return
    if (!('IntersectionObserver' in window)) {
      setInView(true)
      return
    }
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), {
      rootMargin: '240px',
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [media, thumbnailMedia])

  useEffect(() => {
    if (media && inView && full?.src) retain(media, accountId)
    if (thumbnailMedia && inView && thumb?.src) retain(thumbnailMedia, accountId)
    return () => {
      if (media && inView && full?.src) release(media, accountId)
      if (thumbnailMedia && inView && thumb?.src) release(thumbnailMedia, accountId)
    }
  }, [media, thumbnailMedia, accountId, inView, full?.src, thumb?.src])

  useEffect(() => {
    if (!media || !accountId) return
    const cached = getResolvedUrl(media, accountId)
    if (cached) setFull((prev) => (prev?.src === cached ? prev : { src: cached, ready: false }))
  }, [media, accountId]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let active = true
    if (thumbnailMedia && accountId) {
      const cached = getResolvedUrl(thumbnailMedia, accountId)
      if (cached) {
        setThumb((prev) => (prev?.src === cached ? prev : { src: cached, ready: false }))
      } else if (inView) {
        if (inlineSource) {
          setThumb((prev) =>
            prev?.src === inlineSource ? prev : { src: inlineSource, ready: false },
          )
        }
        void load(thumbnailMedia, accountId).then((url) => {
          if (active && url)
            setThumb((prev) => (prev?.src === url ? prev : { src: url, ready: false }))
        })
      } else if (inlineSource) {
        setThumb((prev) =>
          prev?.src === inlineSource ? prev : { src: inlineSource, ready: false },
        )
      } else {
        setThumb(null)
      }
    } else if (inlineSource) {
      setThumb((prev) => (prev?.src === inlineSource ? prev : { src: inlineSource, ready: false }))
    } else {
      setThumb(null)
    }
    return () => {
      active = false
    }
  }, [inlineSource, thumbnailMedia, inView, accountId])

  useEffect(() => {
    let active = true
    if (media && accountId && inView) {
      if (isImageCached(media, accountId)) {
        setLoading(false)
        void load(media, accountId).then((url) => {
          if (active && url)
            setFull((prev) => (prev?.src === url ? prev : { src: url, ready: false }))
        })
      } else {
        setLoading(true)
        void load(media, accountId).then((url) => {
          if (active) {
            if (url) setFull((prev) => (prev?.src === url ? prev : { src: url, ready: false }))
            setLoading(false)
          }
        })
      }
    } else {
      setLoading(false)
    }
    return () => {
      active = false
    }
  }, [media, inView, accountId])

  // When the image re-enters the viewport, reload it if the LRU cache already
  // evicted it (its blob URL was revoked)
  useEffect(() => {
    if (!inView) return
    if (
      media &&
      accountId &&
      fullRef.current?.src &&
      getResolvedUrl(media, accountId) !== fullRef.current.src
    ) {
      setFull(null)
      setLoading(true)
      void reload(media, accountId).then((next) => {
        if (next) setFull((prev) => (prev?.src === next.src ? prev : next))
        setLoading(false)
      })
    }
    if (
      thumbnailMedia &&
      accountId &&
      thumbRef.current?.src &&
      getResolvedUrl(thumbnailMedia, accountId) !== thumbRef.current.src
    ) {
      setThumb(null)
      void reload(thumbnailMedia, accountId).then((next) => {
        if (next) setThumb((prev) => (prev?.src === next.src ? prev : next))
      })
    }
  }, [inView, media, thumbnailMedia, accountId])

  const showFallback = !(thumb && thumb.ready) && !(full && full.ready)
  const thumbRestored = Boolean(
    inlineSource || (thumbnailMedia && accountId && getResolvedUrl(thumbnailMedia, accountId)),
  )
  const fullRestored = Boolean(media && accountId && getResolvedUrl(media, accountId))
  const showBlur = blurred && (media ? !full : !(thumb?.ready ?? false))

  return (
    <span
      ref={containerRef}
      className={cn('relative block overflow-hidden', className)}
      style={style}
    >
      {showFallback ? fallback : null}
      {thumb && (!full || !full.ready) ? (
        <img
          key={thumb.src}
          src={thumb.src}
          alt={alt}
          className={cn(
            'absolute inset-0 size-full',
            fit === 'contain' ? 'object-contain' : 'object-cover',
            !thumbRestored && 'transition-opacity duration-300 ease-out',
            showBlur && 'scale-110 blur-lg',
            thumb.ready ? 'opacity-100' : 'opacity-0',
          )}
          onLoad={markReady(setThumb)}
          onError={() => setThumb(null)}
        />
      ) : null}
      {loading && spinnerWhileLoading ? (
        <span className="absolute inset-0 grid place-items-center">
          <span className="grid size-8 place-items-center rounded-full bg-white/70 shadow">
            <LoaderCircle size={18} className="animate-spin text-slate-600" />
          </span>
        </span>
      ) : null}
      {full ? (
        isVideo ? (
          <video
            key={full.src}
            src={full.src}
            className={cn(
              'absolute inset-0 size-full',
              fit === 'contain' ? 'object-contain' : 'object-cover',
              !fullRestored && 'transition-opacity duration-400 ease-out',
              full.ready ? 'opacity-100' : 'opacity-0',
            )}
            autoPlay
            loop
            muted
            playsInline
            preload="auto"
            onCanPlay={markReady(setFull)}
            onError={() => setFull(null)}
          />
        ) : (
          <img
            key={full.src}
            src={full.src}
            alt={alt}
            className={cn(
              'absolute inset-0 size-full',
              fit === 'contain' ? 'object-contain' : 'object-cover',
              !fullRestored && 'transition-opacity duration-400 ease-out',
              full.ready ? 'opacity-100' : 'opacity-0',
            )}
            onLoad={(event) => {
              markReady(setFull)()
              onFullImageLoad?.(event.currentTarget)
            }}
            onError={() => setFull(null)}
          />
        )
      ) : null}
    </span>
  )
}
