import * as DialogPrimitive from '@radix-ui/react-dialog'
import { ChevronLeft, ChevronRight, Image, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TelegramPreviewMessage } from '../../types'
import { cn } from '../../utils/cn'
import { type ImageGroup } from '../../utils/preview'
import { messageResourceRef } from '../../utils/resource'
import { AuthenticatedImage, preloadAuthenticatedImage } from '../AuthenticatedImage'

const GENERATED_THUMBNAIL_SIZE = 128
const SCALE_EPSILON = 0.001
const ACTUAL_SIZE_SCALE = 1
const ZOOMED_SCALE = 2
const MIN_VIEWPORT_FRACTION = 0.8
const MAX_VIEWPORT_FRACTION = 0.94
const MAX_ASPECT_DISTANCE = Math.log(3)
const LONG_IMAGE_MIN_RATIO = 0.56
const LONG_IMAGE_MAX_RATIO = 2
const LONG_IMAGE_WIDTH_FRACTION = 0.6

function createSquareThumbnail(image: HTMLImageElement): Promise<string | null> {
  const sourceWidth = image.naturalWidth
  const sourceHeight = image.naturalHeight
  if (!sourceWidth || !sourceHeight) return Promise.resolve(null)

  const sourceSize = Math.min(sourceWidth, sourceHeight)
  const sourceX = (sourceWidth - sourceSize) / 2
  const sourceY = (sourceHeight - sourceSize) / 2
  const canvas = document.createElement('canvas')
  canvas.width = GENERATED_THUMBNAIL_SIZE
  canvas.height = GENERATED_THUMBNAIL_SIZE
  const context = canvas.getContext('2d')
  if (!context) return Promise.resolve(null)
  context.imageSmoothingEnabled = true
  context.imageSmoothingQuality = 'high'
  context.drawImage(
    image,
    sourceX,
    sourceY,
    sourceSize,
    sourceSize,
    0,
    0,
    GENERATED_THUMBNAIL_SIZE,
    GENERATED_THUMBNAIL_SIZE,
  )

  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob ? URL.createObjectURL(blob) : null), 'image/webp', 0.82)
  })
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function resolveViewport(
  stageSize: { width: number; height: number },
  stageNode: HTMLDivElement | null,
): { width: number; height: number } {
  return {
    width: stageSize.width || stageNode?.clientWidth || window.innerWidth,
    height: stageSize.height || stageNode?.clientHeight || window.innerHeight,
  }
}

function sourceFrameFor(
  viewportW: number,
  viewportH: number,
  imageRatio: number,
  imageWidth?: number,
  longImage = false,
): { width: number; height: number } {
  const maxWidth = longImage ? viewportW * LONG_IMAGE_WIDTH_FRACTION : viewportW
  const width = imageWidth
    ? Math.min(maxWidth, imageWidth)
    : Math.min(maxWidth, viewportH * imageRatio)
  return { width, height: width / imageRatio }
}

function initialViewFor(
  viewportW: number,
  viewportH: number,
  imageRatio: number,
  imageWidth: number | undefined,
  longImage: boolean,
): { width: number; height: number; scale: number } {
  const frame = sourceFrameFor(viewportW, viewportH, imageRatio, imageWidth, longImage)
  if (longImage) return { ...frame, scale: 1 }
  const viewportRatio = viewportW / viewportH
  const aspectDistance = Math.abs(Math.log(frame.width / frame.height / viewportRatio))
  const progress = clamp(aspectDistance / MAX_ASPECT_DISTANCE, 0, 1)
  const viewportFraction =
    MIN_VIEWPORT_FRACTION + (MAX_VIEWPORT_FRACTION - MIN_VIEWPORT_FRACTION) * progress
  const fitScale = Math.min(viewportW / frame.width, viewportH / frame.height)
  return { ...frame, scale: Math.min(1, fitScale * viewportFraction) }
}

function initialOffsetFor(
  tallImage: boolean,
  frameHeight: number,
  scale: number,
  viewportHeight: number,
): { x: number; y: number } {
  return tallImage ? { x: 0, y: (frameHeight * scale - viewportHeight) / 2 } : { x: 0, y: 0 }
}

