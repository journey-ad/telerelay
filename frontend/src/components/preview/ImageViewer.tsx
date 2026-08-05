import * as DialogPrimitive from '@radix-ui/react-dialog'
import { ChevronLeft, ChevronRight, Image, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TelegramPreviewMessage } from '../../types'
import { cn } from '../../utils/cn'
import { thumbnailPath, visualMediaPath, type ImageGroup } from '../../utils/preview'
import { AuthenticatedImage } from '../AuthenticatedImage'

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
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

  const [scale, setScale] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [stageNode, setStageNode] = useState<HTMLDivElement | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isSettling, setIsSettling] = useState(false)
  const scaleRef = useRef(1)
  const offsetRef = useRef({ x: 0, y: 0 })
  const wheelSettleTimerRef = useRef<number | null>(null)
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
  const ratioRef = useRef(ratio)
  ratioRef.current = ratio

  useEffect(() => {
    setScale(1)
    setOffset({ x: 0, y: 0 })
    scaleRef.current = 1
    offsetRef.current = { x: 0, y: 0 }
    if (wheelSettleTimerRef.current !== null) {
      window.clearTimeout(wheelSettleTimerRef.current)
      wheelSettleTimerRef.current = null
    }
    dragRef.current = null
    setIsDragging(false)
    setIsSettling(false)
  }, [message?.id])

  // 接近旧消息分页边界时预拉取更早的消息（组内 3 组之内）
  useEffect(() => {
    if (groupIndex <= 2 && hasNextPage) onLoadEarlier()
  }, [groupIndex, hasNextPage, onLoadEarlier])

  function boundsFor(
    nextScale: number,
    centerSmallerImage = true,
  ): {
    maxX: number
    maxY: number
    viewportW: number
    viewportH: number
  } {
    const currentRatio = ratioRef.current
    const viewportW = stageNode?.clientWidth || window.innerWidth
    const viewportH = stageNode?.clientHeight || window.innerHeight
    const baseW = Math.min(viewportW, viewportH * currentRatio)
    const baseH = baseW / currentRatio
    const scaledW = baseW * nextScale
    const scaledH = baseH * nextScale
    const shouldCenter = centerSmallerImage && nextScale < 1
    return {
      // Only views below 1x spring back to center; other scales retain their valid pan position.
      maxX: shouldCenter ? 0 : Math.abs(scaledW - viewportW) / 2,
      maxY: shouldCenter ? 0 : Math.abs(scaledH - viewportH) / 2,
      viewportW,
      viewportH,
    }
  }

  function constrainedOffset(
    nextScale: number,
    nextOffset: { x: number; y: number },
    centerSmallerImage = true,
  ) {
    const { maxX, maxY } = boundsFor(nextScale, centerSmallerImage)
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
    const keepSmallerImageCentered = mode === 'settle'
    const { maxX, maxY, viewportW, viewportH } = boundsFor(nextScale, keepSmallerImageCentered)
    if (mode === 'elastic') {
      nextOffset = {
        x: resistOutside(nextOffset.x, maxX, viewportW),
        y: resistOutside(nextOffset.y, maxY, viewportH),
      }
    } else {
      nextOffset = constrainedOffset(nextScale, nextOffset, keepSmallerImageCentered)
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
    const next = scaleRef.current <= 1 ? 2 : 1
    setIsSettling(true)
    updateView(next, { x: 0, y: 0 })
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
      const next = clamp(scaleRef.current * factor, 0.333, 3)
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
                    className={cn(
                      'size-11 shrink-0 overflow-hidden rounded-md border-2 transition',
                      index === itemIndex
                        ? 'border-white'
                        : 'border-transparent opacity-60 hover:opacity-100',
                    )}
                    onClick={() => onNavigate(item)}
                  >
                    <AuthenticatedImage
                      path={null}
                      thumbnailPath={
                        item.media?.inline_thumbnail ? null : thumbnailPath(item.chat_id, item.id)
                      }
                      inlineSource={item.media?.inline_thumbnail}
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
                width: `min(100vw, calc(100dvh * ${ratio}))`,
                aspectRatio: `${ratio}`,
                transform: `translate3d(${offset.x}px, ${offset.y}px, 0) scale(${scale})`,
                transition: isSettling ? 'transform 220ms cubic-bezier(0.22, 1, 0.36, 1)' : 'none',
                cursor: isDragging ? 'grabbing' : scale === 1 ? 'zoom-in' : 'grab',
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
                path={media?.is_visual_media ? visualMediaPath(message.chat_id, message.id) : null}
                inlineSource={media?.inline_thumbnail}
                isVideo={isVideo}
                fit="contain"
                blurred
                spinnerWhileLoading
                alt={media?.file_name || t('telegramPreview.image')}
                accountId={accountId}
                className="size-full"
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
