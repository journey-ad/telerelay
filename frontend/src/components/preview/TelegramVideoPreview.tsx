import {
  Bug,
  Info,
  LoaderCircle,
  Maximize,
  Minimize,
  Pause,
  PictureInPicture2,
  Play,
  RefreshCw,
  Volume2,
  VolumeX,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import type { TelegramResourceStats } from '../../api/telegramResource'
import { useTelegramResourceSession } from '../../hooks/useTelegramResourceSession'
import type { TelegramPreviewMessage } from '../../types'
import { cn } from '../../utils/cn'
import { pauseActiveAudio } from '../../utils/audioPlayback'
import { loadDirectResourceBlob, messageResourceRef } from '../../utils/resource'
import { readMp4TechnicalInfo, type Mp4TechnicalInfo } from '../../utils/mp4TechnicalInfo'
import { mediaDuration } from '../../utils/preview'
import { TelegramVideoStats, type VideoPlaybackStats } from './TelegramVideoStats'

const controlButton =
  'grid size-8 shrink-0 place-items-center rounded text-white/90 transition hover:bg-white/15 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-white'
const CONTROLS_IDLE_MS = 3_000
let pageVideoVolume = 0.8
let pageVideoMuted = false

type ContextMenuPosition = { x: number; y: number }
type FrameSample = { at: number; frames: number; fps: number | null }

function samplePlayback(
  video: HTMLVideoElement,
  previous: FrameSample | null,
  waitingEvents: number,
  stalledEvents: number,
) {
  const quality = video.getVideoPlaybackQuality?.()
  const totalFrames = Math.max(quality?.totalVideoFrames ?? 0, previous?.frames ?? 0)
  const now = performance.now()
  const elapsed = previous ? now - previous.at : 0
  const measuredFps = elapsed > 0 ? ((totalFrames - previous!.frames) * 1_000) / elapsed : null
  const currentFps = video.paused
    ? (previous?.fps ?? null)
    : measuredFps !== null && measuredFps >= 0
      ? measuredFps
      : null
  let bufferedAhead = 0
  for (let index = 0; index < video.buffered.length; index += 1) {
    if (
      video.buffered.start(index) <= video.currentTime &&
      video.buffered.end(index) >= video.currentTime
    ) {
      bufferedAhead = video.buffered.end(index) - video.currentTime
      break
    }
  }
  const rect = video.getBoundingClientRect()
  return {
    value: {
      naturalWidth: video.videoWidth,
      naturalHeight: video.videoHeight,
      displayWidth: Math.round(rect.width),
      displayHeight: Math.round(rect.height),
      currentTime: video.currentTime,
      duration: video.duration,
      bufferedAhead,
      bufferedRanges: video.buffered.length,
      totalFrames,
      droppedFrames: quality?.droppedVideoFrames ?? 0,
      currentFps,
      readyState: video.readyState,
      networkState: video.networkState,
      waitingEvents,
      stalledEvents,
      volume: video.volume,
      muted: video.muted,
    } satisfies VideoPlaybackStats,
    sample: { at: now, frames: totalFrames, fps: currentFps },
  }
}

function playerTime(value: number): string {
  return Number.isFinite(value) && value >= 0 ? mediaDuration(value) : '0:00'
}

export function TelegramVideoPreview({
  accountId,
  message,
  open,
  onClose,
}: {
  accountId: string
  message: TelegramPreviewMessage
  open: boolean
  onClose: () => void
}) {
  const media = message.media
  const { t } = useTranslation()
  const [playbackError, setPlaybackError] = useState(false)
  const { session, error, retry, close } = useTelegramResourceSession({
    accountId,
    chatId: message.chat_id,
    messageId: message.id,
  })
  const playerRef = useRef<HTMLDivElement | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const previousVolumeRef = useRef(pageVideoVolume || 0.8)
  const controlsTimerRef = useRef<number | null>(null)
  const playingRef = useRef(false)
  const frameSampleRef = useRef<FrameSample | null>(null)
  const mediaEventsRef = useRef({ waiting: 0, stalled: 0 })
  const copyTimerRef = useRef<number | null>(null)
  const [playing, setPlaying] = useState(false)
  const [waiting, setWaiting] = useState(true)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [buffered, setBuffered] = useState(0)
  const [volume, setVolume] = useState(pageVideoVolume)
  const [muted, setMuted] = useState(pageVideoMuted)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [posterUrl, setPosterUrl] = useState<string | null>(null)
  const [controlsVisible, setControlsVisible] = useState(true)
  const [contextMenu, setContextMenu] = useState<ContextMenuPosition | null>(null)
  const [statsVisible, setStatsVisible] = useState(false)
  const [transportStats, setTransportStats] = useState<TelegramResourceStats | null>(null)
  const [videoStats, setVideoStats] = useState<VideoPlaybackStats | null>(null)
  const [technicalInfo, setTechnicalInfo] = useState<Mp4TechnicalInfo | null>(null)
  const [statsCopied, setStatsCopied] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let objectUrl: string | null = null
    void loadDirectResourceBlob(accountId, messageResourceRef(message.chat_id, message.id, true))
      .then((blob) => {
        if (controller.signal.aborted) return
        if (blob) {
          objectUrl = URL.createObjectURL(blob)
          setPosterUrl(objectUrl)
          return
        }
        // No downloadable thumbnail (the video only has an embedded stripped
        // image): fall back to the inline data URL carried by the message.
        const inline = message.media?.inline_thumbnail
        if (inline) setPosterUrl(inline)
      })
      .catch((posterError) => {
        if (!controller.signal.aborted)
          console.warn('Telegram video poster failed to load', posterError)
      })
    return () => {
      controller.abort()
      setPosterUrl(null)
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [accountId, message.chat_id, message.id])

  useEffect(() => {
    if (!session || !videoRef.current) return
    const video = videoRef.current
    if (!open) {
      video.pause()
      return
    }
    video.volume = pageVideoVolume
    video.muted = pageVideoMuted
    pauseActiveAudio()
    let cancelled = false
    const start = async () => {
      try {
        await video.play()
      } catch (error) {
        if (cancelled) return
        try {
          video.muted = true
          pageVideoMuted = true
          setMuted(true)
          await video.play()
        } catch (retryError) {
          console.warn('Telegram video autoplay was blocked', retryError ?? error)
          setWaiting(false)
        }
      }
    }
    void start()
    return () => {
      cancelled = true
    }
  }, [open, session])

  useEffect(() => {
    playingRef.current = playing
    if (controlsTimerRef.current !== null) window.clearTimeout(controlsTimerRef.current)
    setControlsVisible(true)
    if (playing) {
      controlsTimerRef.current = window.setTimeout(() => {
        controlsTimerRef.current = null
        setControlsVisible(false)
      }, CONTROLS_IDLE_MS)
    }
  }, [playing])

  useEffect(
    () => () => {
      if (controlsTimerRef.current !== null) window.clearTimeout(controlsTimerRef.current)
      if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current)
    },
    [],
  )

  useEffect(() => {
    if (!open) setContextMenu(null)
  }, [open])

  useEffect(() => {
    if (!session || !statsVisible || !open) return
    let cancelled = false
    if (!technicalInfo) {
      void readMp4TechnicalInfo(session)
        .then((info) => {
          if (!cancelled) setTechnicalInfo(info)
        })
        .catch((metadataError) =>
          console.warn('Telegram video metadata could not be parsed', metadataError),
        )
    }
    const update = async () => {
      const video = videoRef.current
      if (!video || cancelled) return
      const snapshot = samplePlayback(
        video,
        frameSampleRef.current,
        mediaEventsRef.current.waiting,
        mediaEventsRef.current.stalled,
      )
      frameSampleRef.current = snapshot.sample
      setVideoStats(snapshot.value)
      try {
        const stats = await session.getStats()
        if (!cancelled) setTransportStats(stats)
      } catch (statsError) {
        if (!cancelled) console.warn('Telegram video stats could not be read', statsError)
      }
    }
    void update()
    const timer = window.setInterval(() => void update(), 500)
    return () => {
      cancelled = true
      window.clearInterval(timer)
      frameSampleRef.current = null
    }
  }, [open, session, statsVisible, technicalInfo])

  useEffect(() => {
    const onFullscreenChange = () =>
      setIsFullscreen(document.fullscreenElement === playerRef.current)
    document.addEventListener('fullscreenchange', onFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange)
  }, [])

  const syncBuffered = (video: HTMLVideoElement) => {
    let end = 0
    for (let index = 0; index < video.buffered.length; index += 1) {
      end = Math.max(end, video.buffered.end(index))
    }
    setBuffered(end)
  }

  const togglePlayback = () => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) {
      void video
        .play()
        .catch((playError) => console.error('Telegram video playback failed', playError))
    } else {
      video.pause()
    }
  }

  const revealControls = () => {
    setControlsVisible(true)
    if (controlsTimerRef.current !== null) window.clearTimeout(controlsTimerRef.current)
    controlsTimerRef.current = null
    if (playingRef.current) {
      controlsTimerRef.current = window.setTimeout(() => {
        controlsTimerRef.current = null
        setControlsVisible(false)
      }, CONTROLS_IDLE_MS)
    }
  }

  const toggleMute = () => {
    const video = videoRef.current
    if (!video) return
    if (video.muted || video.volume === 0) {
      const nextVolume = previousVolumeRef.current || 1
      video.volume = nextVolume
      video.muted = false
      pageVideoVolume = nextVolume
      pageVideoMuted = false
      setVolume(nextVolume)
      setMuted(false)
    } else {
      previousVolumeRef.current = video.volume
      video.muted = true
      pageVideoMuted = true
      setMuted(true)
    }
  }

  const toggleFullscreen = async () => {
    if (document.fullscreenElement === playerRef.current) {
      await document.exitFullscreen()
    } else if (playerRef.current) {
      await playerRef.current.requestFullscreen()
    }
  }

  const handleVideoError = () => {
    const video = videoRef.current
    console.error('Telegram video element failed', video?.error ?? 'Unknown media error')
    close()
    setPlaybackError(true)
  }

  const closePlayer = () => {
    videoRef.current?.pause()
    if (document.fullscreenElement === playerRef.current) {
      void document.exitFullscreen().catch(() => undefined)
    }
    onClose()
  }

  const openContextMenu = (event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    const rect = playerRef.current?.getBoundingClientRect()
    if (!rect) return
    const menuWidth = Math.min(252, rect.width - 16)
    const menuHeight = 132
    setContextMenu({
      x: Math.max(8, Math.min(event.clientX - rect.left, rect.width - menuWidth - 8)),
      y: Math.max(8, Math.min(event.clientY - rect.top, rect.height - menuHeight - 8)),
    })
    revealControls()
  }

  const togglePictureInPicture = async () => {
    const video = videoRef.current
    setContextMenu(null)
    if (!video || !document.pictureInPictureEnabled) return
    try {
      if (document.pictureInPictureElement === video) {
        await document.exitPictureInPicture()
      } else {
        await video.requestPictureInPicture()
      }
    } catch (pictureInPictureError) {
      console.warn('Video picture-in-picture could not be opened', pictureInPictureError)
    }
  }

  const debugInfo = () => ({
    media: {
      accountId,
      chatId: message.chat_id,
      messageId: message.id,
      mimeType: media?.mime_type,
      fileName: media?.file_name,
      size: media?.size,
      duration: videoStats?.duration,
      dcId: session?.dcId,
      endpoint: session?.endpoint,
    },
    container: technicalInfo,
    playback: videoStats,
    transport: transportStats,
  })

  const copyDebugInfo = () => {
    void navigator.clipboard
      .writeText(JSON.stringify(debugInfo(), null, 2))
      .then(() => {
        setStatsCopied(true)
        if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current)
        copyTimerRef.current = window.setTimeout(() => setStatsCopied(false), 1_500)
      })
      .catch((clipboardError) =>
        console.warn('Video debug info could not be copied', clipboardError),
      )
    setContextMenu(null)
  }

  const poster = posterUrl || undefined
  const width = media?.width && media.width > 0 ? media.width : 16
  const height = media?.height && media.height > 0 ? media.height : 9
  const ratio = Math.min(2.2, Math.max(0.5, width / height))
  const playedPercentage = duration > 0 ? Math.min(100, (currentTime / duration) * 100) : 0
  const bufferedPercentage =
    duration > 0 ? Math.max(playedPercentage, Math.min(100, (buffered / duration) * 100)) : 0
  const showControls = controlsVisible || !playing

  return createPortal(
    <>
      <div
        aria-hidden="true"
        className={cn('fixed inset-0 z-80 bg-slate-950/88 backdrop-blur-[3px]', !open && 'hidden')}
      />
      <div
        className={cn(
          'fixed inset-0 z-81 flex items-center justify-center overflow-hidden p-3 outline-none sm:p-6',
          !open && 'hidden',
        )}
        role="dialog"
        aria-modal="true"
        aria-label={t('telegramPreview.playVideo')}
        onClick={closePlayer}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.preventDefault()
            closePlayer()
          }
        }}
      >
        {session ? (
          <div
            ref={playerRef}
            className={cn(
              'group/player relative overflow-hidden bg-black shadow-2xl outline-none',
              !isFullscreen && 'rounded-[6px]',
              isFullscreen && 'size-full rounded-none',
              playing && !showControls && 'cursor-none',
            )}
            style={
              isFullscreen
                ? undefined
                : {
                    aspectRatio: `${width} / ${height}`,
                    width: `min(94vw, calc(88dvh * ${ratio}))`,
                    maxHeight: '88dvh',
                  }
            }
            tabIndex={0}
            onClick={(event) => event.stopPropagation()}
            onContextMenu={openContextMenu}
            onPointerMove={revealControls}
            onPointerDown={(event) => {
              revealControls()
              if (event.button !== 2) setContextMenu(null)
            }}
            onKeyDown={(event) => {
              revealControls()
              if (
                event.target instanceof HTMLButtonElement ||
                event.target instanceof HTMLInputElement
              )
                return
              const video = videoRef.current
              if (!video) return
              if (event.key === ' ' || event.key.toLowerCase() === 'k') {
                event.preventDefault()
                togglePlayback()
              } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                event.preventDefault()
                const delta = event.key === 'ArrowLeft' ? -5 : 5
                video.currentTime = Math.max(
                  0,
                  Math.min(duration || video.duration || 0, video.currentTime + delta),
                )
              } else if (event.key.toLowerCase() === 'm') {
                toggleMute()
              } else if (event.key.toLowerCase() === 'f') {
                void toggleFullscreen()
              }
            }}
          >
            <video
              ref={videoRef}
              className="size-full object-contain"
              src={session.url}
              poster={poster}
              autoPlay
              loop
              playsInline
              preload="auto"
              onClick={togglePlayback}
              onPlay={() => setPlaying(true)}
              onPlaying={() => {
                setPlaying(true)
                setWaiting(false)
              }}
              onPause={() => setPlaying(false)}
              onWaiting={() => {
                mediaEventsRef.current.waiting += 1
                setWaiting(true)
              }}
              onStalled={() => {
                mediaEventsRef.current.stalled += 1
              }}
              onCanPlay={() => setWaiting(false)}
              onLoadedMetadata={(event) => {
                setDuration(
                  Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0,
                )
                setWaiting(false)
                syncBuffered(event.currentTarget)
              }}
              onDurationChange={(event) => {
                setDuration(
                  Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0,
                )
              }}
              onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
              onProgress={(event) => syncBuffered(event.currentTarget)}
              onEnded={() => setPlaying(false)}
              onError={handleVideoError}
            />
            {statsVisible ? (
              <TelegramVideoStats
                accountId={accountId}
                message={message}
                endpoint={session.endpoint}
                dcId={session.dcId}
                playback={videoStats}
                transport={transportStats}
                technical={technicalInfo}
                waiting={waiting}
                onClose={() => setStatsVisible(false)}
              />
            ) : null}
            {contextMenu ? (
              <div
                className="absolute z-50 w-[252px] max-w-[calc(100%-16px)] overflow-hidden rounded-xl py-1.5 text-sm text-white shadow-[0_8px_28px_rgba(0,0,0,.35)] backdrop-blur-md"
                style={{
                  left: contextMenu.x,
                  top: contextMenu.y,
                  backgroundColor: 'rgba(28, 28, 28, 0.9)',
                  fontFamily: 'Roboto, Arial, Helvetica, sans-serif',
                }}
                role="menu"
                onContextMenu={(event) => event.preventDefault()}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={(event) => event.stopPropagation()}
              >
                <button
                  type="button"
                  role="menuitem"
                  disabled={!document.pictureInPictureEnabled}
                  className="flex h-10 w-full items-center gap-5 px-3 text-left hover:bg-white/10 focus-visible:bg-white/10 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-45"
                  onClick={() => void togglePictureInPicture()}
                >
                  <PictureInPicture2 size={23} strokeWidth={1.9} className="shrink-0" />
                  <span>{t('telegramPreview.stats.miniPlayer')}</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className="flex h-10 w-full items-center gap-5 px-3 text-left hover:bg-white/10 focus-visible:bg-white/10 focus-visible:outline-none"
                  onClick={copyDebugInfo}
                >
                  <Bug size={23} strokeWidth={1.9} className="shrink-0" />
                  {t(statsCopied ? 'telegramPreview.stats.copied' : 'telegramPreview.stats.copy')}
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className="flex h-10 w-full items-center gap-5 px-3 text-left hover:bg-white/10 focus-visible:bg-white/10 focus-visible:outline-none"
                  onClick={() => {
                    setStatsVisible((visible) => !visible)
                    setContextMenu(null)
                  }}
                >
                  <Info size={23} strokeWidth={1.9} className="shrink-0" />
                  <span>{t('telegramPreview.stats.menu')}</span>
                </button>
              </div>
            ) : null}
            {waiting ? (
              <span className="pointer-events-none absolute inset-0 z-10 grid place-items-center bg-black/15 text-white">
                <LoaderCircle size={28} className="animate-spin drop-shadow" />
              </span>
            ) : !playing ? (
              <button
                className="absolute top-1/2 left-1/2 z-10 grid size-12 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-black/65 text-white shadow-lg transition hover:scale-105 hover:bg-black/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                type="button"
                title={t('telegramPreview.playVideo')}
                aria-label={t('telegramPreview.playVideo')}
                onClick={togglePlayback}
              >
                <Play size={22} fill="currentColor" />
              </button>
            ) : null}
            <button
              className={cn(
                'absolute top-2 right-2 z-30 grid size-8 place-items-center rounded bg-black/65 text-white transition hover:bg-black/85 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white',
                showControls ? 'opacity-100' : 'pointer-events-none opacity-0',
              )}
              type="button"
              title={t('telegramPreview.closeVideo')}
              aria-label={t('telegramPreview.closeVideo')}
              onClick={closePlayer}
            >
              <X size={16} />
            </button>
            <div
              className={cn(
                'absolute inset-x-0 bottom-0 z-20 bg-gradient-to-t from-black/90 via-black/55 to-transparent px-2.5 pt-10 pb-2 transition-opacity duration-200',
                showControls ? 'opacity-100' : 'pointer-events-none opacity-0',
              )}
            >
              <div className="flex h-4 items-center">
                <div
                  className="relative h-[3px] w-full rounded-full before:absolute before:inset-x-0 before:-inset-y-1 before:content-['']"
                  style={{
                    background: `linear-gradient(to right, #60a5fa 0%, #60a5fa ${playedPercentage}%, rgba(255,255,255,.42) ${playedPercentage}%, rgba(255,255,255,.42) ${bufferedPercentage}%, rgba(255,255,255,.2) ${bufferedPercentage}%, rgba(255,255,255,.2) 100%)`,
                  }}
                >
                  <input
                    className="absolute inset-x-0 top-1/2 z-1 h-[11px] w-full -translate-y-1/2 cursor-pointer appearance-none bg-transparent focus-visible:outline-none [&::-moz-range-thumb]:size-2.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-white [&::-moz-range-track]:h-[3px] [&::-moz-range-track]:rounded-full [&::-moz-range-track]:bg-transparent [&::-webkit-slider-runnable-track]:h-[3px] [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:bg-transparent [&::-webkit-slider-thumb]:mt-[-3.5px] [&::-webkit-slider-thumb]:size-2.5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:shadow"
                    type="range"
                    min={0}
                    max={duration || 1}
                    step={0.1}
                    value={Math.min(currentTime, duration || 1)}
                    aria-label={t('telegramPreview.seekVideo')}
                    onChange={(event) => {
                      const nextTime = Number(event.currentTarget.value)
                      if (videoRef.current) videoRef.current.currentTime = nextTime
                      setCurrentTime(nextTime)
                    }}
                  />
                </div>
              </div>
              <div className="flex h-8 items-center gap-1">
                <button
                  className={controlButton}
                  type="button"
                  title={t(playing ? 'telegramPreview.pauseVideo' : 'telegramPreview.playVideo')}
                  aria-label={t(
                    playing ? 'telegramPreview.pauseVideo' : 'telegramPreview.playVideo',
                  )}
                  onClick={togglePlayback}
                >
                  {playing ? (
                    <Pause size={17} fill="currentColor" />
                  ) : (
                    <Play size={17} fill="currentColor" />
                  )}
                </button>
                <button
                  className={controlButton}
                  type="button"
                  title={t(
                    muted || volume === 0
                      ? 'telegramPreview.unmuteVideo'
                      : 'telegramPreview.muteVideo',
                  )}
                  aria-label={t(
                    muted || volume === 0
                      ? 'telegramPreview.unmuteVideo'
                      : 'telegramPreview.muteVideo',
                  )}
                  onClick={toggleMute}
                >
                  {muted || volume === 0 ? <VolumeX size={17} /> : <Volume2 size={17} />}
                </button>
                <div
                  className="relative hidden h-[2px] w-20 rounded-full before:absolute before:inset-x-0 before:-inset-y-1 before:content-[''] sm:block"
                  style={{
                    background: `linear-gradient(to right, rgba(255,255,255,.9) 0%, rgba(255,255,255,.9) ${(muted ? 0 : volume) * 100}%, rgba(255,255,255,.25) ${(muted ? 0 : volume) * 100}%, rgba(255,255,255,.25) 100%)`,
                  }}
                >
                  <input
                    className="absolute inset-x-0 top-1/2 z-1 h-[10px] w-full -translate-y-1/2 cursor-pointer appearance-none bg-transparent focus-visible:outline-none [&::-moz-range-thumb]:size-2 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-white [&::-moz-range-track]:h-[2px] [&::-moz-range-track]:rounded-full [&::-moz-range-track]:bg-transparent [&::-webkit-slider-runnable-track]:h-[2px] [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:bg-transparent [&::-webkit-slider-thumb]:mt-[-3px] [&::-webkit-slider-thumb]:size-2 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white"
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={muted ? 0 : volume}
                    aria-label={t('telegramPreview.volumeVideo')}
                    onChange={(event) => {
                      const nextVolume = Number(event.currentTarget.value)
                      const video = videoRef.current
                      if (!video) return
                      video.volume = nextVolume
                      video.muted = nextVolume === 0
                      if (nextVolume > 0) previousVolumeRef.current = nextVolume
                      pageVideoVolume = nextVolume
                      pageVideoMuted = nextVolume === 0
                      setVolume(nextVolume)
                      setMuted(nextVolume === 0)
                    }}
                  />
                </div>
                <span className="ml-1 min-w-22 text-xs font-medium text-white/90 tabular-nums">
                  {playerTime(currentTime)} / {playerTime(duration)}
                </span>
                <span className="flex-1" />
                <button
                  className={controlButton}
                  type="button"
                  title={t(
                    isFullscreen
                      ? 'telegramPreview.exitFullscreen'
                      : 'telegramPreview.enterFullscreen',
                  )}
                  aria-label={t(
                    isFullscreen
                      ? 'telegramPreview.exitFullscreen'
                      : 'telegramPreview.enterFullscreen',
                  )}
                  onClick={() => void toggleFullscreen()}
                >
                  {isFullscreen ? <Minimize size={17} /> : <Maximize size={17} />}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div
            className="relative grid place-items-center overflow-hidden rounded-[6px] bg-slate-950 text-white shadow-2xl"
            style={{
              aspectRatio: `${width} / ${height}`,
              width: `min(94vw, calc(88dvh * ${ratio}))`,
              maxHeight: '88dvh',
            }}
            onClick={(event) => event.stopPropagation()}
          >
            {poster ? (
              <img
                src={poster}
                alt=""
                className="absolute inset-0 size-full object-cover opacity-55"
              />
            ) : null}
            <span className="relative z-1 grid place-items-center gap-2 p-4 text-center">
              {error || playbackError ? (
                <RefreshCw size={22} />
              ) : (
                <LoaderCircle size={22} className="animate-spin" />
              )}
              <span className="text-xs text-white/85">
                {error || playbackError
                  ? t('telegramPreview.videoUnavailable')
                  : t('telegramPreview.videoLoading')}
              </span>
              {error || playbackError ? (
                <button
                  className="rounded border border-white/30 px-2 py-1 text-xs hover:bg-white/10"
                  type="button"
                  onClick={() => {
                    setPlaybackError(false)
                    retry()
                  }}
                >
                  {t('telegramPreview.retryVideo')}
                </button>
              ) : null}
            </span>
          </div>
        )}
      </div>
    </>,
    document.body,
  )
}
