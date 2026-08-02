import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Archive,
  Braces,
  CalendarClock,
  Database,
  Download,
  Eye,
  FileArchive,
  Globe2,
  Play,
  Plus,
  Table2,
  Trash2,
  X,
} from 'lucide-react'
import type { TFunction } from 'i18next'
import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { accountRequest, json } from '../api/client'
import { ChatSelect } from '../components/ChatSelect'
import { useTelegramChats } from '../hooks/useTelegramChats'
import { useAccountScope } from '../hooks/useAccountScope'
import { DownloadButton } from '../components/DownloadButton'
import {
  Badge,
  Button,
  confirm,
  Dialog,
  EmptyState,
  fieldClass,
  IconButton,
  PageHeader,
  Panel,
  Select,
  Switch,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  tableClass,
  tableWrapClass,
  tabsListClass,
} from '../components/ui'
import type { ExportJob, ExportRun, ExportTask } from '../types'
import { cn } from '../utils/cn'
import { messageFrom, shortDate } from '../utils/format'

const formats = ['json', 'csv', 'html', 'sqlite'] as const
const formatIcons = {
  json: Braces,
  csv: Table2,
  html: Globe2,
  sqlite: Database,
}
const errorClass = cn(
  'rounded-[5px] border border-rose-100 bg-rose-50 p-2',
  'text-[13px] text-rose-700',
)
const formatOptionClass = cn(
  'flex h-10.5 items-center justify-center gap-1.5 rounded-[5px] border',
  'text-[13px] leading-none',
)

function downloadOption(file: string) {
  const filename = file.split('/').pop() ?? file
  const extension = filename.split('.').pop() ?? filename
  return {
    url: `/api/v1/exports/file?path=${encodeURIComponent(file)}`,
    label: extension === 'zip' ? 'HTML (ZIP)' : extension.toUpperCase(),
    filename,
  }
}

const exportPhaseLabels = {
  queued: 'exports.phase.queued',
  reading_groups: 'exports.phase.readingGroups',
  reading_messages: 'exports.phase.readingMessages',
  writing_files: 'exports.phase.writingFiles',
  cancelling: 'exports.phase.cancelling',
  completed: 'exports.phase.completed',
  failed: 'exports.phase.failed',
  cancelled: 'exports.phase.cancelled',
} as const

function phaseLabel(phase: string | undefined, t: TFunction): string {
  if (!phase) return t('exports.processingMessages')
  const key = exportPhaseLabels[phase as keyof typeof exportPhaseLabels]
  return key ? t(key) : phase
}

function jobLabel(job: ExportJob, t: TFunction): string {
  if (job.chat_title) {
    const range = job.all_history
      ? t('exports.allHistoryLabel')
      : job.range_start && job.range_end
        ? `${shortDate(job.range_start)} ~ ${shortDate(job.range_end)}`
        : ''
    return range ? `${job.chat_title} · ${range}` : job.chat_title
  }
  return job.id
}

function runFormats(files: string[]): string[] {
  const formats = new Set<string>()
  for (const file of files) {
    const name = file.split('/').pop() ?? file
    if (name.endsWith('.html.zip')) formats.add('HTML')
    else if (name.endsWith('.json')) formats.add('JSON')
    else if (name.endsWith('.csv')) formats.add('CSV')
    else if (name.endsWith('.sqlite3')) formats.add('SQLite')
  }
  return [...formats]
}

function jobProgress(job: ExportJob): number {
  if (job.status === 'completed') return 100
  if (job.total) return Math.min(100, (job.processed / job.total) * 100)
  if (job.range_start && job.range_end && job.progress_date) {
    const start = Date.parse(job.range_start)
    const end = Date.parse(job.range_end)
    const current = Date.parse(job.progress_date)
    if (Number.isFinite(start) && Number.isFinite(end) && end > start && Number.isFinite(current)) {
      return Math.min(100, Math.max(2, ((current - start) / (end - start)) * 100))
    }
  }
  return job.processed > 0 ? 18 : 2
}

