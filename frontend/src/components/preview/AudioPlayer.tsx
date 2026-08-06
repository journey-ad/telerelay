import { LoaderCircle, Mic, Pause, Play, RefreshCw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useTelegramResourceSession } from '../../hooks/useTelegramResourceSession'
import type { TelegramPreviewMessage } from '../../types'
import { cn } from '../../utils/cn'
import { clearActiveAudio, pauseActiveAudio, setActiveAudio } from '../../utils/audioPlayback'
import { fileSize, mediaDuration } from '../../utils/preview'
import { messageResourceRef } from '../../utils/resource'
import { AuthenticatedImage } from '../AuthenticatedImage'

function playerTime(value: number): string {
  return Number.isFinite(value) && value >= 0 ? mediaDuration(value) : '0:00'
}

export function AudioPlayer({
  accountId,
  message,
}: {
  accountId: string
  message: TelegramPreviewMessage
}) {
  const media = message.media
  const { t } = useTranslation()
  const [loaded, setLoaded] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [playbackError, setPlaybackError] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const disposedRef = useRef(false)
  const { session, error, retry, close } = useTelegramResourceSession({
    accountId,
    chatId: message.chat_id,
    messageId: message.id,
    enabled: loaded,
  })

  const isVoice = media?.type === 'voice'
  const title =
    media?.file_name || (isVoice ? t('telegramPreview.voiceMessage') : (media?.type ?? ''))
  const meta = [media?.type, mediaDuration(media?.duration), fileSize(media?.size)]
    .filter(Boolean)
    .join(' · ')

  useEffect(() => {
    if (!session || !audioRef.current) return
    const audio = audioRef.current
    pauseActiveAudio()
    setActiveAudio(audio)
    void audio.play().catch((playError) => {
      console.warn('Telegram audio autoplay was blocked', playError)
    })
    return () => {
      clearActiveAudio(audio)
    }
  }, [session])

  useEffect(
    () => () => {
      disposedRef.current = true
      audioRef.current?.pause()
      close()
    },
    [close],
  )

  const togglePlayback = () => {
    if (playbackError || error) {
      setPlaybackError(false)
      retry()
      return
    }
    if (!loaded) {
      setLoaded(true)
      return
    }
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) {
      pauseActiveAudio()
      setActiveAudio(audio)
      void audio.play().catch((playError) => {
        console.error('Telegram audio playback failed', playError)
        if (!disposedRef.current) setPlaybackError(true)
      })
    } else {
      audio.pause()
    }
  }

  const handleAudioError = () => {
    const audio = audioRef.current
    console.error('Telegram audio element failed', audio?.error ?? 'Unknown media error')
    close()
    setPlaybackError(true)
  }

  const failed = error || playbackError
  const loading = loaded && !session && !failed

  return (
    <div className="w-80 max-w-full rounded-[5px] border border-slate-200 bg-white/70 p-2.5">
      <div className="flex items-center gap-2.5">
        <button
          type="button"
          className={cn(
            'grid size-10 shrink-0 place-items-center rounded-full transition',
            failed
              ? 'bg-rose-50 text-rose-500 hover:bg-rose-100'
              : 'bg-blue-50 text-blue-600 hover:bg-blue-100',
          )}
          onClick={togglePlayback}
          title={t(
            failed
              ? 'telegramPreview.retryAudio'
              : playing
                ? 'telegramPreview.pauseAudio'
                : 'telegramPreview.playAudio',
          )}
          aria-label={t(
            failed
              ? 'telegramPreview.retryAudio'
              : playing
                ? 'telegramPreview.pauseAudio'
                : 'telegramPreview.playAudio',
          )}
        >
          {loading ? (
            <LoaderCircle size={18} className="animate-spin" />
          ) : failed ? (
            <RefreshCw size={18} />
          ) : playing ? (
            <Pause size={18} fill="currentColor" />
          ) : (
            <Play size={18} fill="currentColor" className="ml-0.5" />
          )}
        </button>
        {media?.has_thumbnail ? (
          <div className="size-10 shrink-0 overflow-hidden rounded bg-slate-100">
            <AuthenticatedImage
              media={messageResourceRef(message.chat_id, message.id, true)}
              inlineSource={media.inline_thumbnail}
              blurred
              accountId={accountId}
              alt=""
              className="size-full"
              fallback={
                <span className="grid size-full place-items-center text-slate-300">
                  <Mic size={18} />
                </span>
              }
            />
          </div>
        ) : null}
        <span className="min-w-0 flex-1">
          <strong className="block truncate text-[13px] leading-4.5 text-slate-700">{title}</strong>
          <small className="mt-0.5 block truncate text-xs text-slate-400">
            {failed ? t('telegramPreview.audioUnavailable') : meta}
          </small>
        </span>
      </div>
      {loaded || failed ? (
        <div className="mt-2 flex h-4 items-center gap-2">
          <div
            className="relative h-[3px] flex-1 rounded-full before:absolute before:inset-x-0 before:-inset-y-1.5 before:content-['']"
            style={{
              background: `linear-gradient(to right, #3b82f6 0%, #3b82f6 ${duration ? (currentTime / duration) * 100 : 0}%, rgba(148,163,184,.3) ${duration ? (currentTime / duration) * 100 : 0}%, rgba(148,163,184,.3) 100%)`,
            }}
          >
            <input
              className="absolute inset-x-0 top-1/2 z-1 h-[11px] w-full -translate-y-1/2 cursor-pointer appearance-none bg-transparent focus-visible:outline-none disabled:cursor-default [&::-moz-range-thumb]:size-2.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-white [&::-moz-range-thumb]:shadow [&::-webkit-slider-runnable-track]:h-[3px] [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:bg-transparent [&::-webkit-slider-thumb]:mt-[-3.5px] [&::-webkit-slider-thumb]:size-2.5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:shadow"
              type="range"
              min={0}
              max={duration || 1}
              step={0.1}
              value={Math.min(currentTime, duration || 1)}
              disabled={!session || failed}
              aria-label={t('telegramPreview.seekVideo')}
              onChange={(event) => {
                const nextTime = Number(event.currentTarget.value)
                if (audioRef.current) audioRef.current.currentTime = nextTime
                setCurrentTime(nextTime)
              }}
            />
          </div>
          <span className="shrink-0 text-[11px] text-slate-400 tabular-nums">
            {playerTime(currentTime)} / {playerTime(duration)}
          </span>
        </div>
      ) : null}
      {session ? (
        <audio
          ref={audioRef}
          src={session.url}
          preload="auto"
          playsInline
          onPlay={() => setPlaying(true)}
          onPlaying={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onLoadedMetadata={(event) => {
            setDuration(
              Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0,
            )
          }}
          onDurationChange={(event) => {
            setDuration(
              Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0,
            )
          }}
          onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
          onEnded={() => setPlaying(false)}
          onError={handleAudioError}
        />
      ) : null}
    </div>
  )
}
