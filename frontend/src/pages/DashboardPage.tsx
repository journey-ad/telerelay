import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { TFunction } from 'i18next'
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  CalendarDays,
  Filter,
  Gauge,
  ListChecks,
  Minus,
  Pause,
  Play,
  RefreshCcw,
  Route,
  Send,
  Target,
  TimerReset,
  Trophy,
} from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { accountRequest, json, request } from '../api/client'
import { Button, EmptyState, PageHeader, Panel } from '../components/ui'
import { useEvents } from '../hooks/useEvents'
import { useAccountScope } from '../hooks/useAccountScope'
import type { BotStatus, ForwardQueueItem, RelayEvent, Stats, TelegramAccount } from '../types'
import { cn } from '../utils/cn'
import { formatNumber, messageFrom } from '../utils/format'

type ReportPeriod = '7day' | '14day' | '30day' | 'all'
type DailyStat = Stats['daily'][number] & { total: number }
type DailyIntensityStat = DailyStat & { endDate?: string }

const periodOptions = [
  { value: '7day', labelKey: 'dashboard.periods.sevenDays' },
  { value: '14day', labelKey: 'dashboard.periods.fourteenDays' },
  { value: '30day', labelKey: 'dashboard.periods.thirtyDays' },
  { value: 'all', labelKey: 'dashboard.periods.all' },
] as const satisfies ReadonlyArray<{ value: ReportPeriod; labelKey: string }>
const periodDays = { '7day': 7, '14day': 14, '30day': 30 } as const
const metricTones = {
  blue: 'bg-blue-50 text-blue-600',
  amber: 'bg-amber-50 text-amber-600',
  cyan: 'bg-cyan-50 text-cyan-600',
  green: 'bg-emerald-50 text-emerald-600',
}
const chartTooltipStyle = {
  border: '1px solid #dbe6f4',
  borderRadius: 6,
  boxShadow: '0 12px 32px rgba(22, 63, 116, .12)',
  fontSize: 11,
}
const liveEventLimit = 50
const initialEventLimit = 10
const queuePreviewLimit = 50
const intensitySampleLimit = 30
const eventTypeKeys = {
  ready: 'dashboard.events.types.ready',
  log: 'dashboard.events.types.log',
  bot: 'dashboard.events.types.bot',
  stats: 'dashboard.events.types.stats',
  'telegram-account': 'dashboard.events.types.telegramAccount',
  'telegram-auth': 'dashboard.events.types.telegramAuth',
  forward: 'dashboard.events.types.forward',
  'button-action': 'dashboard.events.types.buttonAction',
  'scheduled-export': 'dashboard.events.types.scheduledExport',
} as const
const eventActionKeys = {
  create: 'dashboard.events.actions.create',
  activate: 'dashboard.events.actions.activate',
  delete: 'dashboard.events.actions.delete',
  start: 'dashboard.events.actions.start',
  stop: 'dashboard.events.actions.stop',
  restart: 'dashboard.events.actions.restart',
  reset: 'dashboard.events.actions.reset',
  phone: 'dashboard.events.actions.phone',
  code: 'dashboard.events.actions.code',
  password: 'dashboard.events.actions.password',
  authenticated: 'dashboard.events.actions.authenticated',
  deauthenticated: 'dashboard.events.actions.deauthenticated',
  connection: 'dashboard.events.actions.connection',
} as const
const eventStatusKeys = {
  completed: 'dashboard.events.statuses.completed',
  retrying: 'dashboard.events.statuses.retrying',
  delayed: 'dashboard.events.statuses.delayed',
  failed: 'dashboard.events.statuses.failed',
  started: 'dashboard.events.statuses.started',
  skipped: 'dashboard.events.statuses.skipped',
  cancelled: 'dashboard.events.statuses.cancelled',
} as const
const authStateKeys = {
  started: 'dashboard.events.authStates.started',
  success: 'dashboard.events.authStates.success',
  cleared: 'dashboard.events.authStates.cleared',
} as const
const queueStatusKeys = {
  processing: 'dashboard.queuePreview.statuses.processing',
  waiting: 'dashboard.queuePreview.statuses.waiting',
  pending: 'dashboard.queuePreview.statuses.pending',
} as const
const dashboardEventTypeList = [
  'bot',
  'stats',
  'telegram-account',
  'telegram-auth',
  'forward',
  'button-action',
  'scheduled-export',
]
const dashboardEventTypes = new Set(dashboardEventTypeList)
const recentEventsPath = `/api/v1/events/recent?${new URLSearchParams([
  ['limit', String(initialEventLimit)],
  ...dashboardEventTypeList.map((type) => ['types', type]),
]).toString()}`

function eventTypeLabel(type: string, t: TFunction): string {
  const key = eventTypeKeys[type as keyof typeof eventTypeKeys]
  return key ? t(key) : t('dashboard.events.types.other')
}

function accountLabel(
  accounts: TelegramAccount[] | undefined,
  event: RelayEvent,
): string | undefined {
  const id = event.payload.account_id ?? event.payload.id
  if (typeof id !== 'string' || !id) return undefined
  return accounts?.find((account) => account.id === id)?.label ?? id
}

