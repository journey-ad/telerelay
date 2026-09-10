import { useQuery } from '@tanstack/react-query'
import { request } from '../api/client'
import { useAccountScope } from './useAccountScope'
import type { ChatRef, TelegramChat } from '../types'

export function useTelegramChats() {
  const accountId = useAccountScope()

  return useQuery({
    queryKey: ['telegram-chats', accountId],
    queryFn: () => request<TelegramChat[]>(`/api/v1/telegram-accounts/${accountId}/chats`),
    staleTime: 0,
    retry: false,
  })
}

/**
 * Resolve referenced chats the directory does not list.
 *
 * Telegram drops banned or deleted chats from the dialog list, so a rule or
 * export task pointing at one would look merely unknown. Only the ids that are
 * actually absent are queried, which keeps this request rare.
 */
export function useReferencedChats(chats: TelegramChat[] | undefined, ids: ChatRef[] = []) {
  const accountId = useAccountScope()
  const missing =
    chats && ids.length
      ? [
          ...new Set(
            ids
              .map((chat) => (typeof chat === 'number' ? chat : Number(chat)))
              .filter((chat) => Number.isFinite(chat)),
          ),
        ]
          .filter((chatId) => !chats.some((chat) => chat.id === chatId))
          .sort((left, right) => left - right)
      : []
  const lookup = missing.join(',')

  return useQuery({
    queryKey: ['telegram-chats-referenced', accountId, lookup],
    queryFn: async () => {
      const all = await request<TelegramChat[]>(
        `/api/v1/telegram-accounts/${accountId}/chats?include=${lookup}`,
      )
      const wanted = new Set(missing)
      return all.filter((chat) => wanted.has(chat.id))
    },
    enabled: missing.length > 0,
    staleTime: 60_000,
    retry: false,
  })
}
