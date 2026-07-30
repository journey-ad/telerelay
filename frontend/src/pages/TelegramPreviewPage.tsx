import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from '@tanstack/react-query'
import {
  Archive,
  ArrowDown,
  ArrowLeft,
  CheckCircle2,
  Download,
  File,
  Image,
  Inbox,
  LoaderCircle,
  MessageCircle,
  MessagesSquare,
  Radio,
  Search,
  UserRound,
  UsersRound,
  X,
} from 'lucide-react'
import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'
import { useTranslation } from 'react-i18next'
import { request } from '../api/client'
import { downloadFile } from '../api/downloads'
import { AuthenticatedImage } from '../components/AuthenticatedImage'
import { EmptyState, IconButton, PageHeader } from '../components/ui'
import type {
  TelegramAccount,
  TelegramPreviewDialog,
  TelegramPreviewDialogsPage,
  TelegramPreviewMessage,
  TelegramPreviewMessagesPage,
} from '../types'
import { cn } from '../utils/cn'
import { hashColor } from '../utils/color'
import { formatNumber, messageFrom } from '../utils/format'

type DialogFolder = 'main' | 'archived'

function initials(value: string): string {
  const parts = value.trim().split(/\s+/).filter(Boolean)
  if (parts.length > 1) return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase()
  return value.slice(0, 2).toUpperCase() || 'TG'
}

function previewTime(value: string | null | undefined, locale: string): string {
  if (!value) return ''
  const date = new Date(value)
  const now = new Date()
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', hour12: false })
  }
  if (date.getFullYear() === now.getFullYear()) {
    return date.toLocaleDateString(locale, { month: 'numeric', day: 'numeric' })
  }
  return date.toLocaleDateString(locale, { year: '2-digit', month: 'numeric', day: 'numeric' })
}

