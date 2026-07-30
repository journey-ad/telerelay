import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, History, Search, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
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
        eyebrow="MESSAGE LEDGER"
        title="消息记录"
        description="查询已经处理的转发消息与来源信息。"
      />
      <form
        className={cn(
          'mb-3 grid grid-cols-[220px_minmax(260px,1fr)_auto] items-end gap-3',
          'rounded-md border border-slate-200 bg-white p-3 max-md:grid-cols-1',
        )}
        onSubmit={search}
      >
        <label className={fieldClass}>
          <span>转发规则</span>
          <Select
            value={rule}
            onValueChange={setRule}
            options={[
              { value: 'all', label: '全部规则' },
              ...(rulesQuery.data ?? []).map((item) => ({ value: item.name, label: item.name })),
            ]}
          />
        </label>
        <label className={fieldClass}>
          <span>内容关键词</span>
          <div
            className={cn(
              'flex h-9.5 items-center gap-2 rounded-[5px] border border-slate-200',
              'px-2.5 text-slate-400 focus-within:border-blue-300',
              'focus-within:ring-3 focus-within:ring-blue-500/10',
            )}
          >
            <Search size={16} />
            <input
              className="w-full border-0 bg-transparent text-[11px] text-slate-700 outline-none"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="搜索消息内容"
            />
          </div>
        </label>
        <div className="flex gap-2 max-md:[&>.button]:flex-1">
          <Button type="submit" icon={Search}>
            查询
          </Button>
          {filters.rule !== 'all' || filters.keyword ? (
            <IconButton type="button" label="清除筛选" icon={X} onClick={reset} />
          ) : null}
        </div>
      </form>
      <section className={tableWrapClass}>
        <div className="flex min-h-12 items-center border-b border-slate-200 px-4">
          <span className="flex items-center gap-2">
            <strong className="text-[11px] text-slate-700">查询结果</strong>
            <small className="text-[9px] text-slate-400">
              {historyQuery.data?.total ?? 0} 条记录
            </small>
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className={cn(tableClass, 'max-md:min-w-195')}>
            <thead>
              <tr>
                <th>处理时间</th>
                <th>规则</th>
                <th>来源</th>
                <th>发送者</th>
                <th>消息内容</th>
                <th>类型</th>
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
                      <small className="mt-1 block text-[8px] text-slate-400">
                        @{item.sender_username}
                      </small>
                    ) : null}
                  </td>
                  <td>
                    <p className="m-0 line-clamp-2 max-w-108 leading-4">
                      {item.content || '[无文本内容]'}
                    </p>
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
          <EmptyState
            icon={History}
            title="没有找到消息记录"
            detail="调整筛选条件，或等待规则开始处理消息。"
          />
        ) : null}
        <footer
          className={cn(
            'flex min-h-13 items-center justify-between border-t border-slate-200',
            'px-4 text-[9px] text-slate-400',
          )}
        >
          <span>
            第 {page} / {pages} 页
          </span>
          <div className="flex gap-1">
            <IconButton
              label="上一页"
              icon={ChevronLeft}
              disabled={page <= 1}
              onClick={() => setPage((value) => value - 1)}
            />
            <IconButton
              label="下一页"
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
