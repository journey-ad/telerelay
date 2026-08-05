import { LoaderCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { TelegramPreviewMessage } from '../../types'
import { cn } from '../../utils/cn'
import { formatNumber } from '../../utils/format'
import {
  hasMediaPreview,
  isPreviewableMedia,
  messageDay,
  messageTime,
  serviceText,
  type MessageGroup,
} from '../../utils/preview'
import { RichText } from '../RichText'
import { Avatar } from './DialogList'
import { MediaPreview } from './MediaPreview'

function DayDivider({ value }: { value?: string | null }) {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage ?? 'zh-CN'
  return (
    <div className="flex items-center gap-3 py-1.5 text-xs text-slate-400">
      <span className="h-px flex-1 bg-slate-200" />
      <time>
        {messageDay(
          value,
          locale,
          t('telegramPreview.unknownDate'),
          t('telegramPreview.today'),
          t('telegramPreview.yesterday'),
        )}
      </time>
      <span className="h-px flex-1 bg-slate-200" />
    </div>
  )
}

function AlbumPreview({
  accountId,
  items,
  onOpenPreview,
}: {
  accountId: string
  items: TelegramPreviewMessage[]
  onOpenPreview: (message: TelegramPreviewMessage) => void
}) {
  const [primary, ...secondary] = items
  const columns = secondary.length <= 3 ? 1 : secondary.length <= 6 ? 2 : 3
  const rows = Math.ceil(secondary.length / columns)
  const remainder = secondary.length % columns
  const baseSpan = 6 / columns

  function columnSpan(index: number) {
    if (!remainder || index < secondary.length - remainder) return baseSpan
    if (remainder === 1) return 6
    if (columns === 3 && remainder === 2) return 3
    return baseSpan
  }

  return (
    <div
      data-testid="media-album"
      className="mb-1.5 grid aspect-[4/3] w-130 max-w-full gap-0.5 overflow-hidden rounded-[5px] bg-slate-200"
      style={{
        gridTemplateColumns:
          items.length > 7 ? 'minmax(0, 3fr) minmax(0, 2fr)' : 'minmax(0, 2fr) minmax(0, 1fr)',
      }}
    >
      <MediaPreview accountId={accountId} message={primary} compact onOpenPreview={onOpenPreview} />
      <div
        className="grid min-h-0 gap-0.5"
        style={{
          gridTemplateColumns: 'repeat(6, minmax(0, 1fr))',
          gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`,
        }}
      >
        {secondary.map((item, index) => (
          <div
            key={item.id}
            className="min-h-0"
            style={{ gridColumn: `span ${columnSpan(index)}` }}
          >
            <MediaPreview
              accountId={accountId}
              message={item}
              compact
              onOpenPreview={onOpenPreview}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

export function MessageBubble({
  accountId,
  group,
  showDay,
  onReplyClick,
  onOpenPreview,
  loadingReplyId,
  unavailableReplyId,
}: {
  accountId: string
  group: MessageGroup
  showDay: boolean
  onReplyClick: (id: number) => void
  onOpenPreview: (message: TelegramPreviewMessage) => void
  loadingReplyId: number | null
  unavailableReplyId: number | null
}) {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage ?? 'zh-CN'
  const message = group.items[0]
  const outgoing = message.outgoing
  if (message.service_action) {
    return (
      <>
        {showDay ? <DayDivider value={message.date} /> : null}
        <div id={`message-${message.id}`} className="my-2 flex justify-center">
          <span className="rounded bg-slate-200/80 px-2.5 py-1 text-xs text-slate-500">
            {message.text ||
              serviceText(
                message.service_action,
                message.service_details,
                message.sender?.name ?? '',
                t,
                locale,
              )}
          </span>
        </div>
      </>
    )
  }
  const textMessage = group.items.find((item) => item.text)?.text ?? ''
  const mediaItems = group.items.filter((item) => item.media && hasMediaPreview(item.media))
  const imageItems = mediaItems.filter((item) => item.media && isPreviewableMedia(item.media))
  const otherMediaItems = mediaItems.filter(
    (item) => !item.media || !isPreviewableMedia(item.media),
  )
  return (
    <>
      {showDay ? <DayDivider value={message.date} /> : null}
      <div
        id={`message-${message.id}`}
        className={cn('flex items-end gap-2', outgoing ? 'justify-end pl-12' : 'pr-12')}
      >
        {!outgoing ? (
          <Avatar
            accountId={accountId}
            peerId={message.sender.id}
            title={message.sender.name}
            className="mb-0.5 size-7.5 rounded"
          />
        ) : null}
        <div
          className={cn(
            'min-w-0 max-w-155 rounded-md border px-2.5 py-2 shadow-xs',
            outgoing
              ? 'border-emerald-200 bg-emerald-50 text-slate-700'
              : 'border-slate-200 bg-white text-slate-700',
          )}
        >
          {!outgoing && message.sender.name ? (
            <strong className="mb-1 block text-[13px] text-blue-600">{message.sender.name}</strong>
          ) : null}
          {message.forward ? (
            <div className="mb-1.5 border-l-2 border-blue-400 pl-2 text-xs text-blue-600">
              {t('telegramPreview.forwardedFrom', { name: message.forward.from_name })}
            </div>
          ) : null}
          {message.reply_to ? (
            <button
              className="mb-1.5 grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-2 border-0 border-l-2 border-slate-300 bg-slate-50/80 py-1 pr-1 pl-2 text-left"
              onClick={() => onReplyClick(message.reply_to!.message_id)}
            >
              <span className="min-w-0">
                {message.reply_to.sender_name ? (
                  <strong className="block truncate text-xs text-blue-600">
                    {message.reply_to.sender_name}
                  </strong>
                ) : null}
                <span className="block truncate text-xs text-slate-500">
                  {message.reply_to.text}
                </span>
              </span>
              {loadingReplyId === message.reply_to.message_id ? (
                <LoaderCircle size={12} className="animate-spin text-blue-500" />
              ) : unavailableReplyId === message.reply_to.message_id ? (
                <span className="text-[11px] text-rose-500">
                  {t('telegramPreview.unavailable')}
                </span>
              ) : null}
            </button>
          ) : null}
          {imageItems.length ? (
            imageItems.length > 1 ? (
              <AlbumPreview
                accountId={accountId}
                items={imageItems}
                onOpenPreview={onOpenPreview}
              />
            ) : (
              <div className="mb-1.5 max-w-full">
                <MediaPreview
                  accountId={accountId}
                  message={imageItems[0]}
                  onOpenPreview={onOpenPreview}
                />
              </div>
            )
          ) : null}
          {otherMediaItems.length ? (
            <div className="mb-1.5 grid min-w-0 max-w-full gap-1">
              {otherMediaItems.map((item) => (
                <MediaPreview
                  key={item.id}
                  accountId={accountId}
                  message={item}
                  onOpenPreview={onOpenPreview}
                />
              ))}
            </div>
          ) : null}
          {textMessage ? (
            <RichText
              text={textMessage}
              entities={message.entities}
              className="m-0 whitespace-pre-wrap wrap-break-word text-[13px] leading-4.5"
            />
          ) : null}
          {message.reactions.length ? (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {message.reactions.map((reaction) => (
                <span
                  key={reaction.label}
                  className={cn(
                    'rounded-full border px-1.5 py-0.5 text-xs',
                    reaction.chosen
                      ? 'border-blue-200 bg-blue-50 text-blue-700'
                      : 'border-slate-200 bg-white/70 text-slate-500',
                  )}
                >
                  <span className="font-emoji">{reaction.label}</span> <span>{reaction.count}</span>
                </span>
              ))}
            </div>
          ) : null}
          <span className="mt-1 flex items-center justify-end gap-1.5 text-[11px] text-slate-400">
            {message.edited_at ? <span>{t('telegramPreview.edited')}</span> : null}
            {message.views ? (
              <span>{t('telegramPreview.views', { value: formatNumber(message.views) })}</span>
            ) : null}
            <time>{messageTime(message.date, locale)}</time>
          </span>
        </div>
      </div>
    </>
  )
}
