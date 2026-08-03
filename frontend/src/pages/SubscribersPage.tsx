import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pause, Play, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { accountRequest, json } from '../api/client'
import { useAccountScope } from '../hooks/useAccountScope'
import {
  Badge,
  EmptyState,
  IconButton,
  PageHeader,
  tableClass,
  tableWrapClass,
} from '../components/ui'
import type { Subscriber, SubscriberList } from '../types'
import { cn } from '../utils/cn'

function formatTimestamp(seconds: number, locale?: string): string {
  if (!seconds) return '-'
  const date = new Date(Number(seconds) * 1000)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString(locale, { hour12: false })
}

export function SubscribersPage() {
  const { t, i18n } = useTranslation()
  const accountId = useAccountScope()
  const queryClient = useQueryClient()
  const subscribersQuery = useQuery({
    queryKey: ['subscribers', accountId],
    queryFn: () => accountRequest<SubscriberList>(accountId, '/api/v1/subscribers'),
  })
  const toggleStatus = useMutation({
    mutationFn: (subscriber: Subscriber) => {
      const action = subscriber.status === 'active' ? 'pause' : 'resume'
      return accountRequest(
        accountId,
        `/api/v1/subscribers/${subscriber.user_id}/${action}`,
        json('POST'),
      )
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['subscribers', accountId] })
    },
  })
  const counts = subscribersQuery.data?.counts
  const items = subscribersQuery.data?.items ?? []

  return (
    <>
      <PageHeader
        eyebrow={t('subscribers.eyebrow')}
        title={t('subscribers.title')}
        description={t('subscribers.description')}
      />
      <div className="mb-4 grid grid-cols-3 gap-3 max-md:grid-cols-1">
        {(
          [
            { key: 'total', tone: 'text-slate-700', label: t('subscribers.total') },
            { key: 'active', tone: 'text-emerald-600', label: t('subscribers.active') },
            { key: 'paused', tone: 'text-rose-600', label: t('subscribers.paused') },
          ] as const
        ).map(({ key, tone, label }) => (
          <div
            key={key}
            className={cn(
              'rounded-md border border-slate-200 bg-white p-4',
              'shadow-[0_2px_7px_rgba(29,57,96,0.025)]',
            )}
          >
            <small className="block text-xs text-slate-400">{label}</small>
            <strong className={cn('mt-1 block text-xl font-bold', tone)}>
              {counts?.[key] ?? 0}
            </strong>
          </div>
        ))}
      </div>
      <section className={tableWrapClass}>
        {items.length === 0 ? (
          <EmptyState
            icon={Users}
            title={t('subscribers.empty')}
            detail={t('subscribers.emptyDetail')}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className={cn(tableClass, 'max-md:min-w-195')}>
              <thead>
                <tr>
                  <th>{t('subscribers.columns.user')}</th>
                  <th>{t('subscribers.columns.status')}</th>
                  <th>{t('subscribers.columns.delivered')}</th>
                  <th>{t('subscribers.columns.firstSeen')}</th>
                  <th>{t('subscribers.columns.updated')}</th>
                  <th aria-label={t('subscribers.columns.actions')} />
                </tr>
              </thead>
              <tbody>
                {items.map((subscriber) => {
                  const active = subscriber.status === 'active'
                  const name = [subscriber.first_name, subscriber.last_name]
                    .filter(Boolean)
                    .join(' ')
                  return (
                    <tr key={subscriber.user_id}>
                      <td>
                        <div className="flex min-w-0 flex-col">
                          <span className="truncate font-medium text-slate-700">
                            {name || subscriber.username || t('subscribers.unknownUser')}
                          </span>
                          <small className="truncate text-xs text-slate-400">
                            {[
                              subscriber.username && `@${subscriber.username}`,
                              `ID ${subscriber.user_id}`,
                            ]
                              .filter(Boolean)
                              .join(' · ')}
                          </small>
                        </div>
                      </td>
                      <td>
                        <Badge tone={active ? 'green' : 'gray'}>
                          {t(active ? 'subscribers.statusActive' : 'subscribers.statusPaused')}
                        </Badge>
                      </td>
                      <td>
                        <strong className="font-mono text-xs font-semibold text-slate-700">
                          {subscriber.delivered_count.toLocaleString(i18n.resolvedLanguage)}
                        </strong>
                      </td>
                      <td className="text-[13px] text-slate-500">
                        {formatTimestamp(subscriber.first_seen_at, i18n.resolvedLanguage)}
                      </td>
                      <td className="text-[13px] text-slate-500">
                        {formatTimestamp(subscriber.updated_at, i18n.resolvedLanguage)}
                      </td>
                      <td>
                        <div className="flex justify-end">
                          <IconButton
                            label={t(active ? 'subscribers.pause' : 'subscribers.resume')}
                            icon={active ? Pause : Play}
                            disabled={toggleStatus.isPending}
                            onClick={() => toggleStatus.mutate(subscriber)}
                          />
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}
