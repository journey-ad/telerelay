import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Filter,
  Pause,
  Play,
  RefreshCcw,
  Route,
  Send,
  TimerReset,
} from 'lucide-react'
import { useCallback } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
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

const metricTones = {
  blue: 'bg-blue-50 text-blue-600',
  amber: 'bg-amber-50 text-amber-600',
  cyan: 'bg-cyan-50 text-cyan-600',
  green: 'bg-emerald-50 text-emerald-600',
}

export function DashboardPage() {
  const client = useQueryClient()
  const statusQuery = useQuery({
    queryKey: ['bot-status'],
    queryFn: () => request<BotStatus>('/api/v1/bot/status'),
    refetchInterval: 4000,
  })
  const statsQuery = useQuery({
    queryKey: ['stats', 14],
    queryFn: () => request<Stats>('/api/v1/stats?days=14'),
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
  const stats = status.stats ?? {}
  const activeQueue = Object.entries(status.queue?.counts ?? {})
    .filter(([key]) => key !== 'completed')
    .reduce((sum, [, value]) => sum + value, 0)
  const daily = statsQuery.data?.daily ?? []
  const forwardedTrend =
    daily.length > 1 ? (daily.at(-1)?.forwarded ?? 0) - (daily.at(-2)?.forwarded ?? 0) : 0
  const metrics = [
    { label: '已转发', value: stats.forwarded, icon: Send, trend: forwardedTrend, tone: 'blue' },
    { label: '已过滤', value: stats.filtered, icon: Filter, trend: 0, tone: 'amber' },
    { label: '总消息流', value: stats.total, icon: Activity, trend: 0, tone: 'cyan' },
    { label: '队列待处理', value: activeQueue, icon: TimerReset, trend: 0, tone: 'green' },
  ] as const

  return (
    <>
      <PageHeader
        eyebrow="Live operations"
        title="运行总览"
        description="监控消息流、队列与 Telegram 连接状态。"
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
                trend > 0 ? 'text-emerald-600' : 'text-slate-400',
              )}
            >
              {trend > 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
              {trend ? `较昨日 ${Math.abs(trend)}` : '当前运行周期'}
            </small>
          </article>
        ))}
      </div>

      <div
        className={cn(
          'grid grid-cols-[minmax(0,1.65fr)_minmax(280px,0.85fr)] gap-3',
          'max-lg:grid-cols-1',
        )}
      >
        <Panel title="消息趋势" meta={<span>近 14 天</span>}>
          {daily.length ? (
            <div className="h-61.5">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={daily} margin={{ top: 12, right: 8, left: -18, bottom: 0 }}>
                  <defs>
                    <linearGradient id="forwarded-fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#2476f3" stopOpacity={0.22} />
                      <stop offset="100%" stopColor="#2476f3" stopOpacity={0.01} />
                    </linearGradient>
                    <linearGradient id="filtered-fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#82b7ff" stopOpacity={0.18} />
                      <stop offset="100%" stopColor="#82b7ff" stopOpacity={0.01} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#e6edf7" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(value: string) => value.slice(5)}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#7b8ca5', fontSize: 11 }}
                    dy={8}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#7b8ca5', fontSize: 11 }}
                  />
                  <Tooltip
                    contentStyle={{
                      border: '1px solid #dbe6f4',
                      borderRadius: 6,
                      boxShadow: '0 12px 32px rgba(22, 63, 116, .12)',
                      fontSize: 12,
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="forwarded"
                    name="已转发"
                    stroke="#2476f3"
                    strokeWidth={2}
                    fill="url(#forwarded-fill)"
                  />
                  <Area
                    type="monotone"
                    dataKey="filtered"
                    name="已过滤"
                    stroke="#82b7ff"
                    strokeWidth={1.5}
                    fill="url(#filtered-fill)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState
              icon={Activity}
              title="暂无趋势数据"
              detail="消息开始流转后，这里会显示每日变化。"
            />
          )}
          <div className="flex gap-4 px-3 pt-2 text-[9px] text-slate-500">
            <span className="flex items-center gap-1.5 before:h-0.5 before:w-4 before:bg-blue-600">
              已转发
            </span>
            <span className="flex items-center gap-1.5 before:h-0.5 before:w-4 before:bg-blue-300">
              已过滤
            </span>
          </div>
        </Panel>

        <Panel
          title="节点控制"
          meta={
            <span className={status.is_running ? 'text-emerald-600' : ''}>
              {status.is_running ? '运行中' : '已停止'}
            </span>
          }
        >
          <div
            className={cn(
              'mb-4 flex items-center gap-3 rounded-[5px] border',
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
          <div className="mt-4 border-t border-slate-100">
            <div
              className={cn(
                'flex justify-between border-b border-slate-100 py-2.5',
                'text-[9px] font-semibold text-slate-700',
              )}
            >
              <span>持久队列</span>
              <b className="text-blue-600">{activeQueue} 待处理</b>
            </div>
            {Object.entries(status.queue?.counts ?? {}).map(([key, value]) => (
              <div
                className={cn(
                  'flex justify-between border-b border-slate-100 py-2.5',
                  'text-[9px] text-slate-500',
                )}
                key={key}
              >
                <span className="capitalize">{key}</span>
                <strong className="text-slate-600">{value}</strong>
              </div>
            ))}
            {!Object.keys(status.queue?.counts ?? {}).length ? (
              <div className="flex justify-between py-2.5 text-[9px] text-slate-500">
                <span>队列为空</span>
                <strong>0</strong>
              </div>
            ) : null}
          </div>
        </Panel>

        <Panel title="规则健康度" meta={<span>{statsQuery.data?.rules.length ?? 0} 条规则</span>}>
          <div className="flex flex-col gap-3">
            {(statsQuery.data?.rules ?? []).slice(0, 6).map((rule) => {
              const rate = rule.total ? Math.round((rule.forwarded / rule.total) * 100) : 0
              return (
                <div
                  className={cn(
                    'grid grid-cols-[minmax(0,1fr)_110px_30px] items-center gap-2.5',
                    'max-sm:grid-cols-[minmax(0,1fr)_85px_25px]',
                  )}
                  key={rule.rule_name}
                >
                  <div className="flex min-w-0 flex-col">
                    <strong className="truncate text-[10px] text-slate-700">
                      {rule.rule_name}
                    </strong>
                    <span className="text-[8px] text-slate-400">{formatNumber(rule.total)} 条</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-sm bg-slate-100">
                    <i className="block h-full bg-blue-600" style={{ width: `${rate}%` }} />
                  </div>
                  <small className="text-[8px] text-slate-400">{rate}%</small>
                </div>
              )
            })}
            {!statsQuery.data?.rules.length ? (
              <EmptyState icon={Route} title="暂无规则统计" />
            ) : null}
          </div>
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
