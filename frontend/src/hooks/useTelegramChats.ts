import { useQuery } from '@tanstack/react-query'
import { request } from '../api/client'
import { useAccountScope } from './useAccountScope'
import type { TelegramChat } from '../types'

export function useTelegramChats() {
  const accountId = useAccountScope()

  return useQuery({
    queryKey: ['telegram-chats', accountId],
    queryFn: () => request<TelegramChat[]>(`/api/v1/telegram-accounts/${accountId}/chats`),
    staleTime: 0,
    retry: false,
  })
}
