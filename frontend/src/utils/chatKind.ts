import type { TelegramChat } from '../types'

/** Picker buckets: Telegram's supergroup shares the group bucket. */
export type ChatKind = 'private' | 'bot' | 'group' | 'channel' | 'unknown'
export type ChatKindFilter = 'all' | ChatKind

export const chatKindFilters: ChatKindFilter[] = [
  'all',
  'private',
  'bot',
  'group',
  'channel',
  'unknown',
]

export function chatKind(kind: TelegramChat['kind']): ChatKind {
  return kind === 'supergroup' ? 'group' : kind
}

export function chatKindMatches(chat: Pick<TelegramChat, 'kind'>, filter: ChatKindFilter): boolean {
  return filter === 'all' || chatKind(chat.kind) === filter
}

export interface ChatKindSection<T> {
  kind: ChatKind
  chats: T[]
}

/** Split chats into the buckets the picker lists, in a fixed order. */
export function chatKindSections<T extends Pick<TelegramChat, 'kind'>>(
  chats: T[],
  filter: ChatKindFilter,
): ChatKindSection<T>[] {
  return chatKindFilters
    .filter((kind): kind is ChatKind => kind !== 'all' && (filter === 'all' || filter === kind))
    .map((kind) => ({ kind, chats: chats.filter((chat) => chatKind(chat.kind) === kind) }))
    .filter((section) => section.chats.length > 0)
}

/** Per-filter totals, so a filter button counts what selecting it would list. */
export function chatKindCounts<T extends Pick<TelegramChat, 'kind'>>(
  chats: T[],
): Record<ChatKindFilter, number> {
  const counts: Record<ChatKindFilter, number> = {
    all: chats.length,
    private: 0,
    bot: 0,
    group: 0,
    channel: 0,
    unknown: 0,
  }
  for (const chat of chats) counts[chatKind(chat.kind)] += 1
  return counts
}
