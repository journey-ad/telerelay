import type { TFunction } from 'i18next'
import type { TelegramChat } from '../types'

function withUsername(name: string, chat: Pick<TelegramChat, 'username'>): string {
  return chat.username ? `${name} (@${chat.username})` : name
}

/**
 * Label for an input, which shows no id of its own: Telegram stops naming
 * deleted accounts and banned chats, so the name falls back to the last one the
 * backend cached and then to the unknown-chat label carrying the id.
 */
export function chatLabel(
  chat: Pick<TelegramChat, 'id' | 'title' | 'username'>,
  t: TFunction,
): string {
  return withUsername(chat.title || t('chatInput.unknown', { id: chat.id }), chat)
}

/** Label for a picker row, which already lists the id beside its name. */
export function chatRowLabel(chat: Pick<TelegramChat, 'title' | 'username'>, t: TFunction): string {
  return withUsername(chat.title || t('common.unknownChat'), chat)
}
