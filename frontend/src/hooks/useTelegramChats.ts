import { useQuery } from '@tanstack/react-query'
import { request } from '../api/client'
import type { TelegramAccount, TelegramChat } from '../types'

export function useTelegramChats() {
  const accounts = useQuery({
    queryKey: ['telegram-accounts'],
    queryFn: () => request<TelegramAccount[]>('/api/v1/telegram-accounts'),
    staleTime: 15_000,
  })
  const accountId = accounts.data?.find((account) => account.active)?.id

  return useQuery({
    queryKey: ['telegram-chats', accountId],
    queryFn: () => request<TelegramChat[]>(`/api/v1/telegram-accounts/${accountId}/chats`),
    enabled: Boolean(accountId),
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
}
