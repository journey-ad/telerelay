import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { TFunction } from 'i18next'
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  CalendarDays,
  Filter,
  Gauge,
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
import { useMemo, useState } from 'react'
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
import { json, request } from '../api/client'
import { Button, EmptyState, PageHeader, Panel } from '../components/ui'
import { useEvents } from '../hooks/useEvents'
import type { BotStatus, RelayEvent, Stats } from '../types'
import { cn } from '../utils/cn'
import { formatNumber, messageFrom } from '../utils/format'

type ReportPeriod = '7day' | '14day' | '30day' | 'all'
type DailyStat = Stats['daily'][number] & { total: number }

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
const liveEventLimit = 12
const eventTypeKeys = {
  ready: 'dashboard.events.types.ready',
  log: 'dashboard.events.types.log',
  bot: 'dashboard.events.types.bot',
  stats: 'dashboard.events.types.stats',
  'telegram-account': 'dashboard.events.types.telegramAccount',
  'telegram-auth': 'dashboard.events.types.telegramAuth',
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
} as const
const dashboardEventTypes = new Set(['bot', 'stats', 'telegram-account', 'telegram-auth'])

function eventTypeLabel(type: string, t: TFunction): string {
  const key = eventTypeKeys[type as keyof typeof eventTypeKeys]
  return key ? t(key) : t('dashboard.events.types.other')
}

function eventDetail(event: RelayEvent, t: TFunction): string {
  const message = event.payload.message
  if (['string', 'number', 'boolean'].includes(typeof message)) return String(message)

  const action = event.payload.action ?? event.payload.submitted
  if (typeof action === 'string') {
    const key = eventActionKeys[action as keyof typeof eventActionKeys]
    return key ? t(key) : action
  }

  return t('dashboard.statusUpdate')
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
  const [reportPeriod, setReportPeriod] = useState<ReportPeriod>('14day')
  const reportDays = reportPeriod === 'all' ? null : periodDays[reportPeriod]
  const allTime = reportDays === null
  const statusQuery = useQuery({
    queryKey: ['bot-status'],
    queryFn: () => request<BotStatus>('/api/v1/bot/status'),
  })
  const statsQuery = useQuery({
    queryKey: ['stats', reportPeriod],
    queryFn: () => request<Stats>(`/api/v1/stats?date_limit=${reportPeriod}`),
    refetchInterval: 15_000,
  })
  const { recent, connected } = useEvents(undefined, {
    maxRecent: liveEventLimit,
    shouldStore: shouldStoreDashboardEvent,
  })
  const control = useMutation({
    mutationFn: (action: 'start' | 'stop' | 'restart') =>
      request(`/api/v1/bot/${action}`, json('POST')),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['bot-status'] }),
  })

  const status = statusQuery.data ?? {}
  const runtimeStats = status.stats ?? {}
  const activeQueue = Object.entries(status.queue?.counts ?? {})
    .filter(([key]) => key !== 'completed')
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
    const maxDailyTotal = Math.max(...currentDaily.map((item) => item.total), 1)

    return {
      current,
      previous,
      currentDaily,
      peak,
      activeDays,
      maxDailyTotal,
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
    },
    {
      label: t('dashboard.periodFiltered'),
      value: report.current.filtered,
      icon: Filter,
      trend: report.filteredChange,
      hint: allTime ? t('dashboard.allTimeTotal') : undefined,
      tone: 'amber',
    },
    {
      label: t('dashboard.totalTraffic'),
      value: report.current.total,
      icon: Activity,
      trend: report.change,
      hint: allTime ? t('dashboard.allTimeTotal') : undefined,
      tone: 'cyan',
    },
    {
      label: t('dashboard.queuePending'),
      value: activeQueue,
      icon: TimerReset,
      trend: undefined,
      hint: t('dashboard.liveBacklog'),
      tone: 'green',
    },
  ] as const

  return (
    <>
      <PageHeader
        eyebrow={t('dashboard.eyebrow')}
        title={t('dashboard.title')}
        description={t('dashboard.description')}
        actions={
          <div
            className={cn(
              'flex h-8.5 items-center gap-2 rounded-[5px] border px-3 text-xs',
              status.is_connected
                ? 'border-emerald-100 bg-emerald-50 text-emerald-700'
                : 'border-slate-200 bg-white text-slate-500',
            )}
          >
            <span
              className={cn(
                'size-2 rounded-full',
                status.is_connected ? 'bg-emerald-500' : 'bg-slate-300',
              )}
            />
            {t(
              status.is_connected
                ? 'dashboard.telegramConnected'
                : 'dashboard.telegramDisconnected',
            )}
          </div>
        }
      />

      <div className="mb-3 grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
        {metrics.map(({ label, value, icon: Icon, trend, hint, tone }) => (
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
          </article>
        ))}
      </div>

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
              <span>{t('dashboard.lowToHigh')}</span>
            </div>
            <div className="flex h-7 items-stretch gap-1">
              {report.currentDaily.map((item) => (
                <span
                  key={item.date}
                  title={t('dashboard.dayTraffic', {
                    date: formatReportDate(item.date, locale),
                    count: item.total,
                  })}
                  className="min-w-1 flex-1 rounded-sm bg-blue-600"
                  style={{
                    opacity: item.total ? 0.16 + (item.total / report.maxDailyTotal) * 0.84 : 0.06,
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
                <p className="m-0 text-[13px] leading-4 text-slate-500">
                  {status.is_connected
                    ? t('dashboard.clientConnected')
                    : t('dashboard.clientWaiting')}
                </p>
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
            {recent.map((event, index) => (
              <div
                className={cn(
                  'grid grid-cols-[7px_1fr_auto] items-start gap-2 border-b',
                  'border-slate-100 pb-2.5 last:border-0',
                )}
                key={`${event.at}-${event.type}-${index}`}
              >
                <span className="mt-1 size-2 rounded-full border-2 border-blue-100 bg-blue-400" />
                <div className="min-w-0">
                  <strong className="text-[13px] text-slate-600 uppercase">
                    {eventTypeLabel(event.type, t)}
                  </strong>
                  <p className="mt-0.5 truncate text-[13px] text-slate-500">
                    {eventDetail(event, t)}
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