function resistOutside(value: number, limit: number, viewportSize: number): number {
  const distance = Math.abs(value)
  if (distance <= limit) return value
  const overflow = distance - limit
  const elasticity = 0.72
  const resisted = (overflow * viewportSize * elasticity) / (viewportSize + overflow * elasticity)
  return Math.sign(value) * (limit + resisted)
}

function wheelDeltaInPixels(event: WheelEvent, pageHeight: number): number {
  if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) return event.deltaY * 16
  if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) return event.deltaY * pageHeight
  return event.deltaY
}

export function ImageViewer({
  accountId,
  groups,
  groupIndex,
  itemIndex,
  hasNextPage,
  onNavigate,
  onLoadEarlier,
  onClose,
}: {
  accountId: string
  groups: ImageGroup[]
  groupIndex: number
  itemIndex: number
  hasNextPage: boolean
  onNavigate: (message: TelegramPreviewMessage) => void
  onLoadEarlier: () => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const group = groups[groupIndex]
  const message = group.items[itemIndex]
  const media = message?.media
  const closeLabel = t('telegramPreview.closePreview')
  const previousLabel = t('telegramPreview.previousImage')
  const nextLabel = t('telegramPreview.nextImage')

  const [scale, setScale] = useState(MIN_VIEWPORT_FRACTION)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [stageNode, setStageNode] = useState<HTMLDivElement | null>(null)
  const [stageSize, setStageSize] = useState({ width: 0, height: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [isSettling, setIsSettling] = useState(false)
  const [generatedThumbnails, setGeneratedThumbnails] = useState<Map<number, string>>(
    () => new Map(),
  )
  const scaleRef = useRef(MIN_VIEWPORT_FRACTION)
  const defaultScaleRef = useRef(MIN_VIEWPORT_FRACTION)
  const offsetRef = useRef({ x: 0, y: 0 })
  const wheelSettleTimerRef = useRef<number | null>(null)
  const generatedThumbnailUrlsRef = useRef<Map<number, string | null>>(new Map())
  const mountedRef = useRef(true)
  const dragRef = useRef<{
    pointerId: number
    startX: number
    startY: number
    offsetX: number
    offsetY: number
  } | null>(null)
  const isVideo = Boolean(
    media?.mime_type === 'video/webm' || media?.file_name?.toLowerCase().endsWith('.webm'),
  )
  const ratio =
    media?.width && media?.height && media.width > 0 && media.height > 0
      ? media.width / media.height
      : 16 / 9
  const sourceWidth = media?.width && media.width > 0 ? media.width : undefined
  const longImage = ratio < LONG_IMAGE_MIN_RATIO || ratio > LONG_IMAGE_MAX_RATIO
  const tallImage = ratio < LONG_IMAGE_MIN_RATIO
  const ratioRef = useRef(ratio)
  ratioRef.current = ratio

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      for (const url of generatedThumbnailUrlsRef.current.values()) {
        if (url) URL.revokeObjectURL(url)
      }
      generatedThumbnailUrlsRef.current.clear()
    }
  }, [])

  useEffect(() => {
    if (!stageNode) return
    const syncSize = () => {
      const width = stageNode.clientWidth
      const height = stageNode.clientHeight
      if (!width || !height) return
      setStageSize((current) =>
        current.width === width && current.height === height ? current : { width, height },
      )
      const previousDefault = defaultScaleRef.current
      const view = initialViewFor(width, height, ratioRef.current, sourceWidth, longImage)
      defaultScaleRef.current = view.scale
      if (Math.abs(scaleRef.current - previousDefault) < SCALE_EPSILON) {
        const nextOffset = initialOffsetFor(tallImage, view.height, view.scale, height)
        scaleRef.current = view.scale
        offsetRef.current = nextOffset
        setScale(view.scale)
        setOffset(nextOffset)
      }
    }
    syncSize()
    const observer = new ResizeObserver(syncSize)
    observer.observe(stageNode)
    return () => observer.disconnect()
  }, [stageNode, sourceWidth, longImage, tallImage])

  useEffect(() => {
    let active = true
    const decodingImages: HTMLImageElement[] = []
    for (const item of group.items) {
      if (!item.media?.is_visual_media) continue
      void preloadAuthenticatedImage(messageResourceRef(item.chat_id, item.id), accountId).then(
        (url) => {
          if (!active || !url) return
          const image = new window.Image()
          decodingImages.push(image)
          image.onload = () => {
            if (active) generateThumbnail(item.id, image)
          }
          image.src = url
        },
      )
    }
    return () => {
      active = false
      for (const image of decodingImages) image.onload = null
    }
  }, [accountId, group])

  useEffect(() => {
    const { width: viewportW, height: viewportH } = resolveViewport(stageSize, stageNode)
    const view = initialViewFor(viewportW, viewportH, ratioRef.current, sourceWidth, longImage)
    const initialOffset = initialOffsetFor(tallImage, view.height, view.scale, viewportH)
    setScale(view.scale)
    setOffset(initialOffset)
    scaleRef.current = view.scale
    defaultScaleRef.current = view.scale
    offsetRef.current = initialOffset
    if (wheelSettleTimerRef.current !== null) {
      window.clearTimeout(wheelSettleTimerRef.current)
      wheelSettleTimerRef.current = null
    }
    dragRef.current = null
    setIsDragging(false)
    setIsSettling(false)
  }, [message?.id])

  // Prefetch earlier messages when nearing the older-message pagination boundary
  // (within 3 groups of the edge)
  useEffect(() => {
    if (groupIndex <= 2 && hasNextPage) onLoadEarlier()
  }, [groupIndex, hasNextPage, onLoadEarlier])

  function boundsFor(nextScale: number): {
    maxX: number
    maxY: number
    viewportW: number
    viewportH: number
  } {
    const { width: viewportW, height: viewportH } = resolveViewport(stageSize, stageNode)
    const frame = sourceFrameFor(viewportW, viewportH, ratioRef.current, sourceWidth, longImage)
    const scaledW = frame.width * nextScale
    const scaledH = frame.height * nextScale
    return {
      maxX: Math.max(0, (scaledW - viewportW) / 2),
      maxY: Math.max(0, (scaledH - viewportH) / 2),
      viewportW,
      viewportH,
    }
  }

  function constrainedOffset(nextScale: number, nextOffset: { x: number; y: number }) {
    const { maxX, maxY } = boundsFor(nextScale)
    return {
      x: clamp(nextOffset.x, -maxX, maxX),
      y: clamp(nextOffset.y, -maxY, maxY),
    }
  }

  function updateView(
    nextScale: number,
    nextOffset: { x: number; y: number },
    mode: 'settle' | 'elastic' | 'zoom' = 'settle',
  ) {
    const { maxX, maxY, viewportW, viewportH } = boundsFor(nextScale)
    if (mode === 'elastic') {
      nextOffset = {
        x: resistOutside(nextOffset.x, maxX, viewportW),
        y: resistOutside(nextOffset.y, maxY, viewportH),
      }
    } else {
      nextOffset = constrainedOffset(nextScale, nextOffset)
    }
    scaleRef.current = nextScale
    offsetRef.current = nextOffset
    setScale(nextScale)
    setOffset(nextOffset)
  }

  function settleView() {
    const nextOffset = constrainedOffset(scaleRef.current, offsetRef.current)
    setIsDragging(false)
    if (nextOffset.x === offsetRef.current.x && nextOffset.y === offsetRef.current.y) {
      setIsSettling(false)
      return
    }
    setIsSettling(true)
    updateView(scaleRef.current, nextOffset)
  }

  function toggleScale() {
    const defaultScale = defaultScaleRef.current
    const actualSizeScale =
      defaultScale < ACTUAL_SIZE_SCALE - SCALE_EPSILON ? ACTUAL_SIZE_SCALE : ZOOMED_SCALE
    const next = scaleRef.current <= defaultScale + SCALE_EPSILON ? actualSizeScale : defaultScale
    setIsSettling(true)
    updateView(next, { x: 0, y: 0 })
  }

  function generateThumbnail(messageId: number, image: HTMLImageElement) {
    if (generatedThumbnailUrlsRef.current.has(messageId)) return
    generatedThumbnailUrlsRef.current.set(messageId, null)
    void createSquareThumbnail(image).then((url) => {
      if (!url) {
        generatedThumbnailUrlsRef.current.delete(messageId)
        return
      }
      if (!mountedRef.current) {
        URL.revokeObjectURL(url)
        return
      }
      generatedThumbnailUrlsRef.current.set(messageId, url)
      setGeneratedThumbnails((current) => {
        const next = new Map(current)
        next.set(messageId, url)
        return next
      })
    })
  }

  function move(delta: number) {
    const target = itemIndex + delta
    if (target >= 0 && target < group.items.length) {
      onNavigate(group.items[target])
      return
    }
    const sibling = groupIndex + delta
    if (sibling >= 0 && sibling < groups.length) {
      const next = groups[sibling]
      onNavigate(delta > 0 ? next.items[0] : next.items[next.items.length - 1])
    }
  }

  useEffect(() => {
    if (!stageNode) return
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      const deltaY = wheelDeltaInPixels(event, stageNode.clientHeight)
      const factor = Math.exp(-deltaY * 0.002)
      const minScale = Math.min(defaultScaleRef.current, 0.333)
      const next = clamp(scaleRef.current * factor, minScale, 3)
      if (next !== scaleRef.current) {
        const current = offsetRef.current
        const ratioScale = next / scaleRef.current
        setIsSettling(false)
        updateView(
          next,
          {
            x: current.x * ratioScale,
            y: current.y * ratioScale,
          },
          'zoom',
        )
      }
      if (wheelSettleTimerRef.current !== null) {
        window.clearTimeout(wheelSettleTimerRef.current)
      }
      wheelSettleTimerRef.current = window.setTimeout(() => {
        wheelSettleTimerRef.current = null
        if (scaleRef.current < 1) settleView()
      }, 160)
    }
    stageNode.addEventListener('wheel', onWheel, { passive: false })
    return () => {
      stageNode.removeEventListener('wheel', onWheel)
      if (wheelSettleTimerRef.current !== null) {
        window.clearTimeout(wheelSettleTimerRef.current)
        wheelSettleTimerRef.current = null
      }
    }
    // stageNode changes when the Radix portal mounts; live view values are held in refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stageNode])

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (!event.isPrimary || (event.pointerType === 'mouse' && event.button !== 0)) return
    if (wheelSettleTimerRef.current !== null) {
      window.clearTimeout(wheelSettleTimerRef.current)
      wheelSettleTimerRef.current = null
    }
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      offsetX: offsetRef.current.x,
      offsetY: offsetRef.current.y,
    }
    setIsDragging(true)
    setIsSettling(false)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    updateView(
      scaleRef.current,
      {
        x: drag.offsetX + (event.clientX - drag.startX),
        y: drag.offsetY + (event.clientY - drag.startY),
      },
      'elastic',
    )
  }

  function onPointerUp(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    dragRef.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    const moved = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY)
    if (moved < 6) {
      setIsDragging(false)
      toggleScale()
    } else {
      settleView()
    }
  }

  function onPointerCancel(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    dragRef.current = null
    settleView()
  }

  const { width: viewportW, height: viewportH } = resolveViewport(stageSize, stageNode)
  const frame = sourceFrameFor(viewportW, viewportH, ratio, sourceWidth, longImage)

  return (
    <DialogPrimitive.Root
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-80 bg-slate-950/85 backdrop-blur-[3px]" />
        <DialogPrimitive.Content
          className="fixed inset-0 z-81 overflow-hidden outline-none"
          aria-label={t('telegramPreview.imagePreview')}
          onClick={onClose}
        >
          <DialogPrimitive.Close asChild>
            <button
              type="button"
              className="absolute top-3 right-3 z-10 grid size-9 place-items-center rounded-full bg-slate-900/60 text-white transition hover:bg-slate-900/80"
              title={closeLabel}
              aria-label={closeLabel}
              onClick={(event) => event.stopPropagation()}
            >
              <X size={18} />
            </button>
          </DialogPrimitive.Close>
          <button
            type="button"
            className="absolute top-1/2 left-3 z-10 grid size-10 -translate-y-1/2 place-items-center rounded-full bg-slate-900/60 text-white transition hover:bg-slate-900/80 disabled:opacity-0"
            title={previousLabel}
            aria-label={previousLabel}
            disabled={groupIndex <= 0 && itemIndex <= 0}
            onClick={(event) => {
              event.stopPropagation()
              move(-1)
            }}
          >
            <ChevronLeft size={22} />
          </button>
          <button
            type="button"
            className="absolute top-1/2 right-3 z-10 grid size-10 -translate-y-1/2 place-items-center rounded-full bg-slate-900/60 text-white transition hover:bg-slate-900/80 disabled:opacity-0"
            title={nextLabel}
            aria-label={nextLabel}
            disabled={groupIndex >= groups.length - 1 && itemIndex >= group.items.length - 1}
            onClick={(event) => {
              event.stopPropagation()
              move(1)
            }}
          >
            <ChevronRight size={22} />
          </button>
          {group.items.length > 1 ? (
            <div className="absolute right-0 bottom-3 left-0 z-10 flex justify-center px-6">
              <div
                className="flex max-w-full items-center gap-1.5 overflow-x-auto rounded-lg bg-slate-900/50 p-1.5"
                onClick={(event) => event.stopPropagation()}
              >
                {group.items.map((item, index) => (
                  <button
                    key={item.id}
                    type="button"
                    data-testid="lightbox-thumbnail"
                    className={cn(
                      'size-11 shrink-0 overflow-hidden rounded-md border-2 transition',
                      index === itemIndex
                        ? 'border-white'
                        : 'border-transparent opacity-60 hover:opacity-100',
                    )}
                    onClick={() => onNavigate(item)}
                  >
                    <AuthenticatedImage
                      media={null}
                      thumbnailMedia={
                        generatedThumbnails.has(item.id) || item.media?.inline_thumbnail
                          ? null
                          : messageResourceRef(item.chat_id, item.id, true)
                      }
                      inlineSource={
                        generatedThumbnails.get(item.id) ?? item.media?.inline_thumbnail
                      }
                      accountId={accountId}
                      className="size-full"
                      fallback={null}
                      alt=""
                    />
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <div
            ref={setStageNode}
            className="absolute inset-0 flex touch-none items-center justify-center overflow-hidden"
            onDragStart={(event) => event.preventDefault()}
          >
            <div
              key={message?.id}
              className="relative"
              style={{
                width: `${frame.width}px`,
                aspectRatio: `${ratio}`,
                transform: `translate3d(${offset.x}px, ${offset.y}px, 0) scale(${scale})`,
                transition: isSettling ? 'transform 220ms cubic-bezier(0.22, 1, 0.36, 1)' : 'none',
                cursor: isDragging
                  ? 'grabbing'
                  : scale > defaultScaleRef.current + SCALE_EPSILON
                    ? 'grab'
                    : 'zoom-in',
                willChange: 'transform',
              }}
              onClick={(event) => event.stopPropagation()}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerCancel}
              onTransitionEnd={(event) => {
                if (event.propertyName === 'transform') setIsSettling(false)
              }}
            >
              <AuthenticatedImage
                media={
                  media?.is_visual_media ? messageResourceRef(message.chat_id, message.id) : null
                }
                inlineSource={media?.inline_thumbnail}
                isVideo={isVideo}
                fit="contain"
                blurred
                spinnerWhileLoading
                alt={media?.file_name || t('telegramPreview.image')}
                accountId={accountId}
                className="size-full"
                onFullImageLoad={(image) => generateThumbnail(message.id, image)}
                fallback={
                  <span className="grid size-full place-items-center text-slate-400">
                    <Image size={40} />
                  </span>
                }
              />
            </div>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
