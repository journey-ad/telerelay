import { useQuery } from '@tanstack/react-query'
import { Download, FileClock, Pause, Play, RefreshCw, Search } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { request } from '../api/client'
import { Badge, Button, EmptyState, IconButton, PageHeader, Select } from '../components/ui'
import { useEvents } from '../hooks/useEvents'
import { cn } from '../utils/cn'

function level(line: string) {
  const value = line.toLowerCase()
  if (value.includes('error') || value.includes('exception')) return 'error'
  if (value.includes('warning') || value.includes('flood')) return 'warning'
  if (value.includes('debug')) return 'debug'
  return 'info'
}

const levelColors = {
  info: 'text-slate-300',
  warning: 'text-amber-300',
  error: 'text-rose-300',
  debug: 'text-slate-500',
}

export function LogsPage() {
  const { t } = useTranslation()
  const [filter, setFilter] = useState('')
  const [levelFilter, setLevelFilter] = useState('all')
  const [paused, setPaused] = useState(false)
  const [live, setLive] = useState<string[]>([])
  const logs = useQuery({
    queryKey: ['logs'],
    queryFn: () => request<{ lines: string[] }>('/api/v1/logs?lines=800'),
    refetchInterval: paused ? false : 10_000,
  })
  const receiveEvent = useCallback(
    (event: { type: string; payload: Record<string, unknown> }) => {
      if (!paused && event.type === 'log' && event.payload.message)
        setLive((current) => [...current, String(event.payload.message)].slice(-500))
    },
    [paused],
  )
  useEvents(receiveEvent)
  const lines = useMemo(
    () =>
      [...(logs.data?.lines ?? []), ...live]
        .filter(
          (line) =>
            (!filter || line.toLowerCase().includes(filter.toLowerCase())) &&
            (levelFilter === 'all' || level(line) === levelFilter),
        )
        .slice(-1000),
    [filter, levelFilter, live, logs.data?.lines],
  )
  function downloadLogs() {
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'telerelay.log'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <PageHeader
        eyebrow={t('logs.eyebrow')}
        title={t('logs.title')}
        description={t('logs.description')}
        actions={
          <>
            <Button variant="secondary" icon={Download} onClick={downloadLogs}>
              {t('logs.download')}
            </Button>
            <IconButton
              label={t('logs.refresh')}
              icon={RefreshCw}
              onClick={() => void logs.refetch()}
            />
          </>
        }
      />
      <div
        className={cn(
          'mb-3 flex min-h-14 items-center gap-3 rounded-md border',
          'border-slate-200 bg-white p-3 max-md:flex-col max-md:items-stretch',
        )}
      >
        <div
          className={cn(
            'flex h-9 w-full max-w-85 items-center gap-2 rounded-[5px] border',
            'border-slate-200 bg-slate-50 px-2.5 text-slate-400 max-md:max-w-none',
          )}
        >
          <Search size={17} />
          <input
            className="w-full border-0 bg-transparent text-[13px] text-slate-700 outline-none"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder={t('logs.filter')}
          />
        </div>
        <div className="w-35 max-md:w-full">
          <Select
            value={levelFilter}
            onValueChange={setLevelFilter}
            options={[
              { value: 'all', label: t('logs.allLevels') },
              { value: 'info', label: t('logs.level.info') },
              { value: 'warning', label: t('logs.level.warning') },
              { value: 'error', label: t('logs.level.error') },
              { value: 'debug', label: t('logs.level.debug') },
            ]}
          />
        </div>
        <Button
          className="ml-auto max-md:ml-0 max-md:w-full"
          variant="secondary"
          icon={paused ? Play : Pause}
          onClick={() => setPaused((value) => !value)}
        >
          {t(paused ? 'logs.resume' : 'logs.pause')}
        </Button>
      </div>
      <section
        className={cn(
          'overflow-hidden rounded-md border border-slate-700',
          'bg-slate-900 shadow-xl',
        )}
      >
        <header
          className={cn(
            'grid h-10.5 grid-cols-[1fr_auto_1fr] items-center border-b',
            'border-slate-700 bg-slate-800 px-3.5 text-[13px] text-slate-400',
          )}
        >
          <div className="flex gap-1.5">
            <span className="size-2 rounded-full bg-rose-400" />
            <span className="size-2 rounded-full bg-amber-400" />
            <span className="size-2 rounded-full bg-emerald-400" />
          </div>
          <span>logs/telerelay.log</span>
          <span className="justify-self-end">
            <Badge tone={paused ? 'amber' : 'green'}>
              {t(paused ? 'logs.paused' : 'logs.live')}
            </Badge>
          </span>
        </header>
        <div className="min-h-120 max-h-[calc(100vh-250px)] overflow-auto py-3">
          {lines.map((line, index) => (
            <p
              className={cn(
                'm-0 grid min-w-175 grid-cols-[50px_1fr] px-3.5 py-0.5',
                'text-[13px] leading-4 hover:bg-slate-800',
              )}
              key={`${index}-${line}`}
            >
              <span className="text-slate-600 select-none">
                {String(index + 1).padStart(4, '0')}
              </span>
              <code className={cn('font-mono whitespace-pre-wrap', levelColors[level(line)])}>
                {line}
              </code>
            </p>
          ))}
          {!lines.length ? (
            <EmptyState icon={FileClock} title={t('logs.empty')} detail={t('logs.emptyDetail')} />
          ) : null}
        </div>
      </section>
    </>
  )
}
