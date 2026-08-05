import { Bot, CheckCircle2, Radio, UserRound, UsersRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { TelegramPreviewDialog } from '../../types'
import { avatarInitials } from '../../utils/avatar'
import { cn } from '../../utils/cn'
import { hashColor } from '../../utils/color'
import { peerAvatarPath, previewTime, serviceText } from '../../utils/preview'
import { AuthenticatedImage } from '../AuthenticatedImage'

export function ChatGlyph({
  kind,
  size = 14,
}: {
  kind: TelegramPreviewDialog['kind']
  size?: number
}) {
  const Icon =
    kind === 'bot' ? Bot : kind === 'private' ? UserRound : kind === 'channel' ? Radio : UsersRound
  return <Icon size={size} />
}

export function Avatar({
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
  const colors = hashColor(String(peerId ?? title))
  return (
    <AuthenticatedImage
      path={peerAvatarPath(peerId)}
      inlineSource={inlineSource}
      alt={t('telegramPreview.avatarAlt', { title })}
      accountId={accountId}
      className={cn('grid shrink-0 place-items-center rounded-md', className)}
      style={{ backgroundColor: colors.background, color: colors.foreground }}
      fallback={
        <span className="grid size-full place-items-center text-xs font-bold">
          {title ? avatarInitials(title) : kind ? <ChatGlyph kind={kind} /> : 'TG'}
        </span>
      }
    />
  )
}

export function DialogRow({
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
          <strong className="truncate text-sm text-slate-700">{dialog.title}</strong>
          {dialog.verified ? <CheckCircle2 size={12} className="shrink-0 text-blue-500" /> : null}
        </span>
        <span className="mt-1 flex min-w-0 items-center gap-1 text-xs text-slate-400">
          {dialog.last_message?.outgoing ? (
            <span className="text-blue-500">{t('telegramPreview.you')}</span>
          ) : null}
          <span className="truncate">
            {dialog.last_message
              ? dialog.last_message.service_action
                ? serviceText(
                    dialog.last_message.service_action,
                    dialog.last_message.service_details,
                    dialog.last_message.sender_name ?? '',
                    t,
                    locale,
                  )
                : dialog.last_message.preview || t('telegramPreview.noMessages')
              : t('telegramPreview.noMessages')}
          </span>
        </span>
      </span>
      <span className="flex h-full min-w-8 flex-col items-end justify-center gap-1.5">
        <time className="text-xs text-slate-400">
          {previewTime(dialog.last_message?.date, locale)}
        </time>
        {dialog.unread_count ? (
          <span className="grid min-w-4.5 place-items-center rounded-full bg-blue-600 px-1 text-xs font-bold leading-4.5 text-white">
            {dialog.unread_count > 99 ? '99+' : dialog.unread_count}
          </span>
        ) : dialog.pinned ? (
          <span className="text-xs text-slate-300">{t('telegramPreview.pinned')}</span>
        ) : null}
      </span>
    </button>
  )
}
