import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, History, Search, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import Linkify from 'linkify-react'
import { request } from '../api/client'
import {
  Badge,
  Button,
  EmptyState,
  fieldClass,
  IconButton,
  PageHeader,
  Select,
  tableClass,
  tableWrapClass,
} from '../components/ui'
import type { ForwardingRule, HistoryPage as HistoryResult } from '../types'
import { cn } from '../utils/cn'
import { shortDate } from '../utils/format'

export function HistoryPage() {
  const { t } = useTranslation()
  const [rule, setRule] = useState('all')
  const [keyword, setKeyword] = useState('')
  const [filters, setFilters] = useState({ rule: 'all', keyword: '' })
  const [page, setPage] = useState(1)
  const rulesQuery = useQuery({
    queryKey: ['rules'],
    queryFn: () => request<ForwardingRule[]>('/api/v1/rules'),
  })
  const historyQuery = useQuery({
    queryKey: ['history', filters, page],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page), page_size: '20' })
      if (filters.rule !== 'all') params.set('rule_name', filters.rule)
      if (filters.keyword) params.set('keyword', filters.keyword)
      return request<HistoryResult>(`/api/v1/history?${params}`)
    },
  })
  const pages = Math.max(1, Math.ceil((historyQuery.data?.total ?? 0) / 20))
  function search(event?: FormEvent) {
    event?.preventDefault()
    setPage(1)
    setFilters({ rule, keyword: keyword.trim() })
  }
  function reset() {
    setRule('all')
    setKeyword('')
    setPage(1)
    setFilters({ rule: 'all', keyword: '' })
  }

  return (
    <>
      <PageHeader
        eyebrow={t('history.eyebrow')}
        title={t('history.title')}
        description={t('history.description')}
      />
      <form
        className={cn(
          'mb-3 grid grid-cols-[220px_minmax(260px,1fr)_auto] items-end gap-3',
          'rounded-md border border-slate-200 bg-white p-3 max-md:grid-cols-1',
        )}
        onSubmit={search}
      >
        <label className={fieldClass}>
          <span>{t('history.rule')}</span>
          <Select
            value={rule}
            onValueChange={setRule}
            options={[
              { value: 'all', label: t('history.allRules') },
              ...(rulesQuery.data ?? []).map((item) => ({ value: item.name, label: item.name })),
            ]}
          />
        </label>
        <label className={fieldClass}>
          <span>{t('history.keyword')}</span>
          <div
            className={cn(
              'flex h-9.5 items-center gap-2 rounded-[5px] border border-slate-200',
              'px-2.5 text-slate-400 focus-within:border-blue-300',
              'focus-within:ring-3 focus-within:ring-blue-500/10',
            )}
          >
            <Search size={16} />
            <input
              className="w-full border-0 bg-transparent text-[13px] text-slate-700 outline-none"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder={t('history.searchPlaceholder')}
            />
          </div>
        </label>
        <div className="flex gap-2 max-md:[&>.button]:flex-1">
          <Button type="submit" icon={Search}>
            {t('history.search')}
          </Button>
          {filters.rule !== 'all' || filters.keyword ? (
            <IconButton type="button" label={t('history.clearFilters')} icon={X} onClick={reset} />
          ) : null}
        </div>
      </form>
      <section className={tableWrapClass}>
        <div className="flex min-h-12 items-center border-b border-slate-200 px-4">
          <span className="flex items-center gap-2">
            <strong className="text-[13px] text-slate-700">{t('history.results')}</strong>
            <small className="text-[13px] text-slate-400">
              {t('history.recordCount', { count: historyQuery.data?.total ?? 0 })}
            </small>
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className={cn(tableClass, 'max-md:min-w-195')}>
            <thead>
              <tr>
                <th>{t('history.columns.processedAt')}</th>
                <th>{t('history.columns.rule')}</th>
                <th>{t('history.columns.source')}</th>
                <th>{t('history.columns.sender')}</th>
                <th>{t('history.columns.content')}</th>
                <th>{t('history.columns.type')}</th>
              </tr>
            </thead>
            <tbody>
              {(historyQuery.data?.items ?? []).map((item) => (
                <tr key={item.id}>
                  <td className="min-w-32 font-mono text-slate-500">
                    {shortDate(item.forwarded_at)}
                  </td>
                  <td>
                    <strong className="text-slate-700">{item.rule_name}</strong>
                  </td>
                  <td>
                    <span className="block max-w-48 truncate">
                      {item.source_chat_name || item.source_chat_id}
                    </span>
                  </td>
                  <td>
                    <span>{item.sender_name || '-'}</span>
                    {item.sender_username ? (
                      <small className="mt-1 block text-xs text-slate-400">
                        @{item.sender_username}
                      </small>
                    ) : null}
                  </td>
                  <td>
                    <Linkify
                      as="p"
                      options={{ target: '_blank', rel: 'noopener noreferrer', className: 'linkified' }}
                      className="m-0 line-clamp-2 max-w-108 leading-4"
                    >
                      {item.content || t('history.noText')}
                    </Linkify>
                  </td>
                  <td>
                    <Badge tone="gray">{item.media_type || 'text'}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!historyQuery.data?.items.length ? (
          <EmptyState icon={History} title={t('history.empty')} detail={t('history.emptyDetail')} />
        ) : null}
        <footer
          className={cn(
            'flex min-h-13 items-center justify-between border-t border-slate-200',
            'px-4 text-[13px] text-slate-400',
          )}
        >
          <span>{t('history.pagination', { page, pages })}</span>
          <div className="flex gap-1">
            <IconButton
              label={t('history.previous')}
              icon={ChevronLeft}
              disabled={page <= 1}
              onClick={() => setPage((value) => value - 1)}
            />
            <IconButton
              label={t('history.next')}
              icon={ChevronRight}
              disabled={page >= pages}
              onClick={() => setPage((value) => value + 1)}
            />
          </div>
        </footer>
      </section>
    </>
  )
}
