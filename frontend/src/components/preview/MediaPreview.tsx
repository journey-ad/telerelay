import { Download, ExternalLink, File, Image, Play } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useState } from 'react'
import { downloadFile } from '../../api/downloads'
import type { TelegramPreviewMessage } from '../../types'
import { cn } from '../../utils/cn'
import { formatNumber } from '../../utils/format'
import {
  fileSize,
  hasMediaPreview,
  isPreviewableMedia,
  mediaDuration,
  mediaFrame,
  thumbnailPath,
  visualMediaPath,
} from '../../utils/preview'
import { AuthenticatedImage } from '../AuthenticatedImage'
import { TelegramVideoPreview } from './TelegramVideoPreview'

function safeWebPageUrl(value?: string | null): string | null {
  if (!value) return null
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null
  } catch {
    return null
  }
}

function WebPagePreview({
  accountId,
  message,
  compact,
}: {
  accountId: string
  message: TelegramPreviewMessage
  compact: boolean
}) {
  const { t } = useTranslation()
  const media = message.media
  const webpage = media?.webpage
  if (!media || !webpage) return null
  const href = safeWebPageUrl(webpage.url)
  const source = webpage.site_name || webpage.display_url || webpage.url
  const content = (
    <>
      {media.has_thumbnail ? (
        <div className={cn('shrink-0 overflow-hidden bg-slate-100', compact ? 'h-28' : 'h-36')}>
          <AuthenticatedImage
            path={thumbnailPath(message.chat_id, message.id)}
            thumbnailPath={null}
            inlineSource={media.inline_thumbnail}
            blurred
            accountId={accountId}
            alt={webpage.title || source || t('telegramPreview.linkPreview')}
            className="size-full"
            fallback={
              <span className="grid size-full place-items-center text-slate-300">
                <Image size={28} />
              </span>
            }
          />
        </div>
      ) : null}
      <span className="block min-w-0 p-3">
        <span className="flex items-start gap-3">
          <span className="min-w-0 flex-1">
            {source ? (
              <span className="block truncate text-[11px] font-medium text-blue-600">{source}</span>
            ) : null}
            {webpage.title ? (
              <strong className="mt-0.5 line-clamp-2 block text-[13px] leading-4.5 text-slate-700">
                {webpage.title}
              </strong>
            ) : null}
          </span>
          {href ? <ExternalLink size={14} className="mt-0.5 shrink-0 text-slate-400" /> : null}
        </span>
        {webpage.description ? (
          <span className="mt-1.5 line-clamp-3 block max-h-12 overflow-hidden wrap-break-word text-xs leading-4 text-slate-500">
            {webpage.description}
          </span>
        ) : null}
      </span>
    </>
  )
  const className = cn(
    'block w-90 max-w-full overflow-hidden rounded-[5px] border border-slate-200 bg-white/80 text-left no-underline',
    href &&
      'transition hover:border-blue-300 hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500',
  )
  return href ? (
    <a
      className={className}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={webpage.title || t('telegramPreview.openLink')}
    >
      {content}
    </a>
  ) : (
    <div className={className}>{content}</div>
  )
}

