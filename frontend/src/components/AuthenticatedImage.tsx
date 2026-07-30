import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { authorization } from '../api/credentials'
import { cn } from '../utils/cn'

const objectUrls = new Map<string, Promise<string | null>>()

function load(path: string): Promise<string | null> {
  const cached = objectUrls.get(path)
  if (cached) return cached

  const promise = (async () => {
    const headers = new Headers()
    const auth = authorization()
    if (auth) headers.set('Authorization', auth)
    const response = await fetch(path, { headers })
    if (!response.ok) return null
    return URL.createObjectURL(await response.blob())
  })()
    .catch(() => null)
    .then((url) => {
      if (!url) objectUrls.delete(path)
      return url
    })
  objectUrls.set(path, promise)
  return promise
}

export function clearAuthenticatedImages() {
  for (const promise of objectUrls.values()) {
    void promise.then((url) => {
      if (url) URL.revokeObjectURL(url)
    })
  }
  objectUrls.clear()
}

export function AuthenticatedImage({
  path,
  inlineSource,
  alt,
  className,
  style,
  fallback,
}: {
  path?: string | null
  inlineSource?: string | null
  alt: string
  className?: string
  style?: CSSProperties
  fallback?: ReactNode
}) {
  const [source, setSource] = useState<string | null>(null)
  const [nearViewport, setNearViewport] = useState(false)
  const containerRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    const node = containerRef.current
    if (!node || !path) return
    if (!('IntersectionObserver' in window)) {
      setNearViewport(true)
      return
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setNearViewport(true)
          observer.disconnect()
        }
      },
      { rootMargin: '240px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [path])

  useEffect(() => {
    let active = true
    setSource(inlineSource ?? null)
    if (path && nearViewport) {
      void load(path).then((url) => {
        if (active) setSource(url)
      })
    }
    return () => {
      active = false
    }
  }, [inlineSource, nearViewport, path])

  return (
    <span
      ref={containerRef}
      className={cn('relative block overflow-hidden', className)}
      style={style}
    >
      {fallback}
      {source ? (
        <img
          src={source}
          alt={alt}
          className="absolute inset-0 size-full object-cover"
          onError={() => setSource(null)}
        />
      ) : null}
    </span>
  )
}