function ExportFilesRow({ files, accountId }: { files: string[]; accountId: string }) {
  const { t } = useTranslation()
  const [previewUrl, setPreviewUrl] = useState('')
  const previewFile = files.find((file) => file.endsWith('.html.zip'))
  async function openPreview(file: string) {
    const filename = file.split('/').pop() ?? file
    const root = filename.replace(/\.html\.zip$/i, '')
    const { token } = await accountRequest<{ token: string }>(
      accountId,
      `/api/v1/exports/preview-token?path=${encodeURIComponent(file)}`,
    )
    setPreviewUrl(
      `/api/v1/exports/preview/${token}/${encodeURIComponent(root)}/index.html?account_id=${encodeURIComponent(accountId)}`,
    )
  }
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <DownloadButton files={files.map(downloadOption)} accountId={accountId} />
        {previewFile ? (
          <IconButton
            label={t('exports.preview')}
            icon={Eye}
            onClick={() => void openPreview(previewFile)}
          />
        ) : null}
      </div>
      {previewUrl ? (
        <div className="fixed inset-0 z-120 bg-white">
          <header className="flex h-11 items-center justify-between border-b border-slate-200 px-4">
            <strong className="text-sm font-semibold text-slate-700">
              {t('exports.previewTitle')}
            </strong>
            <IconButton label={t('common.close')} icon={X} onClick={() => setPreviewUrl('')} />
          </header>
          <iframe
            src={previewUrl}
            title={t('exports.previewTitle')}
            className="block h-[calc(100dvh-2.75rem)] w-full border-0 bg-white"
          />
        </div>
      ) : null}
    </>
  )
}

