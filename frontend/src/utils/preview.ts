import type { TFunction } from 'i18next'
import type { TelegramPreviewMessage } from '../types'

export type DialogFolder = 'main' | 'archived'

export interface MessageGroup {
  key: string
  items: TelegramPreviewMessage[]
}

/** Visual media grouped per message (same-album messages share one group) */
export interface ImageGroup {
  message: TelegramPreviewMessage
  items: TelegramPreviewMessage[]
}

export function previewTime(value: string | null | undefined, locale: string): string {
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

export function messageTime(value: string | null | undefined, locale: string): string {
  if (!value) return ''
  return new Date(value).toLocaleTimeString(locale, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

export function messageDay(
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

export function fileSize(value?: number | null): string {
  if (!value) return ''
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`
}

export function mediaDuration(value?: number | null): string {
  if (value === null || value === undefined || value < 0) return ''
  const seconds = Math.floor(value)
  const parts = [Math.floor(seconds / 3600), Math.floor((seconds % 3600) / 60), seconds % 60]
  return (parts[0] ? parts : parts.slice(1))
    .map((part, index) => (index === 0 ? String(part) : String(part).padStart(2, '0')))
    .join(':')
}

export function isPreviewableMedia(media: NonNullable<TelegramPreviewMessage['media']>): boolean {
  return (
    !['sticker', 'video', 'video_note', 'webpage'].includes(media.type) &&
    media.is_visual_media &&
    media.has_thumbnail
  )
}

export function hasMediaPreview(media: NonNullable<TelegramPreviewMessage['media']>): boolean {
  if (media.type !== 'webpage') return true
  return Boolean(
    media.has_thumbnail ||
    media.webpage?.site_name ||
    media.webpage?.title ||
    media.webpage?.description ||
    media.webpage?.author,
  )
}

export function serviceText(
  action: string | null | undefined,
  details: TelegramPreviewMessage['service_details'],
  senderName: string,
  t: TFunction,
  locale: string,
): string {
  const joiner = locale.startsWith('zh') ? '、' : ', '
  const names = (details?.user_names ?? []).join(joiner)
  const title = details?.title ?? ''
  const sender = senderName || names
  switch (action) {
    case 'MessageActionChatAddUser':
      return t('telegramPreview.service.chatAddUser', { names })
    case 'MessageActionChatDeleteUser':
      return t('telegramPreview.service.chatDeleteUser', { names })
    case 'MessageActionChatCreate':
      return t('telegramPreview.service.chatCreate', { sender, title })
    case 'MessageActionChatEditTitle':
      return t('telegramPreview.service.chatEditTitle', { title })
    case 'MessageActionChatEditPhoto':
      return t('telegramPreview.service.chatEditPhoto')
    case 'MessageActionChatJoinedByLink':
      return t('telegramPreview.service.chatJoinedByLink', { sender })
    case 'MessageActionChatJoinedByRequest':
      return t('telegramPreview.service.chatJoinedByRequest', { sender })
    case 'MessageActionPinMessage':
      return t('telegramPreview.service.chatPinMessage', { sender })
    default:
      return t('telegramPreview.serviceUpdated')
  }
}

export function mediaFrame(media: NonNullable<TelegramPreviewMessage['media']>) {
  const width = media.width && media.width > 0 ? media.width : 4
  const height = media.height && media.height > 0 ? media.height : 3
  const isStickerLike =
    media.type === 'sticker' ||
    media.mime_type === 'video/webm' ||
    media.file_name?.toLowerCase().endsWith('.webm')
  if (isStickerLike) {
    return {
      aspectRatio: `${width} / ${height}`,
      width: '180px',
      maxWidth: '100%',
    }
  }
  const image = isPreviewableMedia(media)
  const minimumRatio = image ? 0.72 : 0.56
  const ratio = Math.min(2, Math.max(minimumRatio, width / height))
  const preferredWidth =
    ratio < 1
      ? image
        ? 280 + ((ratio - 0.72) / 0.28) * 80
        : 240 + ((ratio - 0.56) / 0.44) * 120
      : 360 + (ratio - 1) * 160
  return {
    aspectRatio: image ? `${ratio}` : `${width} / ${height}`,
    width: `${Math.round(preferredWidth)}px`,
    maxWidth: '100%',
  }
}

export function groupMessages(messages: TelegramPreviewMessage[]): MessageGroup[] {
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
