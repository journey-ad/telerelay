import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
import { useCallback, useMemo, useState } from 'react'
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
import type { BotStatus, Stats } from '../types'
import { cn } from '../utils/cn'
import { formatNumber, messageFrom } from '../utils/format'

type ReportDays = 7 | 14 | 30
type DailyStat = Stats['daily'][number] & { total: number }

const periodOptions: ReportDays[] = [7, 14, 30]
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

function formatReportDate(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
    weekday: 'short',
  })
}

function TrendLabel({ value, fallback }: { value?: number; fallback?: string }) {
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
      较上周期 {value > 0 ? '+' : ''}
      {formatPercent(value)}
    </>
  )
}

export function DashboardPage() {
  const client = useQueryClient()
  const [reportDays, setReportDays] = useState<ReportDays>(14)
  const statusQuery = useQuery({
    queryKey: ['bot-status'],
    queryFn: () => request<BotStatus>('/api/v1/bot/status'),
    refetchInterval: 4000,
  })
  const statsQuery = useQuery({
    queryKey: ['stats', reportDays * 2],
    queryFn: () => request<Stats>(`/api/v1/stats?days=${reportDays * 2}`),
    refetchInterval: 15_000,
  })
  const refreshLiveData = useCallback(() => {
    void client.invalidateQueries({ queryKey: ['bot-status'] })
    void client.invalidateQueries({ queryKey: ['stats'] })
  }, [client])
  const { recent, connected } = useEvents(refreshLiveData)
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
    const series = fillDailySeries(statsQuery.data?.daily ?? [], reportDays * 2)
    const currentDaily = series.slice(-reportDays)
    const previousDaily = series.slice(0, reportDays)
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
      change: percentChange(current.total, previous.total),
      forwardedChange: percentChange(current.forwarded, previous.forwarded),
      filteredChange: percentChange(current.filtered, previous.filtered),
      forwardRate: current.total ? (current.forwarded / current.total) * 100 : 0,
      dailyAverage: current.total / reportDays,
    }
  }, [reportDays, statsQuery.data?.daily])
  const rankedRules = useMemo(
    () => [...(statsQuery.data?.rules ?? [])].sort((left, right) => right.total - left.total),
    [statsQuery.data?.rules],
  )
  const maxRuleTotal = Math.max(...rankedRules.map((rule) => rule.total), 1)
  const flowComposition = [
    { name: '已转发', value: report.current.forwarded, color: '#2563eb' },
    { name: '已过滤', value: report.current.filtered, color: '#f59e0b' },
  ]
  const metrics = [
    {
      label: '周期转发',
      value: report.current.forwarded,
      icon: Send,
      trend: report.forwardedChange,
      tone: 'blue',
    },
    {
      label: '周期过滤',
      value: report.current.filtered,
      icon: Filter,
      trend: report.filteredChange,
      tone: 'amber',
    },
    {
      label: '消息总流量',
      value: report.current.total,
      icon: Activity,
      trend: report.change,
      tone: 'cyan',
    },
    {
      label: '队列待处理',
      value: activeQueue,
      icon: TimerReset,
      trend: undefined,
      tone: 'green',
    },
  ] as const

  return (
    <>
      <PageHeader
        eyebrow="Live operations"
        title="运行总览"
        description="监控消息吞吐、规则效率、队列与 Telegram 连接状态。"
        actions={
          <div
            className={cn(
              'flex h-8.5 items-center gap-2 rounded-[5px] border px-3 text-[10px]',
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
            {status.is_connected ? 'Telegram 已连接' : 'Telegram 未连接'}
          </div>
        }
      />

      <div className="mb-3 grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
        {metrics.map(({ label, value, icon: Icon, trend, tone }) => (
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
            <span className="text-[10px] text-slate-500">{label}</span>
            <strong className="font-display my-0.5 text-[23px] text-slate-800">
              {formatNumber(value)}
            </strong>
            <small
              className={cn(
                'flex items-center gap-0.5 text-[8px]',
                trend === undefined
                  ? 'text-slate-400'
                  : trend > 0
                    ? 'text-emerald-600'
                    : trend < 0
                      ? 'text-rose-500'
                      : 'text-slate-400',
              )}
            >
              <TrendLabel value={trend} fallback="当前实时积压" />
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
          title="消息吞吐趋势"
          meta={
            <div
              className="flex rounded-[5px] bg-slate-100 p-0.5"
              role="group"
              aria-label="报表周期"
            >
              {periodOptions.map((days) => (
                <button
                  type="button"
                  key={days}
                  className={cn(
                    'h-6 min-w-10 rounded border-0 px-2 text-[8px] font-semibold',
                    days === reportDays
                      ? 'bg-white text-blue-700 shadow-sm'
                      : 'bg-transparent text-slate-400 hover:text-slate-600',
                  )}
                  aria-pressed={days === reportDays}
                  onClick={() => setReportDays(days)}
                >
                  {days} 天
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
                    labelFormatter={(value) => formatReportDate(String(value))}
                  />
                  <Area
                    type="monotone"
                    dataKey="forwarded"
                    name="已转发"
                    stackId="flow"
                    stroke="#2563eb"
                    strokeWidth={2}
                    fill="url(#dashboard-forwarded-fill)"
                  />
                  <Area
                    type="monotone"
                    dataKey="filtered"
                    name="已过滤"
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
              title="暂无趋势数据"
              detail="消息开始流转后，这里会显示每日吞吐变化。"
            />
          )}
          <div className="flex flex-wrap gap-4 px-3 pt-2 text-[9px] text-slate-500">
            <span className="flex items-center gap-1.5 before:h-0.5 before:w-4 before:bg-blue-600">
              已转发
            </span>
            <span className="flex items-center gap-1.5 before:h-0.5 before:w-4 before:bg-amber-500">
              已过滤
            </span>
            <span className="ml-auto text-slate-400 max-sm:ml-0">
              当前周期 {formatNumber(report.current.total)} 条
            </span>
          </div>
        </Panel>

        <Panel title="周期摘要" meta={<span>近 {reportDays} 天</span>}>
          <div className="divide-y divide-slate-100">
            <div className="grid grid-cols-[32px_1fr_auto] items-center gap-3 py-3 first:pt-0">
              <span className="grid size-8 place-items-center rounded-[5px] bg-blue-50 text-blue-600">
                <Gauge size={16} />
              </span>
              <span className="flex flex-col">
                <small className="text-[8px] text-slate-400">较上周期</small>
                <strong className="mt-0.5 text-[10px] text-slate-700">总流量变化</strong>
              </span>
              <b
                className={cn(
                  'text-[12px]',
                  report.change > 0
                    ? 'text-emerald-600'
                    : report.change < 0
                      ? 'text-rose-500'
                      : 'text-slate-500',
                )}
              >
                {report.change > 0 ? '+' : ''}
                {formatPercent(report.change)}
              </b>
            </div>
            <div className="grid grid-cols-[32px_1fr_auto] items-center gap-3 py-3">
              <span className="grid size-8 place-items-center rounded-[5px] bg-cyan-50 text-cyan-600">
                <Activity size={16} />
              </span>
              <span className="flex flex-col">
                <small className="text-[8px] text-slate-400">日均吞吐</small>
                <strong className="mt-0.5 text-[10px] text-slate-700">消息处理速度</strong>
              </span>
              <b className="text-[12px] text-slate-700">
                {formatNumber(Math.round(report.dailyAverage))}
              </b>
            </div>
            <div className="grid grid-cols-[32px_1fr_auto] items-center gap-3 py-3">
              <span className="grid size-8 place-items-center rounded-[5px] bg-amber-50 text-amber-600">
                <Trophy size={16} />
              </span>
              <span className="flex flex-col">
                <small className="text-[8px] text-slate-400">峰值日期</small>
                <strong className="mt-0.5 text-[10px] text-slate-700">
                  {report.peak ? formatReportDate(report.peak.date) : '-'}
                </strong>
              </span>
              <b className="text-[12px] text-slate-700">{formatNumber(report.peak?.total)}</b>
            </div>
            <div className="grid grid-cols-[32px_1fr_auto] items-center gap-3 py-3">
              <span className="grid size-8 place-items-center rounded-[5px] bg-emerald-50 text-emerald-600">
                <CalendarDays size={16} />
              </span>
              <span className="flex flex-col">
                <small className="text-[8px] text-slate-400">活跃天数</small>
                <strong className="mt-0.5 text-[10px] text-slate-700">周期覆盖率</strong>
              </span>
              <b className="text-[12px] text-slate-700">
                {report.activeDays}/{reportDays}
              </b>
            </div>
          </div>
          <div className="mt-3 border-t border-slate-100 pt-3">
            <div className="mb-2 flex justify-between text-[8px] text-slate-400">
              <span>每日流量强度</span>
              <span>低 → 高</span>
            </div>
            <div className="flex h-7 items-stretch gap-1">
              {report.currentDaily.map((item) => (
                <span
                  key={item.date}
                  title={`${formatReportDate(item.date)}：${item.total} 条`}
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
        <Panel title="流量结构" meta={<span>转发效率 {formatPercent(report.forwardRate)}</span>}>
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
                  <strong className="font-display text-[20px] text-slate-800">
                    {formatPercent(report.forwardRate)}
                  </strong>
                  <small className="text-[8px] text-slate-400">转发率</small>
                </div>
              </div>
              <div className="divide-y divide-slate-100">
                {flowComposition.map((item) => (
                  <div
                    className="flex items-center justify-between py-3 first:pt-0"
                    key={item.name}
                  >
                    <span className="flex items-center gap-2 text-[9px] text-slate-500">
                      <i className="size-2 rounded-sm" style={{ backgroundColor: item.color }} />
                      {item.name}
                    </span>
                    <strong className="text-[11px] text-slate-700">
                      {formatNumber(item.value)}
                    </strong>
                  </div>
                ))}
                <div className="flex items-center justify-between py-3">
                  <span className="text-[9px] text-slate-500">累计样本</span>
                  <strong className="text-[11px] text-slate-700">
                    {formatNumber(report.current.total)}
                  </strong>
                </div>
              </div>
            </div>
          ) : (
            <EmptyState icon={Target} title="暂无流量结构" />
          )}
        </Panel>

        <Panel
          title="节点控制"
          meta={
            <span className={status.is_running ? 'text-emerald-600' : ''}>
              {status.is_running ? '运行中' : '已停止'}
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
                <strong className="mb-1 block text-[11px] text-slate-700">
                  {status.is_running ? '消息中继正在运行' : '消息中继已停止'}
                </strong>
                <p className="m-0 text-[9px] leading-4 text-slate-500">
                  {status.is_connected
                    ? '客户端连接正常，可处理新消息。'
                    : '等待 Telegram 客户端建立连接。'}
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
                  停止
                </Button>
              ) : (
                <Button
                  icon={Play}
                  onClick={() => control.mutate('start')}
                  disabled={control.isPending}
                >
                  启动
                </Button>
              )}
              <Button
                variant="secondary"
                icon={RefreshCcw}
                onClick={() => control.mutate('restart')}
                disabled={control.isPending}
              >
                重启
              </Button>
            </div>
          </div>
          {control.error ? (
            <p
              className={cn(
                'mt-3 rounded-[5px] border border-rose-100 bg-rose-50 p-2',
                'text-[9px] text-rose-700',
              )}
            >
              {messageFrom(control.error)}
            </p>
          ) : null}
          <div className="mt-4 grid grid-cols-3 divide-x divide-slate-100 border-t border-slate-100 pt-4 max-sm:grid-cols-1 max-sm:divide-x-0 max-sm:divide-y">
            <div className="px-4 first:pl-0 max-sm:px-0 max-sm:py-2">
              <small className="block text-[8px] text-slate-400">本次运行转发</small>
              <strong className="mt-1 block text-[14px] text-slate-700">
                {formatNumber(runtimeStats.forwarded)}
              </strong>
            </div>
            <div className="px-4 max-sm:px-0 max-sm:py-2">
              <small className="block text-[8px] text-slate-400">本次运行过滤</small>
              <strong className="mt-1 block text-[14px] text-slate-700">
                {formatNumber(runtimeStats.filtered)}
              </strong>
            </div>
            <div className="px-4 max-sm:px-0 max-sm:py-2">
              <small className="block text-[8px] text-slate-400">持久队列</small>
              <strong className="mt-1 block text-[14px] text-blue-600">
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
        <Panel title="规则表现排行" meta={<span>{rankedRules.length} 条规则 · 累计数据</span>}>
          {rankedRules.length ? (
            <div className="overflow-x-auto">
              <div className="min-w-135">
                <div className="grid grid-cols-[28px_minmax(130px,1fr)_minmax(160px,1.25fr)_70px_70px] gap-3 border-b border-slate-100 pb-2 text-[8px] font-bold text-slate-400 uppercase">
                  <span>#</span>
                  <span>规则</span>
                  <span>处理量</span>
                  <span className="text-right">转发率</span>
                  <span className="text-right">总计</span>
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
                          'grid size-5 place-items-center rounded text-[8px] font-bold',
                          index < 3 ? 'bg-blue-50 text-blue-700' : 'bg-slate-100 text-slate-500',
                        )}
                      >
                        {index + 1}
                      </span>
                      <div className="min-w-0">
                        <strong className="block truncate text-[10px] text-slate-700">
                          {rule.rule_name}
                        </strong>
                        <small className="mt-0.5 block text-[8px] text-slate-400">
                          {formatNumber(rule.forwarded)} 转发 · {formatNumber(rule.filtered)} 过滤
                        </small>
                      </div>
                      <div className="h-2 overflow-hidden rounded-sm bg-slate-100">
                        <i
                          className="block h-full bg-blue-600"
                          style={{ width: `${(rule.total / maxRuleTotal) * 100}%` }}
                        />
                      </div>
                      <strong className="text-right text-[9px] text-slate-600">
                        {formatPercent(rate)}
                      </strong>
                      <strong className="text-right text-[10px] text-slate-700">
                        {formatNumber(rule.total)}
                      </strong>
                    </div>
                  )
                })}
              </div>
            </div>
          ) : (
            <EmptyState icon={Route} title="暂无规则统计" />
          )}
        </Panel>

        <Panel
          title="实时事件"
          meta={
            <span className={connected ? 'text-emerald-600' : ''}>
              {connected ? 'SSE 已连接' : '等待事件'}
            </span>
          }
        >
          <div className="flex flex-col gap-3">
            {recent.slice(0, 7).map((event) => (
              <div
                className={cn(
                  'grid grid-cols-[7px_1fr_auto] items-start gap-2 border-b',
                  'border-slate-100 pb-2.5 last:border-0',
                )}
                key={`${event.at}-${event.type}`}
              >
                <span className="mt-1 size-2 rounded-full border-2 border-blue-100 bg-blue-400" />
                <div className="min-w-0">
                  <strong className="text-[9px] text-slate-600 uppercase">{event.type}</strong>
                  <p className="mt-0.5 truncate text-[9px] text-slate-500">
                    {String(event.payload.message ?? event.payload.action ?? '状态更新')}
                  </p>
                </div>
                <time className="text-[8px] text-slate-400">
                  {new Date(event.at).toLocaleTimeString('zh-CN', {
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
                title="等待实时事件"
                detail="连接成功后，新事件会在这里出现。"
              />
            ) : null}
          </div>
        </Panel>
      </div>
    </>
  )
}
