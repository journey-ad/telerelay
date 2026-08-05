import { LoaderCircle } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, Dispatch, ReactNode, SetStateAction } from 'react'
import { ACCOUNT_ID_HEADER } from '../api/client'
import { authorization } from '../api/credentials'
import { cn } from '../utils/cn'

const MAX_CACHED_IMAGES = 200

type CacheEntry = {
  promise: Promise<string | null>
  url: string | null
  refs: number
}

// LRU 缓存：Map 保持插入顺序，load 命中时 touch 刷新为最新；
// 超出上限时淘汰最久未使用且无组件引用的条目并 revoke 其 blob URL。
const imageCache = new Map<string, CacheEntry>()

function cacheKey(path: string, accountId?: string): string {
  return `${accountId ?? ''}:${path}`
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

function load(path: string, accountId?: string): Promise<string | null> {
  const key = cacheKey(path, accountId)
  const cached = imageCache.get(key)
  if (cached) {
    touch(key)
    return cached.promise
  }

  const promise = (async () => {
    const headers = new Headers()
    const auth = authorization()
    if (auth) headers.set('Authorization', auth)
    if (accountId) headers.set(ACCOUNT_ID_HEADER, accountId)
    const response = await fetch(path, { headers })
    if (!response.ok) return null
    return URL.createObjectURL(await response.blob())
  })()
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

export function preloadAuthenticatedImage(
  path: string,
  accountId?: string,
): Promise<string | null> {
  return load(path, accountId)
}

function getResolvedUrl(path: string, accountId?: string): string | null {
  const entry = imageCache.get(cacheKey(path, accountId))
  return entry?.url ?? null
}

function isImageCached(path: string, accountId?: string): boolean {
  return imageCache.has(cacheKey(path, accountId))
}

function retain(path: string, accountId?: string) {
  const entry = imageCache.get(cacheKey(path, accountId))
  if (entry) entry.refs += 1
}

function release(path: string, accountId?: string) {
  const entry = imageCache.get(cacheKey(path, accountId))
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

function reload(path: string, accountId?: string) {
  return load(path, accountId).then((url) => (url ? { src: url, ready: false } : null))
}

export function AuthenticatedImage({
  path,
  thumbnailPath,
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
  path?: string | null
  thumbnailPath?: string | null
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
      : thumbnailPath
        ? (() => {
            const cached = getResolvedUrl(thumbnailPath, accountId)
            return cached ? { src: cached, ready: false } : null
          })()
        : null,
  )
  const [full, setFull] = useState<Layer>(() =>
    path
      ? (() => {
          const cached = getResolvedUrl(path, accountId)
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
    if (!node || (!path && !thumbnailPath)) return
    if (!('IntersectionObserver' in window)) {
      setInView(true)
      return
    }
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), {
      rootMargin: '240px',
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [path, thumbnailPath])

  useEffect(() => {
    if (path && inView && full?.src) retain(path, accountId)
    if (thumbnailPath && inView && thumb?.src) retain(thumbnailPath, accountId)
    return () => {
      if (path && inView && full?.src) release(path, accountId)
      if (thumbnailPath && inView && thumb?.src) release(thumbnailPath, accountId)
    }
  }, [path, thumbnailPath, accountId, inView, full?.src, thumb?.src])

  useEffect(() => {
    if (!path) return
    const cached = getResolvedUrl(path, accountId)
    if (cached) setFull((prev) => (prev?.src === cached ? prev : { src: cached, ready: false }))
  }, [path, accountId]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let active = true
    if (thumbnailPath) {
      const cached = getResolvedUrl(thumbnailPath, accountId)
      if (cached) {
        setThumb((prev) => (prev?.src === cached ? prev : { src: cached, ready: false }))
      } else if (inView) {
        if (inlineSource) {
          setThumb((prev) =>
            prev?.src === inlineSource ? prev : { src: inlineSource, ready: false },
          )
        }
        void load(thumbnailPath, accountId).then((url) => {
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
  }, [inlineSource, thumbnailPath, inView, accountId])

  useEffect(() => {
    let active = true
    if (path && inView) {
      if (isImageCached(path, accountId)) {
        setLoading(false)
        void load(path, accountId).then((url) => {
          if (active && url)
            setFull((prev) => (prev?.src === url ? prev : { src: url, ready: false }))
        })
      } else {
        setLoading(true)
        void load(path, accountId).then((url) => {
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
  }, [path, inView, accountId])

  // 重新进入视口时，若当前图已被 LRU 淘汰（blob 已 revoke），重新加载
  useEffect(() => {
    if (!inView) return
    if (path && fullRef.current?.src && getResolvedUrl(path, accountId) !== fullRef.current.src) {
      setFull(null)
      setLoading(true)
      void reload(path, accountId).then((next) => {
        if (next) setFull((prev) => (prev?.src === next.src ? prev : next))
        setLoading(false)
      })
    }
    if (
      thumbnailPath &&
      thumbRef.current?.src &&
      getResolvedUrl(thumbnailPath, accountId) !== thumbRef.current.src
    ) {
      setThumb(null)
      void reload(thumbnailPath, accountId).then((next) => {
        if (next) setThumb((prev) => (prev?.src === next.src ? prev : next))
      })
    }
  }, [inView, path, thumbnailPath, accountId])

  const showFallback = !(thumb && thumb.ready) && !(full && full.ready)
  const thumbRestored = Boolean(
    inlineSource || (thumbnailPath && getResolvedUrl(thumbnailPath, accountId)),
  )
  const fullRestored = Boolean(path && getResolvedUrl(path, accountId))
  const showBlur = blurred && (path ? !full : !(thumb?.ready ?? false))

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
