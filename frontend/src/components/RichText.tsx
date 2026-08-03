import type { ReactNode } from 'react'
import { cn } from '../utils/cn'

export type RichEntity = {
  type?: string | null
  offset: number
  length: number
  url?: string | null
}

function entityHref(
  type: string | null | undefined,
  raw: string,
  url?: string | null,
): string | null {
  if (url) return url
  switch (type) {
    case 'url':
      return raw
    case 'email':
      return `mailto:${raw}`
    case 'phone':
      return `tel:${raw.replace(/[^\d+]/g, '')}`
    default:
      return null
  }
}

export function RichText({
  text,
  entities,
  className,
}: {
  text: string
  entities?: RichEntity[] | null
  className?: string
}) {
  if (!entities?.length) return <p className={className}>{text}</p>
  const sorted = [...entities].sort((a, b) => a.offset - b.offset)
  const parts: ReactNode[] = []
  let cursor = 0
  for (const entity of sorted) {
    const start = Math.max(cursor, entity.offset)
    const end = entity.offset + entity.length
    if (end <= cursor) continue
    if (start > cursor) parts.push(text.slice(cursor, start))
    const raw = text.slice(start, end)
    if (raw) {
      const href = entityHref(entity.type, raw, entity.url)
      parts.push(
        href ? (
          <a
            key={`${start}-${end}`}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="linkified"
          >
            {raw}
          </a>
        ) : (
          raw
        ),
      )
    }
    cursor = end
  }
  if (cursor < text.length) parts.push(text.slice(cursor))
  return <p className={cn(className)}>{parts}</p>
}
