import { Download, File, Image } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { downloadFile } from '../../api/downloads'
import type { TelegramPreviewMessage } from '../../types'
import { cn } from '../../utils/cn'
import { formatNumber } from '../../utils/format'
import {
  fileSize,
  isPreviewableMedia,
  mediaFrame,
  thumbnailPath,
  visualMediaPath,
} from '../../utils/preview'
import { AuthenticatedImage } from '../AuthenticatedImage'

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
  const media = message.media
  if (!media) return null
  if (media.poll) return <PollPreview poll={media.poll} />
  const path = media.is_visual_media ? visualMediaPath(message.chat_id, message.id) : null
  const canPreview = isPreviewableMedia(media)
  const isWebm =
    media.mime_type === 'video/webm' || media.file_name?.toLowerCase().endsWith('.webm')
  const autoLoadFull =
    media.type === 'photo' ||
    (media.type === 'sticker' && Boolean(media.mime_type?.startsWith('image/'))) ||
    isWebm
  const downloadLabel =
    media.type === 'animation'
      ? t('telegramPreview.downloadAnimation')
      : media.type === 'sticker'
        ? t('telegramPreview.downloadSticker')
        : t('telegramPreview.downloadImage')
  if (media.has_thumbnail) {
    return (
      <div
        className={cn(
          'group relative w-full overflow-hidden rounded-[5px] bg-slate-100',
          compact && 'aspect-square',
          canPreview && 'cursor-zoom-in',
        )}
        style={compact ? undefined : mediaFrame(media)}
        onClick={canPreview ? () => onOpenPreview(message) : undefined}
        role={canPreview ? 'button' : undefined}
        tabIndex={canPreview ? 0 : undefined}
        aria-label={canPreview ? t('telegramPreview.viewImage') : undefined}
        onKeyDown={
          canPreview
            ? (event) => {
                if (event.target !== event.currentTarget) return
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onOpenPreview(message)
                }
              }
            : undefined
        }
      >
        <AuthenticatedImage
          path={autoLoadFull ? visualMediaPath(message.chat_id, message.id) : null}
          thumbnailPath={media.inline_thumbnail ? null : thumbnailPath(message.chat_id, message.id)}
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