function messageTime(value: string | null | undefined, locale: string): string {
  if (!value) return ''
  return new Date(value).toLocaleTimeString(locale, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function messageDay(
  value: string | null | undefined,
  locale: string,
  unknown: string,
  todayLabel: string,
  yesterdayLabel: string,
): string {
  if (!value) return unknown
  const date = new Date(value)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (date.toDateString() === today.toDateString()) return todayLabel
  if (date.toDateString() === yesterday.toDateString()) return yesterdayLabel
  return date.toLocaleDateString(locale, { year: 'numeric', month: 'long', day: 'numeric' })
}

function fileSize(value?: number | null): string {
  if (!value) return ''
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`
}

function peerAvatarPath(accountId: string, peerId?: number | null): string | null {
  if (!peerId) return null
  return `/api/v1/telegram-preview/peers/${peerId}/avatar?account_id=${encodeURIComponent(accountId)}`
}

function thumbnailPath(accountId: string, chatId: number, messageId: number): string {
  return `/api/v1/telegram-preview/chats/${chatId}/messages/${messageId}/thumbnail?account_id=${encodeURIComponent(accountId)}`
}

function visualMediaPath(accountId: string, chatId: number, messageId: number): string {
  return `/api/v1/telegram-preview/chats/${chatId}/messages/${messageId}/visual-media?account_id=${encodeURIComponent(accountId)}`
}

function mediaFrame(media: NonNullable<TelegramPreviewMessage['media']>) {
  const width = media.width && media.width > 0 ? media.width : 4
  const height = media.height && media.height > 0 ? media.height : 3
  const ratio = Math.min(2, Math.max(0.56, width / height))
  const preferredWidth = ratio < 1 ? 240 + ((ratio - 0.56) / 0.44) * 120 : 360 + (ratio - 1) * 160
  return {
    aspectRatio: `${width} / ${height}`,
    width: `${Math.round(preferredWidth)}px`,
    maxWidth: '100%',
  }
}

function ChatGlyph({ kind, size = 14 }: { kind: TelegramPreviewDialog['kind']; size?: number }) {
  const Icon =
    kind === 'private' || kind === 'bot' ? UserRound : kind === 'channel' ? Radio : UsersRound
  return <Icon size={size} />
}

function Avatar({
  accountId,
  peerId,
  inlineSource,
  title,
  kind,
  className,
}: {
  accountId: string
  peerId?: number | null
  inlineSource?: string | null
  title: string
  kind?: TelegramPreviewDialog['kind']
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <AuthenticatedImage
      path={peerAvatarPath(accountId, peerId)}
      inlineSource={inlineSource}
      alt={t('telegramPreview.avatarAlt', { title })}
      className={cn('grid shrink-0 place-items-center rounded-[6px] text-white', className)}
      style={{ backgroundColor: hashColor(String(peerId ?? title)) }}
      fallback={
        <span className="grid size-full place-items-center text-[12px] font-bold">
          {title ? initials(title) : kind ? <ChatGlyph kind={kind} /> : 'TG'}
        </span>
      }
    />
  )
}

function DialogRow({
  accountId,
  dialog,
  selected,
  onSelect,
}: {
  accountId: string
  dialog: TelegramPreviewDialog
  selected: boolean
  onSelect: () => void
}) {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage ?? 'zh-CN'
  return (
    <button
      data-testid={`dialog-${dialog.id}`}
      className={cn(
        'grid min-h-17 w-full grid-cols-[42px_minmax(0,1fr)_auto] items-center gap-2.5',
        'border-0 border-b border-slate-100 bg-transparent px-3 py-2.5 text-left transition',
        selected ? 'bg-blue-50/85 shadow-[inset_2px_0_#2563eb]' : 'hover:bg-slate-50',
      )}
      onClick={onSelect}
    >
      <Avatar
        accountId={accountId}
        peerId={dialog.id}
        inlineSource={dialog.inline_avatar}
        title={dialog.title}
        kind={dialog.kind}
        className="size-10.5"
      />
      <span className="min-w-0">
        <span className="flex min-w-0 items-center gap-1.5">
          <strong className="truncate text-[13px] text-slate-800">{dialog.title}</strong>
          {dialog.verified ? <CheckCircle2 size={12} className="shrink-0 text-blue-500" /> : null}
        </span>
        <span className="mt-1 flex min-w-0 items-center gap-1 text-[11px] text-slate-400">
          {dialog.last_message?.outgoing ? (
            <span className="text-blue-500">{t('telegramPreview.you')}</span>
          ) : null}
          <span className="truncate">
            {dialog.last_message?.preview || t('telegramPreview.noMessages')}
          </span>
        </span>
      </span>
      <span className="flex h-full min-w-8 flex-col items-end justify-center gap-1.5">
        <time className="text-[10px] text-slate-400">
          {previewTime(dialog.last_message?.date, locale)}
        </time>
        {dialog.unread_count ? (
          <span className="grid min-w-4.5 place-items-center rounded-full bg-blue-600 px-1 text-[10px] font-bold leading-4.5 text-white">
            {dialog.unread_count > 99 ? '99+' : dialog.unread_count}
          </span>
        ) : dialog.pinned ? (
          <span className="text-[10px] text-slate-300">{t('telegramPreview.pinned')}</span>
        ) : null}
      </span>
    </button>
  )
}

function MediaPreview({
  accountId,
  message,
  compact = false,
}: {
  accountId: string
  message: TelegramPreviewMessage
  compact?: boolean
}) {
  const { t } = useTranslation()
  const media = message.media
  if (!media) return null
  if (media.poll) return <PollPreview poll={media.poll} />
  const path = media.is_visual_media
    ? visualMediaPath(accountId, message.chat_id, message.id)
    : null
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
        )}
        style={compact ? undefined : mediaFrame(media)}
      >
        <AuthenticatedImage
          path={
            media.inline_thumbnail ? null : thumbnailPath(accountId, message.chat_id, message.id)
          }
          inlineSource={media.inline_thumbnail}
          alt={media.file_name || t('telegramPreview.image')}
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
            onClick={() => void downloadFile(path, media.file_name || `telegram-${message.id}.jpg`)}
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
        <strong className="block truncate text-[12px] text-slate-700">
          {media.file_name || media.type}
        </strong>
        <small className="mt-0.5 block text-[10px] text-slate-400">
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

function PollPreview({
  poll,
}: {
  poll: NonNullable<NonNullable<TelegramPreviewMessage['media']>['poll']>
}) {
  const { t } = useTranslation()
  return (
    <div className="w-80 max-w-full rounded-[5px] border border-slate-200 bg-white/80 p-3">
      <div className="flex items-start justify-between gap-3">
        <strong className="min-w-0 text-[13px] leading-4.5 text-slate-800">{poll.question}</strong>
        {poll.closed ? (
          <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[9px] text-slate-500">
            {t('telegramPreview.poll.closed')}
          </span>
        ) : null}
      </div>
      <span className="mt-1 block text-[10px] text-slate-400">
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
              <div className="flex items-start justify-between gap-3 text-[11px]">
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
                  <span className="shrink-0 text-[10px] text-slate-400">
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
      <div className="mt-2.5 border-t border-slate-100 pt-2 text-[10px] text-slate-400">
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
        <p className="mt-2 rounded bg-emerald-50 p-2 text-[10px] leading-4 text-emerald-700">
          {poll.solution}
        </p>
      ) : null}
    </div>
  )
}

interface MessageGroup {
  key: string
  items: TelegramPreviewMessage[]
}

function groupMessages(messages: TelegramPreviewMessage[]): MessageGroup[] {
  const groups: MessageGroup[] = []
  for (const message of messages) {
    const previous = groups[groups.length - 1]
    if (message.grouped_id && previous?.key === `album-${message.grouped_id}`) {
      previous.items.push(message)
    } else {
      groups.push({
        key: message.grouped_id ? `album-${message.grouped_id}` : `message-${message.id}`,
        items: [message],
      })
    }
  }
  return groups
}

function MessageBubble({
  accountId,
  group,
  showDay,
  onReplyClick,
  loadingReplyId,
  unavailableReplyId,
}: {
  accountId: string
  group: MessageGroup
  showDay: boolean
  onReplyClick: (id: number) => void
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
          <span className="rounded bg-slate-200/80 px-2.5 py-1 text-[10px] text-slate-500">
            {message.text || t('telegramPreview.serviceUpdated')}
          </span>
        </div>
      </>
    )
  }
  const textMessage = group.items.find((item) => item.text)?.text ?? ''
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
            'min-w-0 max-w-155 rounded-[6px] border px-2.5 py-2 shadow-xs',
            outgoing
              ? 'border-emerald-200 bg-emerald-50 text-slate-800'
              : 'border-slate-200 bg-white text-slate-800',
          )}
        >
          {!outgoing && message.sender.name ? (
            <strong className="mb-1 block text-[11px] text-blue-600">{message.sender.name}</strong>
          ) : null}
          {message.forward ? (
            <div className="mb-1.5 border-l-2 border-blue-400 pl-2 text-[10px] text-blue-600">
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
                  <strong className="block truncate text-[10px] text-blue-600">
                    {message.reply_to.sender_name}
                  </strong>
                ) : null}
                <span className="block truncate text-[10px] text-slate-500">
                  {message.reply_to.text}
                </span>
              </span>
              {loadingReplyId === message.reply_to.message_id ? (
                <LoaderCircle size={12} className="animate-spin text-blue-500" />
              ) : unavailableReplyId === message.reply_to.message_id ? (
                <span className="text-[9px] text-rose-500">{t('telegramPreview.unavailable')}</span>
              ) : null}
            </button>
          ) : null}
          {group.items.some((item) => item.media) ? (
            <div
              className={cn(
                'mb-1.5 grid gap-1',
                group.items.length > 1 ? 'grid-cols-2' : 'grid-cols-1',
              )}
              style={
                group.items.length > 1 ? { width: '520px', maxWidth: '100%' } : { maxWidth: '100%' }
              }
            >
              {group.items.map((item) => (
                <MediaPreview
                  key={item.id}
                  accountId={accountId}
                  message={item}
                  compact={group.items.length > 1}
                />
              ))}
            </div>
          ) : null}
          {textMessage ? (
            <p className="m-0 whitespace-pre-wrap break-words text-[13px] leading-4.5">
              {textMessage}
            </p>
          ) : null}
          {message.reactions.length ? (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {message.reactions.map((reaction) => (
                <span
                  key={reaction.label}
                  className={cn(
                    'rounded-full border px-1.5 py-0.5 text-[10px]',
                    reaction.chosen
                      ? 'border-blue-200 bg-blue-50 text-blue-700'
                      : 'border-slate-200 bg-white/70 text-slate-500',
                  )}
                >
                  {reaction.label} {reaction.count}
                </span>
              ))}
            </div>
          ) : null}
          <span className="mt-1 flex items-center justify-end gap-1.5 text-[9px] text-slate-400">
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

function DayDivider({ value }: { value?: string | null }) {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage ?? 'zh-CN'
  return (
    <div className="flex items-center gap-3 py-1.5 text-[10px] text-slate-400">
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

function Loading({ label }: { label: string }) {
  return (
    <div className="flex min-h-28 items-center justify-center gap-2 text-[11px] text-slate-400">
      <LoaderCircle size={15} className="animate-spin" />
      {label}
    </div>
  )
}

function ToolButton({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button
      className="h-8 rounded-[5px] border border-slate-200 bg-white px-3 text-[11px] font-semibold text-slate-600 hover:border-blue-200 hover:text-blue-700"
      onClick={onClick}
    >
      {children}
    </button>
  )
}

export function TelegramPreviewPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage ?? 'zh-CN'
  const queryClient = useQueryClient()
  const [folder, setFolder] = useState<DialogFolder>('main')
  const [dialogFilter, setDialogFilter] = useState('')
  const [selected, setSelected] = useState<TelegramPreviewDialog | null>(null)
  const [searchInput, setSearchInput] = useState('')
  const [messageQuery, setMessageQuery] = useState('')
  const [replyTargetId, setReplyTargetId] = useState<number | null>(null)
  const [loadingReplyId, setLoadingReplyId] = useState<number | null>(null)
  const [unavailableReplyId, setUnavailableReplyId] = useState<number | null>(null)
  const viewportRef = useRef<HTMLDivElement>(null)
  const previousScrollHeight = useRef<number | null>(null)
  const stickToBottom = useRef(true)
  const replyRequestId = useRef(0)

  const accounts = useQuery({
    queryKey: ['telegram-accounts'],
    queryFn: () => request<TelegramAccount[]>('/api/v1/telegram-accounts'),
    refetchInterval: 5000,
  })
  const active = accounts.data?.find((account) => account.active)
  const accountId = active?.id ?? ''

  useEffect(() => {
    replyRequestId.current += 1
    setSelected(null)
    setSearchInput('')
    setMessageQuery('')
    setReplyTargetId(null)
    setLoadingReplyId(null)
    setUnavailableReplyId(null)
  }, [accountId])

  const dialogs = useInfiniteQuery({
    queryKey: ['telegram-preview', 'dialogs', accountId, folder],
    enabled: Boolean(accountId && active?.connected),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ account_id: accountId, folder, limit: '40' })
      if (pageParam) params.set('cursor', pageParam)
      return request<TelegramPreviewDialogsPage>(`/api/v1/telegram-preview/dialogs?${params}`)
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })

  const messages = useInfiniteQuery({
    queryKey: ['telegram-preview', 'messages', accountId, selected?.id ?? null, messageQuery],
    enabled: Boolean(accountId && active?.connected && selected),
    initialPageParam: null as number | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ account_id: accountId, limit: '40' })
      if (pageParam) params.set('before_id', String(pageParam))
      if (messageQuery) params.set('query', messageQuery)
      return request<TelegramPreviewMessagesPage>(
        `/api/v1/telegram-preview/chats/${selected!.id}/messages?${params}`,
      )
    },
    getNextPageParam: (page) => page.next_before_id ?? undefined,
  })

  const allDialogs = useMemo(() => {
    const seen = new Set<number>()
    return (dialogs.data?.pages.flatMap((page) => page.items) ?? []).filter((item) => {
      if (seen.has(item.id)) return false
      seen.add(item.id)
      return !dialogFilter || item.title.toLowerCase().includes(dialogFilter.toLowerCase())
    })
  }, [dialogFilter, dialogs.data?.pages])

  const allMessages = useMemo(() => {
    const seen = new Set<number>()
    return [...(messages.data?.pages ?? [])]
      .reverse()
      .flatMap((page) => page.items)
      .filter((item) => {
        if (seen.has(item.id)) return false
        seen.add(item.id)
        return true
      })
      .sort((left, right) => left.id - right.id)
  }, [messages.data?.pages])
  const messageGroups = useMemo(() => groupMessages(allMessages), [allMessages])
  const newestMessageId = allMessages[allMessages.length - 1]?.id

  useLayoutEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return
    if (previousScrollHeight.current !== null) {
      viewport.scrollTop += viewport.scrollHeight - previousScrollHeight.current
      previousScrollHeight.current = null
      return
    }
    if (stickToBottom.current) viewport.scrollTop = viewport.scrollHeight
  }, [newestMessageId, selected?.id, messages.data?.pages.length])

  useEffect(() => {
    if (replyTargetId === null) return
    const target = document.getElementById(`message-${replyTargetId}`)
    if (!target) return
    const targetId = replyTargetId
    target.scrollIntoView({ block: 'center', behavior: 'smooth' })
    target.classList.add('ring-2', 'ring-blue-300')
    const timeout = window.setTimeout(() => {
      target.classList.remove('ring-2', 'ring-blue-300')
      setReplyTargetId((current) => (current === targetId ? null : current))
    }, 900)
    return () => {
      window.clearTimeout(timeout)
      target.classList.remove('ring-2', 'ring-blue-300')
    }
  }, [allMessages, replyTargetId])

  function selectDialog(dialog: TelegramPreviewDialog) {
    replyRequestId.current += 1
    stickToBottom.current = true
    setSelected(dialog)
    setSearchInput('')
    setMessageQuery('')
    setReplyTargetId(null)
    setLoadingReplyId(null)
    setUnavailableReplyId(null)
  }

  function searchMessages(event: FormEvent) {
    event.preventDefault()
    stickToBottom.current = false
    setMessageQuery(searchInput.trim())
  }

  async function loadOlder() {
    if (viewportRef.current) previousScrollHeight.current = viewportRef.current.scrollHeight
    await messages.fetchNextPage()
  }

  async function replyClick(id: number) {
    const target = document.getElementById(`message-${id}`)
    if (target) {
      setReplyTargetId(id)
      return
    }
    if (!selected || loadingReplyId !== null) return

    setLoadingReplyId(id)
    setUnavailableReplyId(null)
    stickToBottom.current = false
    const requestId = ++replyRequestId.current
    try {
      const params = new URLSearchParams({ account_id: accountId })
      const message = await request<TelegramPreviewMessage>(
        `/api/v1/telegram-preview/chats/${selected.id}/messages/${id}?${params}`,
      )
      if (requestId !== replyRequestId.current) return
      queryClient.setQueryData<InfiniteData<TelegramPreviewMessagesPage>>(
        ['telegram-preview', 'messages', accountId, selected.id, messageQuery],
        (current) => {
          if (!current?.pages.length) return current
          if (current.pages.some((page) => page.items.some((item) => item.id === message.id))) {
            return current
          }
          const pages = [...current.pages]
          const oldestIndex = pages.length - 1
          pages[oldestIndex] = {
            ...pages[oldestIndex],
            items: [...pages[oldestIndex].items, message],
          }
          return { ...current, pages }
        },
      )
      setReplyTargetId(id)
    } catch {
      if (requestId === replyRequestId.current) setUnavailableReplyId(id)
    } finally {
      if (requestId === replyRequestId.current) setLoadingReplyId(null)
    }
  }

  const connected = Boolean(active?.connected)
  return (
    <div className="flex min-h-0 flex-1 flex-col [&>header]:shrink-0">
      <PageHeader
        eyebrow={t('telegramPreview.eyebrow')}
        title={t('telegramPreview.title')}
        description={t('telegramPreview.description')}
      />
      <section
        className={cn(
          'grid min-h-0 flex-1 grid-cols-[310px_minmax(0,1fr)] overflow-hidden',
          'rounded-[6px] border border-slate-200 bg-white shadow-sm',
          'max-md:grid-cols-1',
        )}
      >
        <aside
          className={cn(
            'flex min-h-0 flex-col border-r border-slate-200 bg-white',
            selected && 'max-md:hidden',
          )}
        >
          <div className="border-b border-slate-200 p-3">
            <div className="grid grid-cols-2 rounded-[5px] bg-slate-100 p-0.5">
              {(['main', 'archived'] as const).map((value) => (
                <button
                  key={value}
                  className={cn(
                    'flex h-8 items-center justify-center gap-1.5 rounded-[4px] border-0 text-[11px] font-semibold',
                    folder === value
                      ? 'bg-white text-slate-700 shadow-sm'
                      : 'bg-transparent text-slate-400',
                  )}
                  onClick={() => {
                    setFolder(value)
                    setSelected(null)
                  }}
                >
                  {value === 'main' ? <Inbox size={13} /> : <Archive size={13} />}
                  {t(value === 'main' ? 'telegramPreview.main' : 'telegramPreview.archived')}
                </button>
              ))}
            </div>
            <label className="mt-2.5 flex h-8.5 items-center gap-2 rounded-[5px] border border-slate-200 px-2.5 text-slate-400 focus-within:border-blue-300">
              <Search size={14} />
              <input
                className="min-w-0 flex-1 border-0 bg-transparent text-[11px] text-slate-700 outline-none"
                value={dialogFilter}
                onChange={(event) => setDialogFilter(event.target.value)}
                placeholder={t('telegramPreview.filterChats')}
              />
              {dialogFilter ? (
                <button
                  className="grid size-5 place-items-center border-0 bg-transparent"
                  aria-label={t('telegramPreview.clearChatFilter')}
                  onClick={() => setDialogFilter('')}
                >
                  <X size={12} />
                </button>
              ) : null}
            </label>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {!connected ? (
              <EmptyState
                icon={Radio}
                title={t('telegramPreview.accountDisconnected')}
                detail={t('telegramPreview.accountDisconnectedDetail')}
              />
            ) : dialogs.isLoading ? (
              <Loading label={t('telegramPreview.loadingChats')} />
            ) : dialogs.isError ? (
              <EmptyState
                icon={MessageCircle}
                title={t('telegramPreview.loadChatsFailed')}
                detail={messageFrom(dialogs.error)}
              />
            ) : allDialogs.length ? (
              allDialogs.map((dialog) => (
                <DialogRow
                  key={dialog.id}
                  accountId={accountId}
                  dialog={dialog}
                  selected={selected?.id === dialog.id}
                  onSelect={() => selectDialog(dialog)}
                />
              ))
            ) : (
              <EmptyState
                icon={folder === 'main' ? Inbox : Archive}
                title={
                  dialogFilter
                    ? t('telegramPreview.noMatchingChats')
                    : folder === 'main'
                      ? t('telegramPreview.mainEmpty')
                      : t('telegramPreview.archivedEmpty')
                }
              />
            )}
          </div>
          {dialogs.hasNextPage ? (
            <button
              className="h-10 shrink-0 border-0 border-t border-slate-200 bg-white text-[11px] text-blue-600 hover:bg-blue-50"
              onClick={() => void dialogs.fetchNextPage()}
              disabled={dialogs.isFetchingNextPage}
            >
              {t(
                dialogs.isFetchingNextPage
                  ? 'telegramPreview.loading'
                  : 'telegramPreview.loadMoreChats',
              )}
            </button>
          ) : null}
        </aside>

        <article
          className={cn(
            'relative min-h-0 min-w-0 flex-col bg-[#f4f7fa]',
            selected ? 'flex' : 'hidden md:flex',
          )}
        >
          {selected ? (
            <>
              <header className="flex h-14 shrink-0 items-center gap-2.5 border-b border-slate-200 bg-white px-3.5">
                <IconButton
                  label={t('telegramPreview.backToChats')}
                  icon={ArrowLeft}
                  className="hidden max-md:grid"
                  onClick={() => setSelected(null)}
                />
                <Avatar
                  accountId={accountId}
                  peerId={selected.id}
                  inlineSource={selected.inline_avatar}
                  title={selected.title}
                  kind={selected.kind}
                  className="size-9"
                />
                <div className="min-w-0 flex-1">
                  <strong className="block truncate text-[13px] text-slate-800">
                    {selected.title}
                  </strong>
                  <span className="mt-0.5 flex items-center gap-1 text-[10px] text-slate-400">
                    <ChatGlyph kind={selected.kind} size={11} />
                    {t(`telegramPreview.kinds.${selected.kind}`)}
                    {selected.username ? ` · @${selected.username}` : ''}
                  </span>
                </div>
                <form
                  className="flex h-8.5 w-66 items-center gap-1.5 rounded-[5px] border border-slate-200 bg-slate-50 px-2 max-sm:w-36"
                  onSubmit={searchMessages}
                >
                  <Search size={13} className="shrink-0 text-slate-400" />
                  <input
                    className="min-w-0 flex-1 border-0 bg-transparent text-[11px] text-slate-700 outline-none"
                    value={searchInput}
                    onChange={(event) => setSearchInput(event.target.value)}
                    placeholder={t('telegramPreview.searchCurrent')}
                  />
                  {messageQuery || searchInput ? (
                    <button
                      type="button"
                      className="grid size-5 place-items-center border-0 bg-transparent text-slate-400"
                      aria-label={t('telegramPreview.clearMessageSearch')}
                      onClick={() => {
                        setSearchInput('')
                        setMessageQuery('')
                        stickToBottom.current = true
                      }}
                    >
                      <X size={12} />
                    </button>
                  ) : null}
                </form>
              </header>
              {messageQuery ? (
                <div className="flex h-8 shrink-0 items-center justify-between border-b border-blue-100 bg-blue-50 px-3.5 text-[10px] text-blue-700">
                  <span>{t('telegramPreview.searchResults', { query: messageQuery })}</span>
                  <span>{t('telegramPreview.loadedCount', { count: allMessages.length })}</span>
                </div>
              ) : null}
              <div
                ref={viewportRef}
                data-testid="message-viewport"
                className="min-h-0 flex-1 overflow-y-auto px-5 py-4 max-sm:px-2.5"
                onScroll={(event) => {
                  const node = event.currentTarget
                  stickToBottom.current =
                    node.scrollHeight - node.scrollTop - node.clientHeight < 120
                }}
              >
                {messages.hasNextPage ? (
                  <div className="mb-3 flex justify-center">
                    <ToolButton onClick={() => void loadOlder()}>
                      {t(
                        messages.isFetchingNextPage
                          ? 'telegramPreview.loadingHistory'
                          : 'telegramPreview.loadOlder',
                      )}
                    </ToolButton>
                  </div>
                ) : null}
                {messages.isLoading ? (
                  <Loading label={t('telegramPreview.loadingMessages')} />
                ) : messages.isError ? (
                  <EmptyState
                    icon={MessageCircle}
                    title={t('telegramPreview.loadMessagesFailed')}
                    detail={messageFrom(messages.error)}
                  />
                ) : messageGroups.length ? (
                  <div className="mx-auto flex max-w-230 flex-col gap-2">
                    {messageGroups.map((group, index) => {
                      const previous = messageGroups[index - 1]?.items[0]
                      return (
                        <MessageBubble
                          key={group.key}
                          accountId={accountId}
                          group={group}
                          showDay={
                            !previous ||
                            messageDay(
                              previous.date,
                              locale,
                              t('telegramPreview.unknownDate'),
                              t('telegramPreview.today'),
                              t('telegramPreview.yesterday'),
                            ) !==
                              messageDay(
                                group.items[0].date,
                                locale,
                                t('telegramPreview.unknownDate'),
                                t('telegramPreview.today'),
                                t('telegramPreview.yesterday'),
                              )
                          }
                          onReplyClick={(id) => void replyClick(id)}
                          loadingReplyId={loadingReplyId}
                          unavailableReplyId={unavailableReplyId}
                        />
                      )
                    })}
                  </div>
                ) : (
                  <EmptyState
                    icon={MessagesSquare}
                    title={t(
                      messageQuery
                        ? 'telegramPreview.noMatchingMessages'
                        : 'telegramPreview.chatEmpty',
                    )}
                  />
                )}
              </div>
              {!stickToBottom.current && allMessages.length ? (
                <button
                  className="absolute right-4 bottom-4 grid size-9 place-items-center rounded-full border border-slate-200 bg-white text-slate-500 shadow-lg"
                  title={t('telegramPreview.latest')}
                  aria-label={t('telegramPreview.latest')}
                  onClick={() => {
                    stickToBottom.current = true
                    viewportRef.current?.scrollTo({
                      top: viewportRef.current.scrollHeight,
                      behavior: 'smooth',
                    })
                  }}
                >
                  <ArrowDown size={16} />
                </button>
              ) : null}
            </>
          ) : (
            <div className="grid h-full place-items-center p-8">
              <div className="max-w-72 text-center">
                <span className="mx-auto grid size-12 place-items-center rounded-[6px] border border-slate-200 bg-white text-blue-600 shadow-sm">
                  <MessagesSquare size={24} />
                </span>
                <strong className="mt-4 block text-[14px] text-slate-700">
                  {t('telegramPreview.selectChat')}
                </strong>
              </div>
            </div>
          )}
        </article>
      </section>
    </div>
  )
}