function eventDetail(
  event: RelayEvent,
  t: TFunction,
  accounts: TelegramAccount[] | undefined,
): string {
  const message = event.payload.message
  if (['string', 'number', 'boolean'].includes(typeof message)) return String(message)

  const account = accountLabel(accounts, event)
  const withAccount = (action: string) =>
    t('dashboard.events.details.accountAction', {
      action,
      account: account ?? '',
    })

  const action = event.payload.action ?? event.payload.submitted
  if (typeof action === 'string') {
    if (event.type === 'telegram-account' && action === 'connection') {
      const connected = event.payload.connected === true
      return t(
        connected
          ? 'dashboard.events.details.accountConnected'
          : 'dashboard.events.details.accountDisconnected',
        { account: account ?? '' },
      )
    }
    const key = eventActionKeys[action as keyof typeof eventActionKeys]
    const actionLabel = key ? t(key) : action
    return account ? withAccount(actionLabel) : actionLabel
  }

  if (event.type === 'telegram-auth') {
    const state = event.payload.state
    const stateKey =
      typeof state === 'string' ? authStateKeys[state as keyof typeof authStateKeys] : undefined
    const stateLabel = stateKey ? t(stateKey) : t('dashboard.statusUpdate')
    return account ? withAccount(stateLabel) : stateLabel
  }

  const statusValue = event.payload.status
  const statusKey =
    typeof statusValue === 'string'
      ? eventStatusKeys[statusValue as keyof typeof eventStatusKeys]
      : undefined
  const status = statusKey ? t(statusKey) : t('dashboard.statusUpdate')
  if (event.type === 'forward') {
    const sourceChatId = String(event.payload.source_chat_id ?? '-')
    const sourceChatName = event.payload.source_chat_name
    const sourceChat =
      typeof sourceChatName === 'string' && sourceChatName
        ? `${sourceChatName} (${sourceChatId})`
        : sourceChatId
    return t('dashboard.events.details.forward', {
      rule: String(event.payload.rule ?? '-'),
      source: `${sourceChat}/${String(event.payload.source_message_id ?? '-')}`,
      status,
    })
  }
  if (event.type === 'button-action') {
    const buttons = Array.isArray(event.payload.buttons)
      ? event.payload.buttons.map(String).join(', ')
      : '-'
    return t('dashboard.events.details.buttonAction', {
      rule: String(event.payload.rule ?? '-'),
      buttons,
      status,
    })
  }
  if (event.type === 'scheduled-export') {
    return t('dashboard.events.details.scheduledExport', {
      task: String(event.payload.task_name ?? event.payload.task_id ?? '-'),
      chat: String(event.payload.chat_title ?? event.payload.chat_id ?? '-'),
      status,
    })
  }

  return t('dashboard.statusUpdate')
}

function eventMarkerClass(type: string): string {
  if (type === 'forward') return 'border-blue-100 bg-blue-500'
  if (type === 'button-action') return 'border-cyan-100 bg-cyan-500'
  if (type === 'scheduled-export') return 'border-amber-100 bg-amber-500'
  return 'border-slate-200 bg-slate-400'
}

function queueState(item: ForwardQueueItem): 'processing' | 'waiting' | 'pending' {
  if (item.status === 'processing') return 'processing'
  return item.available_at > Date.now() / 1000 ? 'waiting' : 'pending'
}