function PollPreview({
  poll,
}: {
  poll: NonNullable<NonNullable<TelegramPreviewMessage['media']>['poll']>
}) {
  const { t } = useTranslation()
  return (
    <div className="w-80 max-w-full rounded-[5px] border border-slate-200 bg-white/80 p-3">
      <div className="flex items-start justify-between gap-3">
        <strong className="min-w-0 text-[13px] leading-4.5 text-slate-700">{poll.question}</strong>
        {poll.closed ? (
          <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">
            {t('telegramPreview.poll.closed')}
          </span>
        ) : null}
      </div>
      <span className="mt-1 block text-xs text-slate-400">
        {t(
          poll.quiz
            ? 'telegramPreview.poll.quiz'
            : poll.multiple_choice
              ? 'telegramPreview.poll.multiple'
              : 'telegramPreview.poll.single',
        )}
      </span>
      <div className="mt-2.5 space-y-2">
        {poll.options.map((option, index) => {
          const percentage = poll.total_voters
            ? Math.min(100, Math.round((option.voters / poll.total_voters) * 100))
            : 0
          return (
            <div key={`${index}-${option.text}`}>
              <div className="flex items-start justify-between gap-3 text-[13px]">
                <span
                  className={cn(
                    'min-w-0 break-words',
                    option.correct
                      ? 'font-semibold text-emerald-700'
                      : option.chosen
                        ? 'font-semibold text-blue-700'
                        : 'text-slate-600',
                  )}
                >
                  {option.text}
                  {option.chosen ? t('telegramPreview.poll.chosen') : ''}
                  {option.correct ? t('telegramPreview.poll.correct') : ''}
                </span>
                {poll.results_visible ? (
                  <span className="shrink-0 text-xs text-slate-400">
                    {t('telegramPreview.poll.votes', {
                      percentage,
                      value: formatNumber(option.voters),
                    })}
                  </span>
                ) : null}
              </div>
              {poll.results_visible ? (
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                  <span
                    className={cn(
                      'block h-full rounded-full',
                      option.correct
                        ? 'bg-emerald-500'
                        : option.chosen
                          ? 'bg-blue-500'
                          : 'bg-slate-300',
                    )}
                    style={{ width: `${percentage}%` }}
                  />
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
      <div className="mt-2.5 border-t border-slate-100 pt-2 text-xs text-slate-400">
        {poll.results_visible
          ? t('telegramPreview.poll.participants', {
              value: formatNumber(poll.total_voters),
            })
          : poll.total_voters
            ? t('telegramPreview.poll.participantsHidden', {
                value: formatNumber(poll.total_voters),
              })
            : t('telegramPreview.poll.resultsHidden')}
      </div>
      {poll.solution ? (
        <p className="mt-2 rounded bg-emerald-50 p-2 text-xs leading-4 text-emerald-700">
          {poll.solution}
        </p>
      ) : null}
    </div>
  )
}

export function MediaPreview({
  accountId,
  message,
  compact = false,
  onOpenPreview,
}: {
  accountId: string
  message: TelegramPreviewMessage
  compact?: boolean
  onOpenPreview: (message: TelegramPreviewMessage) => void
}) {
  const { t } = useTranslation()
  const [videoOpen, setVideoOpen] = useState(false)
  const [videoMounted, setVideoMounted] = useState(false)
  const media = message.media
  if (!media) return null
  if (!hasMediaPreview(media)) return null
  if (media.poll) return <PollPreview poll={media.poll} />
  if (media.webpage) {
    return <WebPagePreview accountId={accountId} message={message} compact={compact} />
  }
  const path = media.is_visual_media ? visualMediaPath(message.chat_id, message.id) : null
  const canPreview = isPreviewableMedia(media)
  const isVideo = media.type === 'video' || media.type === 'video_note'
  const isWebm =
    media.mime_type === 'video/webm' || media.file_name?.toLowerCase().endsWith('.webm')
  const autoLoadFull =
    media.type === 'photo' ||
    (media.type === 'sticker' && Boolean(media.mime_type?.startsWith('image/'))) ||
    isWebm
  const openVideo = () => {
    setVideoMounted(true)
    setVideoOpen(true)
  }
  const downloadLabel =
    media.type === 'animation'
      ? t('telegramPreview.downloadAnimation')
      : media.type === 'sticker'
        ? t('telegramPreview.downloadSticker')
        : t('telegramPreview.downloadImage')
  if (media.has_thumbnail) {
    return (
      <>
        <div
          className={cn(
            'group relative w-full overflow-hidden rounded-[5px] bg-slate-100',
            compact && 'aspect-square',
            isVideo ? 'cursor-pointer' : canPreview && 'cursor-zoom-in',
          )}
          style={compact ? undefined : mediaFrame(media)}
          onClick={isVideo ? openVideo : canPreview ? () => onOpenPreview(message) : undefined}
          role={isVideo || canPreview ? 'button' : undefined}
          tabIndex={isVideo || canPreview ? 0 : undefined}
          aria-label={
            isVideo
              ? t('telegramPreview.playVideo')
              : canPreview
                ? t('telegramPreview.viewImage')
                : undefined
          }
          onKeyDown={
            isVideo || canPreview
              ? (event) => {
                  if (event.target !== event.currentTarget) return
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    if (isVideo) openVideo()
                    else onOpenPreview(message)
                  }
                }
              : undefined
          }
        >
          <AuthenticatedImage
            path={autoLoadFull && !isVideo ? visualMediaPath(message.chat_id, message.id) : null}
            thumbnailPath={thumbnailPath(message.chat_id, message.id)}
            inlineSource={media.inline_thumbnail}
            blurred
            spinnerWhileLoading={autoLoadFull}
            isVideo={isWebm}
            alt={media.file_name || t('telegramPreview.image')}
            accountId={accountId}
            className="size-full"
            fallback={
              <span className="grid size-full place-items-center text-slate-300">
                <Image size={28} />
              </span>
            }
          />
          {isVideo ? (
            <span className="pointer-events-none absolute inset-0 grid place-items-center bg-black/10">
              <span className="grid size-11 place-items-center rounded-full bg-slate-950/70 text-white shadow-sm backdrop-blur-sm">
                <Play size={20} fill="currentColor" className="ml-0.5" />
              </span>
            </span>
          ) : null}
          {isVideo && mediaDuration(media.duration) ? (
            <span className="pointer-events-none absolute right-2 bottom-2 rounded bg-slate-950/75 px-1.5 py-0.5 text-[11px] font-medium text-white tabular-nums">
              {mediaDuration(media.duration)}
            </span>
          ) : null}
          {path ? (
            <button
              className="absolute right-2 bottom-2 grid size-7 place-items-center rounded bg-slate-900/70 text-white opacity-0 shadow transition group-hover:opacity-100 focus:opacity-100"
              title={downloadLabel}
              aria-label={downloadLabel}
              onClick={(event) => {
                event.stopPropagation()
                void downloadFile(path, media.file_name || `telegram-${message.id}.jpg`)
              }}
            >
              <Download size={14} />
            </button>
          ) : null}
        </div>
        {isVideo && videoMounted ? (
          <TelegramVideoPreview
            accountId={accountId}
            message={message}
            open={videoOpen}
            onClose={() => setVideoOpen(false)}
          />
        ) : null}
      </>
    )
  }
  return (
    <div
      className={cn(
        'grid w-full items-center gap-2 rounded-[5px] border',
        path ? 'grid-cols-[34px_minmax(0,1fr)_24px]' : 'grid-cols-[34px_minmax(0,1fr)]',
        'border-slate-200 bg-white/70 p-2 text-left',
      )}
    >
      <span className="grid size-8.5 place-items-center rounded bg-blue-50 text-blue-600">
        <File size={17} />
      </span>
      <span className="min-w-0">
        <strong className="block truncate text-xs text-slate-700">
          {media.file_name || media.type}
        </strong>
        <small className="mt-0.5 block text-xs text-slate-400">
          {[media.type, fileSize(media.size)].filter(Boolean).join(' · ')}
        </small>
      </span>
      {path ? (
        <button
          className="grid size-6 place-items-center rounded border-0 bg-transparent text-slate-400 hover:bg-blue-50 hover:text-blue-600"
          title={downloadLabel}
          aria-label={downloadLabel}
          onClick={() => void downloadFile(path, media.file_name || `telegram-${message.id}`)}
        >
          <Download size={14} />
        </button>
      ) : null}
    </div>
  )
}