export function ExportsPage() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const accountId = useAccountScope()
  const [jobId, setJobId] = useState('')
  const [taskOpen, setTaskOpen] = useState(false)
  const [messageForm, setMessageForm] = useState({
    chat_id: '',
    start_at: '',
    end_at: '',
    formats: ['json', 'html', 'sqlite'],
    subdirectory: 'messages',
    all_history: false,
  })
  const [taskForm, setTaskForm] = useState({
    name: '',
    chat_id: '',
    initial_start_at: '',
    formats: ['json', 'html', 'sqlite'],
    subdirectory: 'scheduled',
    schedule_type: 'daily',
    minute: 0,
    hour: 2,
    weekday: 0,
    timezone: 'Asia/Shanghai',
    all_history: false,
    enabled: true,
  })
  const chats = useTelegramChats()
  const tasks = useQuery({
    queryKey: ['export-tasks', accountId],
    queryFn: () => accountRequest<ExportTask[]>(accountId, '/api/v1/exports/tasks'),
    refetchInterval: 10_000,
  })
  const runs = useQuery({
    queryKey: ['export-runs', accountId],
    queryFn: () => accountRequest<ExportRun[]>(accountId, '/api/v1/exports/runs?limit=30'),
    refetchInterval: 10_000,
  })
  const deleteRun = useMutation({
    mutationFn: (runId: number) =>
      accountRequest(accountId, `/api/v1/exports/runs/${runId}`, json('DELETE')),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['export-runs'] })
    },
  })
  async function handleDeleteRun(run: ExportRun) {
    await confirm({
      title: t('exports.deleteRunTitle'),
      description: t('exports.deleteRunConfirm'),
      confirmLabel: t('exports.deleteRun'),
      onConfirm: () => deleteRun.mutateAsync(run.id),
    })
  }
  const job = useQuery({
    queryKey: ['export-job', accountId, jobId],
    queryFn: () => accountRequest<ExportJob>(accountId, `/api/v1/exports/jobs/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) =>
      ['completed', 'failed', 'cancelled'].includes(
        (query.state.data as ExportJob | undefined)?.status ?? '',
      )
        ? false
        : 1000,
  })
  useEffect(() => {
    if (!messageForm.chat_id && chats.data?.[0])
      setMessageForm((form) => ({ ...form, chat_id: String(chats.data![0].id) }))
  }, [chats.data, messageForm.chat_id])

  const startExport = useMutation({
    mutationFn: () =>
      accountRequest<{ job_id: string }>(
        accountId,
        '/api/v1/exports/jobs/messages',
        json('POST', {
          ...messageForm,
          chat_id: Number(messageForm.chat_id),
          start_at: messageForm.start_at || null,
          end_at: messageForm.end_at || null,
        }),
      ),
    onSuccess: (data) => setJobId(data.job_id),
  })
  const saveTask = useMutation({
    mutationFn: () =>
      accountRequest(
        accountId,
        '/api/v1/exports/tasks',
        json('POST', {
          ...taskForm,
          chat_id: Number(taskForm.chat_id),
          initial_start_at: taskForm.initial_start_at || null,
        }),
      ),
    onSuccess: () => {
      setTaskOpen(false)
      void client.invalidateQueries({ queryKey: ['export-tasks'] })
    },
  })
  const removeTask = useMutation({
    mutationFn: (id: number) =>
      accountRequest(accountId, `/api/v1/exports/tasks/${id}`, json('DELETE')),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['export-tasks'] })
    },
  })
  async function deleteTask(id: number) {
    await confirm({
      title: t('exports.deleteTitle'),
      description: t('exports.deleteConfirm', {
        name: tasks.data?.find((task) => task.id === id)?.name ?? t('exports.fallbackTask'),
      }),
      confirmLabel: t('exports.deleteTask'),
      onConfirm: () => removeTask.mutateAsync(id),
    })
  }
  async function runTask(id: number) {
    const result = await accountRequest<{ job_id: string }>(
      accountId,
      `/api/v1/exports/tasks/${id}/run`,
      json('POST'),
    )
    setJobId(result.job_id)
  }
  function selectFormat(name: string, selected: boolean, target: 'message' | 'task') {
    if (target === 'message')
      setMessageForm((form) => ({
        ...form,
        formats: selected
          ? [...form.formats, name]
          : form.formats.filter((value) => value !== name),
      }))
    else
      setTaskForm((form) => ({
        ...form,
        formats: selected
          ? [...form.formats, name]
          : form.formats.filter((value) => value !== name),
      }))
  }
  function submitTask(event: FormEvent) {
    event.preventDefault()
    saveTask.mutate()
  }
  function openTask() {
    setTaskForm((form) => ({
      ...form,
      chat_id: form.chat_id || String(chats.data?.[0]?.id ?? ''),
    }))
    setTaskOpen(true)
  }

  return (
    <>
      <PageHeader
        eyebrow={t('exports.eyebrow')}
        title={t('exports.title')}
        description={t('exports.description')}
        actions={
          <Button icon={Plus} onClick={openTask}>
            {t('exports.newScheduledTask')}
          </Button>
        }
      />
      <Tabs defaultValue="instant">
        <TabsList className={tabsListClass}>
          <TabsTrigger value="instant">
            <FileArchive size={16} />
            {t('exports.instant')}
          </TabsTrigger>
          <TabsTrigger value="scheduled">
            <CalendarClock size={16} />
            {t('exports.scheduled')} <span>{tasks.data?.length ?? 0}</span>
          </TabsTrigger>
          <TabsTrigger value="history">
            <Archive size={16} />
            {t('exports.history')}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="instant" className="outline-none">
          <div
            className={cn(
              'grid grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)] gap-3',
              'max-lg:grid-cols-1',
            )}
          >
            <Panel
              title={t('exports.createMessageExport')}
              meta={<span>{t('exports.availableChats', { count: chats.data?.length ?? 0 })}</span>}
            >
              <form
                className="grid grid-cols-2 gap-4 max-md:grid-cols-1"
                onSubmit={(event) => {
                  event.preventDefault()
                  startExport.mutate()
                }}
              >
                <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
                  <span>{t('exports.selectChat')}</span>
                  <ChatSelect
                    value={messageForm.chat_id}
                    onValueChange={(chat_id) => setMessageForm({ ...messageForm, chat_id })}
                    placeholder={t('exports.selectChatPlaceholder')}
                  />
                </label>
                <label className={fieldClass}>
                  <span>{t('exports.startTime')}</span>
                  <input
                    type="datetime-local"
                    value={messageForm.start_at}
                    disabled={messageForm.all_history}
                    onChange={(event) =>
                      setMessageForm({ ...messageForm, start_at: event.target.value })
                    }
                  />
                </label>
                <label className={fieldClass}>
                  <span>{t('exports.endTime')}</span>
                  <input
                    type="datetime-local"
                    value={messageForm.end_at}
                    onChange={(event) =>
                      setMessageForm({ ...messageForm, end_at: event.target.value })
                    }
                  />
                </label>
                <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
                  <span>{t('exports.directory')}</span>
                  <input
                    value={messageForm.subdirectory}
                    onChange={(event) =>
                      setMessageForm({ ...messageForm, subdirectory: event.target.value })
                    }
                  />
                </label>
                <div className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
                  <span>{t('exports.formats')}</span>
                  <div className="grid grid-cols-4 gap-2 max-sm:grid-cols-2">
                    {formats.map((format) => {
                      const FormatIcon = formatIcons[format]

                      return (
                        <label
                          className={cn(
                            formatOptionClass,
                            messageForm.formats.includes(format)
                              ? 'border-blue-200 bg-blue-50 text-blue-700'
                              : 'border-slate-200 bg-slate-50 text-slate-500',
                          )}
                          key={format}
                        >
                          <input
                            className="sr-only"
                            type="checkbox"
                            checked={messageForm.formats.includes(format)}
                            onChange={(event) =>
                              selectFormat(format, event.target.checked, 'message')
                            }
                          />
                          <FormatIcon className="shrink-0" size={17} />
                          <strong className="inline-flex items-center leading-none">
                            {format.toUpperCase()}
                          </strong>
                        </label>
                      )
                    })}
                  </div>
                </div>
                <div className="col-span-2 max-md:col-span-1">
                  <Switch
                    checked={messageForm.all_history}
                    onCheckedChange={(all_history) =>
                      setMessageForm({ ...messageForm, all_history })
                    }
                    label={t('exports.allHistory')}
                    detail={t('exports.allHistoryDetail')}
                  />
                </div>
                {chats.error ? (
                  <p className={cn('col-span-2 max-md:col-span-1', errorClass)}>
                    {t('exports.connectTelegram')}
                  </p>
                ) : null}
                {startExport.error ? (
                  <p className={cn('col-span-2 max-md:col-span-1', errorClass)}>
                    {messageFrom(startExport.error)}
                  </p>
                ) : null}
                <Button
                  type="submit"
                  icon={Download}
                  disabled={
                    startExport.isPending || !messageForm.chat_id || !messageForm.formats.length
                  }
                >
                  {t(startExport.isPending ? 'exports.creating' : 'exports.start')}
                </Button>
              </form>
            </Panel>
            <Panel
              title={t('exports.currentJob')}
              meta={
                <Badge
                  tone={job.data?.status === 'completed' ? 'green' : job.data ? 'blue' : 'gray'}
                >
                  {job.data?.status
                    ? t(`exports.status.${job.data.status}`, { defaultValue: job.data.status })
                    : t('exports.idle')}
                </Badge>
              }
            >
              {job.data ? (
                <div
                  className={cn(
                    'grid grid-cols-[43px_1fr_auto] items-center gap-3',
                    'max-sm:grid-cols-[43px_1fr]',
                  )}
                >
                  <span
                    className={cn(
                      'grid size-11 place-items-center rounded-[5px]',
                      'bg-blue-50 text-blue-600',
                    )}
                  >
                    <Archive size={24} />
                  </span>
                  <div className="min-w-0">
                    <strong className="text-[13px] text-slate-700">
                      {phaseLabel(job.data.phase, t)}
                    </strong>
                    <p className="mt-1 truncate text-xs text-slate-400">{jobLabel(job.data, t)}</p>
                  </div>
                  <div className="max-sm:col-span-2">
                    <strong className="font-display text-[22px] text-slate-700">
                      {job.data.processed}
                    </strong>
                    {job.data.total ? (
                      <span className="text-[13px] text-slate-400">/ {job.data.total}</span>
                    ) : null}
                  </div>
                  <div className="col-span-full h-2 overflow-hidden rounded-sm bg-slate-100">
                    <i
                      className="block h-full min-w-1 bg-blue-600"
                      style={{ width: `${jobProgress(job.data)}%` }}
                    />
                  </div>
                  {job.data.error ? (
                    <p className={cn('col-span-full', errorClass)}>{job.data.error}</p>
                  ) : null}
                  <div className="col-span-full">
                    <ExportFilesRow files={job.data.files} accountId={accountId} />
                  </div>
                </div>
              ) : (
                <EmptyState
                  icon={Archive}
                  title={t('exports.noActiveJob')}
                  detail={t('exports.noActiveJobDetail')}
                />
              )}
            </Panel>
          </div>
        </TabsContent>
        <TabsContent value="scheduled" className="outline-none">
          <section className={tableWrapClass}>
            <div className="overflow-x-auto">
              <table className={cn(tableClass, 'max-md:min-w-195')}>
                <thead>
                  <tr>
                    <th>{t('exports.columns.task')}</th>
                    <th>{t('exports.columns.chat')}</th>
                    <th>{t('exports.columns.schedule')}</th>
                    <th>{t('exports.columns.format')}</th>
                    <th>{t('exports.columns.nextRun')}</th>
                    <th aria-label={t('common.actions')} />
                  </tr>
                </thead>
                <tbody>
                  {(tasks.data ?? []).map((task) => (
                    <tr key={task.id}>
                      <td>
                        <strong className="block text-slate-700">{task.name}</strong>
                        <small className="mt-1 block">
                          <Badge tone={task.enabled ? 'green' : 'gray'}>
                            {t(task.enabled ? 'exports.enabled' : 'exports.paused')}
                          </Badge>
                        </small>
                      </td>
                      <td>
                        {task.chat_title || task.chat_id}
                        <small className="mt-1 block text-xs text-slate-400">{task.chat_id}</small>
                      </td>
                      <td>
                        {t(`exports.${task.schedule_type}`, { defaultValue: task.schedule_type })}
                        <small className="mt-1 block text-xs text-slate-400">
                          {String(task.hour).padStart(2, '0')}:
                          {String(task.minute).padStart(2, '0')} · {task.timezone}
                        </small>
                      </td>
                      <td>{task.formats.join(', ')}</td>
                      <td className="min-w-32 font-mono text-slate-500">
                        {shortDate(task.next_run_at)}
                      </td>
                      <td>
                        <div className="flex justify-end gap-1">
                          <IconButton
                            label={t('exports.runNow')}
                            icon={Play}
                            onClick={() => void runTask(task.id)}
                          />
                          <IconButton
                            label={t('exports.deleteTask')}
                            icon={Trash2}
                            onClick={() => void deleteTask(task.id)}
                          />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!tasks.data?.length ? (
              <EmptyState
                icon={CalendarClock}
                title={t('exports.noTasks')}
                detail={t('exports.noTasksDetail')}
              />
            ) : null}
          </section>
        </TabsContent>
        <TabsContent value="history" className="outline-none">
          <section className={tableWrapClass}>
            <div className="overflow-x-auto">
              <table className={cn(tableClass, 'max-md:min-w-195')}>
                <thead>
                  <tr>
                    <th>{t('exports.columns.startedAt')}</th>
                    <th>{t('exports.columns.type')}</th>
                    <th>{t('exports.columns.chat')}</th>
                    <th>{t('exports.columns.status')}</th>
                    <th>{t('exports.columns.messages')}</th>
                    <th>{t('exports.columns.format')}</th>
                    <th>{t('common.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {(runs.data ?? []).map((run) => (
                    <tr key={run.id}>
                      <td className="min-w-32 font-mono text-slate-500">
                        {shortDate(run.started_at)}
                      </td>
                      <td>
                        <Badge tone="gray">
                          {t(`exports.runType.${run.run_type}`, { defaultValue: run.run_type })}
                        </Badge>
                      </td>
                      <td>{run.chat_title || run.chat_id || '-'}</td>
                      <td>
                        <Badge
                          tone={
                            run.status === 'completed'
                              ? 'green'
                              : run.status === 'failed'
                                ? 'red'
                                : 'blue'
                          }
                        >
                          {t(`exports.status.${run.status}`, { defaultValue: run.status })}
                        </Badge>
                      </td>
                      <td>{run.message_count}</td>
                      <td>
                        <div className="flex flex-wrap gap-1">
                          {runFormats(run.files).map((format) => (
                            <Badge key={format} tone="blue">
                              {format}
                            </Badge>
                          ))}
                        </div>
                      </td>
                      <td>
                        <div className="flex justify-end gap-1">
                          <ExportFilesRow files={run.files} accountId={accountId} />
                          <IconButton
                            label={t('exports.deleteRun')}
                            icon={Trash2}
                            onClick={() => void handleDeleteRun(run)}
                          />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!runs.data?.length ? <EmptyState icon={Archive} title={t('exports.noRuns')} /> : null}
          </section>
        </TabsContent>
      </Tabs>

      <Dialog
        open={taskOpen}
        onOpenChange={setTaskOpen}
        title={t('exports.newScheduledTitle')}
        description={t('exports.newScheduledDescription')}
      >
        <form onSubmit={submitTask}>
          <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
            <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>{t('exports.taskName')}</span>
              <input
                value={taskForm.name}
                onChange={(event) => setTaskForm({ ...taskForm, name: event.target.value })}
                required
              />
            </label>
            <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>{t('exports.chat')}</span>
              <ChatSelect
                value={taskForm.chat_id}
                onValueChange={(chat_id) => setTaskForm({ ...taskForm, chat_id })}
              />
            </label>
            <label className={fieldClass}>
              <span>{t('exports.frequency')}</span>
              <Select
                value={taskForm.schedule_type}
                onValueChange={(schedule_type) => setTaskForm({ ...taskForm, schedule_type })}
                options={[
                  { value: 'hourly', label: t('exports.hourly') },
                  { value: 'daily', label: t('exports.daily') },
                  { value: 'weekly', label: t('exports.weekly') },
                ]}
              />
            </label>
            <label className={fieldClass}>
              <span>{t('exports.timezone')}</span>
              <input
                value={taskForm.timezone}
                onChange={(event) => setTaskForm({ ...taskForm, timezone: event.target.value })}
              />
            </label>
            <label className={fieldClass}>
              <span>{t('exports.hour')}</span>
              <input
                type="number"
                min="0"
                max="23"
                value={taskForm.hour}
                onChange={(event) => setTaskForm({ ...taskForm, hour: Number(event.target.value) })}
              />
            </label>
            <label className={fieldClass}>
              <span>{t('exports.minute')}</span>
              <input
                type="number"
                min="0"
                max="59"
                value={taskForm.minute}
                onChange={(event) =>
                  setTaskForm({ ...taskForm, minute: Number(event.target.value) })
                }
              />
            </label>
            <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>{t('exports.directory')}</span>
              <input
                value={taskForm.subdirectory}
                onChange={(event) => setTaskForm({ ...taskForm, subdirectory: event.target.value })}
              />
            </label>
            <div className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>{t('exports.formats')}</span>
              <div className="grid grid-cols-4 gap-2 max-sm:grid-cols-2">
                {formats.map((format) => {
                  const FormatIcon = formatIcons[format]

                  return (
                    <label
                      className={cn(
                        formatOptionClass,
                        taskForm.formats.includes(format)
                          ? 'border-blue-200 bg-blue-50 text-blue-700'
                          : 'border-slate-200 bg-slate-50 text-slate-500',
                      )}
                      key={format}
                    >
                      <input
                        className="sr-only"
                        type="checkbox"
                        checked={taskForm.formats.includes(format)}
                        onChange={(event) => selectFormat(format, event.target.checked, 'task')}
                      />
                      <FormatIcon className="shrink-0" size={17} />
                      <strong className="inline-flex items-center leading-none">
                        {format.toUpperCase()}
                      </strong>
                    </label>
                  )
                })}
              </div>
            </div>
          </div>
          <div
            className={cn(
              'mt-5 grid grid-cols-2 gap-2 border-t border-slate-100 pt-4',
              'max-md:grid-cols-1',
            )}
          >
            <Switch
              checked={taskForm.enabled}
              onCheckedChange={(enabled) => setTaskForm({ ...taskForm, enabled })}
              label={t('exports.enableTask')}
            />
            <Switch
              checked={taskForm.all_history}
              onCheckedChange={(all_history) => setTaskForm({ ...taskForm, all_history })}
              label={t('exports.firstRunAllHistory')}
            />
          </div>
          {saveTask.error ? (
            <p
              className={cn(
                'mt-3 rounded-[5px] border border-rose-100 bg-rose-50 p-2',
                'text-[13px] text-rose-700',
              )}
            >
              {messageFrom(saveTask.error)}
            </p>
          ) : null}
          <div className="mt-5 flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button type="button" variant="secondary" onClick={() => setTaskOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={saveTask.isPending || !taskForm.chat_id || !taskForm.formats.length}
            >
              {t('exports.saveTask')}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  )
}