function queueTime(value: number, locale: string): string {
  return new Date(value * 1000).toLocaleString(locale, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function queueSource(item: ForwardQueueItem): string {
  const chat = item.source_chat_name
    ? `${item.source_chat_name} (${item.source_chat_id})`
    : String(item.source_chat_id)
  return `${chat}/${item.source_message_id}`
}

function shouldStoreDashboardEvent(event: RelayEvent): boolean {
  return dashboardEventTypes.has(event.type)
}

function localDateKey(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function fillDailySeries(source: Stats['daily'], days: number): DailyStat[] {
  const byDate = new Map(source.map((item) => [item.date, item]))
  const today = new Date()
  today.setHours(12, 0, 0, 0)

  return Array.from({ length: days }, (_, index) => {
    const date = new Date(today)
    date.setDate(today.getDate() - (days - index - 1))
    const key = localDateKey(date)
    const item = byDate.get(key)
    const forwarded = item?.forwarded ?? 0
    const filtered = item?.filtered ?? 0
    return { date: key, forwarded, filtered, total: forwarded + filtered }
  })
}

function allTimeDays(source: Stats['daily']): number {
  if (!source.length) return 1
  const first = new Date(`${source[0].date}T12:00:00`)
  const today = new Date()
  today.setHours(12, 0, 0, 0)
  return Math.max(1, Math.round((today.getTime() - first.getTime()) / 86_400_000) + 1)
}

function aggregateDaily(items: DailyStat[]) {
  return items.reduce(
    (total, item) => ({
      forwarded: total.forwarded + item.forwarded,
      filtered: total.filtered + item.filtered,
      total: total.total + item.total,
    }),
    { forwarded: 0, filtered: 0, total: 0 },
  )
}

function sampleDailyIntensity(
  items: DailyStat[],
  limit = intensitySampleLimit,
): DailyIntensityStat[] {
  if (items.length <= limit) return items

  return Array.from({ length: limit }, (_, index) => {
    const start = Math.floor((index * items.length) / limit)
    const end = Math.floor(((index + 1) * items.length) / limit)
    const bucket = items.slice(start, end)
    const totals = aggregateDaily(bucket)
    return {
      date: bucket[0].date,
      endDate: bucket[bucket.length - 1].date,
      forwarded: Math.round(totals.forwarded / bucket.length),
      filtered: Math.round(totals.filtered / bucket.length),
      total: Math.round(totals.total / bucket.length),
    }
  })
}

function percentChange(current: number, previous: number): number {
  if (!previous) return current ? 100 : 0
  return Math.round(((current - previous) / previous) * 1000) / 10
}

function formatPercent(value: number): string {
  return `${Math.round(value * 10) / 10}%`
}

function formatReportDate(value: string, locale: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(locale, {
    month: 'short',
    day: 'numeric',
    weekday: 'short',
  })
}

function TrendLabel({ value, fallback, t }: { value?: number; fallback?: string; t: TFunction }) {
  if (value === undefined) {
    return <>{fallback}</>
  }

  return (
    <>
      {value > 0 ? (
        <ArrowUpRight size={13} />
      ) : value < 0 ? (
        <ArrowDownRight size={13} />
      ) : (
        <Minus size={13} />
      )}
      {t('dashboard.comparedToPrevious', {
        value: `${value > 0 ? '+' : ''}${formatPercent(value)}`,
      })}
    </>
  )
}

export function DashboardPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage ?? 'zh-CN'
  const client = useQueryClient()
  const accountId = useAccountScope()
  const [reportPeriod, setReportPeriod] = useState<ReportPeriod>('14day')
  const [queuePreviewOpen, setQueuePreviewOpen] = useState(false)
  const reportDays = reportPeriod === 'all' ? null : periodDays[reportPeriod]
  const allTime = reportDays === null
  const statusQuery = useQuery({
    queryKey: ['bot-status', accountId],
    queryFn: () => accountRequest<BotStatus>(accountId, '/api/v1/bot/status'),
  })
  const queueQuery = useQuery({
    queryKey: ['forward-queue-items', accountId],
    queryFn: () =>
      accountRequest<ForwardQueueItem[]>(
        accountId,
        `/api/v1/queue/items?limit=${queuePreviewLimit}`,
      ),
    enabled: queuePreviewOpen,
    refetchInterval: queuePreviewOpen ? 5_000 : false,
  })
  const statsQuery = useQuery({
    queryKey: ['stats', accountId, reportPeriod],
    queryFn: () => accountRequest<Stats>(accountId, `/api/v1/stats?date_limit=${reportPeriod}`),
    refetchInterval: 15_000,
  })
  const eventHistoryQuery = useQuery({
    queryKey: ['dashboard-events', accountId, initialEventLimit],
    queryFn: () => accountRequest<RelayEvent[]>(accountId, recentEventsPath),
    refetchOnMount: 'always',
    gcTime: 0,
  })
  const accountsQuery = useQuery({
    queryKey: ['telegram-accounts'],
    queryFn: () => request<TelegramAccount[]>('/api/v1/telegram-accounts'),
    refetchInterval: 30_000,
  })
  const handleDashboardEvent = useCallback(
    (event: RelayEvent) => {
      if (event.type === 'forward') {
        void client.invalidateQueries({ queryKey: ['forward-queue-items'] })
        void client.invalidateQueries({ queryKey: ['bot-status'] })
        void client.invalidateQueries({ queryKey: ['stats'] })
      }
    },
    [client],
  )
  const { recent, connected } = useEvents(handleDashboardEvent, {
    accountId,
    maxRecent: liveEventLimit,
    initialRecent: eventHistoryQuery.data,
    shouldStore: shouldStoreDashboardEvent,
  })
  const control = useMutation({
    mutationFn: (action: 'start' | 'stop' | 'restart') =>
      accountRequest(accountId, `/api/v1/bot/${action}`, json('POST')),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['bot-status'] }),
  })

  const status = statusQuery.data ?? {}
  const telegramStatusLabel =
    typeof status.connected_account_count === 'number' &&
    typeof status.authenticated_account_count === 'number'
      ? t('dashboard.telegramAccountsConnected', {
          connected: status.connected_account_count,
          total: status.authenticated_account_count,
        })
      : t(status.is_connected ? 'dashboard.telegramConnected' : 'dashboard.telegramDisconnected')
  const runtimeStats = status.stats ?? {}
  const queueItems = queueQuery.data ?? []
  const activeQueue = Object.entries(status.queue?.counts ?? {})
    .filter(([key]) => key === 'pending' || key === 'processing')
    .reduce((sum, [, value]) => sum + value, 0)
  const report = useMemo(() => {
    const source = statsQuery.data?.daily ?? []
    const durationDays = reportDays ?? allTimeDays(source)
    const series = fillDailySeries(source, allTime ? durationDays : reportDays * 2)
    const currentDaily = allTime ? series : series.slice(-reportDays)
    const previousDaily = allTime ? [] : series.slice(0, reportDays)
    const current = aggregateDaily(currentDaily)
    const previous = aggregateDaily(previousDaily)
    const peak = currentDaily.reduce<DailyStat | null>(
      (best, item) => (item.total > 0 && (!best || item.total > best.total) ? item : best),
      null,
    )
    const activeDays = currentDaily.filter((item) => item.total > 0).length
    const intensityDaily = sampleDailyIntensity(currentDaily)
    const maxIntensityTotal = Math.max(...intensityDaily.map((item) => item.total), 1)

    return {
      current,
      previous,
      currentDaily,
      intensityDaily,
      peak,
      activeDays,
      maxIntensityTotal,
      durationDays,
      change: allTime ? undefined : percentChange(current.total, previous.total),
      forwardedChange: allTime ? undefined : percentChange(current.forwarded, previous.forwarded),
      filteredChange: allTime ? undefined : percentChange(current.filtered, previous.filtered),
      forwardRate: current.total ? (current.forwarded / current.total) * 100 : 0,
      dailyAverage: current.total / durationDays,
    }
  }, [allTime, reportDays, statsQuery.data?.daily])
  const rankedRules = useMemo(
    () => [...(statsQuery.data?.rules ?? [])].sort((left, right) => right.total - left.total),
    [statsQuery.data?.rules],
  )
  const maxRuleTotal = Math.max(...rankedRules.map((rule) => rule.total), 1)
  const flowComposition = [
    { name: t('dashboard.forwarded'), value: report.current.forwarded, color: '#2563eb' },
    { name: t('dashboard.filtered'), value: report.current.filtered, color: '#f59e0b' },
  ]
  const metrics = [
    {
      label: t('dashboard.periodForwarded'),
      value: report.current.forwarded,
      icon: Send,
      trend: report.forwardedChange,
      hint: allTime ? t('dashboard.allTimeTotal') : undefined,
      tone: 'blue',
      queueAction: false,
    },
    {
      label: t('dashboard.periodFiltered'),
      value: report.current.filtered,
      icon: Filter,
      trend: report.filteredChange,
      hint: allTime ? t('dashboard.allTimeTotal') : undefined,
      tone: 'amber',
      queueAction: false,
    },
    {
      label: t('dashboard.totalTraffic'),
      value: report.current.total,
      icon: Activity,
      trend: report.change,
      hint: allTime ? t('dashboard.allTimeTotal') : undefined,
      tone: 'cyan',
      queueAction: false,
    },
    {
      label: t('dashboard.queuePending'),
      value: activeQueue,
      icon: TimerReset,
      trend: undefined,
      hint: t('dashboard.liveBacklog'),
      tone: 'green',
      queueAction: true,
    },
  ] as const

  return (
    <>
      <PageHeader
        eyebrow={t('dashboard.eyebrow')}
        title={t('dashboard.title')}
        description={t('dashboard.description')}
      />

      <div className="mb-3 grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
        {metrics.map(({ label, value, icon: Icon, trend, hint, tone, queueAction }) => (
          <article
            className={cn(
              'grid min-w-0 grid-cols-[40px_1fr] grid-rows-[auto_auto_auto] gap-x-3',
              'rounded-md border border-slate-200 bg-white p-4 shadow-xs',
            )}
            key={label}
          >
            <div
              className={cn(
                'row-span-3 grid size-10 place-items-center rounded-[5px]',
                metricTones[tone],
              )}
            >
              <Icon size={19} />
            </div>
            <span className="text-xs text-slate-500">{label}</span>
            <strong className="font-display my-0.5 text-[23px] text-slate-700">
              {formatNumber(value)}
            </strong>
            {queueAction ? (
              <small className="flex items-center gap-1.5 text-xs text-slate-400">
                <span>{hint}</span>
                <button
                  type="button"
                  className="rounded border-0 bg-transparent p-0 text-xs text-blue-600 transition hover:text-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
                  aria-expanded={queuePreviewOpen}
                  aria-controls="forward-queue-preview"
                  onClick={() => setQueuePreviewOpen((current) => !current)}
                >
                  {t('dashboard.queuePreview.show')}
                </button>
              </small>
            ) : (
              <small
                className={cn(
                  'flex items-center gap-0.5 text-xs',
                  trend === undefined
                    ? 'text-slate-400'
                    : trend > 0
                      ? 'text-emerald-600'
                      : trend < 0
                        ? 'text-rose-500'
                        : 'text-slate-400',
                )}
              >
                <TrendLabel value={trend} fallback={hint} t={t} />
              </small>
            )}
          </article>
        ))}
      </div>

      {queuePreviewOpen ? (
        <Panel
          className="mb-3"
          title={t('dashboard.queuePreview.title')}
          meta={
            <button
              type="button"
              className="rounded border-0 bg-transparent p-0 text-xs text-slate-400 transition hover:text-blue-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
              onClick={() => setQueuePreviewOpen(false)}
            >
              {t('dashboard.queuePreview.hide')}
            </button>
          }
        >
          <div id="forward-queue-preview">
            <p className="mb-3 text-right text-xs text-slate-400">
              {t('dashboard.queuePreview.meta', {
                shown: queueItems.length,
                total: activeQueue,
              })}
            </p>
            {queueQuery.isPending ? (
              <div className="py-8 text-center text-[13px] text-slate-400">
                {t('dashboard.queuePreview.loading')}
              </div>
            ) : queueQuery.error ? (
              <EmptyState
                icon={ListChecks}
                title={t('dashboard.queuePreview.loadFailed')}
                detail={messageFrom(queueQuery.error)}
              />
            ) : queueItems.length ? (
              <div className="overflow-x-auto">
                <div className="min-w-225">
                  <div className="grid grid-cols-[minmax(120px,0.8fr)_minmax(140px,1fr)_minmax(170px,1.1fr)_100px_110px_70px_minmax(160px,1fr)] gap-3 border-b border-slate-100 pb-2 text-xs font-bold text-slate-400 uppercase">
                    <span>{t('dashboard.queuePreview.columns.account')}</span>
                    <span>{t('dashboard.queuePreview.columns.rule')}</span>
                    <span>{t('dashboard.queuePreview.columns.source')}</span>
                    <span>{t('dashboard.queuePreview.columns.status')}</span>
                    <span>{t('dashboard.queuePreview.columns.progress')}</span>
                    <span className="text-right">
                      {t('dashboard.queuePreview.columns.retries')}
                    </span>
                    <span>{t('dashboard.queuePreview.columns.waiting')}</span>
                  </div>
                  {queueItems.map((item) => {
                    const state = queueState(item)
                    return (
                      <div
                        className="grid grid-cols-[minmax(120px,0.8fr)_minmax(140px,1fr)_minmax(170px,1.1fr)_100px_110px_70px_minmax(160px,1fr)] items-center gap-3 border-b border-slate-100 py-3 last:border-0"
                        key={`${item.account_id}-${item.id}`}
                      >
                        <div className="min-w-0">
                          <strong className="block truncate text-[13px] text-slate-700">
                            {item.account_label}
                          </strong>
                          <small className="mt-0.5 block truncate text-xs text-slate-400">
                            {item.account_id}
                          </small>
                        </div>
                        <strong className="truncate text-[13px] text-slate-600">
                          {item.rule_name}
                        </strong>
                        <span className="font-mono text-xs text-slate-500">
                          {queueSource(item)}
                        </span>
                        <span
                          className={cn(
                            'w-fit rounded px-2 py-1 text-xs font-semibold',
                            state === 'processing'
                              ? 'bg-blue-50 text-blue-700'
                              : state === 'waiting'
                                ? 'bg-amber-50 text-amber-700'
                                : 'bg-slate-100 text-slate-600',
                          )}
                        >
                          {t(queueStatusKeys[state])}
                        </span>
                        <div className="min-w-0">
                          <span className="mb-1 block text-xs text-slate-500">
                            {t('dashboard.queuePreview.targetProgress', {
                              current: Math.min(item.next_target_index, item.target_count),
                              total: item.target_count,
                            })}
                          </span>
                          <div className="h-1.5 overflow-hidden rounded-sm bg-slate-100">
                            <i
                              className="block h-full bg-blue-500"
                              style={{
                                width: `${item.target_count ? Math.min(100, (item.next_target_index / item.target_count) * 100) : 0}%`,
                              }}
                            />
                          </div>
                        </div>
                        <strong className="text-right text-xs text-slate-600">
                          {item.failure_count}
                        </strong>
                        <div className="min-w-0">
                          <span className="block text-xs text-slate-500">
                            {queueTime(item.available_at, locale)}
                          </span>
                          {item.last_error ? (
                            <small
                              className="mt-0.5 block truncate text-xs text-rose-500"
                              title={item.last_error}
                            >
                              {item.last_error}
                            </small>
                          ) : null}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            ) : (
              <EmptyState
                icon={ListChecks}
                title={t('dashboard.queuePreview.empty')}
                detail={t('dashboard.queuePreview.emptyDetail')}
              />
            )}
          </div>
        </Panel>
      ) : null}

      <div
        className={cn(
          'mb-3 grid grid-cols-[minmax(0,1.7fr)_minmax(280px,0.8fr)] gap-3',
          'max-lg:grid-cols-1',
        )}
      >
        <Panel
          title={t('dashboard.trafficTrend')}
          meta={
            <div
              className="flex rounded-[5px] bg-slate-100 p-0.5"
              role="group"
              aria-label={t('dashboard.reportPeriod')}
            >
              {periodOptions.map((option) => (
                <button
                  type="button"
                  key={option.value}
                  className={cn(
                    'h-6.5 min-w-10 rounded border-0 px-2 text-xs font-semibold',
                    option.value === reportPeriod
                      ? 'bg-white text-blue-700 shadow-sm'
                      : 'bg-transparent text-slate-400 hover:text-slate-600',
                  )}
                  aria-pressed={option.value === reportPeriod}
                  onClick={() => setReportPeriod(option.value)}
                >
                  {t(option.labelKey)}
                </button>
              ))}
            </div>
          }
        >
          {report.current.total ? (
            <div className="h-68">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={report.currentDaily}
                  margin={{ top: 12, right: 8, left: -18, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="dashboard-forwarded-fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#2563eb" stopOpacity={0.28} />
                      <stop offset="100%" stopColor="#2563eb" stopOpacity={0.03} />
                    </linearGradient>
                    <linearGradient id="dashboard-filtered-fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.24} />
                      <stop offset="100%" stopColor="#f59e0b" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#e6edf7" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(value: string) => value.slice(5)}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#7b8ca5', fontSize: 10 }}
                    dy={8}
                    minTickGap={18}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#7b8ca5', fontSize: 10 }}
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={chartTooltipStyle}
                    labelFormatter={(value) => formatReportDate(String(value), locale)}
                  />
                  <Area
                    type="monotone"
                    dataKey="forwarded"
                    name={t('dashboard.forwarded')}
                    stackId="flow"
                    stroke="#2563eb"
                    strokeWidth={2}
                    fill="url(#dashboard-forwarded-fill)"
                  />
                  <Area
                    type="monotone"
                    dataKey="filtered"
                    name={t('dashboard.filtered')}
                    stackId="flow"
                    stroke="#f59e0b"
                    strokeWidth={1.5}
                    fill="url(#dashboard-filtered-fill)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState
              icon={Activity}
              title={t('dashboard.noTrend')}
              detail={t('dashboard.noTrendDetail')}
            />
          )}
          <div className="flex flex-wrap gap-4 px-3 pt-2 text-[13px] text-slate-500">
            <span className="flex items-center gap-1.5 before:h-0.5 before:w-4 before:bg-blue-600">
              {t('dashboard.forwarded')}
            </span>
            <span className="flex items-center gap-1.5 before:h-0.5 before:w-4 before:bg-amber-500">
              {t('dashboard.filtered')}
            </span>
            <span className="ml-auto text-slate-400 max-sm:ml-0">
              {t('dashboard.currentPeriodCount', { value: formatNumber(report.current.total) })}
            </span>
          </div>
        </Panel>

        <Panel
          title={t('dashboard.periodSummary')}
          meta={
            <span>
              {allTime
                ? t('dashboard.allTime')
                : t('dashboard.recentDays', { count: reportDays ?? 0 })}
            </span>
          }
        >
          <div className="divide-y divide-slate-100">
            <div className="grid grid-cols-[32px_1fr_auto] items-center gap-3 py-3 first:pt-0">
              <span className="grid size-8 place-items-center rounded-[5px] bg-blue-50 text-blue-600">
                <Gauge size={16} />
              </span>
              <span className="flex flex-col">
                <small className="text-xs text-slate-400">
                  {allTime
                    ? t('dashboard.cumulativeRange')
                    : t('dashboard.comparedToPrevious', { value: '' }).trim()}
                </small>
                <strong className="mt-0.5 text-xs text-slate-700">
                  {allTime ? t('dashboard.totalTraffic') : t('dashboard.totalTrafficChange')}
                </strong>
              </span>
              <b
                className={cn(
                  'text-sm',
                  report.change === undefined
                    ? 'text-slate-700'
                    : report.change > 0
                      ? 'text-emerald-600'
                      : report.change < 0
                        ? 'text-rose-500'
                        : 'text-slate-500',
                )}
              >
                {report.change === undefined
                  ? formatNumber(report.current.total)
                  : `${report.change > 0 ? '+' : ''}${formatPercent(report.change)}`}
              </b>
            </div>
            <div className="grid grid-cols-[32px_1fr_auto] items-center gap-3 py-3">
              <span className="grid size-8 place-items-center rounded-[5px] bg-cyan-50 text-cyan-600">
                <Activity size={16} />
              </span>
              <span className="flex flex-col">
                <small className="text-xs text-slate-400">{t('dashboard.dailyAverage')}</small>
                <strong className="mt-0.5 text-xs text-slate-700">
                  {t('dashboard.processingSpeed')}
                </strong>
              </span>
              <b className="text-sm text-slate-700">
                {formatNumber(Math.round(report.dailyAverage))}
              </b>
            </div>
            <div className="grid grid-cols-[32px_1fr_auto] items-center gap-3 py-3">
              <span className="grid size-8 place-items-center rounded-[5px] bg-amber-50 text-amber-600">
                <Trophy size={16} />
              </span>
              <span className="flex flex-col">
                <small className="text-xs text-slate-400">{t('dashboard.peakDate')}</small>
                <strong className="mt-0.5 text-xs text-slate-700">
                  {report.peak ? formatReportDate(report.peak.date, locale) : '-'}
                </strong>
              </span>
              <b className="text-sm text-slate-700">{formatNumber(report.peak?.total)}</b>
            </div>
            <div className="grid grid-cols-[32px_1fr_auto] items-center gap-3 py-3">
              <span className="grid size-8 place-items-center rounded-[5px] bg-emerald-50 text-emerald-600">
                <CalendarDays size={16} />
              </span>
              <span className="flex flex-col">
                <small className="text-xs text-slate-400">{t('dashboard.activeDays')}</small>
                <strong className="mt-0.5 text-xs text-slate-700">
                  {t('dashboard.periodCoverage')}
                </strong>
              </span>
              <b className="text-sm text-slate-700">
                {report.activeDays}/{report.durationDays}
              </b>
            </div>
          </div>
          <div className="mt-3 border-t border-slate-100 pt-3">
            <div className="mb-2 flex justify-between text-xs text-slate-400">
              <span>{t('dashboard.dailyIntensity')}</span>
            </div>
            <div
              className="grid h-7 grid-flow-col auto-cols-fr items-stretch gap-1 overflow-hidden"
              data-testid="daily-intensity"
            >
              {report.intensityDaily.map((item) => (
                <span
                  key={`${item.date}-${item.endDate ?? item.date}`}
                  title={t(
                    item.endDate && item.endDate !== item.date
                      ? 'dashboard.rangeAverageTraffic'
                      : 'dashboard.dayTraffic',
                    {
                      date:
                        item.endDate && item.endDate !== item.date
                          ? `${formatReportDate(item.date, locale)} - ${formatReportDate(item.endDate, locale)}`
                          : formatReportDate(item.date, locale),
                      count: item.total,
                    },
                  )}
                  className="min-w-0 rounded-sm bg-blue-600"
                  data-testid="daily-intensity-point"
                  style={{
                    opacity: item.total
                      ? 0.16 + (item.total / report.maxIntensityTotal) * 0.84
                      : 0.06,
                  }}
                />
              ))}
            </div>
          </div>
        </Panel>
      </div>

      <div
        className={cn(
          'mb-3 grid grid-cols-[minmax(280px,0.8fr)_minmax(0,1.2fr)] gap-3',
          'max-lg:grid-cols-1',
        )}
      >
        <Panel
          title={t('dashboard.trafficComposition')}
          meta={
            <span>
              {t('dashboard.forwardingEfficiency', { value: formatPercent(report.forwardRate) })}
            </span>
          }
        >
          {report.current.total ? (
            <div className="grid grid-cols-[150px_1fr] items-center gap-4 max-sm:grid-cols-1">
              <div className="relative mx-auto h-36 w-36">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={flowComposition}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={48}
                      outerRadius={66}
                      paddingAngle={3}
                      stroke="none"
                    >
                      {flowComposition.map((item) => (
                        <Cell key={item.name} fill={item.color} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={chartTooltipStyle} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                  <strong className="font-display text-[20px] text-slate-700">
                    {formatPercent(report.forwardRate)}
                  </strong>
                  <small className="text-xs text-slate-400">{t('dashboard.forwardingRate')}</small>
                </div>
              </div>
              <div className="divide-y divide-slate-100">
                {flowComposition.map((item) => (
                  <div
                    className="flex items-center justify-between py-3 first:pt-0"
                    key={item.name}
                  >
                    <span className="flex items-center gap-2 text-[13px] text-slate-500">
                      <i className="size-2 rounded-sm" style={{ backgroundColor: item.color }} />
                      {item.name}
                    </span>
                    <strong className="text-[13px] text-slate-700">
                      {formatNumber(item.value)}
                    </strong>
                  </div>
                ))}
                <div className="flex items-center justify-between py-3">
                  <span className="text-[13px] text-slate-500">
                    {t('dashboard.cumulativeSamples')}
                  </span>
                  <strong className="text-[13px] text-slate-700">
                    {formatNumber(report.current.total)}
                  </strong>
                </div>
              </div>
            </div>
          ) : (
            <EmptyState icon={Target} title={t('dashboard.noComposition')} />
          )}
        </Panel>

        <Panel
          title={t('dashboard.nodeControl')}
          meta={
            <span className={status.is_running ? 'text-emerald-600' : ''}>
              {t(status.is_running ? 'dashboard.running' : 'dashboard.stopped')}
            </span>
          }
        >
          <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-4 max-sm:grid-cols-1">
            <div
              className={cn(
                'flex items-center gap-3 rounded-[5px] border',
                'border-slate-100 bg-slate-50 p-3',
              )}
            >
              <span
                className={cn(
                  'grid size-10.5 shrink-0 place-items-center rounded-[5px] border',
                  status.is_running
                    ? 'border-emerald-100 bg-emerald-50 text-emerald-600'
                    : 'border-slate-200 bg-white text-slate-400',
                )}
              >
                {status.is_running ? <Play size={22} fill="currentColor" /> : <Pause size={22} />}
              </span>
              <div>
                <strong className="mb-1 block text-[13px] text-slate-700">
                  {t(status.is_running ? 'dashboard.relayRunning' : 'dashboard.relayStopped')}
                </strong>
                <p className="m-0 text-[13px] leading-4 text-slate-500">{telegramStatusLabel}</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {status.is_running ? (
                <Button
                  variant="danger"
                  icon={Pause}
                  onClick={() => control.mutate('stop')}
                  disabled={control.isPending}
                >
                  {t('dashboard.stop')}
                </Button>
              ) : (
                <Button
                  icon={Play}
                  onClick={() => control.mutate('start')}
                  disabled={control.isPending}
                >
                  {t('dashboard.start')}
                </Button>
              )}
              <Button
                variant="secondary"
                icon={RefreshCcw}
                onClick={() => control.mutate('restart')}
                disabled={control.isPending}
              >
                {t('dashboard.restart')}
              </Button>
            </div>
          </div>
          {control.error ? (
            <p
              className={cn(
                'mt-3 rounded-[5px] border border-rose-100 bg-rose-50 p-2',
                'text-[13px] text-rose-700',
              )}
            >
              {messageFrom(control.error)}
            </p>
          ) : null}
          <div className="mt-4 grid grid-cols-3 divide-x divide-slate-100 border-t border-slate-100 pt-4 max-sm:grid-cols-1 max-sm:divide-x-0 max-sm:divide-y">
            <div className="px-4 first:pl-0 max-sm:px-0 max-sm:py-2">
              <small className="block text-xs text-slate-400">
                {t('dashboard.runtimeForwarded')}
              </small>
              <strong className="mt-1 block text-base text-slate-700">
                {formatNumber(runtimeStats.forwarded)}
              </strong>
            </div>
            <div className="px-4 max-sm:px-0 max-sm:py-2">
              <small className="block text-xs text-slate-400">
                {t('dashboard.runtimeFiltered')}
              </small>
              <strong className="mt-1 block text-base text-slate-700">
                {formatNumber(runtimeStats.filtered)}
              </strong>
            </div>
            <div className="px-4 max-sm:px-0 max-sm:py-2">
              <small className="block text-xs text-slate-400">
                {t('dashboard.persistentQueue')}
              </small>
              <strong className="mt-1 block text-base text-blue-600">
                {formatNumber(activeQueue)}
              </strong>
            </div>
          </div>
        </Panel>
      </div>

      <div
        className={cn(
          'grid grid-cols-[minmax(0,1.4fr)_minmax(300px,0.6fr)] gap-3',
          'max-lg:grid-cols-1',
        )}
      >
        <Panel
          title={t('dashboard.ruleRanking')}
          meta={<span>{t('dashboard.ruleRankingMeta', { count: rankedRules.length })}</span>}
        >
          {rankedRules.length ? (
            <div className="overflow-x-auto">
              <div className="min-w-135">
                <div className="grid grid-cols-[28px_minmax(130px,1fr)_minmax(160px,1.25fr)_70px_70px] gap-3 border-b border-slate-100 pb-2 text-xs font-bold text-slate-400 uppercase">
                  <span>#</span>
                  <span>{t('dashboard.rule')}</span>
                  <span>{t('dashboard.processed')}</span>
                  <span className="text-right">{t('dashboard.forwardingRate')}</span>
                  <span className="text-right">{t('dashboard.total')}</span>
                </div>
                {rankedRules.slice(0, 8).map((rule, index) => {
                  const rate = rule.total ? (rule.forwarded / rule.total) * 100 : 0
                  return (
                    <div
                      className="grid grid-cols-[28px_minmax(130px,1fr)_minmax(160px,1.25fr)_70px_70px] items-center gap-3 border-b border-slate-100 py-3 last:border-0"
                      key={rule.rule_name}
                    >
                      <span
                        className={cn(
                          'grid size-5 place-items-center rounded text-xs font-bold',
                          index < 3 ? 'bg-blue-50 text-blue-700' : 'bg-slate-100 text-slate-500',
                        )}
                      >
                        {index + 1}
                      </span>
                      <div className="min-w-0">
                        <strong className="block truncate text-xs text-slate-700">
                          {rule.rule_name}
                        </strong>
                        <small className="mt-0.5 block text-xs text-slate-400">
                          {t('dashboard.ruleBreakdown', {
                            forwarded: formatNumber(rule.forwarded),
                            filtered: formatNumber(rule.filtered),
                          })}
                        </small>
                      </div>
                      <div className="h-2 overflow-hidden rounded-sm bg-slate-100">
                        <i
                          className="block h-full bg-blue-600"
                          style={{ width: `${(rule.total / maxRuleTotal) * 100}%` }}
                        />
                      </div>
                      <strong className="text-right text-[13px] text-slate-600">
                        {formatPercent(rate)}
                      </strong>
                      <strong className="text-right text-xs text-slate-700">
                        {formatNumber(rule.total)}
                      </strong>
                    </div>
                  )
                })}
              </div>
            </div>
          ) : (
            <EmptyState icon={Route} title={t('dashboard.noRuleStats')} />
          )}
        </Panel>

        <Panel
          title={t('dashboard.liveEvents')}
          meta={
            <span className={connected ? 'text-emerald-600' : ''}>
              {t(connected ? 'dashboard.sseConnected' : 'dashboard.waitingEvents')}
            </span>
          }
        >
          <div className="flex max-h-72 flex-col gap-3 overflow-y-auto overscroll-contain pr-1">
            {recent.map((event) => (
              <div
                className={cn(
                  'grid grid-cols-[7px_1fr_auto] items-start gap-2 border-b',
                  'border-slate-100 pb-2.5 last:border-0',
                )}
                key={event.id}
              >
                <span
                  className={cn('mt-1 size-2 rounded-full border-2', eventMarkerClass(event.type))}
                />
                <div className="min-w-0">
                  <strong className="text-[13px] text-slate-600 uppercase">
                    {eventTypeLabel(event.type, t)}
                  </strong>
                  <p className="mt-0.5 truncate text-[13px] text-slate-500">
                    {eventDetail(event, t, accountsQuery.data)}
                  </p>
                </div>
                <time className="text-xs text-slate-400">
                  {new Date(event.at).toLocaleTimeString(locale, {
                    hour12: false,
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </time>
              </div>
            ))}
            {!recent.length ? (
              <EmptyState
                icon={Activity}
                title={t('dashboard.waitingLiveEvents')}
                detail={t('dashboard.waitingLiveEventsDetail')}
              />
            ) : null}
          </div>
        </Panel>
      </div>
    </>
  )
}
